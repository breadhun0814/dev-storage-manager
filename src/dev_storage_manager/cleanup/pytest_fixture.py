"""Build and recycle owned diagnostic metadata, never execute a test suite."""
import json
from pathlib import Path
from datetime import datetime, timezone
from dev_storage_manager.cleanup.policy import PYTEST_README, PYTEST_TAG_CONTENT
from dev_storage_manager.cleanup.service import prepare, execute
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.scanning.scanner import scan


def create_fixture(project: Path):
    project.mkdir()
    (project / "pyproject.toml").write_bytes(b'[project]\nname="owned-cache-fixture"\n')
    (project / "test_owned.py").write_bytes(b"# Generated diagnostic source; never executed\n")
    cache = project / ".pytest_cache"
    (cache / "v/cache").mkdir(parents=True)
    (cache / "README.md").write_bytes(PYTEST_README)
    (cache / "CACHEDIR.TAG").write_bytes(PYTEST_TAG_CONTENT)
    (cache / ".gitignore").write_bytes(b"# Created by pytest automatically.\n*\n")
    values = {"nodeids": ["test_owned.py::test_fixture"], "lastfailed": {"test_owned.py::test_fixture": True},
              "stepwise": {"last_failed": None, "last_test_count": 1, "last_cache_date_str": datetime.now(timezone.utc).isoformat()}}
    for name, value in values.items():
        (cache / "v/cache" / name).write_text(json.dumps(value), encoding="utf-8")


def check_fixture(fixture: Path, backend, cancel):
    project = fixture / "pytest-project"
    create_fixture(project)
    originals = {path: path.read_bytes() for path in (project / "pyproject.toml", project / "test_owned.py")}
    result = scan(project, cancel)
    candidate = next(c for c in result.candidates if c.kind == "pytest-cache")
    plan = prepare(result, candidate, cancel)
    journal = Journal(fixture / "pytest-journal")
    failure = None
    try:
        execute([plan], journal, backend, cancel)
        rows = journal.history()
        if not rows or rows[0][3] != "succeeded":
            failure = rows[0][4] if rows else "Missing fixture journal result"
    finally:
        journal.close()
    if any(path.read_bytes() != data for path, data in originals.items()):
        raise ValueError("Generated pytest sources were changed")
    if failure:
        raise ValueError(failure)
