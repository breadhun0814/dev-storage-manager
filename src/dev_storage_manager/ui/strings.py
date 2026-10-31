from dev_storage_manager.i18n import tr
TITLE = tr('개발 저장공간 관리자')
STATUS = {"new": tr('미분석'), "running": tr('분석 중'), "complete": tr('탐색 완료 (제외 항목 별도)'),
          "incomplete": tr('읽기 오류 · 불완전'), "cancelled": tr('취소 · 부분 결과'), "failed": tr('분석 실패'),
          "interrupted": tr('앱 종료로 중단 · 재분석 필요'), "needs-analysis": tr('정리 시도 후 재분석 필요')}
NOTICE = tr('단위: 1 KB = 1,024 B. 논리적 크기는 실제 디스크 사용량과 다를 수 있습니다. 제외 경로는 집계하지 않으며 분석은 실시간 스냅샷이 아닙니다.')
