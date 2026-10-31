import os
import subprocess
from types import SimpleNamespace
import pytest
from dev_storage_manager.cleanup.capability import qualify

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows 명령 전달 시험")


def test_owned_paths_are_separate_arguments_and_failure_reason_is_preserved(tmp_path, monkeypatch):
    calls = []
    def denied(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(returncode=5, stderr=b"Access is denied.", stdout=b"")
    monkeypatch.setattr(subprocess, "run", denied)
    result = qualify(tmp_path / "한글 공백 시험")
    assert not result.ready
    command = calls[0]
    assert command[:5] == ["cmd.exe", "/d", "/c", "mklink", "/J"]
    assert len(command) == 7
    assert all('"' not in argument for argument in command)
    assert "한글 공백 시험" in command[5]
    assert "Access is denied." in result.reason and "5" in result.reason
