"""Minimal local diagnostics: no project paths or environment-variable dump."""
import platform
import sys
from PySide6 import __version__ as qt_python_version
from dev_storage_manager import __version__


def runtime_info() -> dict[str, str]:
    return {"app_version": __version__, "python_version": platform.python_version(),
            "pyside6_version": qt_python_version, "platform": platform.platform(),
            "mode": "frozen" if getattr(sys, "frozen", False) else "source"}
