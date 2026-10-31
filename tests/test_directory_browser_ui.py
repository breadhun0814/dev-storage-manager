import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def test_browse_child_parent_search_and_file_selection_without_execution(tmp_path, wait_for_idle):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    (root / "sub").mkdir(parents=True)
    source = root / "sub/한글 A[1].py"
    source.write_bytes(b"raise AssertionError('must never execute')")
    store = Store(tmp_path / "data")
    store.add(str(root)); store.save(scan(root))
    window = Window(store)
    window.projects.selectRow(0); wait_for_idle(window, app)
    window.browse_selected_folder(); wait_for_idle(window, app)
    browser = window.browser
    assert browser.model.rowCount() == 1
    browser.table.setCurrentIndex(browser.proxy.index(0, 0))
    assert browser.open_button.isEnabled()
    browser.open_button.click(); wait_for_idle(window, app)
    assert browser.path == root / "sub"
    browser.search.setText("A[1]")
    assert browser.proxy.rowCount() == 1
    browser.table.setCurrentIndex(browser.proxy.index(0, 0))
    assert str(source) in browser.selected.toPlainText() and not browser.open_button.isEnabled()
    browser.home.click(); wait_for_idle(window, app)
    assert browser.path == root
    browser.table.setCurrentIndex(browser.proxy.index(0, 0))
    browser.open_button.click(); wait_for_idle(window, app)
    browser.up.click(); wait_for_idle(window, app)
    assert browser.path == root and not browser.up.isEnabled()
    browser.reject()
    assert window.browser is None and source.read_bytes().startswith(b"raise AssertionError")
    window.close()


@pytest.mark.parametrize("close_dialog", [True, False])
def test_close_cancels_slow_listing_without_reopening_dialog(tmp_path, monkeypatch, wait_for_idle, close_dialog):
    import dev_storage_manager.ui.directory_browser as ui
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"; root.mkdir()
    (root / "file.txt").write_bytes(b"owned")
    store = Store(tmp_path / "data"); store.add(str(root)); store.save(scan(root))
    window = Window(store); window.projects.selectRow(0); wait_for_idle(window, app)
    entered = Event()
    original = ui.list_directory
    def slow(result, target, cancel, protected, exclusions):
        entered.set()
        assert cancel.wait(5), "Closing browser did not cancel its read"
        return original(result, target, cancel, protected, exclusions)
    monkeypatch.setattr(ui, "list_directory", slow)
    window.browse_selected_folder()
    QTimer.singleShot(20, lambda: window.browser.reject() if close_dialog else window.browser.cancel_button.click())
    wait_for_idle(window, app)
    if not close_dialog:
        assert "취소" in window.browser.status.text()
        window.browser.reject()
    assert entered.is_set() and window.browser is None
    assert window.current_result is not None and window.browse_button.isEnabled()
    assert (root / "file.txt").read_bytes() == b"owned"
    window.close()
