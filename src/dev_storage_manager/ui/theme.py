"""A quiet, readable Widgets theme; all components remain native Qt widgets."""
STYLE = """
QMainWindow, QDialog, QScrollArea, QScrollArea > QWidget > QWidget { background: #f4f6fa; }
QWidget { color: #18243b; font-size: 13px; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #13213a; }
QLabel#subtitle, QLabel#notice { color: #64748b; font-size: 12px; }
QLabel#sectionTitle { color: #52647f; font-weight: 600; }
QLabel#localBadge { color: #2563eb; background: #e8efff; border-radius: 10px; padding: 7px 12px; font-weight: 600; }
QFrame#metricCard { background: white; border: 1px solid #e2e7f0; border-radius: 12px; }
QLabel#metricLabel { color: #64748b; font-size: 11px; }
QLabel#metricValue { color: #162945; font-size: 21px; font-weight: 700; }
QLabel#summary { background: #edf3ff; color: #284a7d; border: 1px solid #dce7fa; border-radius: 10px; padding: 10px 14px; }
QPushButton { background: white; border: 1px solid #dbe2ec; border-radius: 7px; padding: 8px 13px; font-weight: 600; min-height: 18px; }
QPushButton:hover { background: #eef3fc; border-color: #9fb5db; }
QPushButton:pressed { background: #dce7fa; }
QPushButton:focus { border: 2px solid #7aa4f8; }
QPushButton:disabled { background: #f0f2f6; color: #9aa5b6; border-color: #e3e7ef; }
QPushButton#primary { background: #2864e8; border-color: #2864e8; color: white; }
QPushButton#primary:hover { background: #1951ca; }
QPushButton#primary:disabled { background: #baccee; border-color: #baccee; color: #edf3ff; }
QPushButton#danger { color: #b34b4b; }
QLineEdit { background: white; border: 1px solid #dbe2ec; border-radius: 8px; padding: 10px 12px; selection-background-color: #dce8ff; }
QLineEdit:focus { border-color: #4b82ee; }
QComboBox { background: white; border: 1px solid #dbe2ec; border-radius: 8px; padding: 3px 8px; min-height: 30px; }
QComboBox QLineEdit { border: none; padding: 3px; }
QTableView, QTreeWidget { background: white; alternate-background-color: #f8faff; border: 1px solid #e0e6ef; border-radius: 9px; gridline-color: #edf0f6; selection-background-color: #e5eeff; selection-color: #1746a0; outline: none; }
QTableView::item, QTreeWidget::item { padding: 7px; border-bottom: 1px solid #f0f3f8; }
QTableView::item:selected, QTreeWidget::item:selected { background: #e5eeff; color: #1746a0; }
QHeaderView::section { background: #f8fafd; color: #65748b; border: none; border-bottom: 1px solid #e1e7f0; padding: 10px 8px; font-weight: 600; font-size: 11px; }
QTableCornerButton::section { background: #f8fafd; border: none; }
QPlainTextEdit { background: #f8fafd; border: 1px solid #e1e7f0; border-radius: 9px; padding: 10px; selection-background-color: #dce8ff; }
QTabWidget::pane { border: none; background: transparent; padding-top: 10px; }
QTabBar::tab { background: transparent; color: #718096; padding: 10px 20px; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: #245edb; border-bottom-color: #2864e8; }
QTabBar::tab:hover { background: #eaf0fc; border-radius: 5px; }
QScrollBar:vertical { background: #f4f6fa; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c7d0e0; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: #e3eafa; border: none; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #3c78ed; border-radius: 2px; }
QToolTip { background: #172b48; color: white; padding: 7px; border: none; }
"""
