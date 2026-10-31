# Windows 배포 진행

첫 선택은 PySide6 6.10.2의 pyside6-deploy. `pysidedeploy.spec`로 Qt Widgets(Core/Gui/Widgets), standalone, 콘솔 비활성 설정을 준비했다. Nuitka 2.7.11 패키지 설치 중 긴 경로의 헤더 파일 생성이 실패하여 실제 컴파일까지 진행하지 못했다. 시스템 보안/긴 경로 설정을 변경하거나 다른 프로젝트를 옮기지 않았다.

대안은 PyInstaller 6.16.0. 고정된 의존성은 requirements-build-fallback.txt, 설정은 dev-storage-manager.spec. `console=False`, `uac_admin=False`, onedir 형태로 Python/Qt를 포함한다. 단일 EXE만 복사하면 작동하지 않으므로 같은 폴더의 _internal 파일을 함께 배포해야 한다.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build-fallback.txt
.venv\Scripts\python.exe scripts\build_windows.py
```

첫 EXE 시작은 PATH의 Poppler ICU DLL이 Qt의 Windows ICU ABI와 충돌하여 실패했다. `scripts/build_windows.py`로 DLL 검색 경로를 제한하고 혼입을 거부하도록 수정한 뒤, EXE가 소스 없이 Qt·작업 스레드·임시 SQLite 분석을 수행하는 시험을 통과했다. Windows PE GUI subsystem=2, console=False이다.

재현 빌드는 `.venv\Scripts\python.exe scripts\build_windows.py`를 사용한다. 현재 버전의 build/windows-<버전>이 있으면 덮어쓰지 않고 중단한다. 이전 자체 빌드물을 보관한 뒤 다시 실행한다. 앱 표시 버전과 프로젝트 메타데이터 버전이 같아야 한다. 사용하지 않는 QML/PDF/가상 키보드 컴포넌트를 제외한다. 깨끗한 환경/일반 Windows 휴지통 긍정 경로/서명/라이선스 포함 검증 후에만 정식 배포물로 확정한다.

소스의 `app.py --self-test <새 JSON 경로>`는 지정 출력 파일의 부모 아래 임시 프로젝트만 만들고 Qt 창·백그라운드 분석·SQLite 결과를 자동 확인한다. 실제 사용자 DB는 사용하지 않으며 휴지통 이동도 실행하지 않는다. 오프스크린 시험은 `QT_QPA_PLATFORM=offscreen` 환경에서 사용한다.
