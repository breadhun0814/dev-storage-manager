import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event, get_ident
from time import monotonic

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget

from dev_storage_manager.cleanup.review import Review, IncludedFile
from dev_storage_manager.domain.models import Candidate
from dev_storage_manager.ui.review_dialog import ReviewDialog, IndexWorker


def review(count=1000, blocked=None):
    root = r"C:\시험 공간\한국어 후보"
    candidate = Candidate(root, "node-deps", 123456, count, "소유 프로젝트 근거", "사용자 수정이 있을 수 있음", "재설치 조건 확인")
    files = [IncludedFile(root + rf"\하위\파일 {n:05d} [100%_].bin", (count - n) * 1024) for n in range(count)]
    return Review(r"C:\시험 공간", candidate, files, "fixture", blocked or [])


def wait(dialog, app):
    deadline = monotonic() + 8
    while dialog.worker is not None or dialog.timer.isActive():
        assert monotonic() < deadline
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
        app.processEvents()


def test_large_review_search_sort_selection_and_scope():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(800, 600)
    data = review(50000)
    dialog = ReviewDialog(data, [], True, parent)
    dialog.show()
    wait(dialog, app)
    assert dialog.model.rowCount() == 50000
    assert not dialog.table.selectionModel().hasSelection()
    assert not dialog.confirmed.isChecked() and not dialog.run_button.isEnabled()
    assert dialog.rect().contains(dialog.run_button.mapTo(dialog, dialog.run_button.rect().bottomRight()))
    dialog.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    wait(dialog, app)
    assert dialog.model.file_at(0).size == 1024
    dialog.table.selectRow(0)
    assert data.files[-1].path in dialog.selection.toPlainText()
    assert "1,024 B" in dialog.selection.toPlainText()
    target = dialog.target.toPlainText()
    dialog.search.setText("파일 00002 [100%_]")
    wait(dialog, app)
    assert dialog.model.rowCount() == 1 and dialog.model.file_at(0) is data.files[2]
    assert dialog.target.toPlainText() == target
    assert "50,000" in dialog.scope.text() and len(data.files) == 50000
    dialog.confirmed.setChecked(True)
    assert dialog.run_button.isEnabled()
    dialog.search.setText("does not exist")
    wait(dialog, app)
    assert dialog.model.rowCount() == 0 and len(data.files) == 50000
    dialog.reject()
    wait(dialog, app)
    parent.close()


def test_blocked_review_cannot_enable_run():
    app = QApplication.instance() or QApplication([])
    data = review(12, ["전체 목록 확인 실패"])
    dialog = ReviewDialog(data, data.blocked, False)
    wait(dialog, app)
    assert not dialog.confirmed.isEnabled()
    dialog.confirmed.setChecked(True)
    assert not dialog.run_button.isEnabled()
    assert "전체 목록/실행 조건 미확인" in dialog.scope.text()
    assert "전체 목록 확인 실패" in dialog.conditions.toPlainText()
    dialog.reject()


def test_slow_indexing_does_not_block_ui_and_close_cancels(monkeypatch):
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    original = IndexWorker.run
    threads = []
    def slow(self):
        threads.append(get_ident())
        entered.set()
        assert release.wait(3)
        original(self)
    monkeypatch.setattr(IndexWorker, "run", slow)
    dialog = ReviewDialog(review(), [], False)
    dialog.show()
    interactions = []
    def interact():
        interactions.append(entered.is_set())
        dialog.search.setText("UI interaction")
        dialog.reject()
        assert dialog.worker.cancel.is_set()
        release.set()
    QTimer.singleShot(40, interact)
    wait(dialog, app)
    assert interactions == [True] and all(t != get_ident() for t in threads)
    assert not dialog.isVisible()


def test_display_error_revokes_confirmation_and_retry_requires_new_confirmation(monkeypatch):
    app = QApplication.instance() or QApplication([])
    original = IndexWorker.run
    def failed(self):
        self.failed.emit("fixture display failure")
    monkeypatch.setattr(IndexWorker, "run", failed)
    dialog = ReviewDialog(review(), [], True)
    wait(dialog, app)
    dialog.confirmed.setChecked(True)
    assert not dialog.run_button.isEnabled()
    assert "표시 실패" in dialog.count.text()
    monkeypatch.setattr(IndexWorker, "run", original)
    dialog.search.setText("00001")
    wait(dialog, app)
    assert dialog.confirmed.isEnabled() and not dialog.run_button.isEnabled()
    # A programmatic toggle above must not become an automatic approval on retry.
    assert not dialog.confirmed.isChecked()
    dialog.reject()


def test_main_window_close_waits_for_review_indexer(tmp_path, monkeypatch):
    from dev_storage_manager.ui.main_window import Window
    from dev_storage_manager.persistence.store import Store
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    original = IndexWorker.run
    def slow(self):
        entered.set()
        assert release.wait(3)
        original(self)
    monkeypatch.setattr(IndexWorker, "run", slow)
    window = Window(Store(tmp_path / "data"))
    window.show()
    window.show_review((review(), None))
    def close():
        assert entered.is_set()
        window.close()
        assert window.isVisible() and window._closing
        release.set()
    QTimer.singleShot(40, close)
    deadline = monotonic() + 8
    while window.isVisible() or window.history_worker is not None:
        assert monotonic() < deadline
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
        app.processEvents()
    assert window.review_dialog is None
