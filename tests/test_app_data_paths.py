import pytest
from dev_storage_manager.platform.paths import data_dir


def test_relative_appdata_cannot_create_project_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", "relative-app-data")
    with pytest.raises(RuntimeError, match="절대 경로"):
        data_dir()
    assert list(tmp_path.iterdir()) == []


def test_absolute_user_data_path_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "owned user data"))
    assert data_dir() == tmp_path / "owned user data" / "DevStorageManager"
    assert list(tmp_path.iterdir()) == []
