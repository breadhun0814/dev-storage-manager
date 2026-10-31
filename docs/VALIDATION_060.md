# 0.6.0 확인 범위

- 전체 pytest: 80 passed, 3 skipped (`work/pytest-060-release`). 이전 원본 보호/변경 검증/취소/비선택/정리 제한 검사를 유지했다.
- 새 검사는 링크 실패 후 생성한 캐시만 진단하는지, 캐시 이동 테스트 대역이 통과해도 링크 실패가 실행을 차단하는지, 사전 취소 시 Shell/휴지통을 호출하지 않는지 확인한다.
- 성공으로 저장된 기록과 손상/초과 크기 JSON으로 이번 세션의 정리가 활성화되지 않는지 확인했다.
- 실제 에이전트 환경 점검: boundary failed / protection passed / recycle failed / preservation passed. 실패는 mklink 접근 거부 및 PreDelete recycle 플래그 부재(0x202)로 각각 기록했다. 원본 보존 확인. 정상 Windows 휴지통 이동·복원은 아직 미검증이다.
- Qt offscreen으로 실제 네 단계 결과를 표시한 창을 확인했다. 모든 실물 모니터/DPI/깨끗한 Windows 검증을 의미하지 않는다.
- GitHub에 올리지 않았다.
