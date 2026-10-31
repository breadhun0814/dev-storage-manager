import py_compile

import pytest

from dev_storage_manager.cleanup.policy import cache_proof
from dev_storage_manager.cleanup.review import inspect
from dev_storage_manager.scanning.scanner import scan


def cache(root):
    source = root / "한글.py"
    source.write_text("value = 42\n", encoding="utf-8")
    # Compile a disposable fixture only; never execute its code.
    py_compile.compile(str(source), doraise=True)
    result = scan(root)
    return inspect(result, result.candidates[0])


def test_valid_python_cache_proof(tmp_path):
    review = cache(tmp_path)
    proof = cache_proof(review)
    assert len(proof) == 1 and len(next(iter(proof.values()))) == 64


def test_user_file_in_cache_is_blocked(tmp_path):
    cache(tmp_path)
    (tmp_path / "__pycache__" / "personal.txt").write_bytes(b"preserve")
    result = scan(tmp_path)
    with pytest.raises(ValueError, match="검증되지 않은"):
        cache_proof(inspect(result, result.candidates[0]))


def test_source_changed_after_compile_is_blocked(tmp_path):
    review = cache(tmp_path)
    (tmp_path / "한글.py").write_bytes(b"changed source content")
    with pytest.raises(ValueError, match="일치하지"):
        cache_proof(review)


def test_fake_pyc_header_is_blocked(tmp_path):
    review = cache(tmp_path)
    path = next((tmp_path / "__pycache__").iterdir())
    path.write_bytes(b"fake user data")
    with pytest.raises(ValueError, match="검증되지 않은"):
        cache_proof(review)


def test_pytest_proof_and_modified_marker_rejected(tmp_path):
    from dev_storage_manager.cleanup.policy import PYTEST_README, PYTEST_TAG_CONTENT
    (tmp_path / "pyproject.toml").write_bytes(b"")
    target = tmp_path / ".pytest_cache"
    (target / "v/cache").mkdir(parents=True)
    (target / "README.md").write_bytes(PYTEST_README)
    (target / "CACHEDIR.TAG").write_bytes(PYTEST_TAG_CONTENT)
    (target / ".gitignore").write_bytes(b"# Created by pytest automatically.\n*\n")
    (target / "v/cache/nodeids").write_bytes(b'["test_fixture.py::test_one"]')
    result = scan(tmp_path)
    assert len(cache_proof(inspect(result, result.candidates[0]))) == 4
    (target / "README.md").write_bytes(PYTEST_README + b"personal note\n")
    with pytest.raises(ValueError, match="README"):
        cache_proof(inspect(result, result.candidates[0]))


def test_timestamp_cache_plan_detects_same_size_source_edit_with_restored_time(tmp_path):
    import os
    from dev_storage_manager.cleanup.service import prepare, verify
    source = tmp_path / "source.py"
    source.write_bytes(b"value = 11\n")
    py_compile.compile(str(source), doraise=True)
    result = scan(tmp_path)
    plan = prepare(result, result.candidates[0])
    before = source.stat()
    source.write_bytes(b"value = 22\n")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ValueError, match="변경"):
        verify(plan)
    assert source.read_bytes() == b"value = 22\n"


def test_corresponding_source_hardlink_metadata_blocks_proof(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from dev_storage_manager.cleanup import policy
    from dev_storage_manager.platform.path_safety import normalized
    review = cache(tmp_path)
    source = tmp_path / "한글.py"
    original = policy.os.lstat
    def source_link_metadata(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if normalized(path) == source:
            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime", "st_mtime_ns", "st_ctime_ns", "st_file_attributes")
            return SimpleNamespace(**{field: getattr(info, field, 0) for field in fields}, st_nlink=2)
        return info
    monkeypatch.setattr(policy.os, "lstat", source_link_metadata)
    with pytest.raises(ValueError, match="하드링크"):
        cache_proof(review)
    assert source.read_text(encoding="utf-8") == "value = 42\n"
