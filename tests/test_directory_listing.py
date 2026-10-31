import os
from pathlib import Path
from threading import Event
from contextlib import contextmanager
from types import SimpleNamespace
import stat
import pytest
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.scanning import listing as module


def test_direct_listing_respects_boundaries_protection_and_readonly(tmp_path):
    root = tmp_path / "프로젝트"
    root.mkdir()
    for name in ("sub", ".git", "excluded", "runtime"):
        (root / name).mkdir()
        (root / name / "file.txt").write_bytes(b"owned fixture")
    (root / "한글 A[1].txt").write_bytes(b"contents")
    before = (root / "한글 A[1].txt").stat().st_mtime_ns
    result = scan(root, protected=[root / "runtime"], exclusions=["excluded"])
    listing = module.list_directory(result, root, protected=[root / "runtime"])
    assert listing.status == "complete"
    rows = {row.name: row for row in listing.entries}
    assert rows["sub"].navigable and rows["sub"].size is None
    assert rows["한글 A[1].txt"].size == 8
    assert all(rows[name].kind == "blocked" and rows[name].size is None for name in (".git", "excluded", "runtime"))
    for path in (tmp_path, root / ".git", root / "excluded", root / "runtime"):
        with pytest.raises(ValueError):
            module.list_directory(result, path, protected=[root / "runtime"])
    assert (root / "한글 A[1].txt").read_bytes() == b"contents"
    assert (root / "한글 A[1].txt").stat().st_mtime_ns == before
    (root / "new-folder").mkdir()
    fresh = module.list_directory(result, root, protected=[root / "runtime"])
    added = next(row for row in fresh.entries if row.name == "new-folder")
    assert not added.navigable and "다시 분석" in added.note


def test_current_exclusions_apply_to_live_listing(tmp_path):
    (tmp_path / "sub").mkdir()
    result = scan(tmp_path)
    with pytest.raises(ValueError):
        module.list_directory(result, tmp_path / "sub", exclusions=["sub"])
    with pytest.raises(ValueError):
        module.list_directory(result, tmp_path, exclusions=["../outside"])


def test_link_and_read_failure_are_visible_without_following(tmp_path, monkeypatch):
    for name in ("pretend-link", "denied.txt"):
        (tmp_path / name).write_bytes(b"owned")
    result = scan(tmp_path)
    original = os.scandir
    calls = []
    class Entry:
        def __init__(self, entry):
            self.path, self.name = entry.path, entry.name
        def stat(self, follow_symlinks):
            assert follow_symlinks is False
            if self.name == "pretend-link":
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
            raise PermissionError("owned fixture access denied")
    @contextmanager
    def entries(path):
        calls.append(path)
        with original(path) as children:
            yield (Entry(child) for child in children)
    monkeypatch.setattr(os, "scandir", entries)
    listing = module.list_directory(result, tmp_path)
    assert len(calls) == 1 and listing.status == "incomplete"
    rows = {row.name: row for row in listing.entries}
    assert rows["pretend-link"].kind == "link" and not rows["pretend-link"].navigable
    assert rows["denied.txt"].kind == "error" and rows["denied.txt"].size is None


def test_cancel_and_limit_never_claim_full_listing(tmp_path, monkeypatch):
    for n in range(6):
        (tmp_path / f"{n}.txt").write_bytes(b"owned")
    result = scan(tmp_path)
    monkeypatch.setattr(module, "MAX_DIRECTORY_ENTRIES", 3)
    listing = module.list_directory(result, tmp_path)
    assert listing.status == "limited" and listing.truncated and len(listing.entries) == 3
    cancel = Event()
    cancel.set()
    partial = module.list_directory(result, tmp_path, cancel)
    assert partial.status == "cancelled" and not partial.entries
