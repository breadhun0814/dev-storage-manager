import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dev_storage_manager import i18n
from dev_storage_manager.persistence.store import Store


@pytest.fixture(autouse=True)
def reset_language():
    yield
    i18n.set_language("ko")


def test_english_covers_every_literal_and_all_catalog_placeholders_match():
    root = Path(i18n.__file__).parent
    messages = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr" and node.args:
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    messages.add(node.args[0].value)
    english = i18n.catalog("en")
    assert not messages - english.keys()
    assert all(not any("가" <= c <= "힣" for c in value) for value in english.values())
    for language in ("ja", "zh_CN", "vi"):
        translated = i18n.catalog(language)
        assert translated and not translated.keys() - english.keys()


@pytest.mark.parametrize("language", ["en", "ja", "zh_CN", "vi"])
def test_missing_entry_falls_back_to_english_and_preserves_formatting(language):
    i18n.set_language(language)
    assert i18n.tr("휴지통 작업 실패/취소 또는 결과 미확정") == "Recycling failed/cancelled or outcome unconfirmed"
    source = "휴지통 이동으로 확인되지 않은 작업 차단: flags={p0:#x}, path={p1}, expected={p2}"
    value = i18n.tr(source).format(p0=0x202, p1="한국어 日本語 Tiếng Việt 中文", p2="outside")
    assert "0x202" in value and "한국어 日本語 Tiếng Việt 中文" in value


def test_missing_target_catalog_uses_english_and_unknown_language_is_rejected(monkeypatch):
    original = i18n.catalog
    def missing(language):
        if language == "ja":
            raise FileNotFoundError
        return original(language)
    monkeypatch.setattr(i18n, "catalog", missing)
    i18n.set_language("ja")
    assert i18n.tr("폴더 추가") == "Add folder"
    with pytest.raises(ValueError):
        i18n.set_language("../en")
    assert i18n.get_language() == "ja"


def test_invalid_placeholder_does_not_replace_the_current_language(tmp_path, monkeypatch):
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "en.json").write_text(json.dumps({"경로 {path}": "Path {other}"}), encoding="utf-8")
    monkeypatch.setattr(i18n, "__file__", str(tmp_path / "i18n.py"))
    with pytest.raises(ValueError, match="placeholders"):
        i18n.set_language("en")
    assert i18n.get_language() == "ko"


def test_language_dialog_saves_for_restart_and_keeps_current_language(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from dev_storage_manager.ui.language_dialog import LanguageDialog
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "app-data")
    dialog = LanguageDialog(store)
    dialog.languages.setCurrentIndex(dialog.languages.findData("vi"))
    monkeypatch.setattr(QMessageBox, "information", lambda *_: None)
    dialog.save()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert store.language() == "vi" and i18n.get_language() == "ko"
    store.close()


def test_language_dialog_save_failure_does_not_accept(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from dev_storage_manager.ui.language_dialog import LanguageDialog
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "app-data")
    dialog = LanguageDialog(store)
    dialog.languages.setCurrentIndex(dialog.languages.findData("ja"))
    def fail(_):
        raise OSError("owned test write failure")
    monkeypatch.setattr(store, "set_language", fail)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    dialog.save()
    assert warnings and dialog.result() != dialog.DialogCode.Accepted
    assert store.language() == "ko" and i18n.get_language() == "ko"
    dialog.close()
    store.close()


def test_saved_language_survives_restart_and_invalid_setting_is_not_applied(tmp_path):
    store = Store(tmp_path / "app-data")
    assert store.language() == "ko"
    store.set_language("vi")
    store.close()
    store = Store(tmp_path / "app-data")
    assert store.language() == "vi"
    with pytest.raises(ValueError):
        store.set_language("../other")
    assert store.language() == "vi"
    store.db.execute("UPDATE app_settings SET value='invalid'")
    store.db.commit()
    assert store.language() == "ko"
    store.close()


@pytest.mark.parametrize("language,label", [
    ("ko", "폴더 추가"), ("en", "Add folder"), ("ja", "フォルダーを追加"),
    ("zh_CN", "添加文件夹"), ("vi", "Thêm thư mục")])
def test_each_language_in_fresh_ui_process_uses_real_owned_analysis(tmp_path, language, label):
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "startup.json"
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    completed = subprocess.run([sys.executable, str(root / "scripts/run.pyw"), "--self-test-language", language, str(report)],
                               cwd=tmp_path, env=environment, capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["passed"] and result["language"] == language
    assert result["add_folder_label"] == label
    assert result["analysis_status"] == "complete" and result["files"] == 2
    assert result["demo_proof_verified"] and result["cleanup_enabled"] is False
    assert result["qualified_kinds"] == []
