from dev_storage_manager.i18n import tr
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dev_storage_manager.domain.models import Result
from dev_storage_manager.domain.coverage import folder_coverage


def export_json(result: Result, path: Path):
    coverage = folder_coverage(result)
    report = {"schema_version": 2, "exported_at": datetime.now(timezone.utc).isoformat(),
              "size_definition": tr('확인된 논리적 파일 크기. 불완전·취소·제외 범위의 전체 크기는 미확인이며 압축/하드링크 등으로 실제 디스크 사용량과 다를 수 있습니다.'),
              "folder_coverage": {folder.path: coverage.state(folder.path) for folder in result.folders},
              "analysis": asdict(result)}
    # Open in exclusive mode so reports cannot overwrite existing source files.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)


def export_csv(result: Result, path: Path):
    coverage = folder_coverage(result)
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([tr('폴더 (하위 포함)'), tr('확인된 논리적 바이트'), tr('확인된 파일 수'), tr('분류'), tr('전체 분석 상태'), tr('폴더 분석 범위'), tr('전체 크기 확인 여부')])
        for folder in result.folders:
            # Spreadsheet formula handling also covers imported/non-Windows results.
            display = "'" + folder.path if folder.path.startswith(("=", "+", "-", "@", "\t", "\r")) else folder.path
            state = coverage.state(folder.path)
            writer.writerow([display, folder.size, folder.files, folder.category, result.status, state, tr("미확인") if state != "complete" else tr("읽은 범위 완료")])


def export_files_csv(result: Result, path: Path):
    if not result.file_sample_available:
        raise ValueError(tr("이전 분석에는 큰 파일 정보가 없습니다. 다시 분석한 뒤 내보내세요."))
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([tr("큰 파일 전체 경로"), tr("논리적 바이트"), tr("분석 상태"), tr("보관 상한"), tr("전체 확인 파일 수")])
        for file in result.largest_files:
            display = "'" + file.path if file.path.startswith(("=", "+", "-", "@", "\t", "\r")) else file.path
            writer.writerow([display, file.size, result.status, result.file_sample_limit, result.files])
