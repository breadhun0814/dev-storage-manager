import json

import pytest

from dev_storage_manager.domain.comparison import compare
from dev_storage_manager.persistence.report import export_json, export_csv, export_files_csv
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.scanning.scanner import scan


def test_comparison_and_export(tmp_path):
    project = tmp_path / "프로젝트"
    project.mkdir()
    source = project / "main.py"
    source.write_bytes(b"1")
    store = Store(tmp_path / "data")
    store.add(str(project))
    before = scan(project)
    store.save(before)
    source.write_bytes(b"12345")
    after = scan(project)
    store.save(after)
    changes = compare(store.previous(str(project)), store.load(str(project)))
    assert changes[0].delta == 4
    report = tmp_path / "분석.json"
    export_json(after, report)
    assert json.loads(report.read_text(encoding="utf-8"))["analysis"]["size"] == 5
    export_csv(after, tmp_path / "분석.csv")
    assert "논리적 바이트" in (tmp_path / "분석.csv").read_text(encoding="utf-8-sig")
    with pytest.raises(FileExistsError):
        export_json(before, source)
    assert source.read_bytes() == b"12345"
    store.close()


def test_largest_file_csv_preserves_bytes_scope_and_existing_sources(tmp_path):
    import csv
    from dev_storage_manager.domain.models import Result, FileSummary
    result = Result("fixture", status="cancelled", files=600, file_sample_available=True,
                    largest_files=[FileSummary("=formula.csv", 1234)])
    target = tmp_path / "large-files.csv"
    export_files_csv(result, target)
    with target.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1] == ["'=formula.csv", "1234", "cancelled", "500", "600"]
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        export_files_csv(result, target)
    assert target.read_bytes() == before
    with pytest.raises(ValueError):
        export_files_csv(Result("legacy"), tmp_path / "must-not-create.csv")
    assert not (tmp_path / "must-not-create.csv").exists()


def test_partial_and_different_scope_not_comparable(tmp_path):
    before, after = scan(tmp_path), scan(tmp_path)
    after.status = "cancelled"
    with pytest.raises(ValueError):
        compare(before, after)
    after.status = "complete"
    after.exclusions = ["data"]
    with pytest.raises(ValueError):
        compare(before, after)
