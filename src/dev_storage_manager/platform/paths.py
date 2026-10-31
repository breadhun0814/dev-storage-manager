from dev_storage_manager.i18n import tr
import os
import sys
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError(tr('LOCALAPPDATA가 없어 사용자 데이터 위치를 결정할 수 없습니다.'))
    if not Path(base).is_absolute():
        raise RuntimeError(tr("LOCALAPPDATA는 절대 경로여야 합니다. 프로젝트 폴더에 앱 데이터를 쓰지 않도록 시작을 중단합니다."))
    return Path(base) / "DevStorageManager"


def protected_paths() -> list[Path]:
    paths = [data_dir(), Path(sys.prefix), Path(sys.executable).parent,
             Path(__file__).absolute().parents[1]]
    for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        if os.environ.get(name):
            paths.append(Path(os.environ[name]))
    return list(dict.fromkeys(paths + [path.resolve(strict=False) for path in paths]))
