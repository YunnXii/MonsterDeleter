from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QImage, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .resources import resource_path


PET_HEIGHT = 145
DRAG_THRESHOLD_PX = 6
DEFAULT_MARGIN_PX = 18
CLICK_STREAK_SECONDS = 1.4
BUBBLE_HIDE_MS = 2600


class SpeechBubble(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(
            "QLabel{background:rgba(255,255,255,248);color:#1f252b;"
            "border:1px solid rgba(31,37,43,28);border-radius:14px;"
            "padding:9px 14px;font-family:'Microsoft YaHei UI';"
            "font-size:13px;font-weight:600;}"
        )
        self.label.setMaximumWidth(260)
        layout.addWidget(self.label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str, anchor: QWidget) -> None:
        self.label.setText(text)
        self.label.adjustSize()
        self.adjustSize()

        anchor_rect = anchor.frameGeometry()
        anchor_global = anchor_rect.center()
        screen = QApplication.screenAt(anchor_global) or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        x = anchor_rect.center().x() - self.width() // 2
        y = anchor_rect.top() - self.height() - 4

        if y < available.top() + 6:
            y = anchor_rect.bottom() + 4
        x = max(available.left() + 6, min(available.right() - self.width() - 6, x))
        y = max(available.top() + 6, min(available.bottom() - self.height() - 6, y))

        self.move(x, y)
        self.show()
        self.raise_()
        self._hide_timer.start(BUBBLE_HIDE_MS)


class PetWidget(QWidget):
    interaction_requested = pyqtSignal(int)
    context_menu_requested = pyqtSignal(QPoint)
    position_committed = pyqtSignal(QPoint)

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self._pixmap = self._load_front_pose()
        self.setFixedSize(self._pixmap.width() + 8, self._pixmap.height() + 8)

        self.bubble = SpeechBubble()
        self._press_global: QPoint | None = None
        self._press_window: QPoint | None = None
        self._dragging = False
        self._last_click_at = 0.0
        self._click_streak = 0

    @staticmethod
    def _load_front_pose() -> QPixmap:
        path = resource_path("characters", "jiaqi", "sprites", "walk.png")
        sheet = QImage(str(path))
        if sheet.isNull() or sheet.width() % 9 != 0:
            raise RuntimeError(f"无法加载常驻小人精灵图：{path}")

        frame_width = sheet.width() // 9
        frame = sheet.copy(frame_width * 8, 0, frame_width, sheet.height())
        pixmap = QPixmap.fromImage(frame).scaled(
            10000,
            PET_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return pixmap

    def show_message(self, text: str) -> None:
        if not self.isVisible():
            self.show()
        self.bubble.show_message(text, self)

    def visual_rect_global(self) -> QRect:
        """Return the exact on-screen rectangle occupied by the painted sprite."""
        x = self.x() + (self.width() - self._pixmap.width()) // 2
        y = self.y() + self.height() - self._pixmap.height() - 4
        return QRect(x, y, self._pixmap.width(), self._pixmap.height())

    def foot_anchor_global(self) -> QPoint:
        """Return the painted sprite's global bottom-centre baseline anchor."""
        rect = self.visual_rect_global()
        return QPoint(
            rect.x() + rect.width() // 2,
            rect.y() + rect.height(),
        )

    def snap_to_default(self) -> None:
        center = self.frameGeometry().center()
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            area.right() - self.width() - DEFAULT_MARGIN_PX + 1,
            area.bottom() - self.height() - DEFAULT_MARGIN_PX + 1,
        )
        self.position_committed.emit(self.pos())

    def restore_or_default(self, saved: QPoint | None) -> None:
        if saved is not None and self._position_is_on_screen(saved):
            self.move(saved)
        else:
            self.snap_to_default()

    def _position_is_on_screen(self, point: QPoint) -> bool:
        center = QPoint(point.x() + self.width() // 2, point.y() + self.height() // 2)
        return any(screen.availableGeometry().contains(center) for screen in QApplication.screens())

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = (self.width() - self._pixmap.width()) // 2
        y = self.height() - self._pixmap.height() - 4
        painter.drawPixmap(x, y, self._pixmap)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_window = self.pos()
            self._dragging = False
            self.bubble.hide()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if (
            self._press_global is not None
            and self._press_window is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            current = event.globalPosition().toPoint()
            delta = current - self._press_global
            if not self._dragging and delta.manhattanLength() >= DRAG_THRESHOLD_PX:
                self._dragging = True
            if self._dragging:
                self.move(self._press_window + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() != Qt.MouseButton.LeftButton or self._press_global is None:
            super().mouseReleaseEvent(event)
            return

        was_dragging = self._dragging
        self._press_global = None
        self._press_window = None
        self._dragging = False

        if was_dragging:
            self._keep_center_on_a_screen()
            self.position_committed.emit(self.pos())
        else:
            now = time.monotonic()
            if now - self._last_click_at <= CLICK_STREAK_SECONDS:
                self._click_streak += 1
            else:
                self._click_streak = 1
            self._last_click_at = now
            self.interaction_requested.emit(self._click_streak)
        event.accept()

    def _keep_center_on_a_screen(self) -> None:
        if self._position_is_on_screen(self.pos()):
            return
        self.snap_to_default()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802 - Qt API
        self.bubble.hide()
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.bubble.hide()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.bubble.close()
        super().closeEvent(event)
