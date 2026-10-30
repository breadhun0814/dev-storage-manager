# 기술 결정

## 0.2.0 추가

Windows에서는 탐색 중 조상 디렉터리 핸들을 유지한다. FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES, share READ|WRITE, BACKUP_SEMANTICS|OPEN_REPARSE_POINT를 사용하고 reparse 속성 및 GetFinalPathNameByHandleW 결과를 확인한다. 탐색 이후 핸들은 즉시 닫는다. 임시 폴더 이름 변경 차단은 시험했지만 실제 junction 경합/네트워크 파일 시스템 시험은 미완료다. 휴지통 호출과의 원자성은 제공하지 않는다.

후보는 분석 중 관측한 일반 파일 표식과 연결 관계로 판별한다. 설정 파일은 실행/임포트하지 않는다. 캐시 후보에도 사용자 파일이 있을 수 있어 실제 정리는 모두 미지원으로 둔다. pytest 표식은 현재 파일명 구성만 확인하므로 내용 검증 전 후보임을 표시한다.

폴더 서명은 정렬한 메타데이터와 자식 서명의 SHA-256이다. 파일 내용의 동일성을 보장하는 해시가 아니며, 현재 단계의 변경 감지/검토용이다. 작업 전후 검사도 원자적인 경계 고정은 아니므로 휴지통 이동에 바로 사용하지 않는다.

후보 검토는 두 번 재탐색하고 포함 파일을 열거한다. 검토할 대상을 사용자가 직접 선택하며 작업을 취소할 수 있다. 향후 대규모 목록에는 모델 기반 가상화/한도 표시가 필요하다.

- Python 3.12 계열로 제한한다. 이 환경에서 발견한 3.12.14 x64 런타임을 사용한다. PySide6 6.10.2와 핵심/부가 모듈·shiboken6를 같은 버전으로 고정한다. 실제 설치 및 검증 결과는 PROGRESS에 기록한다. 최신 버전으로 무조건 올리지 않는다.
- Qt Widgets와 QThread를 사용한다. 취소는 threading.Event로 요청하고 파일/디렉터리 사이에서 확인한다. OS 파일 시스템 호출 자체를 강제로 끊지 않으며 작업 중 창 종료는 취소 요청 후 재시도하게 한다.
- os.scandir와 follow_symlinks=False 메타데이터만 읽는다. Python 재귀 호출 대신 스택으로 탐색하고 하위 폴더를 역순 합산한다. 폴더 행은 하위 포함 값이므로 행들을 다시 합산하면 안 된다.
- 링크와 Windows FILE_ATTRIBUTE_REPARSE_POINT(0x400)를 제외한다. 시작 경로의 모든 조상과 탐색 직전 디렉터리를 검사한다. 단, 메타데이터 검사와 OS 열기 사이의 외부 변경을 원자적으로 방지하는 핸들 기반 탐색은 아직 없다. 적대적인 동시 경로 교체에 대한 보장을 하지 않는다. 정리 기능을 추가하기 전에 별도의 검증이 필요하다.
- SQLite는 `%LOCALAPPDATA%\DevStorageManager\analysis.sqlite3`에 저장한다. 소스 폴더에 DB/로그를 쓰지 않는다. 프로젝트별 마지막 결과를 JSON으로 저장한다. 취소는 부분 결과로, 읽기 실패는 불완전으로, 재시작 시 running은 interrupted로 표시한다.
- 현재 폴더 수에 비례하여 메모리를 사용하고 파일 목록 전체는 보관하지 않는다. 결과 표는 폴더별 행을 일괄 구성한다. 대규모 폴더에서 UI 행 생성 병목은 아직 실측하지 않았다.
- 한국어 공통 문구·상태는 ui/strings.py에 분리했다. 나머지 UI/오류 문구 전체의 번역 카탈로그 전환은 후속 과제다.
- 삭제 API/Send2Trash는 아직 설치하거나 사용하지 않는다. 정리 보호 시험 이후 검증한 버전을 고정한다. 영구 삭제 fallback은 허용하지 않는다.
- Windows 배포는 pyside6-deploy를 우선 검토한다. 현재는 pythonw 소스 실행기를 제공한다. 실행 파일 빌드/서명/설치 및 깨끗한 환경 검증은 미완료다.

참고: [PySide6 6.10.2](https://pypi.org/project/PySide6/6.10.2/), [pytest 9.0.2](https://pypi.org/project/pytest/9.0.2/), [Qt 배포 도구](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html).
