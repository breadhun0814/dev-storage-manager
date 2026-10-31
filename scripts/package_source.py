"""Archive only application source, tests and documentation, not user data."""
from pathlib import Path
import tomllib
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    output = root / "outputs" / ("dev-storage-manager-" + version + "-source.zip")
    paths = []
    for directory in ("src", "tests", "docs", "scripts", ".github"):
        for path in (root / directory).rglob("*"):
            if not path.is_file() or any(part in {"__pycache__", ".pytest_cache"} or part.endswith(".egg-info") for part in path.relative_to(root).parts):
                continue
            if path.suffix in {".pyc", ".sqlite3", ".log"}:
                continue
            paths.append(path)
    paths.extend(p for p in root.iterdir() if p.is_file() and
                 (p.suffix in {".toml", ".spec"} or p.name.startswith("requirements") or
                  p.name in {"app.py", "README.md", ".gitignore", ".gitattributes"}))
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            archive.write(path, path.relative_to(root))
    print(output)


if __name__ == "__main__":
    main()
