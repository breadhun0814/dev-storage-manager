"""All three metadata passes must describe the same included entries."""
import py_compile
from pathlib import Path
import pytest

from dev_storage_manager.cleanup.service import prepare
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.platform.path_safety import normalized


@pytest.mark.parametrize("duplicate_known_file", [False, True])
def test_omitted_personal_file_cannot_be_approved_between_matching_scans(tmp_path, monkeypatch, duplicate_known_file):
    from dev_storage_manager.cleanup import review
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_bytes(b'[project]\nname="fixture"\n')
    source = root / "module.py"
    source.write_bytes(b"value = 42\n")
    py_compile.compile(str(source), doraise=True)
    cache = root / "__pycache__"
    pyc = next(cache.iterdir())
    personal = cache / "personal.txt"
    personal.write_bytes(b"p" * pyc.stat().st_size)
    before = personal.read_bytes()
    result = scan(root)
    candidate = next(c for c in result.candidates if c.kind == "python-cache")
    original = review.os.scandir
    passes = []
    class Omitted:
        def __init__(self, iterator):
            self.iterator = iterator
        def __enter__(self):
            known = [entry for entry in self.iterator if entry.name != "personal.txt"]
            return iter(known * (2 if duplicate_known_file else 1))
        def __exit__(self, *args):
            self.iterator.close()
    def inconsistent(path):
        iterator = original(path)
        if normalized(path) == cache:
            passes.append(True)
            if len(passes) == 2:
                return Omitted(iterator)
        return iterator
    monkeypatch.setattr(review.os, "scandir", inconsistent)
    with pytest.raises(ValueError, match="포함 목록"):
        prepare(result, candidate)
    assert len(passes) >= 2
    assert personal.read_bytes() == before and pyc.is_file()
