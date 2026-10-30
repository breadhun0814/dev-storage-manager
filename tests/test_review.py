from threading import Event

from dev_storage_manager.cleanup.review import inspect, deduplicate_paths
from dev_storage_manager.scanning.scanner import scan


def fixture(root):
    (root / "main.py").write_bytes(b"source")
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "main.cpython-312.pyc").write_bytes(b"cache")
    return scan(root)


def test_review_includes_files_and_stays_disabled(tmp_path):
    result = fixture(tmp_path)
    review = inspect(result, result.candidates[0])
    assert len(review.files) == 1 and review.files[0].size == 5
    assert len(review.blocked) == 1 and "아직 검증" in review.blocked[0]


def test_changed_cache_requires_rescan(tmp_path):
    result = fixture(tmp_path)
    (tmp_path / "__pycache__" / "added.txt").write_bytes(b"user file")
    review = inspect(result, result.candidates[0])
    assert any("변경" in reason for reason in review.blocked)


def test_replaced_same_size_file_detected(tmp_path):
    result = fixture(tmp_path)
    file = tmp_path / "__pycache__" / "main.cpython-312.pyc"
    file.unlink()
    file.write_bytes(b"other")
    assert any("변경" in s for s in inspect(result, result.candidates[0]).blocked)


def test_cancelled_analysis_is_blocked(tmp_path):
    result = fixture(tmp_path)
    result.status = "cancelled"
    event = Event()
    event.set()
    review = inspect(result, result.candidates[0], event)
    assert any("취소" in s for s in review.blocked)


def test_parent_child_deduplication(tmp_path):
    root = str(tmp_path)
    assert deduplicate_paths([str(tmp_path / "child"), root, root]) == [root]
