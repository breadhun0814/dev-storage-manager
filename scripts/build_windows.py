"""Build with a restricted DLL search PATH, excluding unrelated host runtimes."""
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import ast
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="Replace this version's generated build only; never touches outputs")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    metadata = ast.parse((root / "src/dev_storage_manager/__init__.py").read_text(encoding="utf-8"))
    runtime_version = next(ast.literal_eval(node.value) for node in metadata.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    if runtime_version != version:
        raise RuntimeError("앱 표시 버전과 pyproject 버전이 다릅니다. 빌드를 중단합니다.")
    output = root / "build" / ("windows-" + version)
    build_root = (root / "build").resolve()
    if not output.resolve().is_relative_to(build_root):
        raise RuntimeError("빌드 출력 경계 확인 실패")
    bundle = output / "DevStorageManager"
    if output.resolve() != output.absolute() or bundle.resolve() != bundle.absolute():
        raise RuntimeError("링크로 연결된 빌드 출력은 덮어쓰지 않습니다.")
    if output.exists() and not args.rebuild:
        raise RuntimeError(f"{output}가 이미 있습니다. 기존 시험물을 덮어쓰지 않습니다.")
    temporary = root / "work" / "build-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
                                        Path(sys.base_prefix), windows / "System32", windows]))
    environment["PYTHONNOUSERSITE"] = "1"
    environment["TEMP"] = environment["TMP"] = str(temporary)
    environment["PYINSTALLER_CONFIG_DIR"] = str(root / "work" / "build-cache")
    return subprocess.call([sys.executable, "-m", "PyInstaller", *(["--noconfirm"] if args.rebuild else []), "--distpath", str(output),
                             "--workpath", str(root / "work" / ("windows-build-" + version)),
                             str(root / "dev-storage-manager.spec")], cwd=root, env=environment)


if __name__ == "__main__":
    sys.exit(main())
