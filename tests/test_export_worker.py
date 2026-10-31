import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event
import json

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def test_export_does_not_block_ui_or_overwrite_source(tmp_path, monkeypatch, wait_for_idle):
    import dev_storage_manager.ui.main_window as ui
    app = QApplication.instance() or QApplication([])
    project = tmp_path / "project"
    project.mkdir()
    source = project / "source.py"
    source.write_bytes(b"fixture")
    store = Store(tmp_path / "data")
    store.add(str(project))
    store.save(scan(project))
    window = Window(store)
    window.projects.selectRow(0)
    wait_for_idle(window, app)
    output = tmp_path / "report.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args, **_kwargs: (str(output), "JSON 보고서 (*.json)"))
    release = Event()
    original = ui.export_json
    def slow_export(result, path):
        assert release.wait(5), "UI 이벤트가 저장 스레드로 전달되지 않음"
        original(result, path)
    monkeypatch.setattr(ui, "export_json", slow_export)
    window.export_report()
    assert not window.stop.isEnabled()
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    def interact():
        window.search.setText("source")
        release.set()
    QTimer.singleShot(20, interact)
    QTimer.singleShot(7000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None
    assert window.search.text() == "source"
    assert json.loads(output.read_text(encoding="utf-8"))["analysis"]["size"] == 7
    assert source.read_bytes() == b"fixture"
    window.close()
