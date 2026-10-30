import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
from dev_storage_manager.domain.models import Result
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def test_event_loop_responds_while_worker_waits(tmp_path, monkeypatch):
    # Deterministic slow filesystem stand-in: tests UI delivery, not disk speed.
    import dev_storage_manager.ui.main_window as ui
    def slow_scan(root, cancel, progress, protected, exclusions):
        progress(0, 0, str(root))
        if not cancel.wait(5):
            raise AssertionError("UI가 취소를 전달하지 못함")
        return Result(str(root), status="cancelled")
    monkeypatch.setattr(ui, "scan", slow_scan)
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "data")
    store.add(str(tmp_path))
    window = Window(store)
    window.projects.selectRow(0)
    window.start_scan()
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(20, window.stop.click)
    QTimer.singleShot(7000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None
    assert store.load(str(tmp_path)).status == "cancelled"
    window.close()
