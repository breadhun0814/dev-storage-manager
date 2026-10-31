# 0.6.1 휴지통 결과 오판 회귀 검사

사용자 제공 진단: boundary/protection/preservation 통과, recycle 실패. callback flags=0x282, result=0x270008, receipt=True. 개인 프로젝트를 재현에 사용하지 않았다.

Microsoft SDK 정의에서 COPYENGINE_S_DONT_PROCESS_CHILDREN은 0x00270008 성공/정보 값이다. 앱이 PostDeleteItem에서 result != 0을 오류로 보아 정상 정보 값을 거부한 결함을 고쳤다. 허용 결과는 S_OK와 이 값으로 한정한다.

`pytest --basetemp work/pytest-061-hresult`: **90 passed, 3 skipped**. 임시 자료와 COM 프로토콜 대역으로 다음을 검증했다.

- flags=0x282 + 0x00270008 + 영수증 + 원래 경로 소멸일 때 완료 인정.
- S_OK의 기존 완료 흐름도 유지.
- 영수증 없음, 원래 경로가 남음, 중단됨, callback veto, recycle 플래그 없음은 계속 차단.
- 대기/무시/알 수 없는 양수/부호 있는 오류/부호 없는 오류는 완료로 인정하지 않음.
- 테스트 대역은 시험 폴더를 같은 임시 부모 아래의 fake-bin으로 이름 변경하고 바이트 보존을 확인했다. 실제 Windows 휴지통 성공 또는 복원 검증으로 주장하지 않는다.

현재 에이전트 환경의 실제 Shell은 이전과 달리 recycle 플래그를 주지 않는 제한이 있어 사용자 정상 Windows와 다르다. 수정 EXE의 사용자 환경 재시험과 수동 복원 검증은 남아 있다. GitHub 업로드 없음.
