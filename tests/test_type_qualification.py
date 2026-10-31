import pytest
from dev_storage_manager.cleanup.capability import Check, qualified_kinds


@pytest.mark.parametrize("boundary, python, pytest_status, expected", [
    ("passed", "passed", "failed", ("python-cache",)),
    ("passed", "failed", "passed", ("pytest-cache",)),
    ("passed", "passed", "passed", ("python-cache", "pytest-cache")),
    ("failed", "passed", "passed", ()),
    ("passed", "skipped", "failed", ())])
def test_each_cache_type_needs_core_and_its_own_probe(boundary, python, pytest_status, expected):
    checks = [Check(code, code, state, "fixture") for code, state in (
        ("boundary", boundary), ("protection", "passed"), ("preservation", "passed"),
        ("recycle", python), ("pytest-recycle", pytest_status))]
    assert qualified_kinds(checks) == expected
    assert qualified_kinds(checks + [Check("interrupted", "interrupted", "failed", "fixture")]) == ()
