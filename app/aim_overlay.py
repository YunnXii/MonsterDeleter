from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget


PROBE_INTERVAL_MS = 140
CURSOR_RADIUS = 15
LABEL_OFFSET = QPoint(22, 22)


class AimOverlay(QWidget):
    """Mouse-transparent visual layer for real aim mode.

    Input is captured by AimInputHook instead of this window, which means UI
    Automation still hit-tests the real Desktop / Explorer item underneath.
    """

    probe_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None)
        primary = QApplication.primaryScreen()
        if primary is None:
            raise RuntimeError("没有可用显示器")

        self._virtual_geometry = primary.virtualGeometry()
        self.setGeometry(self._virtual_geometry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._cursor_global = QCursor.pos()
        self._text = "瞄准一个倒霉文件"
        self._valid = False
        self._resolving = False

        self._paint_timer = QTimer(self)
        self._paint_timer.setInterval(16)
        self._paint_timer.timeout.connect(self._track_cursor)

        self._probe_timer = QTimer(self)
        self._probe_timer.setInterval(PROBE_INTERVAL_MS)
        self._probe_timer.timeout.connect(self.probe_requested.emit)

    def start(self) -> None:
        self._cursor_global = QCursor.pos()
        self.show()
        self.raise_()
        self._paint_timer.start()
        self._probe_timer.start()
        QTimer.singleShot(0, self.probe_requested.emit)
        self.update()

    def stop(self) -> None:
        self._paint_timer.stop()
        self._probe_timer.stop()
        self.hide()

    def set_preview(self, text: str, *, valid: bool) -> None:
        self._text = text or "这儿没东西，瞄准点。"
        self._valid = bool(valid)
        self._resolving = False
        self.update()

    def set_resolving(self, text: str = "我看看……") -> None:
        self._text = text
        self._valid = False
        self._resolving = True
        self.update()

    def _track_cursor(self) -> None:
        point = QCursor.pos()
        if point != self._cursor_global:
            self._cursor_global = point
            self.update()

    def _cursor_local(self) -> QPoint:
        return self._cursor_global - self._virtual_geometry.topLeft()

    def _label_rect(self, painter: QPainter, cursor: QPoint) -> QRect:
        font = QFont("Microsoft YaHei UI", 11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_width = min(420, max(120, metrics.horizontalAdvance(self._text) + 28))
        text_height = metrics.height() + 20

        x = cursor.x() + LABEL_OFFSET.x()
        y = cursor.y() + LABEL_OFFSET.y()
        if x + text_width > self.width() - 8:
            x = cursor.x() - text_width - LABEL_OFFSET.x()
        if y + text_height > self.height() - 8:
            y = cursor.y() - text_height - LABEL_OFFSET.y()
        x = max(8, min(self.width() - text_width - 8, x))
        y = max(8, min(self.height() - text_height - 8, y))
        return QRect(x, y, text_width, text_height)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cursor = self._cursor_local()

        accent = QColor(83, 214, 126) if self._valid else QColor(255, 90, 90)
        if self._resolving:
            accent = QColor(255, 196, 76)

        painter.setPen(QPen(accent, 2.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            cursor.x() - CURSOR_RADIUS,
            cursor.y() - CURSOR_RADIUS,
            CURSOR_RADIUS * 2,
            CURSOR_RADIUS * 2,
        )
        gap = 6
        arm = 24
        painter.drawLine(cursor.x(), cursor.y() - arm, cursor.x(), cursor.y() - gap)
        painter.drawLine(cursor.x(), cursor.y() + gap, cursor.x(), cursor.y() + arm)
        painter.drawLine(cursor.x() - arm, cursor.y(), cursor.x() - gap, cursor.y())
        painter.drawLine(cursor.x() + gap, cursor.y(), cursor.x() + arm, cursor.y())

        rect = self._label_rect(painter, cursor)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 24, 29, 224))
        painter.drawRoundedRect(rect, 12, 12)
        painter.setPen(QColor(245, 247, 249))
        painter.drawText(
            rect.adjusted(14, 6, -14, -6),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._text,
        )

        hint = "左键确定 · 右键 / Esc 取消"
        hint_font = QFont("Microsoft YaHei UI", 9)
        painter.setFont(hint_font)
        hint_metrics = painter.fontMetrics()
        hint_width = hint_metrics.horizontalAdvance(hint) + 22
        hint_rect = QRect(
            max(8, min(self.width() - hint_width - 8, rect.x())),
            min(self.height() - 34, rect.bottom() + 6),
            hint_width,
            28,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 24, 29, 188))
        painter.drawRoundedRect(hint_rect, 10, 10)
        painter.setPen(QColor(220, 224, 228))
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, hint)
