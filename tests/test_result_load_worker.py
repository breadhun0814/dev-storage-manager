import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event, get_ident
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def test_large_result_loading_leaves_ui_responsive(tmp_path, monkeypatch, wait_for_idle):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    root.mkdir()
    (root / "owned.txt").write_bytes(b"owned fixture")
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.save(scan(root))
    window = Window(store)
    main_thread = get_ident()
    release = Event()
    calls = []
    original = Store.load
    def slow_load(self, path):
        calls.append(get_ident())
        assert get_ident() != main_thread
        assert release.wait(5), "UI interaction did not release background load"
        return original(self, path)
    monkeypatch.setattr(Store, "load", slow_load)
    window.projects.selectRow(0)
    assert window.worker is not None and not window.stop.isEnabled()
    def interact():
        window.search.setText("owned")
        release.set()
    QTimer.singleShot(20, interact)
    wait_for_idle(window, app)
    assert calls and window.search.text() == "owned"
    assert window.current_result.files == 1 and window.file_proxy.rowCount() == 1
    window.close()


def test_corrupt_saved_result_clears_stale_data_and_reports_error(tmp_path, wait_for_idle):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    root.mkdir()
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.db.execute("UPDATE projects SET result='broken' WHERE path=?", (str(root),))
    store.db.commit()
    window = Window(store)
    window.projects.selectRow(0)
    wait_for_idle(window, app)
    assert window.current_result is None and window.file_proxy.rowCount() == 0
    assert "읽기 실패" in window.summary.text()
    assert not window.review_button.isEnabled()
    window.close()
