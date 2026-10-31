from dev_storage_manager.i18n import tr

LABELS = {"complete": tr("읽은 범위 완료"), "excluded": tr("일부 제외"),
          "incomplete": tr("읽기 실패 · 불완전"), "cancelled": tr("취소 · 부분 결과"), "unknown": tr("범위 미확인")}


def coverage_note(state):
    if state == "complete":
        return tr("분석 시점에 이 폴더의 읽은 범위에서 확인한 논리적 합계입니다. 행끼리 더하면 하위를 중복 계산합니다.")
    if state == "excluded":
        return tr("보호·링크·사용자 제외 등으로 읽지 않은 항목이 있습니다. 표시 값은 확인분이며 제외한 내용의 크기/파일 수는 포함하지 않습니다.")
    return tr("읽기 실패·취소 등으로 전체 크기와 파일 수를 확인하지 못했습니다. 확인분이 0이어도 빈 폴더나 0바이트라고 확정할 수 없습니다. 오류·제외 범위를 확인하고 다시 분석하세요.")
