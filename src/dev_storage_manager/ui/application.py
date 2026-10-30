import os
from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase


def configure_font(app):
    # Explicit Korean fallback also works in Qt offscreen verification.
    font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / "malgun.ttf"
    if font.is_file():
        index = QFontDatabase.addApplicationFont(str(font))
        families = QFontDatabase.applicationFontFamilies(index)
        if families:
            app.setFont(QFont(families[0], 10))
