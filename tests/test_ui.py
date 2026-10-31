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
    assert window.folder_proxy.rowCount() == 1
    assert store.load(str(root)).size == 5
    window.close()


def test_background_save_failure_is_not_shown_as_success(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append(_args[-1]))
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "fixture-project"
    root.mkdir()
    source = root / "source.py"
    source.write_bytes(b"preserve source")
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.db.execute("CREATE TRIGGER fail_complete BEFORE UPDATE ON projects WHEN NEW.status='complete' BEGIN SELECT RAISE(ABORT,'fixture disk failure'); END")
    store.db.commit()
    window = Window(store)
    window.projects.selectRow(0)
    window.start_scan()
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None
    assert store.projects()[0][2] == "failed"
    assert store.load(str(root)) is None
    assert messages and "fixture disk failure" in messages[0]
    assert source.read_bytes() == b"preserve source"
    window.close()
