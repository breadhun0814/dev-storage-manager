import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def test_worker_to_results(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "시험 프로젝트"
    root.mkdir()
    (root / "hello.py").write_bytes(b"hello")
    store = Store(tmp_path / "data")
    store.add(str(root))
    window = Window(store)
    window.projects.selectRow(0)
    window.start_scan()
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None
    assert window.folders.topLevelItemCount() == 1
    assert store.load(str(root)).size == 5
    window.close()
