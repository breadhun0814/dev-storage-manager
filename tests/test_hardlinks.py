import os
import py_compile
import pytest
from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.cleanup.service import prepare


def test_hardlink_logical_sizes_and_cleanup_refusal(tmp_path):
    source = tmp_path / "main.py"
    source.write_bytes(b"owned_fixture = 42\n")
    py_compile.compile(str(source), doraise=True)
    cache = next((tmp_path / "__pycache__").iterdir())
    original = cache.read_bytes()
    alias = tmp_path / "second-path.pyc"
    try:
        os.link(cache, alias)
    except OSError as exc:
        pytest.skip("실행 환경이 임시 하드링크 생성을 거부함: " + str(exc))
    result = scan(tmp_path)
    assert result.status == "complete"
    assert result.files == 3
    assert result.size == len(b"owned_fixture = 42\n") + 2 * len(original)
    with pytest.raises(ValueError, match="하드링크"):
        prepare(result, result.candidates[0])
    assert cache.read_bytes() == alias.read_bytes() == original
    assert source.read_bytes() == b"owned_fixture = 42\n"
