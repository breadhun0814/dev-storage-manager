"""Local catalogs: selected language, then English; Korean remains the default."""
import json
from pathlib import Path
from string import Formatter
from collections import Counter

LANGUAGES = {"ko": "한국어", "en": "English", "ja": "日本語", "zh_CN": "简体中文", "vi": "Tiếng Việt"}
_language = "ko"
_english = {}
_selected = {}


def fields(message):
    return Counter((name, spec, conversion) for _, name, spec, conversion in Formatter().parse(message)
                   if name is not None)


def catalog(language):
    if language not in LANGUAGES or language == "ko":
        return {}
    value = json.loads((Path(__file__).parent / "locales" / (language + ".json")).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid translation catalog")
    for source, translated in value.items():
        if not isinstance(source, str) or not isinstance(translated, str) or not translated.strip():
            raise ValueError("Invalid translation entry")
        if fields(source) != fields(translated):
            raise ValueError("Translation placeholders differ: " + source)
    return value


def set_language(language: str = "ko"):
    global _language, _english, _selected
    if language not in LANGUAGES:
        raise ValueError("Unsupported language: " + str(language))
    # Load and validate before publishing state; failed loading changes nothing.
    english = catalog("en") if language != "ko" else {}
    try:
        selected = catalog(language) if language not in {"ko", "en"} else english
    except FileNotFoundError:
        selected = {}
    _language, _english, _selected = language, english, selected


def get_language():
    return _language


def tr(message: str) -> str:
    return message if _language == "ko" else _selected.get(message, _english.get(message, message))
