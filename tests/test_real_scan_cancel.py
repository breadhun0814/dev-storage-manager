import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def test_real_scan_can_be_cancelled_from_ui_after_progress(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "actual-files"
    root.mkdir()
    for number in range(3000):
        (root / f"fixture-{number:04}.txt").write_bytes(b"original fixture")
    store = Store(tmp_path / "data")
    store.add(str(root))
    window = Window(store)
    window.projects.selectRow(0)
    window.start_scan()
    def interact_and_cancel(*_):
        window.search.setText("fixture")
        window.stop.click()
    window.worker.progress.connect(interact_and_cancel)
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None
    result = store.load(str(root))
    assert result.status == "cancelled" and result.files < 3000
    assert window.search.text() == "fixture"
    assert (root / "fixture-0000.txt").read_bytes() == b"original fixture"
    window.close()
