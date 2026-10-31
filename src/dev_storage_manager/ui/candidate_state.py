"""Explain absent results without mistaking partial scans for a clean project."""
from dev_storage_manager.i18n import tr


def empty_candidate_message(result):
    if result is None:
        return tr("아직 분석 결과가 없습니다. 위에서 프로젝트를 선택하고 '선택 프로젝트 분석'을 누르세요. 분석이 끝나면 이곳에 정리 후보가 표시됩니다.")
    if result.status != "complete":
        return tr("분석이 완료되지 않아 현재 확인된 정리 후보가 없습니다. 후보가 없다고 확정할 수 없습니다. '오류·제외 범위'를 확인하고 다시 분석하세요.")
    if result.issues or result.exclusions:
        return tr("이번에 읽은 범위에서는 정리 후보를 찾지 못했습니다. 제외하거나 읽지 않은 경로는 이 결과에 포함되지 않습니다. '오류·제외 범위'와 제외 목록을 확인하세요.")
    if result.files == 0:
        return tr("분석한 폴더에서 파일을 찾지 못했습니다. 선택한 프로젝트 경로를 확인하세요. 현재 선택하거나 정리할 항목은 없습니다.")
    return tr("분석 완료 · 현재 규칙으로 확인된 정리 후보가 없습니다. 선택하거나 지울 항목이 없는 상태입니다. '폴더별 용량'과 '큰 파일'에서 공간을 많이 차지하는 항목을 확인하세요.\n현재 정리는 유형별 환경 시험과 내용 검증을 통과한 Python 실행 캐시·pytest 테스트 캐시를 지원합니다. 캐시 폴더를 직접 만들거나 찾을 필요는 없습니다.")
