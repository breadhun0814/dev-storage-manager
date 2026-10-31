from dev_storage_manager.i18n import tr
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal, QSortFilterProxyModel, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QTabWidget, QHeaderView, QAbstractItemView,
    QPlainTextEdit, QInputDialog, QDialog, QDialogButtonBox, QTableView, QCheckBox, QApplication, QFrame, QProgressBar, QScrollArea, QSplitter, QComboBox, QMenu)

from dev_storage_manager.scanning.scanner import scan
from dev_storage_manager.platform.paths import protected_paths
from dev_storage_manager.ui.strings import TITLE, STATUS, NOTICE
from dev_storage_manager.detection.rules import CATEGORIES
from dev_storage_manager.cleanup.review import inspect
from dev_storage_manager.domain.comparison import compare
from dev_storage_manager.persistence.report import export_json, export_csv, export_files_csv
from dev_storage_manager.persistence.journal import Journal
from dev_storage_manager.ui.history_worker import HistoryWorker
from dev_storage_manager.ui.result_tabs import ResultTabs
from dev_storage_manager.ui.review_dialog import ReviewDialog
from dev_storage_manager.ui.cleanup_result_dialog import CleanupResultDialog
from dev_storage_manager.domain.cleanup_result import CleanupReport
from dev_storage_manager.demo.project import create_demo
from dev_storage_manager.ui.usage_help import UsageHelp
from dev_storage_manager.ui.coverage_text import LABELS as COVERAGE_LABELS, coverage_note
from dev_storage_manager.ui.folder_model import FolderModel
from dev_storage_manager.ui.folder_proxy import FolderProxy
from dev_storage_manager.cleanup.policy import cache_proof, EXECUTABLE_KINDS
from dev_storage_manager.cleanup.service import Plan, execute
from dev_storage_manager.cleanup.capability import qualify, load_report
from dev_storage_manager.platform.recycle import WindowsRecycle
from dev_storage_manager.platform.path_safety import normalized
from dev_storage_manager.persistence.store import Store
from dev_storage_manager.ui.comparison_model import ComparisonModel
from dev_storage_manager.ui.issue_model import IssueModel
from dev_storage_manager import __version__
from dev_storage_manager.platform.diagnostics import runtime_info
from dev_storage_manager.ui.theme import STYLE
from dev_storage_manager.ui.formatting import format_size, exact_size
from dev_storage_manager.ui.candidate_state import empty_candidate_message
from dev_storage_manager.ui.file_model import FileModel
from dev_storage_manager.ui.directory_browser import DirectoryBrowser, ListingWorker


def size_text(value):
    return format_size(value)


def compact_size(value):
    return format_size(value)


class Worker(QThread):
    progress = Signal(int, object, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, path, exclusions=None, directory=None):
        super().__init__()
        self.path = path
        self.cancel = Event()
        self.exclusions = exclusions or []
        self.directory = directory

    def run(self):
        try:
            result = scan(Path(self.path), self.cancel, self.progress.emit, protected_paths(), self.exclusions)
            if self.directory is not None:
                store = Store(self.directory, recover_running=False)
                try:
                    store.save(result)
                finally:
                    store.close()
            self.result.emit(result)
        except Exception as exc:
            self.failed.emit(tr("분석 또는 결과 저장에 실패했습니다: ") + str(exc))


class ReviewWorker(QThread):
    progress = Signal(int, object, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, result, candidate, cleanup_ready=False):
        super().__init__()
        self.analysis, self.candidate = result, candidate
        self.cancel = Event()
        kinds = {"python-cache"} if cleanup_ready is True else (set(cleanup_ready) if cleanup_ready else set())
        self.cleanup_ready = candidate.kind in kinds & EXECUTABLE_KINDS

    def run(self):
        try:
            review = inspect(self.analysis, self.candidate, self.cancel,
                             self.progress.emit, protected_paths(), require_supported=not self.cleanup_ready)
            plan = None
            if self.cleanup_ready and not review.blocked:
                try:
                    plan = Plan(self.analysis, self.candidate, review.signature, cache_proof(review, self.cancel))
                except Exception as exc:
                    review.blocked.append(str(exc))
            self.result.emit((review, plan))
        except Exception as exc:
            self.failed.emit(str(exc))


class ExportWorker(QThread):
    result = Signal(object)
    failed = Signal(str)
    cancellable = False

    def __init__(self, directory, project, path, csv_format=False):
        super().__init__()
        self.directory, self.project, self.path = directory, project, path
        self.csv_format = csv_format
        self.cancel = Event()

    def run(self):
        store = None
        try:
            store = Store(self.directory, recover_running=False)
            result = store.load(self.project)
            if result is None:
                raise ValueError(tr("저장된 분석 결과가 없습니다."))
            exporter = export_files_csv if self.csv_format == "files" else (export_csv if self.csv_format else export_json)
            exporter(result, self.path)
            self.result.emit(str(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if store is not None:
                store.close()


class LoadWorker(QThread):
    result = Signal(object)
    failed = Signal(str)
    cancellable = False

    def __init__(self, directory, path):
        super().__init__()
        self.directory, self.path = directory, path
        self.cancel = Event()

    def run(self):
        store = None
        try:
            store = Store(self.directory, recover_running=False)
            result = store.load(self.path)
            status = next((state for path, _, state in store.projects() if path == self.path), None)
            self.result.emit((result, status))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if store is not None:
                store.close()


class ComparisonWorker(QThread):
    result = Signal(object)
    failed = Signal(str)
    cancellable = False

    def __init__(self, directory, project):
        super().__init__()
        self.directory, self.project = directory, project
        self.cancel = Event()

    def run(self):
        store = None
        try:
            store = Store(self.directory, recover_running=False)
            current, previous = store.load(self.project), store.previous(self.project)
            if current is None or previous is None:
                raise ValueError(tr("비교할 이전 완료 결과가 없습니다. 다시 분석한 뒤 사용하세요."))
            self.result.emit(compare(previous, current))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if store is not None:
                store.close()


class EnvironmentWorker(QThread):
    result = Signal(object)
    failed = Signal(str)
    phase = Signal(str)

    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        self.cancel = Event()

    def run(self):
        try:
            self.result.emit(qualify(self.directory / "environment-tests", self.cancel, self.phase.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class DemoWorker(QThread):
    progress = Signal(int, object, str)
    created = Signal(str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, parent_directory, data_directory):
        super().__init__()
        self.parent_directory, self.data_directory = parent_directory, data_directory
        self.cancel = Event()

    def run(self):
        store, root = None, None
        try:
            root = create_demo(self.parent_directory, self.cancel)
            self.created.emit(str(root))
            store = Store(self.data_directory, recover_running=False)
            store.add(str(root))
            result = scan(root, self.cancel, self.progress.emit, protected_paths())
            store.save(result)
            self.result.emit(result)
        except Exception as exc:
            suffix = tr("\n생성된 시험 폴더: ") + str(root) if root else ""
            self.failed.emit(str(exc) + suffix)
        finally:
            if store:
                store.close()


class CleanupWorker(QThread):
    result = Signal(object)
    failed = Signal(object)

    def __init__(self, plan, directory):
        super().__init__()
        self.plan, self.directory = plan, directory
        self.cancel = Event()

    def run(self):
        journal = None
        try:
            journal = Journal(self.directory)
            store = Store(self.directory, recover_running=False)
            try:
                if self.plan.analysis.root not in {p for p, _, _ in store.projects()}:
                    raise ValueError(tr("등록 목록에서 제거된 프로젝트입니다."))
                store.status(self.plan.analysis.root, "needs-analysis")
            finally:
                store.close()
            job = execute([self.plan], journal, WindowsRecycle(), self.cancel, protected_paths())
            self.result.emit(CleanupReport(self.plan.analysis.root, self.plan.candidate.path, job, journal.job_result(job)))
        except Exception as exc:
            job = journal.last_job if journal else None
            result, error = None, str(exc)
            if job:
                try:
                    result = journal.job_result(job)
                except Exception as read_error:
                    error += tr("\n결과 조회 오류: ") + str(read_error)
            self.failed.emit(CleanupReport(self.plan.analysis.root, self.plan.candidate.path, job, result, error))
        finally:
            if journal:
                journal.close()


class Window(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store, self.worker, self.active_path = store, None, None
        self.current_result = None
        self.history_worker = None
        self.history_page = None
        self.history_offset, self.history_anchor = 0, None
        self.history_job = None
        self._history_pending = False
        self._closing = False
        self.browser = None
        self.cleanup_ready = False
        self.qualified_kinds = frozenset()
        self.cleanup_reason = tr("정리 실행 전 확인 필요 · '관리 · 도구 → 정리 환경 확인'에서 앱이 만든 시험 자료로 먼저 확인하세요.")
        self.last_capability = load_report(store.directory / "environment-tests")
        if self.last_capability:
            self.cleanup_reason = self.last_capability.reason
        self.setWindowTitle(f"{TITLE} · {__version__}")
        self.resize(1040, 760)
        self.setStyleSheet(STYLE)
        body = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel(tr("개발 저장공간 관리자"))
        self.heading_title = title
        title.setObjectName("pageTitle")
        subtitle = QLabel(tr("프로젝트의 용량을 이해하고, 근거를 확인한 뒤 정리하세요."))
        self.heading_subtitle = subtitle
        subtitle.setObjectName("subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        badge = QLabel(tr("로컬 전용  ·  읽기 전용 분석"))
        self.heading_badge = badge
        badge.setObjectName("localBadge")
        heading.addWidget(badge)
        layout.addLayout(heading)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        more = QHBoxLayout()
        layout.addLayout(more)
        section = QPushButton(tr("프로젝트 목록 펼치기 / 접기"))
        section.setObjectName("sectionTitle")
        section.setCheckable(True)
        section.toggled.connect(lambda visible: (self.projects.setVisible(visible), self.project_location.setVisible(visible)))
        more.addWidget(section)
        more.addStretch()
        self.compare_button = QPushButton(tr('이전 완료 결과와 비교'))
        self.export_button = QPushButton(tr('분석 보고서 내보내기'))
        more.addWidget(self.compare_button)
        more.addWidget(self.export_button)
        self.environment_button = QPushButton(tr("정리 환경 확인"))
        more.addWidget(self.environment_button)
        self.environment_button.clicked.connect(self.start_environment_test)
        about_button = QPushButton(tr("프로그램 정보"))
        more.addWidget(about_button)
        about_button.clicked.connect(self.show_about)
        report_button = QPushButton(tr("환경 점검 결과 보기"))
        report_button.clicked.connect(self.show_environment_report)
        self.compare_button.clicked.connect(self.show_comparison)
        self.export_button.clicked.connect(self.export_report)
        self.add = QPushButton(tr('폴더 추가'))
        self.start = QPushButton(tr('선택 프로젝트 분석'))
        self.remove = QPushButton(tr('목록에서 제거'))
        self.exclude = QPushButton(tr('분석 제외 목록'))
        self.stop = QPushButton(tr('작업 취소'))
        self.stop.setEnabled(False)
        self.start.setObjectName("primary")
        self.stop.setObjectName("danger")
        for button in (self.add, self.start, self.stop):
            buttons.addWidget(button)
        tools_button = QPushButton(tr("관리 · 도구"))
        tools_menu = QMenu(tools_button)
        self.tool_actions = []
        self.demo_button = QPushButton(tr("시험 프로젝트 만들고 분석"))
        self.demo_button.clicked.connect(self.start_demo_project)
        help_button = QPushButton(tr("사용 방법"))
        help_button.clicked.connect(self.show_usage_help)
        for button in (help_button, section, self.demo_button, self.remove, self.exclude, self.compare_button, self.export_button, self.environment_button, report_button, about_button):
            action = tools_menu.addAction(button.text())
            action.triggered.connect(lambda checked=False, b=button: b.click())
            self.tool_actions.append((button, action))
            button.hide()
        tools_button.setMenu(tools_menu)
        buttons.addWidget(tools_button)
        self.projects = QTableWidget(0, 5)
        self.projects.setHorizontalHeaderLabels([tr('프로젝트'), tr('경로'), tr('마지막 분석'), tr('상태'), tr('확인된 논리적 크기')])
        self.projects.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.projects.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.projects.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.projects.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.projects.setColumnWidth(1, 160)
        self.projects.setColumnWidth(2, 135)
        self.projects.setColumnWidth(3, 150)
        self.projects.setColumnWidth(4, 110)
        self.projects.setWordWrap(True)
        self.projects.setColumnHidden(1, True)
        self.projects.setColumnHidden(2, False)
        self.projects.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.projects.horizontalHeader().sectionResized.connect(lambda *_: self.projects.resizeRowsToContents())
        self.projects.setMaximumHeight(132)
        self.projects.verticalHeader().hide()
        self.projects.verticalHeader().setDefaultSectionSize(36)
        self.projects.setShowGrid(False)
        layout.addWidget(self.projects)
        self.projects.hide()
        self.project_location = QLineEdit()
        self.project_location.setReadOnly(True)
        self.project_location.setPlaceholderText(tr("프로젝트를 선택하면 전체 경로가 표시됩니다. 선택해서 복사할 수 있습니다."))
        layout.addWidget(self.project_location)
        self.project_location.hide()
        self.project_picker = QComboBox()
        self.project_picker.setEditable(True)
        self.project_picker.lineEdit().setReadOnly(True)
        self.project_picker.setPlaceholderText(tr("분석할 프로젝트를 선택하세요"))
        self.project_picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.project_picker.currentIndexChanged.connect(lambda index: self.projects.selectRow(index) if index >= 0 else None)
        layout.addWidget(self.project_picker)
        metrics = QHBoxLayout()
        self.metric_values = []
        self.metric_cards = []
        for caption in (tr("확인된 논리적 크기"), tr("확인된 파일"), tr("정리 후보"), tr("오류 · 제외 경로")):
            card = QFrame()
            card.setObjectName("metricCard")
            self.metric_cards.append(card)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 10, 15, 10)
            label = QLabel(caption)
            label.setObjectName("metricLabel")
            value = QLabel("—")
            value.setObjectName("metricValue")
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            metrics.addWidget(card)
            self.metric_values.append(value)
        layout.addLayout(metrics)
        self.summary = QLabel(tr('아직 분석 결과가 없습니다.'))
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        notice = QLabel(NOTICE)
        self.unit_notice = notice
        notice.setObjectName("notice")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.cleanup_status = QLabel(self.cleanup_reason)
        if self.last_capability:
            self.cleanup_status.setText(tr("정리 비활성 · 이전 점검 기록은 '관리 · 도구 → 환경 점검 결과 보기'에서 확인하세요. 이번 실행에서는 다시 점검해야 합니다."))
        self.cleanup_status.setWordWrap(True)
        self.cleanup_status.setObjectName("summary")
        self.cleanup_status.setTextFormat(Qt.TextFormat.PlainText)
        self.cleanup_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.cleanup_status)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(tr('폴더 경로 검색 (표시만 필터링)'))
        layout.addWidget(self.search)
        tabs = ResultTabs()
        self.tabs = tabs
        self.folders = QTableView()
        self.folder_model = FolderModel(self)
        self.folder_proxy = FolderProxy(self)
        self.folder_proxy.setSourceModel(self.folder_model)
        self.folder_proxy.idle.connect(lambda: QTimer.singleShot(0, self.close) if self._closing else None)
        self.folders.setModel(self.folder_proxy)
        self.folders.setSortingEnabled(True)
        self.folders.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.folders.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.folders.setColumnWidth(1, 115)
        self.folders.setColumnWidth(2, 65)
        self.folders.setColumnWidth(3, 130)
        self.folders.setColumnWidth(4, 145)
        self.folders.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.folders.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.issues = QTableView()
        self.issue_model = IssueModel(self)
        self.issue_proxy = QSortFilterProxyModel(self)
        self.issue_proxy.setSourceModel(self.issue_model)
        self.issues.setModel(self.issue_proxy)
        self.issues.setSortingEnabled(True)
        self.issues.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.issues.setColumnWidth(0, 530)
        self.issues.setColumnWidth(1, 90)
        self.issues.horizontalHeader().setStretchLastSection(True)
        self.candidates = QTreeWidget()
        self.candidates.setHeaderLabels([tr('① 검토할 후보 선택'), tr('분류'), tr('크기 (논리적)'), tr('실행 가능 여부')])
        self.candidates.horizontalScrollBar().setSingleStep(20)
        self.candidates.header().setStretchLastSection(False)
        self.candidates.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.candidates.setColumnWidth(1, 140)
        self.candidates.setColumnWidth(2, 105)
        self.candidates.setColumnWidth(3, 190)
        self.candidates.setRootIsDecorated(False)
        self.candidates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(tr('후보를 선택하면 근거·주의사항·재생성 조건을 표시합니다. 실행 지원 여부는 환경 시험과 개별 검증에 따라 결정됩니다.'))
        candidate_page = QWidget()
        candidate_layout = QVBoxLayout(candidate_page)
        guide = QLabel(tr("후보 한 행을 클릭한 뒤 포함 파일을 검토하세요. 폴더 단위로 정리하며 개별 파일 삭제는 지원하지 않습니다."))
        self.candidate_guide = guide
        guide.setWordWrap(True)
        candidate_layout.addWidget(guide)
        self.candidate_state = QLabel(empty_candidate_message(None))
        self.candidate_state.setWordWrap(True)
        self.candidate_state.setTextFormat(Qt.TextFormat.PlainText)
        self.candidate_state.setObjectName("summary")
        candidate_layout.addWidget(self.candidate_state)
        self.candidate_folder_button = QPushButton(tr("분석한 폴더별 용량 보기"))
        self.candidate_folder_button.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.candidate_folder_button.setEnabled(False)
        candidate_layout.addWidget(self.candidate_folder_button)
        self.candidate_files_button = QPushButton(tr("큰 파일 확인하기"))
        self.candidate_files_button.clicked.connect(lambda: self.tabs.setCurrentWidget(self.file_page))
        self.candidate_files_button.setEnabled(False)
        candidate_layout.addWidget(self.candidate_files_button)
        self.candidate_demo_button = QPushButton(tr("시험 자료로 사용 흐름 익히기"))
        self.candidate_demo_button.clicked.connect(self.start_demo_project)
        candidate_layout.addWidget(self.candidate_demo_button)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.candidates)
        split.addWidget(self.details)
        split.setSizes([170, 100])
        candidate_layout.addWidget(split)
        self.review_button = QPushButton(tr('② 후보를 선택한 뒤 포함 파일 검토'))
        self.review_button.setEnabled(False)
        candidate_layout.addWidget(self.review_button)
        candidate_layout.insertWidget(1, self.review_button)
        self.review_button.clicked.connect(self.start_review)
        tabs.addTab(candidate_page, tr('프로젝트·정리 후보'))
        folder_page = QWidget()
        folder_layout = QVBoxLayout(folder_page)
        self.folder_search_status = QLabel()
        self.folder_proxy.updated.connect(self.update_folder_search_status)
        folder_layout.addWidget(self.folder_search_status)
        folder_layout.addWidget(self.folders)
        self.folder_selection = QLabel(tr("행을 선택하면 전체 경로와 크기를 확인할 수 있습니다. 정리는 '프로젝트·정리 후보'에서 지원하는 후보만 검토하세요."))
        self.folder_selection.setWordWrap(True)
        self.folder_selection.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_layout.addWidget(self.folder_selection)
        self.browse_button = QPushButton(tr("프로젝트 폴더 내용 보기"))
        self.browse_button.setEnabled(False)
        self.browse_button.clicked.connect(self.browse_selected_folder)
        folder_layout.addWidget(self.browse_button)
        self.folders.doubleClicked.connect(lambda _: self.browse_selected_folder())
        self.folders.selectionModel().currentChanged.connect(self.folder_selected)
        tabs.addTab(folder_page, tr('폴더별 용량'))
        tabs.addTab(self.issues, tr('오류·제외 범위'))
        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_help = QLabel('<a href="restore">' + tr("Windows 휴지통에서 복원하는 방법 보기") + '</a>')
        history_help.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        history_help.linkActivated.connect(self.show_restore_help)
        history_layout.addWidget(history_help)
        self.history_search = QLineEdit()
        self.history_search.setMaxLength(512)
        self.history_search.setClearButtonEnabled(True)
        self.history_search.setPlaceholderText(tr("전체 정리 이력에서 경로·실패 이유 검색"))
        history_layout.addWidget(self.history_search)
        history_scope = QHBoxLayout()
        self.history_job_label = QLabel()
        self.history_job_label.setTextFormat(Qt.TextFormat.PlainText)
        self.history_all = QPushButton(tr("전체 이력 보기"))
        self.history_all.clicked.connect(lambda: self.show_cleanup_history(None))
        history_scope.addWidget(self.history_job_label, 1)
        history_scope.addWidget(self.history_all)
        self.history_job_label.hide()
        self.history_all.hide()
        history_layout.addLayout(history_scope)
        self.history = QTreeWidget()
        self.history.setRootIsDecorated(False)
        self.history.setUniformRowHeights(True)
        self.history.setHeaderLabels([tr('실행 시간'), tr('원래 경로'), tr('크기 (논리적)'), tr('상태'), tr('실패 이유 / 결과')])
        self.history.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.history.header().setStretchLastSection(False)
        self.history.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.history.setColumnWidth(0, 160)
        self.history.setColumnWidth(2, 95)
        self.history.setColumnWidth(3, 120)
        self.history_details = QPlainTextEdit()
        self.history_details.setReadOnly(True)
        self.history_details.setPlaceholderText(tr("이력을 선택하면 전체 원래 경로·실패 이유·작업 상태를 표시합니다."))
        history_splitter = QSplitter(Qt.Orientation.Vertical)
        history_splitter.addWidget(self.history)
        history_splitter.addWidget(self.history_details)
        history_splitter.setSizes([240, 110])
        history_layout.addWidget(history_splitter)
        self.history_summary = QLabel(tr("실행 이력을 선택하면 이동 확인 크기와 관측한 디스크 여유 공간을 별도로 표시합니다."))
        self.history_summary.setWordWrap(True)
        history_layout.addWidget(self.history_summary)
        self.history.currentItemChanged.connect(self.history_selected)
        history_navigation = QHBoxLayout()
        self.history_previous = QPushButton(tr("이전 페이지"))
        self.history_next = QPushButton(tr("다음 페이지"))
        self.history_refresh = QPushButton(tr('이력 새로고침'))
        self.history_page_label = QLabel()
        self.history_page_label.setWordWrap(True)
        self.history_page_label.setTextFormat(Qt.TextFormat.PlainText)
        self.history_page_label.setToolTip(tr("페이지당 최대 200개입니다. 페이지 이동 중에는 새 작업이 앞에 끼어들지 않습니다. 최신 이력은 새로고침하세요."))
        self.history_previous.clicked.connect(lambda: self.history_turn(-1))
        self.history_next.clicked.connect(lambda: self.history_turn(1))
        self.history_refresh.clicked.connect(lambda: self.refresh_history())
        for control in (self.history_previous, self.history_next, self.history_page_label, self.history_refresh):
            history_navigation.addWidget(control)
        history_layout.addLayout(history_navigation)
        self.history_search_timer = QTimer(self)
        self.history_search_timer.setSingleShot(True)
        self.history_search_timer.setInterval(250)
        self.history_search_timer.timeout.connect(self.refresh_history)
        self.history_search.textChanged.connect(self.history_search_changed)
        tabs.addTab(history_page, tr('정리 이력'))
        self.file_page = QWidget()
        file_layout = QVBoxLayout(self.file_page)
        self.file_info = QLabel(tr("새로 분석하면 큰 파일을 확인할 수 있습니다. 이 목록은 삭제 후보가 아닙니다."))
        self.file_scope = self.file_info.text()
        self.file_info.setWordWrap(True)
        file_layout.addWidget(self.file_info)
        self.file_search = QLineEdit()
        self.file_search.setClearButtonEnabled(True)
        self.file_search.setPlaceholderText(tr("큰 파일 목록에서 이름·경로 검색"))
        file_layout.addWidget(self.file_search)
        self.file_table = QTableView()
        self.file_model = FileModel(self)
        self.file_proxy = QSortFilterProxyModel(self)
        self.file_proxy.setSourceModel(self.file_model)
        self.file_proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.file_proxy.setFilterRole(Qt.ItemDataRole.UserRole)
        self.file_proxy.setFilterKeyColumn(0)
        self.file_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.file_table.setModel(self.file_proxy)
        self.file_table.setSortingEnabled(True)
        self.file_table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_table.verticalHeader().hide()
        self.file_table.setShowGrid(False)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.file_table.setColumnWidth(2, 120)
        file_layout.addWidget(self.file_table)
        self.file_selection = QLabel(tr("파일 행을 선택하면 전체 경로를 확인합니다. 파일 삭제 선택이 아닙니다."))
        self.file_selection.setWordWrap(True)
        self.file_selection.setTextFormat(Qt.TextFormat.PlainText)
        self.file_selection.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_layout.addWidget(self.file_selection)
        self.file_table.selectionModel().currentChanged.connect(self.file_selected)
        self.file_search.textChanged.connect(self.filter_files)
        tabs.addTab(self.file_page, tr("큰 파일"))
        tabs.currentChanged.connect(self.update_tab_context)
        tabs.setCurrentIndex(1)
        tabs.setMinimumHeight(260)
        layout.addWidget(tabs, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        for table in (self.folders, self.issues):
            table.verticalHeader().hide()
            table.verticalHeader().setDefaultSectionSize(35)
            table.setShowGrid(False)
            table.setAlternatingRowColors(True)
        self.review_button.setObjectName("primary")
        self.add.clicked.connect(self.add_project)
        self.start.clicked.connect(self.start_scan)
        self.remove.clicked.connect(self.remove_project)
        self.exclude.clicked.connect(self.edit_exclusions)
        self.candidates.currentItemChanged.connect(self.candidate_selected)
        self.stop.clicked.connect(self.cancel_scan)
        self.projects.itemSelectionChanged.connect(self.open_result)
        self.search.textChanged.connect(self.filter_rows)
        self.refresh()
        self.refresh_history()
        self.update_candidate_state(None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the result and its action within reach on ordinary laptop screens.
        if hasattr(self, "metric_cards"):
            for card in self.metric_cards:
                card.setVisible(self.height() >= 850)
            self.unit_notice.setVisible(self.height() >= 850)
            self.heading_subtitle.setVisible(self.height() >= 850)
            self.heading_title.setVisible(self.height() >= 700)
            self.heading_badge.setVisible(self.height() >= 700)

    def update_tab_context(self, index):
        self.search.setVisible(index == 1)
        self.project_picker.setVisible(index != 3)
        self.cleanup_status.setVisible(index != 3)

    def show_about(self):
        info = runtime_info()
        message = tr("개발 저장공간 관리자 · 시험 버전\n앱 버전: {app}\nPython: {python}\nPySide6: {qt}\n운영체제: {platform}\n실행 방식: {mode}\n\n회원가입·클라우드 업로드 없이 로컬에서 동작합니다.\n정리 지원은 실행 세션의 환경 시험과 후보별 검증 결과에 따릅니다.").format(
            app=info["app_version"], python=info["python_version"], qt=info["pyside6_version"],
            platform=info["platform"], mode=tr("배포 EXE") if info["mode"] == "frozen" else tr("Python 소스"))
        box = QMessageBox(self)
        box.setWindowTitle(tr("프로그램 정보"))
        box.setText(message)
        box.setTextFormat(Qt.TextFormat.PlainText)
        copy_button = box.addButton(tr("환경 정보 복사"), QMessageBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(message))
        box.addButton(QMessageBox.StandardButton.Close)
        box.open()
        self.about_dialog = box

    def show_restore_help(self):
        QMessageBox.information(self, tr("Windows 휴지통에서 복원"), tr("Windows 휴지통을 열고 원래 위치와 삭제 시간을 확인한 뒤 '복원'을 선택하세요.\n미확정 결과는 원래 경로와 휴지통을 직접 확인하세요. 복원 결과는 다시 분석해서 확인할 수 있습니다.\n앱은 자동 복원을 제공하지 않으며 휴지통을 비우지 않습니다. 휴지통을 이미 비웠거나 Windows가 항목을 제거했다면 앱에서 복구할 수 없습니다."))

    def history_search_changed(self):
        if self._closing:
            return
        self._history_pending = False
        if self.history_worker:
            self.history_worker.cancel.set()
        self.history_previous.setEnabled(False)
        self.history_next.setEnabled(False)
        self.history_page_label.setText(tr("검색 중…"))
        self.history_search_timer.start()

    def refresh_history(self, reset=True):
        if self._closing:
            return
        self.history_search_timer.stop()
        if reset:
            self.history_offset, self.history_anchor = 0, None
        self._history_pending = True
        if self.history_worker:
            self.history_worker.cancel.set()
            return
        self.start_history_query()

    def start_history_query(self):
        self._history_pending = False
        self.history_page_label.setText(tr("이력 불러오는 중…"))
        for button in (self.history_previous, self.history_next, self.history_refresh):
            button.setEnabled(False)
        worker = HistoryWorker(self.store.directory, self.history_offset, self.history_anchor, self.history_search.text(), self.history_job)
        self.history_worker = worker
        worker.result.connect(self.history_loaded)
        worker.failed.connect(self.history_failed)
        worker.finished.connect(self.history_finished)
        worker.start()

    def history_turn(self, direction):
        if self.history_worker or self.history_search_timer.isActive() or not self.history_page or self.history_page.query != self.history_search.text():
            return
        page = self.history_page
        target = page.offset + direction * page.limit
        if target < 0 or target >= page.total:
            return
        self.history_offset = target
        self.refresh_history(reset=False)

    def history_loaded(self, page):
        if self._closing or self._history_pending or page.query != self.history_search.text() or page.job != self.history_job:
            return
        self.history_page = page
        self.history_offset, self.history_anchor = page.offset, page.anchor
        self.history.clear()
        self.history_details.clear()
        self.history_summary.setText(tr("검색 결과가 없습니다. 검색어를 비우거나 이력을 새로고침하세요.") if page.query else tr("실행 이력이 없습니다. 앱은 자동 복원을 제공하지 않으며 Windows 휴지통을 직접 확인해야 합니다."))
        statuses = {"succeeded": tr('휴지통 이동 확인'), "failed": tr('실패'), "unknown": tr('결과 미확정'), "running": tr('실행 중'), "pending": tr('대기'), "cancelled": tr('실행 전 취소')}
        job_statuses = {**statuses, "partial": tr("일부 결과가 서로 다름"), "interrupted": tr("중단 · 완료 기록 미확정")}
        for created, path, size, status, reason, destination, before, after, job, job_status in page.records:
            uncertain = status in {"running", "pending"}
            status_text = tr("진행 상태 미확정") if status == "running" else tr("대기 기록") if status == "pending" else statuses.get(status, status)
            job_text = tr("완료 미확정") if job_status == "running" else job_statuses.get(job_status, job_status)
            note = tr("조회 시점의 기록된 상태: {status}. 이 기록만으로 현재 진행 여부·성공·원본 보존을 단정할 수 없습니다. 이력을 새로고침하고 기록 오류가 있었다면 저장 기능 회복 후 앱을 다시 시작하세요.").format(status=statuses.get(status, status)) if uncertain else ""
            item = QTreeWidgetItem([created[:19].replace("T", " "), path, format_size(size), status_text, reason or note or destination or ""])
            item.setToolTip(0, created)
            item.setToolTip(1, path)
            item.setToolTip(2, exact_size(size))
            item.setData(0, Qt.ItemDataRole.UserRole, (page.moved.get(job, 0), before, after))
            item.setToolTip(4, reason or note or destination or "")
            item.setData(1, Qt.ItemDataRole.UserRole, tr("실행 시간: {time}\n원래 경로: {path}\n논리적 파일 크기: {size}\n항목 결과: {status}\n전체 작업 상태: {job_status}\n실패 이유 / 결과: {reason}\n휴지통 영수증 경로: {destination}\n작업 ID: {job}").format(time=created, path=path, size=exact_size(size), status=status_text, job_status=job_text, reason=reason or tr("기록 없음"), destination=destination or tr("확인된 영수증 없음"), job=job) + ("\n" + note if note else ""))
            self.history.addTopLevelItem(item)
        if page.records:
            self.history.setCurrentItem(self.history.topLevelItem(0))
        self.history_page_label.setText(tr("{start:,}–{end:,} / {scope} {total:,}개").format(start=page.offset + 1 if page.records else 0, end=page.offset + len(page.records), scope=tr("검색 결과") if page.query else tr("전체"), total=page.total))

    def history_failed(self, message):
        if self._closing or self._history_pending or (self.history_worker and (self.history_worker.query != self.history_search.text() or self.history_worker.job != self.history_job)):
            return
        self.history_page = None
        self.history.clear()
        self.history_details.clear()
        self.history_summary.setText(tr("이력을 불러오지 못했습니다. 기록이 없거나 작업이 성공했다는 뜻이 아닙니다. 새로고침으로 다시 확인하세요."))
        self.history_page_label.setText(tr("이력 조회 실패: ") + message)

    def history_finished(self):
        self.history_worker.deleteLater()
        self.history_worker = None
        if self._closing:
            self.close()
        elif self._history_pending:
            self.start_history_query()
        else:
            page = self.history_page
            ready = page is not None and page.query == self.history_search.text() and not self.history_search_timer.isActive()
            self.history_previous.setEnabled(ready and page.offset > 0)
            self.history_next.setEnabled(ready and page.offset + page.limit < page.total)
            self.history_refresh.setEnabled(True)

    def history_selected(self, item, previous):
        if item is None:
            self.history_details.clear()
            return
        self.history_details.setPlainText(item.data(1, Qt.ItemDataRole.UserRole) or "")
        moved, before, after = item.data(0, Qt.ItemDataRole.UserRole)
        before_text = size_text(before) if before is not None else tr("관측 실패")
        after_text = size_text(after) if after is not None else tr("관측 실패")
        self.history_summary.setText(tr("이 작업에서 휴지통 이동을 확인한 논리적 크기: {moved}\n관측한 디스크 여유 공간 — 실행 전: {before} / 실행 후: {after}\n휴지통 이동은 즉시 여유 공간이 늘어났음을 의미하지 않습니다.").format(moved=size_text(moved), before=before_text, after=after_text))

    def selected(self):
        row = self.projects.currentRow()
        return self.projects.item(row, 1).text() if row >= 0 else None

    def refresh(self, select=None, load_result=True):
        previous = self.projects.blockSignals(True)
        picker_previous = self.project_picker.blockSignals(True)
        try:
            self.projects.setRowCount(0)
            self.project_picker.clear()
            for path, updated, status, logical_size in self.store.project_summaries():
                self.project_picker.addItem(Path(path).name, path)
                row = self.projects.rowCount()
                self.projects.insertRow(row)
                for col, value in enumerate((Path(path).name, path, updated or "—", STATUS.get(status, status), size_text(logical_size) if logical_size is not None else "—")):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    if col == 4 and logical_size is not None:
                        item.setToolTip(exact_size(logical_size))
                    self.projects.setItem(row, col, item)
                if path == select:
                    self.projects.selectRow(row)
            self.project_picker.setCurrentIndex(self.projects.currentRow())
        finally:
            self.projects.blockSignals(previous)
            self.project_picker.blockSignals(picker_previous)
        self.projects.resizeRowsToContents()
        if select and load_result:
            self.open_result()

    def add_project(self):
        folder = QFileDialog.getExistingDirectory(self, tr('프로젝트 폴더 선택'))
        if folder:
            try:
                path = str(normalized(folder))
                self.store.add(path)
                self.refresh(path)
            except ValueError as exc:
                QMessageBox.warning(self, tr("프로젝트 경로 오류"), str(exc))

    def start_demo_project(self):
        if self.worker:
            return
        import tempfile
        parent = QFileDialog.getExistingDirectory(self, tr("새 시험 프로젝트를 만들 상위 폴더 선택 · 기존 파일은 덮어쓰지 않습니다"), tempfile.gettempdir())
        if not parent:
            return
        self.set_busy(True)
        self.summary.setText(tr("새 시험 폴더에 고정 자료를 만들고 실제 분석합니다. 정리는 자동 실행하지 않습니다."))
        self.worker = DemoWorker(parent, self.store.directory)
        self.worker.created.connect(lambda path: setattr(self, "active_path", path))
        self.worker.progress.connect(self.show_progress)
        self.worker.result.connect(self.demo_result)
        self.worker.failed.connect(self.demo_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def show_usage_help(self):
        dialog = UsageHelp(self, allow_demo=self.worker is None)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.demo_requested.connect(lambda: (dialog.accept(), self.start_demo_project()))
        dialog.open()
        self.usage_dialog = dialog

    def demo_result(self, result):
        self.active_path = result.root
        self.refresh(result.root, load_result=False)
        self.display(result)
        self.tabs.setCurrentIndex(0)
        message = (tr("앱이 만든 시험 프로젝트입니다. __pycache__ 후보를 선택하고 '② 포함 파일 검토'를 누르세요. 정리에는 환경 시험과 직접 확인이 필요합니다.")
                   if result.status == "complete" and any(c.kind == "python-cache" for c in result.candidates)
                   else tr("시험 폴더를 만들었지만 분석이 완료되지 않았거나 후보를 확인하지 못했습니다. 오류·제외 범위와 생성 위치를 확인하고 다시 분석하세요."))
        self.summary.setText(message + "\n" + result.root)

    def demo_failed(self, message):
        self.refresh(load_result=False)
        self.clear_metrics()
        self.candidates.clear()
        self.details.clear()
        self.folder_model.set_folders([])
        self.issue_model.set_issues([])
        self.update_candidate_state(None, tr("시험 프로젝트를 완료하지 못했습니다. 생성된 새 폴더 위치와 오류를 확인하세요."))
        self.summary.setText(tr("시험 자료 생성/분석을 완료하지 못했습니다. 남은 새 폴더 위치를 확인하세요."))
        QMessageBox.warning(self, tr("시험 프로젝트 오류"), message)

    def remove_project(self):
        path = self.selected()
        if path:
            self.store.remove(path)
            self.refresh()
            self.folder_model.set_folders([])
            self.issue_model.set_issues([])
            self.candidates.clear()
            self.details.clear()
            self.clear_metrics()
            self.summary.setText(tr('목록에서 제거했습니다. 실제 폴더는 변경하지 않았습니다.'))
            self.update_candidate_state(None)

    def start_scan(self):
        path = self.selected()
        if not path or self.worker:
            return
        self.active_path = path
        self.update_candidate_state(None, tr("분석 중입니다. 완료 후 이곳에 후보 또는 후보를 찾지 못한 이유를 표시합니다."))
        self.details.clear()
        self.store.status(path, "running")
        self.refresh(path, load_result=False)
        self.set_busy(True)
        self.clear_metrics()
        self.worker = Worker(path, self.store.exclusions(path), self.store.directory)
        self.worker.progress.connect(self.show_progress)
        self.worker.result.connect(self.scan_result)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def set_busy(self, busy):
        self.progress_bar.setVisible(busy)
        for widget in (self.add, self.start, self.remove, self.exclude, self.projects, self.project_picker, self.review_button, self.compare_button, self.export_button, self.environment_button, self.browse_button, self.demo_button, self.candidate_demo_button):
            widget.setEnabled(not busy)
        self.stop.setEnabled(busy)
        for button, action in self.tool_actions:
            action.setEnabled(button.isEnabled())
        self.review_button.setEnabled(not busy and self.candidates.currentItem() is not None)
        self.browse_button.setEnabled(not busy and self.current_result is not None)

    def cancel_scan(self):
        if self.worker:
            if not getattr(self.worker, "cancellable", True):
                self.summary.setText(tr("결과 읽기 또는 저장 작업이 진행 중입니다. 완료될 때까지 기다려주세요."))
                return
            self.worker.cancel.set()
            self.stop.setEnabled(False)
            self.summary.setText(tr('취소 요청 중 · 현재 파일 시스템 호출이 끝나면 중단합니다.'))

    def show_progress(self, files, size, path):
        self.metric_values[0].setText(compact_size(size))
        self.metric_values[0].setToolTip(exact_size(size))
        self.metric_values[1].setText(f"{files:,}")
        self.summary.setText(tr('분석 중 · {p0:,}개 파일 · {p1}\n{p2}').format(p0=files, p1=size_text(size), p2=path))

    def scan_result(self, result):
        self.refresh(self.active_path, load_result=False)
        self.display(result)

    def scan_failed(self, message):
        self.clear_metrics()
        self.store.status(self.active_path, "failed")
        self.refresh(self.active_path, load_result=False)
        self.folder_model.set_folders([])
        self.issue_model.set_issues([])
        self.candidates.clear()
        self.details.clear()
        self.update_candidate_state(None, tr("분석을 완료하지 못했습니다. 오류를 확인하고 다시 분석하세요. 현재 선택 가능한 정리 후보가 없습니다."))
        self.summary.setText(tr('분석 실패 · 현재 결과 없음 · ') + message)
        QMessageBox.warning(self, tr('분석 실패'), message)

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def open_result(self):
        if self.worker:
            return
        self.clear_metrics()
        self.file_search.clear()
        path = self.selected()
        self.project_location.setText(path or "")
        picker_previous = self.project_picker.blockSignals(True)
        self.project_picker.setCurrentIndex(self.projects.currentRow())
        self.project_picker.lineEdit().setCursorPosition(0)
        self.project_picker.setToolTip(path or "")
        self.project_picker.blockSignals(picker_previous)
        self.folder_model.set_folders([])
        self.issue_model.set_issues([])
        self.candidates.clear()
        self.details.clear()
        if not path or not self.store.has_result(path):
            self.update_candidate_state(None)
            self.summary.setText(tr('저장된 분석 결과가 없습니다.'))
            return
        self.update_candidate_state(None, tr("저장된 분석 결과를 읽고 있습니다. 완료 후 결과를 표시합니다."))
        self.summary.setText(tr("저장된 분석 결과를 읽고 있습니다. 화면 검색은 계속 사용할 수 있습니다."))
        self.set_busy(True)
        self.stop.setEnabled(False)
        self.worker = LoadWorker(self.store.directory, path)
        self.worker.result.connect(lambda payload: self.loaded_result(path, payload))
        self.worker.failed.connect(lambda message: self.load_failed(message))
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def loaded_result(self, path, payload):
        if self.selected() != path:
            return
        result, status = payload
        if result is None:
            self.update_candidate_state(None)
            self.summary.setText(tr("저장된 분석 결과가 없습니다."))
            return
        self.display(result)
        if status == "needs-analysis":
            self.current_result = None
            self.candidates.clear()
            self.details.clear()
            self.update_candidate_state(None, tr("정리 시도 후의 이전 분석입니다. 후보를 다시 사용하려면 재분석하세요."))
            self.file_info.setText(tr("정리 전 저장된 큰 파일 목록입니다. 최신 상태는 다시 분석하세요."))
            self.file_scope = self.file_info.text()
        if status != result.status:
            self.summary.setText(tr('최근 시도: ') + STATUS.get(status, str(status)) +
                                 tr(' · 아래는 이전 저장 결과입니다.\n') + self.summary.text())

    def load_failed(self, message):
        self.update_candidate_state(None, tr("저장된 결과를 읽지 못했습니다. 다시 분석하거나 오류를 확인하세요."))
        self.summary.setText(tr("결과 읽기 실패: ") + message)

    def update_candidate_state(self, result, message=None):
        has_candidates = result is not None and bool(result.candidates)
        self.candidate_guide.setVisible(has_candidates)
        self.details.setVisible(has_candidates)
        self.candidates.setVisible(has_candidates)
        self.review_button.setVisible(has_candidates)
        self.candidate_state.setText(message or (tr("정리 후보 {count:,}개 · 행을 선택하면 아래에 근거를 표시합니다. 환경 점검 통과는 이 목록에 후보가 있다는 뜻이 아닙니다.").format(count=len(result.candidates)) if has_candidates else empty_candidate_message(result)))
        self.candidate_folder_button.setVisible(not has_candidates)
        self.candidate_folder_button.setEnabled(result is not None)
        self.candidate_files_button.setVisible(not has_candidates)
        self.candidate_files_button.setEnabled(result is not None and result.file_sample_available)
        self.candidate_demo_button.setVisible(not has_candidates)

    def clear_metrics(self):
        self.current_result = None
        self.browse_button.setEnabled(False)
        if hasattr(self, "file_model"):
            self.file_model.set_result(None)
            self.file_info.setText(tr("새로 분석하면 큰 파일을 확인할 수 있습니다. 이 목록은 삭제 후보가 아닙니다."))
            self.file_scope = self.file_info.text()
            self.file_selection.setText(tr("파일 행을 선택하면 전체 경로를 확인합니다. 파일 삭제 선택이 아닙니다."))
        if hasattr(self, "folder_selection"):
            self.folder_selection.setText(tr("폴더 행을 선택하면 전체 경로와 크기를 확인할 수 있습니다."))
        for label in self.metric_values:
            label.setText("—")
            label.setToolTip("")

    def display(self, result):
        self.current_result = result
        self.browse_button.setEnabled(self.worker is None)
        self.file_selection.setText(tr("파일 행을 선택하면 전체 경로를 확인합니다. 파일 삭제 선택이 아닙니다."))
        self.file_model.set_result(result)
        self.file_info.setText(tr("확인된 {files:,}개 파일 중 큰 파일 {shown:,}개 · 최대 {limit:,}개만 보관합니다. 삭제 후보 판정이 아닙니다.").format(files=result.files, shown=len(result.largest_files), limit=result.file_sample_limit)
                              if result.file_sample_available else tr("이 분석 결과에는 큰 파일 정보가 없습니다. 다시 분석하면 표시됩니다."))
        if result.status != "complete" or result.issues:
            self.file_info.setText(self.file_info.text() + "\n" + tr("취소·읽기 실패·제외 범위에 따라 일부 파일이 포함되지 않을 수 있습니다. 오류·제외 범위도 확인하세요."))
        self.file_scope = self.file_info.text()
        for label, value in zip(self.metric_values, (compact_size(result.size), f"{result.files:,}", f"{len(result.candidates):,}", f"{len(result.issues):,}")):
            label.setText(value)
        self.metric_values[0].setToolTip(exact_size(result.size))
        self.folder_model.set_result(result)
        scope = self.folder_model.coverage.state(result.root)
        if scope != "complete":
            self.metric_values[0].setText(tr("확인 {size}").format(size=compact_size(result.size)) if result.size else tr("미확인"))
            self.metric_values[1].setText(tr("확인 {count:,}").format(count=result.files) if result.files else tr("미확인"))
            self.metric_values[0].setToolTip(tr("확인된 논리적 합계: ") + exact_size(result.size) + "\n" + coverage_note(scope))
        self.issue_model.set_issues([])
        self.candidates.clear()
        self.details.clear()
        self.summary.setText(tr('{status} · 확인된 {files:,}개 파일 · {size} · 오류/제외 {issues:,}건').format(status=STATUS[result.status], files=result.files, size=size_text(result.size), issues=len(result.issues)))
        if scope != "complete":
            known = tr("확인 {files:,}개 파일 · {size}").format(files=result.files, size=size_text(result.size)) if result.files or result.size else tr("확인분 없음")
            self.summary.setText(tr("{status} · {known} · 전체 크기/파일 수 미확인 · 오류/제외 {issues:,}건").format(status=STATUS[result.status], known=known, issues=len(result.issues)))
        self.summary.setToolTip(result.root + "\n" + tr("단위: 1 KB = 1,024 B. 정확한 바이트는 용량 칸의 툴팁에서 확인하세요."))
        self.issue_model.set_issues(result.issues)
        for candidate in result.candidates:
            support = (tr("개별 검증 후 실행 가능") if self.cleanup_ready and candidate.kind in self.qualified_kinds else tr("유형별 환경 확인 필요")) if candidate.kind in EXECUTABLE_KINDS else tr("목록 검토만 · 실행 미지원")
            try:
                relative = str(Path(candidate.path).relative_to(Path(result.root)))
            except ValueError:
                relative = candidate.path
            candidate_scope = self.folder_model.coverage.state(candidate.path)
            candidate_size = format_size(candidate.size) if candidate_scope == "complete" else tr("확인 {size}").format(size=format_size(candidate.size)) if candidate.size else "—"
            item = QTreeWidgetItem([relative, CATEGORIES[candidate.kind], candidate_size, support])
            item.setToolTip(0, candidate.path)
            item.setToolTip(2, tr("확인된 합계: ") + exact_size(candidate.size) + "\n" + coverage_note(candidate_scope))
            item.setData(0, Qt.ItemDataRole.UserRole, candidate)
            self.candidates.addTopLevelItem(item)
        projects = "\n".join(f"{p.kind}: {p.path} · {', '.join(p.markers)}" for p in result.projects)
        self.details.setPlainText(tr('확인된 프로젝트 표식\n') + (projects or tr('표식 없음 · 일반 폴더로 분석')) +
                                  tr('\n\n후보는 삭제 가능 판정이 아닙니다. 폴더 이름만으로 후보를 만들지 않습니다.'))
        self.filter_rows()
        self.filter_files()
        self.update_candidate_state(result)

    def candidate_selected(self, item, previous):
        self.review_button.setEnabled(item is not None and not self.worker)
        self.review_button.setText(tr('② 선택한 후보의 포함 파일 검토') if item else tr('② 후보를 선택한 뒤 포함 파일 검토'))
        if item is None:
            return
        candidate = item.data(0, Qt.ItemDataRole.UserRole)
        if candidate:
            support = tr("이 캐시 유형의 환경 시험을 통과했습니다. 포함 파일과 내용·변경 여부 검증이 필요합니다.") if self.cleanup_ready and candidate.kind in self.qualified_kinds else tr("실행 자격이 없습니다. 해당 유형의 환경 시험과 내용 검증이 필요합니다.")
            self.details.setPlainText(tr('정확한 대상: {p0}\n논리적 파일 크기: {p1} · {p2:,}개 파일\n\n근거: {p3}\n\n주의: {p4}\n\n재생성 조건: {p5}\n\n현재 지원: {p6}').format(p0=candidate.path, p1=size_text(candidate.size), p2=candidate.files, p3=candidate.evidence, p4=candidate.warning, p5=candidate.regeneration, p6=support))
            scope = self.folder_model.coverage.state(candidate.path)
            if scope != "complete":
                self.details.setPlainText(tr("표시한 크기/파일 수는 확인분이며 전체는 미확인입니다.\n") + coverage_note(scope) + "\n\n" + self.details.toPlainText())

    def folder_selected(self, index, previous):
        if not index.isValid():
            self.browse_button.setText(tr("프로젝트 폴더 내용 보기"))
            self.folder_selection.setText(tr("폴더 행을 선택하면 전체 경로와 크기를 확인할 수 있습니다."))
            return
        self.browse_button.setText(tr("선택한 폴더 내용 보기"))
        source = self.folder_proxy.mapToSource(index)
        folder = self.folder_model.folders[source.row()]
        state = self.folder_model.coverage.state(folder.path)
        self.folder_selection.setText(tr("선택한 폴더: {path}\n확인된 하위 포함 합계: {size} · 확인 {files:,}개 파일 · {scope}\n{note}").format(path=folder.path, size=exact_size(folder.size), files=folder.files, scope=COVERAGE_LABELS[state], note=coverage_note(state)))

    def start_review(self):
        item = self.candidates.currentItem()
        if not item or self.worker:
            return
        result = self.current_result
        if not result:
            return
        self.set_busy(True)
        self.worker = ReviewWorker(result, item.data(0, Qt.ItemDataRole.UserRole), self.qualified_kinds if self.cleanup_ready else ())
        self.worker.progress.connect(self.show_progress)
        self.worker.failed.connect(lambda text: QMessageBox.warning(self, tr('검토 실패'), text))
        self.worker.result.connect(self.show_review)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def browse_selected_folder(self):
        if self.current_result is None or self.worker:
            return
        index = self.folders.currentIndex()
        target = self.folder_model.folders[self.folder_proxy.mapToSource(index).row()].path if index.isValid() else self.current_result.root
        self.start_listing(target)

    def start_listing(self, target):
        if self.worker or self.current_result is None:
            return
        if self.current_result.root not in {path for path, _, _ in self.store.projects()}:
            return
        if self.browser is None:
            self.browser = DirectoryBrowser(self.current_result.root, self)
            self.browser.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.browser.open_requested.connect(self.start_listing)
            self.browser.cancel_requested.connect(self.cancel_scan)
            self.browser.finished.connect(lambda _: setattr(self, "browser", None))
            self.browser.open()
        browser = self.browser
        browser.set_loading(target)
        self.set_busy(True)
        self.summary.setText(tr("선택한 폴더의 현재 내용을 읽고 있습니다. 원본은 변경하지 않습니다."))
        self.worker = ListingWorker(self.current_result, target, protected_paths(), self.store.exclusions(self.current_result.root))
        self.worker.result.connect(lambda listing: self.listing_ready(browser, listing))
        self.worker.failed.connect(lambda message: self.listing_failed(browser, message))
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def listing_ready(self, browser, listing):
        if self.browser is browser:
            browser.show_listing(listing)
        states = {"complete": tr("목록 읽기 완료"), "limited": tr("표시 한도 도달"), "incomplete": tr("읽기 실패 포함"), "cancelled": tr("취소 · 부분 목록")}
        self.summary.setText(states.get(listing.status, listing.status) + " · " + listing.path)

    def listing_failed(self, browser, message):
        if self.browser is browser:
            browser.show_error(message)
        self.summary.setText(tr("폴더 내용 읽기 실패: ") + message)

    def file_selected(self, index, previous):
        if not index.isValid():
            return
        source = self.file_proxy.mapToSource(index)
        file = self.file_model.files[source.row()]
        self.file_selection.setText(tr("전체 경로: {path}\n크기: {size} · 분석 시점의 기록이며 삭제 대상 선택이 아닙니다.").format(path=file.path, size=exact_size(file.size)))

    def show_review(self, payload):
        review, plan = payload
        self.summary.setText(tr('후보 검토 완료 · ') + review.candidate.path)
        reasons = list(review.blocked)
        qualified = self.cleanup_ready and review.candidate.kind in self.qualified_kinds
        if not qualified:
            reasons.append(tr("이 후보 유형의 환경 시험을 통과하지 못했습니다. 유형별 점검 결과를 확인하세요.") if self.cleanup_ready else self.cleanup_reason)
        if plan is None and not reasons:
            reasons.append(tr("이 후보 유형 또는 내용은 아직 정리 실행을 지원하지 않습니다. 파일 목록만 검토할 수 있습니다."))
        dialog = ReviewDialog(review, reasons, plan is not None and qualified and not review.blocked, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.run_button.clicked.connect(lambda: self.start_cleanup(plan, dialog))
        dialog.finished.connect(self.review_closed)
        self.review_dialog = dialog
        dialog.open()

    def review_closed(self):
        self.review_dialog = None
        if self._closing:
            QTimer.singleShot(0, self.close)

    def start_environment_test(self):
        if self.worker:
            return
        message = tr("직접 만든 작은 임시 프로젝트로 링크 경계·보호 경로·휴지통 이동을 시험합니다.\n개인 프로젝트는 사용하지 않으며 시험 캐시가 Windows 휴지통에 남을 수 있습니다.\n시험 파일과 기록은 앱 데이터 폴더에 보관합니다.")
        if QMessageBox.question(self, tr("정리 환경 시험"), message,
                                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Ok:
            return
        self.cleanup_ready = False
        self.qualified_kinds = frozenset()
        self.set_busy(True)
        self.summary.setText(tr("임시 프로젝트로 정리 환경을 시험하고 있습니다."))
        self.worker = EnvironmentWorker(self.store.directory)
        self.worker.phase.connect(self.summary.setText)
        self.worker.result.connect(self.environment_result)
        self.worker.failed.connect(lambda text: QMessageBox.warning(self, tr("환경 시험 실패"), text))
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def environment_result(self, capability):
        self.last_capability = capability
        self.qualified_kinds = frozenset(capability.qualified_kinds) & EXECUTABLE_KINDS if capability.ready else frozenset()
        self.cleanup_ready = bool(self.qualified_kinds)
        self.cleanup_reason = capability.reason
        failed = ", ".join(c.label for c in capability.checks if c.status != "passed")
        self.cleanup_status.setText(tr("시험을 통과한 유형: {kinds} · 각 후보의 내용 검증과 직접 확인이 필요합니다.").format(kinds=", ".join(CATEGORIES[kind] for kind in sorted(self.qualified_kinds))) if self.cleanup_ready else
                                    tr("정리 비활성 · {failed} · 자세한 원인은 관리·도구의 환경 점검 결과에서 확인하세요.").format(failed=failed or tr("실행 조건 미충족")))
        path = self.selected()
        if path and self.current_result and self.current_result.root == path:
            self.display(self.current_result)
        self.summary.setText(capability.reason)
        self.show_environment_report()

    def show_environment_report(self):
        capability = self.last_capability
        if capability is None:
            QMessageBox.information(self, tr("환경 점검 결과"), tr("점검 기록이 없습니다. 관리·도구에서 '정리 환경 확인'을 먼저 실행하세요."))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("환경 점검 결과 · 부분 통과는 실행 승인 아님"))
        dialog.resize(820, 610)
        layout = QVBoxLayout(dialog)
        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setPlainText(capability.reason)
        summary.setMaximumHeight(110)
        layout.addWidget(summary)
        table = QTableWidget(0, 3)
        table.setMinimumHeight(220)
        table.setHorizontalHeaderLabels([tr("확인 항목"), tr("결과"), tr("자세한 원인")])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.setColumnWidth(0, 160)
        table.setColumnWidth(1, 75)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        states = {"passed": tr("통과"), "failed": tr("실패"), "skipped": tr("미실행")}
        for check in capability.checks:
            row = table.rowCount()
            table.insertRow(row)
            for col, text in enumerate((check.label, states.get(check.status, check.status), check.detail)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row, col, item)
        table.resizeRowsToContents()
        table.horizontalHeader().sectionResized.connect(lambda *_: table.resizeRowsToContents())
        layout.addWidget(table)
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        detail.setPlaceholderText(tr("점검 행을 선택하면 전체 원인과 기술 정보를 확인할 수 있습니다."))
        detail.setMaximumHeight(120)
        table.currentCellChanged.connect(lambda row, *_: detail.setPlainText(capability.checks[row].detail) if 0 <= row < len(capability.checks) else detail.clear())
        layout.addWidget(detail)
        note = QLabel(tr("점검은 앱이 새로 만든 시험 자료만 사용합니다. 일부 통과로 개인 프로젝트 정리를 활성화하지 않습니다.\n복원은 Windows 휴지통에서 직접 확인해야 하며, 이 표는 복원 검증을 의미하지 않습니다."))
        note.setWordWrap(True)
        layout.addWidget(note)
        copy = QPushButton(tr("점검 결과 복사"))
        payload = capability.reason + "\n\n" + "\n".join(f"{c.label}: {states.get(c.status, c.status)}\n{c.detail}" for c in capability.checks)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(payload))
        layout.addWidget(copy)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.open()
        self.environment_dialog = dialog

    def start_cleanup(self, plan, dialog):
        if not self.cleanup_ready or plan is None or plan.candidate.kind not in self.qualified_kinds or self.worker:
            return
        if plan.analysis.root not in {p for p, _, _ in self.store.projects()}:
            QMessageBox.warning(self, tr("정리 제한"), tr("등록 목록에서 제거된 프로젝트입니다."))
            return
        dialog.accept()
        self.set_busy(True)
        self.summary.setText(tr("실행 직전 다시 검증하고 휴지통으로 이동합니다. Windows 작업이 시작된 뒤에는 취소가 늦게 반영될 수 있습니다."))
        self.worker = CleanupWorker(plan, self.store.directory)
        self.worker.result.connect(self.cleanup_result)
        self.worker.failed.connect(self.cleanup_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def show_cleanup_history(self, job):
        self.history_job = job
        self.history_search.blockSignals(True)
        self.history_search.clear()
        self.history_search.blockSignals(False)
        self.history_search.setPlaceholderText(tr("이 작업에서 경로·실패 이유 검색") if job else tr("전체 정리 이력에서 경로·실패 이유 검색"))
        self.history_job_label.setText(tr("선택한 정리 작업: ") + (job[:12] if job else ""))
        self.history_job_label.setToolTip(job or "")
        self.history_job_label.setVisible(job is not None)
        self.history_all.setVisible(job is not None)
        self.tabs.setCurrentIndex(3)
        self.refresh_history()

    def cleanup_result(self, report):
        if report.error or not report.result or report.result.status != "succeeded":
            self.cleanup_ready = False
        self.current_result = None
        self.candidates.clear()
        self.details.clear()
        self.refresh(select=report.project, load_result=False)
        self.summary.setText(tr("정리 실행 결과를 확인하세요. 성공·실패·미확정은 항목별 기록으로 구분합니다. 최신 상태는 다시 분석하세요."))
        self.update_candidate_state(None, tr("정리 작업 후에는 다시 분석해야 최신 후보를 확인할 수 있습니다. 작업 결과는 '정리 이력'에서 확인하세요."))
        self.file_info.setText(tr("정리 전 분석 시점의 큰 파일 목록입니다. 현재 상태를 확인하려면 다시 분석하세요."))
        self.file_scope = self.file_info.text()
        self.show_cleanup_history(report.job)
        dialog = CleanupResultDialog(report, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.history_requested.connect(lambda: (self.show_cleanup_history(report.job), dialog.accept()))
        dialog.rescan_requested.connect(lambda: self.rescan_after_cleanup(report.project, dialog))
        self.cleanup_dialog = dialog
        dialog.finished.connect(lambda: setattr(self, "cleanup_dialog", None))
        dialog.open()

    def cleanup_failed(self, report):
        self.cleanup_ready = False
        self.cleanup_result(report)

    def rescan_after_cleanup(self, project, dialog):
        dialog.accept()
        def run():
            if project not in {p for p, _, _ in self.store.projects()}:
                QMessageBox.warning(self, tr("분석 제한"), tr("등록 목록에서 제거된 프로젝트입니다."))
                return
            self.refresh(select=project, load_result=False)
            self.tabs.setCurrentIndex(1)
            self.start_scan()
        if isinstance(self.worker, CleanupWorker):
            self.worker.finished.connect(run)
        elif not self.worker:
            run()

    def edit_exclusions(self):
        path = self.selected()
        if not path:
            return
        text, accepted = QInputDialog.getMultiLineText(self, tr('분석 제외 목록'), tr('프로젝트 기준 상대 경로를 한 줄에 하나씩 입력하세요.\n예: data 또는 assets/cache · 와일드카드 미지원\n변경 사항은 다음 분석부터 적용됩니다.'), "\n".join(self.store.exclusions(path)))
        if accepted:
            try:
                self.store.set_exclusions(path, list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip())))
                self.summary.setText(tr('제외 목록을 저장했습니다. 적용하려면 다시 분석하세요.'))
            except ValueError as exc:
                QMessageBox.warning(self, tr('제외 경로 오류'), str(exc))

    def show_comparison(self):
        path = self.selected()
        if path is None or self.worker:
            return
        self.set_busy(True)
        self.stop.setEnabled(False)
        self.summary.setText(tr("저장된 결과를 읽고 이전 완료 결과와 비교하고 있습니다."))
        self.worker = ComparisonWorker(self.store.directory, path)
        self.worker.result.connect(self.display_comparison)
        self.worker.failed.connect(lambda message: QMessageBox.warning(self, tr("비교 제한"), message))
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def display_comparison(self, changes):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('이전 완료 결과 대비 · 논리적 크기 변화'))
        dialog.resize(1000, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr('각 행은 하위 포함 값입니다. 행끼리 합산하지 마세요.\n변화는 휴지통 이동량이나 실제 여유 공간 증가량을 의미하지 않습니다.')))
        tree = QTableView()
        model = ComparisonModel(changes, tree)
        proxy = QSortFilterProxyModel(tree)
        proxy.setSourceModel(model)
        proxy.setSortRole(Qt.ItemDataRole.UserRole)
        tree.setModel(proxy)
        tree.setSortingEnabled(True)
        tree.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        tree.setColumnWidth(0, 550)
        layout.addWidget(tree)
        self.summary.setText(tr("이전 결과 비교가 끝났습니다. 변경 폴더: {count:,}개").format(count=len(changes)))
        if not changes:
            layout.addWidget(QLabel(tr('논리적 크기와 파일 수 변화가 없습니다. 내용 동일성을 뜻하지는 않습니다.')))
        dialog.open()
        self.comparison_dialog = dialog

    def export_report(self):
        project = self.selected()
        if not project or self.worker:
            QMessageBox.information(self, tr('보고서'), tr('저장된 분석 결과가 없습니다.'))
            return
        filters = [tr('JSON 보고서 (*.json)'), tr('폴더 요약 CSV (*.csv)'), tr('큰 파일 목록 CSV (*.csv)')]
        filename, selected_filter = QFileDialog.getSaveFileName(self, tr('새 보고서 파일 저장'), "analysis-report.json", ";;".join(filters), options=QFileDialog.Option.DontConfirmOverwrite)
        if not filename:
            return
        self.set_busy(True)
        self.stop.setEnabled(False)
        self.summary.setText(tr("보고서를 저장하고 있습니다. 화면 검색은 계속 사용할 수 있습니다."))
        self.worker = ExportWorker(self.store.directory, project, Path(filename), "files" if selected_filter == filters[2] else selected_filter == filters[1])
        self.worker.result.connect(lambda path: self.summary.setText(tr('보고서를 저장했습니다: ') + path))
        self.worker.failed.connect(lambda message: QMessageBox.warning(self, tr('보고서 저장 실패'), tr('기존 파일은 덮어쓰지 않습니다. 새 파일명을 사용하세요.\n') + message))
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def filter_rows(self):
        self.folder_proxy.setFilterFixedString(self.search.text())
        self.update_folder_search_status()

    def update_folder_search_status(self):
        if self.folder_proxy.error:
            self.folder_search_status.setText(tr("폴더 표시 실패: ") + self.folder_proxy.error)
            return
        if self.folder_proxy.worker or self.folder_proxy.timer.isActive():
            self.folder_search_status.setText(tr("폴더 검색·정렬 중… 완료 전에는 이전 목록이 보일 수 있습니다."))
            return
        self.folder_search_status.setText(tr("표시된 폴더 {shown:,}개 / 분석된 폴더 {total:,}개").format(shown=self.folder_proxy.rowCount(), total=self.folder_model.rowCount())
                                         + (tr(" · 검색 필터 적용 중") if self.search.text() else ""))

    def filter_files(self):
        self.file_proxy.setFilterFixedString(self.file_search.text())
        self.file_info.setText(self.file_scope + ("\n" + tr("검색 결과: 보관한 {total:,}개 중 {shown:,}개").format(total=self.file_model.rowCount(), shown=self.file_proxy.rowCount()) if self.file_search.text() else ""))

    def closeEvent(self, event):
        if getattr(self, "cleanup_dialog", None):
            self.cleanup_dialog.reject()
        if self.worker:
            self.cancel_scan()
            self.summary.setText(tr('작업 중단 또는 저장이 끝난 후 창을 다시 닫아주세요.'))
            event.ignore()
        elif getattr(self, "review_dialog", None) and self.review_dialog.worker:
            self._closing = True
            self._history_pending = False
            self.history_search_timer.stop()
            self.setEnabled(False)
            self.review_dialog.reject()
            event.ignore()
        elif self.folder_proxy.worker:
            self._closing = True
            self._history_pending = False
            self.history_search_timer.stop()
            self.folder_proxy.shutdown()
            self.setEnabled(False)
            event.ignore()
        elif self.history_worker:
            self._closing = True
            self._history_pending = False
            self.history_search_timer.stop()
            self.history_worker.cancel.set()
            self.setEnabled(False)
            event.ignore()
        else:
            if getattr(self, "review_dialog", None):
                self.review_dialog.reject()
            self._closing = True
            self.folder_proxy.shutdown()
            self.history_search_timer.stop()
            self.store.close()
            event.accept()


