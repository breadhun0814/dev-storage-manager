"""Korean source messages with optional gettext catalogs for future languages."""
import gettext
from pathlib import Path

_translator = gettext.NullTranslations()


def set_language(language: str = "ko"):
    global _translator
    _translator = gettext.translation("messages", localedir=Path(__file__).parent / "locales",
                                      languages=[language], fallback=True)


def tr(message: str) -> str:
    return _translator.gettext(message)
