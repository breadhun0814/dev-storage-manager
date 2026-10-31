# 0.4.0 화면 개선 검사

- `.venv\Scripts\python.exe -m pytest -q --basetemp work\pytest-design-final`: 64 passed, 3 skipped. 기존 원본 보호·취소·정리 제한 검사에 전체 경로 검색 보존과 미분석 프로젝트 요약 초기화 검사를 추가했다.
- Windows PyInstaller 빌드 성공. `scripts/package_preview.py`가 별도 임시 작업 폴더/최소 PATH에서 실제 EXE의 `--self-test`를 실행하고 앱 버전 0.4.0, frozen 방식, 읽기 전용 분석 성공, 초기 정리 비활성을 확인한 뒤 실행 ZIP을 생성했다.
- 임시 생성한 한국어 경로 프로젝트를 실제 스캔하여 Qt offscreen 1280×940 화면의 요약과 표를 육안 확인했다. 이미지: outputs/ui-redesign-preview.png. 합성 숫자 대신 해당 시험 자료의 실제 집계 결과다.
- `pip check`: No broken requirements found.
- 세 가지 링크 관련 파일 시스템 시험은 이 실행 환경의 제약으로 건너뛰었다. 실제 휴지통/복원과 깨끗한 별도 Windows, 여러 모니터의 DPI 배율은 검증하지 않았다.
- GitHub에 업로드하지 않았다.
