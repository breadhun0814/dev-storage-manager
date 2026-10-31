from contextlib import contextmanager
from types import SimpleNamespace
import os
import stat
from dev_storage_manager.cleanup.pytest_fixture import create_fixture
from dev_storage_manager.cleanup.review import inspect
from dev_storage_manager.scanning.scanner import scan


def test_stale_directory_entry_times_do_not_hide_real_child_identity(tmp_path, monkeypatch):
    root = tmp_path / "project"
    create_fixture(root)
    original = os.scandir
    class Entry:
        def __init__(self, entry):
            self.entry = entry
        def __getattr__(self, name):
            return getattr(self.entry, name)
        def stat(self, **kwargs):
            info = self.entry.stat(**kwargs)
            if stat.S_ISDIR(info.st_mode):
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=getattr(info, "st_file_attributes", 0),
                                       st_mtime_ns=info.st_mtime_ns-1000000)
            return info
    @contextmanager
    def stale_directories(path):
        with original(path) as entries:
            yield (Entry(entry) for entry in entries)
    monkeypatch.setattr(os, "scandir", stale_directories)
    result = scan(root)
    monkeypatch.setattr(os, "scandir", original)
    review = inspect(result, result.candidates[0], require_supported=False)
    assert not review.blocked
    # Child directories remain in subtree signatures, so adding one still blocks.
    (root / ".pytest_cache/v/unknown").mkdir()
    changed = inspect(result, result.candidates[0], require_supported=False)
    assert changed.blocked
