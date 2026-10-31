import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sqlite3
import pytest
from PySide6.QtWidgets import QApplication

from dev_storage_manager.domain.cleanup_result import CleanupReport
from dev_storage_manager.persistence.journal import Journal, JournalError
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.cleanup.pytest_fixture import create_fixture
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.cleanup_result_dialog import CleanupResultDialog
from dev_storage_manager.ui.main_window import Window
from dev_storage_manager.cleanup.service import prepare
from dev_storage_manager.platform.recycle import Receipt
from PySide6.QtCore import QEventLoop, QTimer


def test_recorded_result_counts_only_confirmed_moves_and_filters_one_job(tmp_path):
    journal = Journal(tmp_path)
    job = journal.begin([("a", 10), ("b", 20), ("c", 30), ("d", 40)], 1000)
    for path in ("a", "b", "c"):
        journal.item(job, path, "running")
    journal.item(job, "a", "succeeded", destination="fixture-receipt")
    journal.item(job, "b", "unknown", "fixture response lost")
    journal.item(job, "c", "failed", "fixture lock")
    journal.item(job, "d", "cancelled")
    journal.finish(job, "partial", 900)
    other = journal.begin([("other", 99)], None)
    journal.item(other, "other", "cancelled")
    journal.finish(other, "cancelled", None)
    result = journal.job_result(job)
    assert result.counts == {"cancelled": 1, "failed": 1, "succeeded": 1, "unknown": 1}
    assert result.moved_size == 10 and result.total_size == 100
    assert (result.free_before, result.free_after) == (1000, 900)
    page = journal.history_page(job=job)
    assert page.total == 4 and all(row[8] == job for row in page.records)
    assert journal.history_page().total == 5
    with pytest.raises(JournalError):
        journal.history_page(job="missing")
    journal.close()
    app = QApplication.instance() or QApplication([])
    dialog = CleanupResultDialog(CleanupReport("fixture-root", "a", job, result))
    text = dialog.details.toPlainText()
    assert "확인한 논리적 크기: 10 B" in text
    assert "전체 계획의 논리적 크기: 100 B" in text
    assert "fixture response lost" in text and "fixture lock" in text
    assert dialog.headline.text() == "항목별 결과가 다름"
    dialog.reject()


def test_result_limit_does_not_limit_totals_and_corruption_is_not_success(tmp_path):
    journal = Journal(tmp_path)
    paths = [f"fixture-{n:03d}" for n in range(251)]
    job = journal.begin([(path, 10) for path in paths], None)
    with journal.db:
        journal.db.execute("UPDATE cleanup_items SET status='succeeded',destination='fixture-receipt'")
    journal.finish(job, "succeeded", None)
    result = journal.job_result(job)
    assert len(result.items) == 200 and result.counts == {"succeeded": 251}
    assert result.moved_size == 2510
    with journal.db:
        journal.db.execute("UPDATE cleanup_items SET destination=NULL WHERE path=?", (paths[-1],))
    with pytest.raises(JournalError, match="영수증"):
        journal.job_result(job)
    journal.close()


def test_missing_result_does_not_show_zero_or_success():
    app = QApplication.instance() or QApplication([])
    dialog = CleanupResultDialog(CleanupReport("fixture-root", r"C:\한국어 공백\__pycache__", None, None, "fixture database unavailable"))
    assert "확인하지 못했습니다" in dialog.headline.text()
    assert "0 B" not in dialog.details.toPlainText()
    assert "fixture database unavailable" in dialog.details.toPlainText()
    assert "한국어 공백" in dialog.details.toPlainText()
    dialog.reject()


def test_saved_analysis_after_cleanup_attempt_cannot_restore_candidates(tmp_path, wait_for_idle, wait_for_history):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    create_fixture(root)
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.save(scan(root))
    store.status(str(root), "needs-analysis")
    store.close()
    window = Window(Store(tmp_path / "data"))
    window.projects.selectRow(0)
    wait_for_idle(window, app)
    assert window.current_result is None and window.candidates.topLevelItemCount() == 0
    assert "재분석" in window.candidate_state.text()
    assert "정리 전" in window.file_info.text()
    assert not window.review_button.isEnabled()
    window.start_scan()
    wait_for_idle(window, app)
    assert window.current_result is not None and window.candidates.topLevelItemCount() > 0
    wait_for_history(window, app)
    window.close()


def test_job_history_link_resets_filter_and_can_return_to_all(tmp_path, wait_for_history):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "data")
    journal = Journal(store.directory)
    job = journal.begin([("target", 9)], None)
    journal.item(job, "target", "cancelled")
    journal.finish(job, "cancelled", None)
    another = journal.begin([("another", 1)], None)
    journal.item(another, "another", "cancelled")
    journal.finish(another, "cancelled", None)
    journal.close()
    window = Window(store)
    window.history_search.setText("no matching path")
    window.show_cleanup_history(job)
    wait_for_history(window, app)
    assert window.history_job == job and not window.history_search.text()
    assert window.history_page.total == 1 and window.history.topLevelItem(0).text(1) == "target"
    window.history_all.click()
    wait_for_history(window, app)
    assert window.history_job is None and window.history_page.total == 2
    window.close()


@pytest.mark.parametrize("mode", ["failed", "unknown", "record-error"])
def test_worker_returns_durable_failure_or_uncertainty_and_marks_stale_first(tmp_path, monkeypatch, mode):
    import dev_storage_manager.ui.main_window as ui
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    create_fixture(root)
    original = (root / "test_owned.py").read_bytes()
    result = scan(root)
    plan = prepare(result, next(c for c in result.candidates if c.kind == "pytest-cache"))
    directory = tmp_path / "data"
    store = Store(directory)
    store.add(str(root))
    store.save(result)
    store.close()
    calls = []
    class Backend:
        def move(self, path, validate):
            validate()
            check = Store(directory, recover_running=False)
            assert check.db.execute("SELECT status FROM projects WHERE path=?", (str(root),)).fetchone() == ("needs-analysis",)
            check.close()
            calls.append(path)
            if mode == "failed":
                raise OSError("fixture lock")
            destination = tmp_path / "fixture-bin"
            path.rename(destination)
            if mode == "unknown":
                raise OSError("fixture response lost")
            connection = sqlite3.connect(directory / "analysis.sqlite3")
            connection.execute("""CREATE TRIGGER fixture_write_failure BEFORE UPDATE ON cleanup_items
                BEGIN SELECT RAISE(ABORT, 'fixture persistent recording failure'); END""")
            connection.commit()
            connection.close()
            return Receipt(str(path), str(destination))
    monkeypatch.setattr(ui, "WindowsRecycle", Backend)
    worker = ui.CleanupWorker(plan, directory)
    results, errors = [], []
    worker.result.connect(results.append)
    worker.failed.connect(errors.append)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(7000, loop.quit)
    worker.start()
    loop.exec()
    app.processEvents()
    assert not worker.isRunning() and calls == [root / ".pytest_cache"]
    report = (errors or results)[0]
    expected = "running" if mode == "record-error" else mode
    assert report.result.status == expected and report.result.moved_size == 0
    assert bool(errors) == (mode == "record-error")
    assert bool(report.error) == (mode == "record-error")
    dialog = CleanupResultDialog(report)
    assert "휴지통 이동 확인" not in dialog.headline.text()
    assert report.path in dialog.details.toPlainText()
    dialog.reject()
    assert (root / "test_owned.py").read_bytes() == original
    assert (root / ".pytest_cache").exists() == (mode == "failed")
    if mode == "record-error":
        journal = Journal(directory)
        journal.db.execute("DROP TRIGGER fixture_write_failure")
        journal.db.commit()
        journal.recover()
        assert journal.job_result(report.job).status == "interrupted"
        assert journal.job_result(report.job).counts == {"unknown": 1}
        journal.close()


def test_worker_without_readable_journal_does_not_call_backend(tmp_path, monkeypatch):
    import dev_storage_manager.ui.main_window as ui
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    create_fixture(root)
    result = scan(root)
    plan = prepare(result, next(c for c in result.candidates if c.kind == "pytest-cache"))
    def no_journal(*args, **kwargs):
        raise sqlite3.OperationalError("fixture journal unavailable")
    calls = []
    class Forbidden:
        def __init__(self):
            calls.append(True)
    monkeypatch.setattr(ui, "Journal", no_journal)
    monkeypatch.setattr(ui, "WindowsRecycle", Forbidden)
    worker = ui.CleanupWorker(plan, tmp_path / "data")
    errors = []
    worker.failed.connect(errors.append)
    worker.run()
    assert len(errors) == 1 and not calls
    assert errors[0].result is None and errors[0].job is None
    assert "fixture journal unavailable" in errors[0].error
    assert (root / ".pytest_cache").is_dir()


def test_free_space_does_not_query_an_unverified_boundary(monkeypatch):
    from contextlib import contextmanager
    from dev_storage_manager.cleanup import service
    @contextmanager
    def denied(path):
        raise OSError("fixture changed boundary")
        yield
    calls = []
    monkeypatch.setattr(service, "directory_guard", denied)
    monkeypatch.setattr(service.shutil, "disk_usage", lambda path: calls.append(path))
    assert service.free_space("fixture-root") is None and not calls
