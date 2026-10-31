# 포함 소프트웨어와 출처

이 디렉터리는 배포 시험물과 함께 제공하는 원문 라이선스/저작권/기여자 고지 모음이다. 각 원문의 적용 범위와 조건을 유지한다. 자체 앱 소스에 새 라이선스를 임의로 부여하는 문서는 아니다.

- Python 3.12.14: 빌드에 사용한 Python 배포의 LICENSE.txt.
- Qt/PySide6/Shiboken 6.10.2: Qt 공식 동일 버전 소스 아카이브와 설치된 wheel의 고지. Qt Python·Qt Base의 LICENSES와 third-party attribution/라이선스 원문을 모았다.
- Send2Trash 2.1.0, pywin32 311, setuptools와 패키징 시 포함된 구성요소: 설치 패키지의 고지.
- PyInstaller 6.16.0: 부트로더/도구 라이선스와 예외 조항은 원문 참조.

`source-index.json`은 원래 파일 경로, 저장한 파일 이름, 공식 소스 URL을 연결한다. Windows 경로 길이 문제를 피하려고 파일 이름에 경로 해시를 붙였다. 동일 소스 저장소의 모든 고지를 수집했으므로 일부는 실행 번들에 실제 포함되지 않은 부분에 관한 문서일 수 있다.

공식 대응 소스:

- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.2-src/pyside-setup-everywhere-src-6.10.2.tar.xz
- https://download.qt.io/official_releases/qt/6.10/6.10.2/submodules/qtbase-everywhere-src-6.10.2.tar.xz
- https://github.com/arsenetar/send2trash/tree/2.1.0
- https://github.com/mhammond/pywin32
- https://github.com/pyinstaller/pyinstaller/tree/v6.16.0

Qt 라이브러리는 실행 파일에 정적으로 합치지 않고 `_internal` 안의 DLL로 분리한다. 라이브러리 파일을 임의로 숨기거나 교체를 막는 장치를 두지 않는다. Qt를 사용하는 앱의 분석·변경에 관한 적용 라이선스 권리를 제한하지 않는다. Windows 시스템 DLL은 시스템에 있는 것을 사용한다. 정식 공개 배포 전에는 실제 배포 파일 목록에 대한 별도 검토가 필요하다.
