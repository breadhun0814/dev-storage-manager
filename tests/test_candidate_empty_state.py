import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from dev_storage_manager.domain.models import Result, Folder, Issue
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.candidate_state import empty_candidate_message
from dev_storage_manager.ui.main_window import Window
from dev_storage_manager.scanning.scanner import scan


def test_incomplete_and_excluded_scans_never_claim_no_candidates_exist():
    for status in ("cancelled", "incomplete", "failed"):
        assert "확정할 수 없습니다" in empty_candidate_message(Result("fixture", status=status))
    assert "포함되지 않습니다" in empty_candidate_message(Result("fixture", issues=[Issue("excluded", "fixture")]))


def test_complete_scan_with_no_candidates_shows_next_action(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(Store(tmp_path / "appdata"))
    window.show()
    root = tmp_path / "ordinary-project"
    root.mkdir()
    (root / "README.txt").write_bytes(b"owned fixture")
    result = scan(root)
    assert result.status == "complete" and not result.candidates
    window.display(result)
    app.processEvents()
    assert "정리 후보가 없습니다" in window.candidate_state.text()
    assert window.candidates.isHidden() and window.review_button.isHidden()
    assert window.candidate_folder_button.isEnabled()
    window.candidate_folder_button.click()
    assert window.tabs.currentIndex() == 1 and window.folder_proxy.rowCount() == 1
    window.open_result()
    assert "아직 분석 결과가 없습니다" in window.candidate_state.text()
    assert not window.candidate_folder_button.isEnabled()
    window.close()
