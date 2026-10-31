# 문구와 번역

한국어를 기본 원문으로 사용한다. 사용자 표시 문구는 `dev_storage_manager.i18n.tr()`로 전달하고 서식 값은 번역 후 `.format()`에 대입한다. 숫자와 경로, SQL, 기계 상태 코드는 번역하지 않는다. SQLite에 이미 저장한 근거/이력 문구는 기록 당시 언어를 유지한다.

`scripts/extract_messages.py`로 `docs/locales/messages.pot`를 갱신한다. 추후 번역자가 PO를 작성하고 MO로 컴파일하여 `src/dev_storage_manager/locales/<언어>/LC_MESSAGES/messages.mo`에 배치한다. `set_language()`를 UI 모듈 로딩 전에 호출하면 그 카탈로그를 사용한다. 현재 언어 선택 화면이나 다른 언어 카탈로그는 제공하지 않는다. 한국어 카탈로그가 없어도 원문으로 동작한다.

Qt 기본 대화상자의 OS 제공 버튼/시스템 오류 내용은 외부 환경 언어를 따를 수 있다. 번역에 숫자 서식이나 `{p0}` 같은 자리표시자를 보존해야 한다. 배포 설정에서 추후 MO 리소스 포함을 추가 검증해야 한다.
