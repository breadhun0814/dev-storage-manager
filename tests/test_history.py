import hashlib
import os
import sqlite3
from pathlib import Path
from threading import Event, get_ident

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from dev_storage_manager.persistence.journal import Journal, JournalError, HistoryCancelled
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def seed(directory, count=451):
    """Synthetic metadata only. No original paths or trash operations are used."""
    journal = Journal(directory)
    paths = [f"C:/한국어 공백/ΣOURCE {n:04d}/__pycache__" for n in range(count)]
    job = journal.begin([(path, 10) for path in paths], 1000)
    with journal.db:
        journal.db.executemany("UPDATE cleanup_items SET status=?,reason=?,destination=? WHERE job=? AND path=?", [
            ("failed" if n in (350, 450) else "succeeded", "사용 중 [100%_]" if n in (350, 450) else "", None if n in (350, 450) else "fixture-receipt", job, path)
            for n, path in enumerate(paths)])
    journal.finish(job, "partial", 900)
    journal.close()
    return job, paths


def test_pages_keep_boundary_and_whole_job_total(tmp_path):
    directory = tmp_path / "data"
    job, paths = seed(directory)
    reader = Journal(directory, read_only=True)
    page = reader.history_page()
    assert page.total == 451 and len(page.records) == 200 and page.moved == {job: 4490}
    writer = Journal(directory)
    newer = writer.begin([("새 후보", 7)], None)
    writer.item(newer, "새 후보", "cancelled")
    writer.finish(newer, "cancelled", None)
    writer.close()
    pages = [page, reader.history_page(offset=200, anchor=page.anchor), reader.history_page(offset=400, anchor=page.anchor)]
    seen = [row[1] for p in pages for row in p.records]
    assert seen == paths and len(set(seen)) == 451
    assert all(p.total == 451 and p.moved == {job: 4490} for p in pages)
    fresh = reader.history_page()
    assert fresh.total == 452 and fresh.records[0][1] == "새 후보"
    assert fresh.anchor > page.anchor
    reader.close()


def test_search_is_literal_unicode_and_not_limited_to_first_page(tmp_path):
    job, paths = seed(tmp_path)
    journal = Journal(tmp_path, read_only=True)
    result = journal.history_page(query="σource 0350")
    assert result.total == 1 and result.records[0][1] == paths[350]
    assert result.moved == {job: 4490}  # Includes successes outside this filter/page.
    result = journal.history_page(query="[100%_]")
    assert [row[1] for row in result.records] == [paths[350], paths[450]]
    assert journal.history_page(query="missing").total == 0
    assert journal.history_page(offset=999999).offset == 400
    journal.close()


def test_read_only_query_preserves_database_and_cancels(tmp_path):
    seed(tmp_path)
    file = tmp_path / "analysis.sqlite3"
    before = hashlib.sha256(file.read_bytes()).digest(), file.stat().st_mtime_ns
    journal = Journal(tmp_path, read_only=True)
    journal.history_page()
    with pytest.raises(sqlite3.OperationalError):
        journal.begin([("never-created", 1)], None)
    event = Event()
    event.set()
    with pytest.raises(HistoryCancelled):
        journal.history_page(cancel=event)
    # Cancel inside SQL, not just before entering it. A cancelled transaction and
    # its progress handler must not poison the next read on the same connection.
    event.clear()
    statements = []
    journal.db.set_trace_callback(statements.append)
    class DuringQuery:
        calls = 0
        def is_set(self):
            self.calls += 1
            return self.calls > 2
    with pytest.raises(HistoryCancelled):
        journal.history_page(query="not present", cancel=DuringQuery())
    assert any("SELECT COUNT(*)" in sql for sql in statements)
    assert not any(" LIMIT " in sql for sql in statements)
    journal.db.set_trace_callback(None)
    assert journal.history_page().total == 451
    journal.close()
    assert (hashlib.sha256(file.read_bytes()).digest(), file.stat().st_mtime_ns) == before


def test_missing_or_malformed_history_is_not_empty_success(tmp_path):
    store = Store(tmp_path)
    reader = Journal(tmp_path, read_only=True)
    assert reader.history_page().total == 0  # Valid pre-cleanup app database.
    reader.close()
    store.close()
    writer = Journal(tmp_path)
    job = writer.begin([("fixture", 1)], None)
    writer.db.execute("UPDATE cleanup_items SET size=NULL")
    writer.db.commit()
    with pytest.raises(JournalError, match="형식"):
        writer.history_page()
    writer.db.execute("DROP TABLE cleanup_items")
    writer.db.commit()
    with pytest.raises(JournalError, match="일부"):
        writer.history_page()
    writer.close()


def test_history_ui_paging_search_and_full_total(tmp_path, wait_for_history):
    job, paths = seed(tmp_path / "data")
    app = QApplication.instance() or QApplication([])
    window = Window(Store(tmp_path / "data"))
    window.resize(800, 600)
    window.tabs.setCurrentIndex(3)
    window.show()
    wait_for_history(window, app)
    app.processEvents()
    for control in (window.history_next, window.history_details, window.history_refresh):
        assert window.rect().contains(control.mapTo(window, control.rect().bottomRight()))
    assert window.history.horizontalScrollBar().maximum() == 0
    assert window.history.topLevelItemCount() == 200
    assert "451" in window.history_page_label.text()
    assert "4.4 KB" in window.history_summary.text()
    assert not window.history_previous.isEnabled() and window.history_next.isEnabled()
    window.history_next.click()
    wait_for_history(window, app)
    assert window.history.topLevelItem(0).text(1) == paths[200]
    window.history_next.click()
    wait_for_history(window, app)
    assert window.history.topLevelItemCount() == 51 and not window.history_next.isEnabled()
    window.history_previous.click()
    wait_for_history(window, app)
    assert window.history.topLevelItem(0).text(1) == paths[200]
    window.history_search.setText("[100%_]")
    wait_for_history(window, app)
    assert window.history.topLevelItemCount() == 2
    assert "검색 결과 2개" in window.history_page_label.text()
    assert "4.4 KB" in window.history_summary.text()
    window.history_search.setText("not found")
    wait_for_history(window, app)
    assert not window.history.topLevelItemCount() and "검색 결과가 없습니다" in window.history_summary.text()
    window.history_search.clear()
    wait_for_history(window, app)
    assert window.history.topLevelItemCount() == 200
    window.close()


def test_slow_query_keeps_ui_responsive_and_close_waits(tmp_path, monkeypatch, wait_for_history):
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    original = Journal.history_page
    threads = []
    def slow(self, *args, **kwargs):
        threads.append(get_ident())
        entered.set()
        assert release.wait(3)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Journal, "history_page", slow)
    window = Window(Store(tmp_path / "data"))
    interactions = []
    def interact():
        interactions.append(entered.is_set())
        window.search.setText("UI still responsive")
        window.close()
        assert window._closing and window.history_worker is not None
        release.set()
    QTimer.singleShot(40, interact)
    wait_for_history(window, app)
    assert interactions == [True] and threads and all(t != get_ident() for t in threads)
    assert window.history_worker is None and not window.isVisible()


def test_query_failure_is_not_reported_as_no_history(tmp_path, monkeypatch, wait_for_history):
    app = QApplication.instance() or QApplication([])
    original = Journal.history_page
    attempts = []
    def failed(*_, **__):
        attempts.append(True)
        if len(attempts) == 1:
            raise sqlite3.DatabaseError("fixture database failure")
        return original(*_, **__)
    monkeypatch.setattr(Journal, "history_page", failed)
    window = Window(Store(tmp_path / "data"))
    wait_for_history(window, app)
    assert "조회 실패" in window.history_page_label.text()
    assert "fixture database failure" in window.history_page_label.text()
    assert "성공했다는 뜻이 아닙니다" in window.history_summary.text()
    assert not window.history_next.isEnabled() and window.history_refresh.isEnabled()
    window.history_refresh.click()
    wait_for_history(window, app)
    assert "실행 이력이 없습니다" in window.history_summary.text()
    window.close()


def test_unfinished_records_do_not_claim_current_execution(tmp_path, wait_for_history):
    directory = tmp_path / "data"
    writer = Journal(directory)
    job = writer.begin([("a", 10), ("b", 20)], None)
    writer.item(job, "a", "running")
    writer.close()
    app = QApplication.instance() or QApplication([])
    window = Window(Store(directory))
    wait_for_history(window, app)
    assert window.history.topLevelItem(0).text(3) == "진행 상태 미확정"
    assert "현재 진행 여부·성공·원본 보존을 단정할 수 없습니다" in window.history_details.toPlainText()
    window.history.setCurrentItem(window.history.topLevelItem(1))
    assert window.history.topLevelItem(1).text(3) == "대기 기록"
    assert "조회 시점의 기록된 상태: 대기" in window.history_details.toPlainText()
    window.close()
    reader = Journal(directory, read_only=True)
    assert [row[3] for row in reader.history()] == ["running", "pending"]
    reader.close()


def test_new_search_supersedes_running_query(tmp_path, monkeypatch, wait_for_history):
    seed(tmp_path / "data")
    app = QApplication.instance() or QApplication([])
    original = Journal.history_page
    entered, release = Event(), Event()
    queries = []
    def held(self, *args, **kwargs):
        query = kwargs.get("query", "")
        queries.append(query)
        if query == "σource":
            entered.set()
            assert release.wait(3)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Journal, "history_page", held)
    window = Window(Store(tmp_path / "data"))
    wait_for_history(window, app)
    window.history_search.setText("σource")
    def change_search():
        assert entered.is_set()
        window.history_search.setText("0350")
        QTimer.singleShot(350, release.set)
    QTimer.singleShot(400, change_search)
    wait_for_history(window, app)
    assert queries == ["", "σource", "0350"]
    assert window.history_page.query == "0350"
    assert window.history.topLevelItemCount() == 1
    assert "0350" in window.history_details.toPlainText()
    window.close()
