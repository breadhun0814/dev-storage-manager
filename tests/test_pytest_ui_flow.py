import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
from dev_storage_manager.cleanup.capability import Capability
from dev_storage_manager.cleanup.pytest_fixture import create_fixture
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.platform.recycle import Receipt
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.ui.main_window import Window


def wait_worker(window, app):
    loop = QEventLoop()
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(7000, loop.quit)
    loop.exec()
    app.processEvents()
    assert window.worker is None


def choose_pytest(window):
    assert window.candidates.currentItem() is None
    item = next(window.candidates.topLevelItem(i) for i in range(window.candidates.topLevelItemCount())
                if window.candidates.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole).kind == "pytest-cache")
    window.candidates.setCurrentItem(item)


def test_pytest_full_review_move_history_and_reanalysis_with_owned_backend(tmp_path, monkeypatch, wait_for_history):
    import dev_storage_manager.ui.main_window as ui
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "검토할 시험 프로젝트"
    create_fixture(root)
    source_before = (root / "test_owned.py").read_bytes()
    store = Store(tmp_path / "appdata")
    store.add(str(root))
    store.save(scan(root))
    window = Window(store)
    window.show()
    window.projects.selectRow(0)
    wait_worker(window, app)
    # Python approval must not authorize pytest: environment kinds are distinct.
    window.environment_result(Capability(True, "fixture python approval", qualified_kinds=("python-cache",)))
    window.environment_dialog.reject()
    choose_pytest(window)
    window.start_review()
    wait_worker(window, app)
    check = window.review_dialog.findChild(QCheckBox)
    run = next(b for b in window.review_dialog.findChildren(QPushButton) if "휴지통" in b.text())
    check.setChecked(True)
    assert not run.isEnabled()
    window.review_dialog.reject()
    # Independently qualified pytest kind; do not call a real Windows bin here.
    window.environment_result(Capability(True, "fixture pytest approval", qualified_kinds=("pytest-cache",)))
    window.environment_dialog.reject()
    choose_pytest(window)
    window.start_review()
    wait_worker(window, app)
    check = window.review_dialog.findChild(QCheckBox)
    run = next(b for b in window.review_dialog.findChildren(QPushButton) if "휴지통" in b.text())
    assert not check.isChecked() and not run.isEnabled()
    check.setChecked(True)
    assert run.isEnabled()
    class Backend:
        def move(self, path, validate):
            validate()
            assert path == root / ".pytest_cache"
            destination = tmp_path / "fake-bin"
            path.rename(destination)
            return Receipt(str(path), str(destination))
    monkeypatch.setattr(ui, "WindowsRecycle", Backend)
    window.history_search.setText("an unrelated previous history search")
    run.click()
    wait_worker(window, app)
    assert not (root / ".pytest_cache").exists()
    assert (root / "test_owned.py").read_bytes() == source_before
    journal = Journal(store.directory)
    assert journal.history()[0][3] == "succeeded"
    journal.close()
    assert "다시 분석" in window.candidate_state.text()
    assert window.current_result is None
    assert window.cleanup_dialog.headline.text() == "휴지통 이동 확인"
    assert "관측한 디스크 여유 공간" in window.cleanup_dialog.details.toPlainText()
    wait_for_history(window, app)
    assert window.history_job is not None and window.history_page.total == 1
    assert not window.history_search.text()
    assert window.history.topLevelItem(0).text(1) == str(root / ".pytest_cache")
    window.cleanup_dialog.rescan_button.click()
    wait_worker(window, app)
    assert window.candidates.topLevelItemCount() == 0
    assert window.file_model.rowCount() == 2
    window.close()
