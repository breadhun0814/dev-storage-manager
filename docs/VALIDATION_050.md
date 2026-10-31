# 0.5.0 검사와 남은 제한

- 사용자 피드백: 작은 창/이름 잘림, 바이트 숫자 가독성, 후보 선택 흐름, 정리 불가 원인.
- 핵심 검사: `work/pytest-050-release`에서 75 passed, 3 skipped. 800×600 창 유지, 긴 한국어 이름 원문 보존/경로, 메뉴로 목록 펼치기, 후보 선택 후 검토 활성화, 확인 체크만으로 환경 미검증 정리가 활성화되지 않음, 원본 보존을 검사했다.
- KB/MB/GB/TB 경계, 음수 변화, 정확한 바이트 툴팁, 원시 숫자 정렬을 확인했다.
- 임시 프로젝트의 실제 분석을 offscreen Qt 1040×760 및 800×600으로 렌더링해 결과와 선택 안내를 확인했다. 작은 화면은 스크롤을 지원한다. 모든 Windows DPI/실제 모니터에서의 검증은 아니다.
- 에이전트 실행 환경에서 환경 시험을 실제 수행했다. `work/qualification-050/last-result.json`: junction 생성이 코드 1/액세스 거부로 실패. 이 시도는 휴지통 단계에 도달하지 않았다. 사용자 일반 Windows 실행에서도 같은 원인이라고 단정하지 않는다.
- 콜백 flags/결과/영수증 유무가 실패 메시지에서 유지되도록 했다. 원본 보호/승인/플래그 확인을 완화하지 않았다.
- 남은 작업: 정상 Windows의 실제 휴지통/복원, 독립된 깨끗한 Windows 설치, 여러 DPI, 추가 정리 유형 검증. 현재 정식 완료 아님. GitHub 업로드 없음.

공식 계약 확인: [PreDeleteItem](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperationprogresssink-predeleteitem). 실패 HRESULT가 작업을 취소한다는 문서를 근거로 veto 보존 정책을 유지한다.
