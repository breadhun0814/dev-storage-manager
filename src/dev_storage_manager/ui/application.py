import os
from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase
from dev_storage_manager.i18n import get_language


def configure_font(app):
    preferred = {"en": "Segoe UI", "ja": "Yu Gothic UI", "zh_CN": "Microsoft YaHei UI", "vi": "Segoe UI"}.get(get_language())
    if preferred and preferred in QFontDatabase.families():
        app.setFont(QFont(preferred, 10))
        return
    # Explicit Korean fallback also works in Qt offscreen verification.
    font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / "malgun.ttf"
    if font.is_file():
        index = QFontDatabase.addApplicationFont(str(font))
        families = QFontDatabase.applicationFontFamilies(index)
        if families:
            app.setFont(QFont(families[0], 10))
