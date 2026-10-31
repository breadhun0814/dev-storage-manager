import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Event
import pytest
from dev_storage_manager.cleanup.pytest_fixture import create_fixture, check_fixture
from dev_storage_manager.cleanup.policy import cache_proof
from dev_storage_manager.cleanup.review import inspect
from dev_storage_manager.cleanup.service import prepare, execute
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.platform.recycle import Receipt
from dev_storage_manager.scanning.scanner import scan


def pytest_review(root):
    result = scan(root)
    candidate = next(c for c in result.candidates if c.kind == "pytest-cache")
    return result, candidate, inspect(result, candidate, require_supported=False)


def test_owned_pytest_default_metadata_has_strict_proof(tmp_path):
    create_fixture(tmp_path / "project")
    _, _, review = pytest_review(tmp_path / "project")
    assert not review.blocked and len(cache_proof(review)) == 6


@pytest.mark.parametrize("relative, value", [
    ("v/cache/nodeids", b'[123]'),
    ("v/cache/nodeids", b'[NaN]'),
    ("v/cache/lastfailed", b'{"test.py":false}'),
    ("v/cache/lastfailed", b'{"test.py":true,"test.py":true}'),
    ("v/cache/stepwise", b'[]'),
    ("v/cache/stepwise", b'{"last_failed":null,"last_test_count":true,"last_cache_date_str":"2026-10-31"}'),
    ("v/cache/stepwise", b'{"last_failed":null,"last_test_count":2,"last_cache_date_str":"not a date"}'),
    ("v/cache/private", b'{"user":"preserve"}'),
    ("README.md", b'user notes')])
def test_modified_or_unrecognized_pytest_data_is_not_executable(tmp_path, relative, value):
    root = tmp_path / "project"
    create_fixture(root)
    (root / ".pytest_cache" / relative).write_bytes(value)
    _, _, review = pytest_review(root)
    with pytest.raises(ValueError):
        cache_proof(review)
    assert (root / ".pytest_cache" / relative).read_bytes() == value


def test_real_pinned_pytest_generated_cache_is_supported_without_running_user_code(tmp_path):
    # Execute this owned, inert fixture only, in its own config/plugin boundary.
    root = tmp_path / "owned-tests"
    root.mkdir()
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "pyproject.toml").write_bytes(b"")
    (root / "test_owned.py").write_text("def test_owned():\n    assert 1 == 1\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
        environment.pop(key, None)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--sw", "-c", str(root / "pytest.ini"),
                             "--confcutdir", str(root), str(root / "test_owned.py")],
                            cwd=root, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    _, _, review = pytest_review(root)
    assert not review.blocked and "v/cache/stepwise" in cache_proof(review)


def test_pytest_plan_revalidation_blocks_changed_data_and_keeps_sources(tmp_path):
    root = tmp_path / "project"
    create_fixture(root)
    result, candidate, _ = pytest_review(root)
    plan = prepare(result, candidate)
    (root / ".pytest_cache/v/cache/nodeids").write_bytes(b'["changed test"]')
    seen = []
    class Backend:
        def move(self, *_):
            seen.append(True)
            raise AssertionError("Changed data must not reach backend")
    journal = Journal(tmp_path / "journal")
    execute([plan], journal, Backend())
    assert not seen and journal.history()[0][3] == "failed"
    assert (root / "test_owned.py").is_file()
    journal.close()


def test_pytest_runtime_probe_moves_only_owned_cache_with_protocol_double(tmp_path):
    class Backend:
        def move(self, path, validate):
            validate()
            assert path == tmp_path / "pytest-project/.pytest_cache"
            target = path.with_name("fake-bin")
            path.rename(target)
            return Receipt(str(path), str(target))
    check_fixture(tmp_path, Backend(), Event())
    assert (tmp_path / "pytest-project/test_owned.py").is_file()
    assert (tmp_path / "pytest-project/fake-bin/CACHEDIR.TAG").is_file()


def test_content_proof_honors_cancellation_during_reads(tmp_path, monkeypatch):
    from dev_storage_manager.cleanup import policy
    root = tmp_path / "project"
    create_fixture(root)
    _, _, review = pytest_review(root)
    cancel = Event()
    checked = []
    original = policy.read_checked
    def cancel_after_read(path, *args):
        data = original(path, *args)
        checked.append(path)
        cancel.set()
        return data
    monkeypatch.setattr(policy, "read_checked", cancel_after_read)
    with pytest.raises(ValueError, match="취소"):
        policy.cache_proof(review, cancel)
    assert len(checked) == 1 and (root / ".pytest_cache").is_dir()
