"""Lexical Windows path normalization without resolving links."""
import os
from pathlib import Path
from dev_storage_manager.i18n import tr


def normalized(path) -> Path:
    value = os.path.abspath(os.fspath(path))
    if os.name == "nt":
        if value.lower().startswith("\\\\?\\unc\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\") and len(value) >= 7 and value[5:7] == ":\\":
            value = value[4:]
        elif value.startswith(("\\\\?\\", "\\\\.\\")):
            raise ValueError(tr("장치 네임스페이스는 프로젝트 경로로 사용할 수 없습니다."))
    return Path(value)


def native(path) -> str:
    value = str(path)
    if os.name == "nt" and len(value) >= 248 and not value.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return value
