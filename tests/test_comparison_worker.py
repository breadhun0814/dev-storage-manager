import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QTableView
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def test_comparison_remains_responsive_and_displays_delta(tmp_path, monkeypatch, wait_for_idle):
    import dev_storage_manager.ui.main_window as ui
    app = QApplication.instance() or QApplication([])
    project = tmp_path / "project"
    project.mkdir()
    source = project / "source.py"
    source.write_bytes(b"1")
    store = Store(tmp_path / "data")
    store.add(str(project))
    store.save(scan(project))
    source.write_bytes(b"12345")
    store.save(scan(project))
    window = Window(store)
    window.projects.selectRow(0)
    wait_for_idle(window, app)
    release = Event()
    original = ui.compare
    def slow_compare(before, after):
        assert release.wait(5)
        return original(before, after)
    monkeypatch.setattr(ui, "compare", slow_compare)
    window.show_comparison()
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    def interact():
        window.search.setText("source")
        release.set()
    QTimer.singleShot(20, interact)
    QTimer.singleShot(7000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None and window.search.text() == "source"
    table = window.comparison_dialog.findChild(QTableView)
    assert table.model().data(table.model().index(0, 3)) == "4 B"
    assert source.read_bytes() == b"12345"
    window.comparison_dialog.close()
    window.close()
