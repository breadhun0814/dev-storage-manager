from pathlib import Path

import pytest

from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.persistence.store import Store


def put(root, relative, content=b""):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_names_alone_are_not_candidates(tmp_path):
    for name in ("__pycache__", ".pytest_cache", "node_modules", "target", "build", ".venv"):
        put(tmp_path, name + "/personal.txt", b"keep")
    assert scan(tmp_path).candidates == []


def test_python_sources_and_environment(tmp_path):
    put(tmp_path, "pyproject.toml")
    put(tmp_path, "src/main.py")
    put(tmp_path, "src/__pycache__/main.cpython-312.pyc", b"cache")
    put(tmp_path, ".venv/pyvenv.cfg", b"home = C:/Python312")
    put(tmp_path, ".pytest_cache/CACHEDIR.TAG")
    put(tmp_path, ".pytest_cache/README.md")
    put(tmp_path, ".pytest_cache/.gitignore")
    result = scan(tmp_path)
    assert {c.kind for c in result.candidates} == {"python-cache", "python-environment", "pytest-cache"}
    assert all(not c.cleanup_supported for c in result.candidates)
    assert result.projects[0].kind == "Python"
    assert result.size == sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())


def test_node_lock_and_no_nested_candidates(tmp_path):
    put(tmp_path, "package.json")
    put(tmp_path, "node_modules/package/package.json")
    assert not scan(tmp_path).candidates
    put(tmp_path, "package-lock.json")
    put(tmp_path, "node_modules/package/lib.py")
    put(tmp_path, "node_modules/package/__pycache__/lib.cpython-312.pyc")
    result = scan(tmp_path)
    assert [c.kind for c in result.candidates] == ["node-dependencies"]


def test_java_build_direct_parent_only(tmp_path):
    put(tmp_path, "maven/pom.xml")
    put(tmp_path, "maven/target/app.jar", b"jar")
    put(tmp_path, "gradle/build.gradle.kts")
    put(tmp_path, "gradle/build/app.jar", b"jar")
    put(tmp_path, "maven/source/target/personal", b"keep")
    assert {c.kind for c in scan(tmp_path).candidates} == {"maven-build", "gradle-build"}


def test_exclusions_persist_and_old_result_compatibility(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    put(root, "pyproject.toml")
    put(root, "excluded/src.py", b"keep")
    put(root, "main.py", b"123")
    result = scan(root, exclusions=["excluded"])
    assert result.size == 3
    assert result.exclusions == ["excluded"]
    assert any(i.reason == "사용자 제외 목록" for i in result.issues)
    store = Store(tmp_path / "data")
    store.add(str(root))
    store.set_exclusions(str(root), ["excluded"])
    store.save(result)
    assert store.load(str(root)).projects == result.projects
    assert store.exclusions(str(root)) == ["excluded"]
    # v0.1 JSON had neither new collections nor folder category.
    store.db.execute("UPDATE projects SET result=?", ('{"root":"old","folders":[{"path":"old","size":1,"files":1}],"issues":[],"size":1,"files":1}',))
    assert store.load(str(root)).folders[0].category == "unclassified"
    store.close()


@pytest.mark.parametrize("value", ["../outside", "C:\\Windows", "C:relative", ".", ""])
def test_exclusion_boundary_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        scan(tmp_path, exclusions=[value])
