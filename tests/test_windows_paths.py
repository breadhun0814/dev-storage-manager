import os
from pathlib import Path
import pytest

from dev_storage_manager.platform.path_safety import normalized, native
from dev_storage_manager.scanning.scanner import scan

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows 경로 시험")


def test_namespace_spelling_cannot_bypass_protection(tmp_path):
    folder = tmp_path / "protected"
    folder.mkdir()
    extended = "\\\\?\\" + str(folder)
    assert normalized(extended) == folder
    with pytest.raises(ValueError, match="보호"):
        scan(Path(extended), protected=[folder])
    with pytest.raises(ValueError):
        normalized("\\\\.\\C:\\")
    with pytest.raises(ValueError):
        normalized("\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1")


def test_long_path_analysis(tmp_path):
    long = tmp_path
    while len(str(long)) < 330:
        long = long / "한글 긴 경로 fixture"
    extended = Path("\\\\?\\" + str(long))
    extended.mkdir(parents=True)
    (extended / "source.txt").write_bytes(b"long fixture")
    result = scan(tmp_path)
    assert result.status == "complete", result.issues
    assert result.size == len(b"long fixture") and result.files == 1
    assert all(not f.path.startswith("\\\\?\\") for f in result.folders)


def test_long_cache_review_and_content_proof(tmp_path):
    import py_compile
    from dev_storage_manager.cleanup.service import prepare
    long = tmp_path
    while len(str(long)) < 330:
        long = long / "long-cache-fixture"
    extended = Path("\\\\?\\" + str(long))
    extended.mkdir(parents=True)
    source = extended / "main.py"
    source.write_bytes(b"long_fixture = 42\n")
    py_compile.compile(str(source), doraise=True)
    result = scan(tmp_path)
    assert result.status == "complete"
    assert len(result.candidates) == 1
    plan = prepare(result, result.candidates[0])
    assert len(plan.proof) == 1
    assert source.read_bytes() == b"long_fixture = 42\n"
