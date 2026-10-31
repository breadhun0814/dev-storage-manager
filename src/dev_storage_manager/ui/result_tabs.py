"""Fit the active result page before asking the outer area to scroll."""
from PySide6.QtWidgets import QTabWidget


class ResultTabs(QTabWidget):
    def heightForWidth(self, width):
        page = self.currentWidget()
        if page is None:
            return super().heightForWidth(width)
        layout = page.layout()
        height = layout.minimumHeightForWidth(max(1, width - 4)) if layout else -1
        if height < 0:
            height = page.minimumSizeHint().height()
        # The stylesheet adds 10 px above the page, plus its frame boundary.
        return max(self.minimumHeight(), height + self.tabBar().sizeHint().height() + 12)
