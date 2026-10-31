"""Package a separately verified build; never overwrites an existing deliverable."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import os
import subprocess
import tempfile
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    built = root / ("build/windows-" + version) / "DevStorageManager"
    output = root / "outputs" / ("DevStorageManager-" + version + "-preview")
    archive = output.parent / (output.name + ".zip")
    if output.exists() or archive.exists():
        raise RuntimeError("동일 이름의 배포 시험물이 이미 있습니다. 기존 파일을 덮어쓰지 않습니다.")
    if not (built / "DevStorageManager.exe").is_file():
        raise RuntimeError("먼저 Windows 빌드와 자체 시작 검사를 완료하세요.")
    # Verify the actual executable with no source checkout or venv in its cwd/PATH.
    with tempfile.TemporaryDirectory(prefix="package-check-", dir=root / "work") as temporary:
        report = Path(temporary) / "startup.json"
        environment = os.environ.copy()
        environment["PATH"] = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
        environment["QT_QPA_PLATFORM"] = "offscreen"
        for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(key, None)
        completed = subprocess.run([str(built / "DevStorageManager.exe"), "--self-test", str(report)],
                                   cwd=temporary, env=environment, timeout=30,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode or not report.exists():
            raise RuntimeError("배포 EXE 자체 시작 검사 실패")
        verification = json.loads(report.read_text(encoding="utf-8"))
        if not verification.get("passed") or verification.get("cleanup_enabled") is not False:
            raise RuntimeError("배포 EXE 검사 결과가 완료 조건과 다릅니다.")
        if verification.get("history_rows") != 1 or verification.get("history_item_status") != "cancelled":
            raise RuntimeError("배포 EXE의 비동기 이력 조회 검사 실패")
        if verification.get("review_rows") != 2 or verification.get("review_cleanup_enabled") is not False:
            raise RuntimeError("배포 EXE의 읽기 전용 후보 검토 검사 실패")
        if verification.get("cleanup_result_status") != "cancelled" or verification.get("cleanup_result_read_only") is not True:
            raise RuntimeError("배포 EXE의 정리 결과 표시 검사 실패")
        if verification.get("demo_candidates") != 1 or verification.get("demo_proof_verified") is not True:
            raise RuntimeError("배포 EXE의 시험 프로젝트 생성/분석/증거 검사 실패")
        if verification.get("partial_zero_displayed_as_unknown") is not True:
            raise RuntimeError("배포 EXE의 불완전 분석 표시 검사 실패")
        if verification.get("folder_query_verified") is not True:
            raise RuntimeError("배포 EXE의 비동기 폴더 검색·정렬 검사 실패")
        if verification.get("runtime", {}).get("app_version") != version or verification["runtime"].get("mode") != "frozen":
            raise RuntimeError("EXE의 실제 버전 또는 실행 방식이 패키징 대상과 다릅니다.")
        language_checks = {}
        expected = {"ko": "폴더 추가", "en": "Add folder", "ja": "フォルダーを追加", "zh_CN": "添加文件夹", "vi": "Thêm thư mục"}
        for language, label in expected.items():
            language_report = Path(temporary) / ("language-" + language + ".json")
            checked = subprocess.run([str(built / "DevStorageManager.exe"), "--self-test-language", language, str(language_report)],
                                     cwd=temporary, env=environment, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            if checked.returncode or not language_report.is_file():
                raise RuntimeError("배포 EXE 언어 시작 검사 실패: " + language)
            data = json.loads(language_report.read_text(encoding="utf-8"))
            if not data.get("passed") or data.get("language") != language or data.get("add_folder_label") != label:
                raise RuntimeError("배포 EXE의 실제 표시 언어가 다릅니다: " + language)
            if data.get("cleanup_enabled") is not False or data.get("qualified_kinds") != []:
                raise RuntimeError("언어 검사 중 정리 실행이 활성화되었습니다.")
            if data.get("runtime", {}).get("mode") != "frozen" or data["runtime"].get("app_version") != version:
                raise RuntimeError("언어 검사 실행 방식 또는 버전이 다릅니다.")
            if language != "ko" and data.get("english_fallback_sample") != "Recycling failed/cancelled or outcome unconfirmed":
                raise RuntimeError("영어 대체 표시 검사 실패: " + language)
            language_checks[language] = data
    shutil.copytree(built, output)
    (output / "STARTUP-CHECK.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    (output / "LANGUAGE-CHECKS.json").write_text(json.dumps(language_checks, indent=2, ensure_ascii=False), encoding="utf-8")
    for name in ["QUICKSTART.md", "SUPPORT.md", "PROGRESS.md", "RECYCLE_VALIDATION.md", "DEPLOYMENT.md", "PERFORMANCE.md", "UI_DESIGN.md", "USER_VALIDATION.md", "VALIDATION.md", "RELEASE_AUDIT.md", "USER_GUIDE.md", "LOCALIZATION.md"]:
        shutil.copy2(root / "docs" / name, output / name)
    validation = root / "docs" / ("VALIDATION_" + version.replace(".", "") + ".md")
    if validation.is_file():
        shutil.copy2(validation, output / validation.name)
    shutil.copytree(root / "docs/third-party", output / "third-party")
    files = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in output.rglob("*") if p.is_file()}
    (output / "SHA256.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in output.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(output.parent))
    print(archive)


if __name__ == "__main__":
    main()
