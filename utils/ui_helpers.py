# Project Path: utils/ui_helpers.py
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QTableWidget, QToolTip
)


class SmartTooltipTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)
        self._last_tooltip_text = ""

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        item = self.itemAt(pos)
        if item:
            rect = self.visualItemRect(item)
            fm = QFontMetrics(item.font() if item.font() else self.font())
            text = item.text()
            text_width = fm.horizontalAdvance(text)
            cell_width = rect.width() - 6

            if text_width > cell_width:
                if self._last_tooltip_text != text:
                    item.setToolTip(text)
                    self._last_tooltip_text = text
            else:
                if self._last_tooltip_text != "":
                    item.setToolTip("")
                    self._last_tooltip_text = ""
        else:
            if self._last_tooltip_text != "":
                self._last_tooltip_text = ""
                QToolTip.hideText()
        super().mouseMoveEvent(event)
