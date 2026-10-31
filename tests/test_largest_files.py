import json
import os
from dataclasses import asdict
from threading import Event
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.main_window import Window


def test_largest_files_are_bounded_exact_and_respect_scan_exclusions(tmp_path):
    root = tmp_path / "프로젝트"
    root.mkdir()
    for number in range(520):
        (root / f"자료 {number}.bin").write_bytes(b"x" * number)
    for name in (".git", "excluded", "runtime"):
        (root / name).mkdir()
        (root / name / "protected.bin").write_bytes(b"private fixture" * 5000)
    original = (root / "자료 519.bin").stat().st_mtime_ns
    result = scan(root, protected=[root / "runtime"], exclusions=["excluded"])
    assert result.files == 520 and result.size == sum(range(520))
    assert result.file_sample_available and len(result.largest_files) == 500
    assert [f.size for f in result.largest_files] == list(range(519, 19, -1))
    assert all("protected.bin" not in file.path for file in result.largest_files)
    assert (root / "자료 519.bin").stat().st_mtime_ns == original
    assert (root / "자료 519.bin").read_bytes() == b"x" * 519


def test_partial_scan_marks_sample_partial_and_roundtrips(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for n in range(15):
        (root / f"{n}.txt").write_bytes(b"owned")
    cancel = Event()
    result = scan(root, cancel, lambda *_: cancel.set())
    assert result.status == "cancelled"
    assert result.file_sample_available and len(result.largest_files) == result.files
    store = Store(tmp_path / "appdata")
    store.add(str(root))
    store.save(result)
    loaded = store.load(str(root))
    assert loaded.largest_files == result.largest_files and loaded.file_sample_available
    legacy = asdict(result)
    for key in ("largest_files", "file_sample_available", "file_sample_limit"):
        legacy.pop(key)
    assert not Store.decode(json.dumps(legacy)).file_sample_available


def test_released_app_payload_compatibility_and_stale_sample_invalidation(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "file.bin").write_bytes(b"owned fixture")
    store = Store(tmp_path / "data")
    store.add(str(root))
    result = scan(root)
    store.save(result)
    payload = store.db.execute("SELECT result FROM projects WHERE path=?", (str(root),)).fetchone()[0]
    data = json.loads(payload)
    assert not {"largest_files", "file_sample_available", "file_sample_limit"} & data.keys()
    assert store.load(str(root)).file_sample_available
    store.db.execute("UPDATE file_samples SET result='broken' WHERE project=?", (str(root),))
    store.db.commit()
    assert store.load(str(root)).files == 1 and not store.load(str(root)).file_sample_available
    store.save(result)
    # Simulate an older app rewriting the snapshot with a new analysis result.
    data["started_at"] = "legacy-app-new-snapshot"
    store.db.execute("UPDATE projects SET result=? WHERE path=?", (json.dumps(data), str(root)))
    store.db.commit()
    loaded = store.load(str(root))
    assert not loaded.file_sample_available and not loaded.largest_files
    store.remove(str(root))
    assert store.db.execute("SELECT count(*) FROM file_samples").fetchone()[0] == 0


def test_file_view_search_size_sort_and_no_stale_selection(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "project"
    root.mkdir()
    (root / "한글 A[1].txt").write_bytes(b"x" * 100)
    (root / "B.txt").write_bytes(b"xx")
    store = Store(tmp_path / "data")
    window = Window(store)
    window.display(scan(root))
    window.candidate_files_button.click()
    assert window.tabs.currentWidget() is window.file_page
    assert window.file_proxy.index(0, 2).data(Qt.ItemDataRole.UserRole) == 100
    window.file_search.setText("A[1]")
    assert window.file_proxy.rowCount() == 1
    window.file_table.setCurrentIndex(window.file_proxy.index(0, 0))
    assert str(root / "한글 A[1].txt") in window.file_selection.text()
    assert "삭제 대상 선택이 아닙니다" in window.file_selection.text()
    window.open_result()
    assert window.file_proxy.rowCount() == 0
    window.close()
