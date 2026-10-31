import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import py_compile
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
from dev_storage_manager.cleanup.review import inspect
from dev_storage_manager.cleanup.policy import cache_proof
from dev_storage_manager.cleanup.service import Plan
from dev_storage_manager.cleanup.capability import qualify
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def test_no_cleanup_is_selected_or_enabled_automatically(tmp_path, wait_for_idle):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    root.mkdir()
    source = root / "main.py"
    source.write_bytes(b"fixture = 1\n")
    py_compile.compile(str(source), doraise=True)
    result = scan(root)
    candidate = result.candidates[0]
    review = inspect(result, candidate, require_supported=False)
    plan = Plan(result, candidate, review.signature, cache_proof(review))
    store = Store(tmp_path / "appdata")
    store.add(str(root))
    store.save(result)
    window = Window(store)
    window.projects.selectRow(0)
    wait_for_idle(window, app)
    assert not window.cleanup_ready
    assert window.candidates.currentItem() is None
    # Simulate an independently qualified environment; do not invoke a backend.
    window.cleanup_ready = True
    window.qualified_kinds = frozenset({"python-cache"})
    window.show_review((review, plan))
    checkbox = window.review_dialog.findChild(QCheckBox)
    run = next(b for b in window.review_dialog.findChildren(QPushButton) if "휴지통" in b.text())
    assert not checkbox.isChecked() and not run.isEnabled()
    checkbox.setChecked(True)
    assert run.isEnabled()
    window.review_dialog.reject()
    assert source.read_bytes() == b"fixture = 1\n"
    assert (root / "__pycache__").is_dir()
    window.close()


def test_failed_environment_qualification_cannot_enable_cleanup(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import subprocess
    from dev_storage_manager.cleanup import capability as module
    class DeniedBackend:
        def move(self, *_):
            raise OSError("fixture backend denied")
    monkeypatch.setattr(module, "WindowsRecycle", DeniedBackend)
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1))
    capability = qualify(tmp_path / "owned-fixtures")
    assert not capability.ready
    assert "junction" in capability.reason
    assert list((tmp_path / "owned-fixtures").rglob("fixture.py"))


def test_history_separates_confirmed_size_and_free_space(tmp_path, wait_for_history):
    from dev_storage_manager.persistence.journal import Journal
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "data")
    journal = Journal(store.directory)
    job = journal.begin([("fixture-a", 15), ("fixture-b", 12)], 1000)
    journal.item(job, "fixture-a", "running")
    journal.item(job, "fixture-b", "running")
    journal.item(job, "fixture-a", "succeeded", destination="fixture-bin")
    journal.item(job, "fixture-b", "failed", "사용 중 시험")
    journal.finish(job, "partial", 900)
    journal.close()
    window = Window(store)
    wait_for_history(window, app)
    summary = window.history_summary.text()
    assert "15 B" in summary and "27 B" not in summary
    assert "1,000 B" in summary and "900 B" in summary
    window.close()


def test_history_displays_full_paths_reason_and_interrupted_job(tmp_path, wait_for_history):
    from dev_storage_manager.persistence.journal import Journal
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "data")
    journal = Journal(store.directory)
    path = str(tmp_path / ("한국어 공백 폴더 " * 12) / "__pycache__")
    job = journal.begin([(path, 1536)], None)
    journal.item(job, path, "running")
    journal.item(job, path, "succeeded", destination="fixture-bin/receipt")
    journal.interrupt(job)
    journal.close()
    window = Window(store)
    wait_for_history(window, app)
    window.resize(800, 600)
    detail = window.history_details.toPlainText()
    assert window.history_details.isReadOnly()
    assert path in detail and "1,536 B" in detail
    assert "항목 결과: 휴지통 이동 확인" in detail
    assert "전체 작업 상태: 중단" in detail
    assert "fixture-bin/receipt" in detail
    assert "관측 실패" in window.history_summary.text()
    window.close()


def test_history_retains_full_failure_reason(tmp_path, wait_for_history):
    from dev_storage_manager.persistence.journal import Journal
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "data")
    journal = Journal(store.directory)
    job = journal.begin([("fixture", 7)], 100)
    journal.item(job, "fixture", "running")
    reason = "fixture <읽기 실패> " * 40
    journal.item(job, "fixture", "failed", reason)
    journal.finish(job, "failed", 90)
    journal.close()
    window = Window(store)
    wait_for_history(window, app)
    assert reason in window.history_details.toPlainText()
    assert "확인된 영수증 없음" in window.history_details.toPlainText()
    assert reason == window.history.topLevelItem(0).toolTip(4)
    window.close()
