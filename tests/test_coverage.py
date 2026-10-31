import csv
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtWidgets import QApplication

from dev_storage_manager.domain.models import Result, Folder, Issue
from dev_storage_manager.domain.coverage import folder_coverage
from dev_storage_manager.ui.folder_model import FolderModel
from dev_storage_manager.persistence.report import export_json, export_csv
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan


def test_error_and_exclusion_propagate_only_to_containing_folders():
    root = "C:/프로젝트"
    result = Result(root, status="incomplete", folders=[Folder(root), Folder(root + "/denied"), Folder(root + "/known"), Folder(root + "/excluded")],
                    issues=[Issue(root + "/denied", "읽기 거부", True), Issue(root + "/excluded/private", "사용자 제외")])
    coverage = folder_coverage(result)
    assert coverage.state(root) == "incomplete"
    assert coverage.state(root + "/denied") == "incomplete"
    assert coverage.state(root + "/known") == "complete"
    assert coverage.state(root + "/excluded") == "excluded"
    # Windows lexical path equivalence, not filesystem resolution.
    assert coverage.state(root.lower() + "/DENIED") == "incomplete"


def test_cancel_and_unlocated_failure_never_imply_complete_zero():
    for status in ("cancelled", "incomplete", "failed", "interrupted"):
        result = Result("C:/fixture", status=status, folders=[Folder("C:/fixture")])
        assert folder_coverage(result).state(result.root) != "complete"
    result = Result("C:/fixture", status="incomplete", issues=[Issue("D:/outside", "unlocated error", True)])
    assert folder_coverage(result).state(result.root) == "incomplete"


def test_zero_unknown_and_confirmed_numeric_sort_are_distinct():
    app = QApplication.instance() or QApplication([])
    root = "C:/시험"
    result = Result(root, status="incomplete", folders=[Folder(root, 2048, 2), Folder(root + "/denied"), Folder(root + "/empty")],
                    issues=[Issue(root + "/denied", "거부", True)])
    model = FolderModel()
    model.set_result(result)
    assert model.data(model.index(1, 1)) == "—"
    assert model.data(model.index(1, 2)) == "—"
    assert model.data(model.index(1, 4)) == "읽기 실패 · 불완전"
    assert "빈 폴더나 0바이트라고 확정할 수 없습니다" in model.data(model.index(1, 1), Qt.ItemDataRole.ToolTipRole)
    assert model.data(model.index(2, 1)) == "0 B" and model.data(model.index(2, 2)) == 0
    assert model.data(model.index(0, 1)) == "확인 2.0 KB"
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(Qt.ItemDataRole.UserRole)
    proxy.sort(1, Qt.SortOrder.DescendingOrder)
    assert proxy.data(proxy.index(0, 1), Qt.ItemDataRole.UserRole) == 2048


def test_real_scan_read_failure_survives_storage_ui_and_reports(tmp_path, monkeypatch):
    from dev_storage_manager.scanning import scanner
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "한국어 프로젝트"
    denied, empty = root / "denied", root / "empty"
    denied.mkdir(parents=True)
    empty.mkdir()
    (denied / "must-stay.bin").write_bytes(b"owned fixture")
    original = scanner.os.scandir
    def failure(path):
        if os.path.normcase(str(path)) == os.path.normcase(str(denied)):
            raise PermissionError("fixture read denial")
        return original(path)
    monkeypatch.setattr(scanner.os, "scandir", failure)
    result = scan(root)
    assert result.status == "incomplete" and result.size == 0
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.save(result)
    saved = store.load(str(root))
    store.close()
    model = FolderModel()
    model.set_result(saved)
    rows = {folder.path: index for index, folder in enumerate(model.folders)}
    assert model.data(model.index(rows[str(denied)], 1)) == "—"
    assert model.data(model.index(rows[str(empty)], 1)) == "0 B"
    output = tmp_path / "report.csv"
    export_csv(saved, output)
    with output.open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.reader(stream))
    denied_row = next(row for row in records[1:] if row[0] == str(denied))
    empty_row = next(row for row in records[1:] if row[0] == str(empty))
    assert denied_row[1] == "0" and denied_row[5:] == ["incomplete", "미확인"]
    assert empty_row[5:] == ["complete", "읽은 범위 완료"]
    export_json(saved, tmp_path / "report.json")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == 2 and report["folder_coverage"][str(denied)] == "incomplete"
    assert report["analysis"]["size"] == 0


def test_window_summary_and_selection_do_not_present_unknown_as_zero(tmp_path, wait_for_history):
    from dev_storage_manager.ui.main_window import Window
    app = QApplication.instance() or QApplication([])
    root = str(tmp_path / "fixture")
    result = Result(root, status="incomplete", folders=[Folder(root)], issues=[Issue(root, "fixture denial", True)])
    window = Window(Store(tmp_path / "data"))
    window.display(result)
    assert "전체 크기/파일 수 미확인" in window.summary.text()
    assert "0 B" not in window.summary.text()
    assert window.metric_values[0].text() == "미확인"
    assert window.metric_values[1].text() == "미확인"
    window.folders.selectRow(0)
    assert "전체 크기와 파일 수를 확인하지 못했습니다" in window.folder_selection.text()
    wait_for_history(window, app)
    window.close()
