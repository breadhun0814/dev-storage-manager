import os

import pytest

from dev_storage_manager.platform.guard import directory_guard


@pytest.mark.skipif(os.name != "nt", reason="Windows handle 시험")
def test_directory_rename_blocked_only_during_guard(tmp_path):
    folder = tmp_path / "한글 폴더"
    folder.mkdir()
    moved = tmp_path / "moved"
    with directory_guard(folder):
        with pytest.raises(OSError):
            folder.rename(moved)
    folder.rename(moved)
    assert moved.is_dir()


def test_guard_failure_does_not_hold_ancestor_handles(tmp_path):
    missing = tmp_path / "missing"
    if os.name != "nt":
        pytest.skip("Windows handle 실패 시험")
    with pytest.raises(OSError):
        with directory_guard(missing):
            pass
    moved = tmp_path.with_name(tmp_path.name + "-moved")
    tmp_path.rename(moved)
    moved.rename(tmp_path)
