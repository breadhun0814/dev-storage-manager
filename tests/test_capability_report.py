import json
from dev_storage_manager.cleanup import capability


def test_failed_qualification_retains_local_reason_without_enabling(tmp_path, monkeypatch):
    monkeypatch.setattr(capability, "_qualify", lambda *_: capability.Capability(False, "junction fixture denied", "owned-fixture"))
    result = capability.qualify(tmp_path / "appdata")
    saved = json.loads((tmp_path / "appdata/last-result.json").read_text(encoding="utf-8"))
    assert not result.ready and not saved["ready_in_that_session"]
    assert saved["reason"] == "junction fixture denied"
