import os
import sys
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA가 없어 사용자 데이터 위치를 결정할 수 없습니다.")
    return Path(base) / "DevStorageManager"


def protected_paths() -> list[Path]:
    paths = [data_dir(), Path(sys.prefix), Path(sys.executable).parent]
    for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        if os.environ.get(name):
            paths.append(Path(os.environ[name]))
    return paths
