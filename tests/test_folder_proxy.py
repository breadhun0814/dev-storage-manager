import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event, get_ident
from time import monotonic

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QAbstractItemModelTester

from dev_storage_manager.domain.models import Folder
from dev_storage_manager.ui.folder_model import FolderModel
from dev_storage_manager.ui.folder_proxy import FolderProxy, FolderIndexWorker
from dev_storage_manager.ui.main_window import Window
from dev_storage_manager.persistence.store import Store


def settle(proxy, app):
    deadline = monotonic() + 8
    while proxy.worker is not None or proxy.timer.isActive():
        assert monotonic() < deadline
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
        app.processEvents()


def test_literal_filter_numeric_sort_and_source_mapping():
    app = QApplication.instance() or QApplication([])
    model = FolderModel()
    model.set_folders([Folder("C:/한국어/A[1]", 100, 2), Folder("C:/한국어/B", 2, 100)])
    proxy = FolderProxy()
    proxy.setSourceModel(model)
    tester = QAbstractItemModelTester(proxy, QAbstractItemModelTester.FailureReportingMode.Fatal)
    proxy.sort(1, Qt.SortOrder.AscendingOrder)
    settle(proxy, app)
    assert proxy.data(proxy.index(0, 1), Qt.ItemDataRole.UserRole) == 2
    assert proxy.mapToSource(proxy.index(0, 0)).row() == 1
    assert proxy.mapFromSource(model.index(1, 0)).row() == 0
    proxy.setFilterFixedString("a[1]")
    settle(proxy, app)
    assert proxy.rowCount() == 1 and proxy.mapToSource(proxy.index(0, 0)).row() == 0
    assert not proxy.mapFromSource(model.index(1, 0)).isValid()
    proxy.setFilterFixedString("")
    proxy.sort(-1)
    settle(proxy, app)
    assert proxy.mapToSource(proxy.index(0, 0)).row() == 0
    assert proxy.rowCount() == 2
    proxy.shutdown()


def test_changed_source_and_query_discard_old_generation(monkeypatch):
    app = QApplication.instance() or QApplication([])
    model, proxy = FolderModel(), FolderProxy()
    model.set_folders([Folder("C:/old", 1, 1)])
    proxy.setSourceModel(model)
    entered, release = Event(), Event()
    original = FolderIndexWorker.run
    generations = []
    def held(self):
        generations.append(self.generation)
        if len(generations) == 1:
            entered.set()
            assert release.wait(3)
        original(self)
    monkeypatch.setattr(FolderIndexWorker, "run", held)
    proxy.sort(1)
    def replace():
        assert entered.is_set()
        model.set_folders([Folder("C:/new A[1]", 99, 1), Folder("C:/new B", 20, 1)])
        proxy.setFilterFixedString("A[1]")
        QTimer.singleShot(250, release.set)
    QTimer.singleShot(40, replace)
    settle(proxy, app)
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0), Qt.ItemDataRole.UserRole) == "C:/new A[1]"
    assert proxy.mapToSource(proxy.index(0, 0)).row() == 0
    assert len(generations) == 2 and generations[0] != generations[1]
    proxy.shutdown()


def test_busy_sort_keeps_ui_responsive_and_app_close_waits(tmp_path, monkeypatch, wait_for_history):
    app = QApplication.instance() or QApplication([])
    window = Window(Store(tmp_path / "data"))
    window.show()
    wait_for_history(window, app)
    window.folder_model.set_folders([Folder(f"C:/fixture/{n}", n, 1) for n in range(10000)])
    entered, release = Event(), Event()
    original = FolderIndexWorker.run
    threads = []
    def held(self):
        threads.append(get_ident())
        entered.set()
        assert release.wait(3)
        original(self)
    monkeypatch.setattr(FolderIndexWorker, "run", held)
    window.folders.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    interactions = []
    def interact():
        interactions.append(entered.is_set())
        window.search.setText("still responsive")
        window.close()
        assert window.isVisible() and window._closing
        release.set()
    QTimer.singleShot(40, interact)
    settle(window.folder_proxy, app)
    app.processEvents()
    assert interactions == [True] and all(t != get_ident() for t in threads)
    assert not window.isVisible()


def test_failed_index_is_not_an_empty_success_and_can_retry(monkeypatch):
    app = QApplication.instance() or QApplication([])
    model, proxy = FolderModel(), FolderProxy()
    model.set_folders([Folder("C:/fixture", 100, 1)])
    proxy.setSourceModel(model)
    original = FolderIndexWorker.run
    monkeypatch.setattr(FolderIndexWorker, "run", lambda self: self.failed.emit("fixture failure"))
    proxy.sort(1)
    settle(proxy, app)
    assert proxy.rowCount() == 0 and proxy.error == "fixture failure"
    monkeypatch.setattr(FolderIndexWorker, "run", original)
    proxy.sort(1)
    settle(proxy, app)
    assert proxy.rowCount() == 1 and not proxy.error
    proxy.shutdown()
