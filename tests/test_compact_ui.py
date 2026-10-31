import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import py_compile
from PySide6.QtWidgets import QApplication, QScrollArea, QCheckBox, QPushButton
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.cleanup.review import inspect
from dev_storage_manager.ui.main_window import Window


def test_small_window_project_picker_and_explicit_candidate_review(tmp_path, wait_for_idle):
    app = QApplication.instance() or QApplication([])
    project = tmp_path / ("이름이 긴 개발 프로젝트 " * 3).strip()
    project.mkdir()
    source = project / "fixture.py"
    source.write_text("owned_fixture = 42\n", encoding="utf-8")
    py_compile.compile(str(source), doraise=True)
    store = Store(tmp_path / "appdata")
    store.add(str(project))
    result = scan(project)
    store.save(result)
    window = Window(store)
    window.resize(800, 600)
    window.show()
    window.project_picker.setCurrentIndex(0)
    wait_for_idle(window, app)
    app.processEvents()
    assert window.width() == 800 and window.height() == 600
    assert window.project_picker.currentText() == project.name
    assert window.project_location.text() == str(project)
    assert isinstance(window.centralWidget(), QScrollArea)
    assert not window.projects.isVisible()
    toggle = next(action for button, action in window.tool_actions if "프로젝트 목록" in button.text())
    toggle.trigger()
    assert window.projects.isVisible() and window.project_location.isVisible()
    toggle.trigger()
    assert not window.projects.isVisible()
    assert window.candidates.currentItem() is None
    assert not window.review_button.isEnabled()
    candidate = window.candidates.topLevelItem(0)
    window.candidates.setCurrentItem(candidate)
    assert window.review_button.isEnabled()
    review = inspect(result, result.candidates[0], require_supported=False)
    window.show_review((review, None))
    checkbox = window.review_dialog.findChild(QCheckBox)
    run = next(b for b in window.review_dialog.findChildren(QPushButton) if "휴지통" in b.text())
    checkbox.setChecked(True)
    assert not run.isEnabled() and not window.cleanup_ready
    window.review_dialog.reject()
    window.candidates.clear()
    assert not window.review_button.isEnabled()
    window.close()
    assert source.read_text(encoding="utf-8") == "owned_fixture = 42\n"
