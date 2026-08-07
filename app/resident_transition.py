from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .resources import resource_path


GROW_DURATION_MS = 210
SHRINK_DURATION_MS = 180


def rect_from_foot(foot: QPoint, width: int, height: int) -> QRect:
    """Build a global rectangle whose bottom-centre is the supplied foot anchor."""
    return QRect(
        foot.x() - width // 2,
        foot.y() - height,
        width,
        height,
    )


def foot_from_rect(rect: QRect) -> QPoint:
    return QPoint(
        rect.x() + rect.width() // 2,
        rect.y() + rect.height(),
    )


class ResidentMorphWidget(QWidget):
    """Scale the front pose between pet and execution sizes without foot drift."""

    finished = pyqtSignal()

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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._frame = self._load_front_frame()
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.finished.connect(self.finished.emit)

    @staticmethod
    def _load_front_frame() -> QPixmap:
        path = resource_path("characters", "jiaqi", "sprites", "walk.png")
        sheet = QImage(str(path))
        if sheet.isNull() or sheet.width() % 9 != 0:
            raise RuntimeError(f"无法加载常驻过渡精灵图：{path}")
        frame_width = sheet.width() // 9
        return QPixmap.fromImage(sheet.copy(frame_width * 8, 0, frame_width, sheet.height()))

    def start(
        self,
        start_rect: QRect,
        end_rect: QRect,
        *,
        duration_ms: int,
        easing: QEasingCurve.Type,
    ) -> None:
        self._animation.stop()
        self.setGeometry(start_rect)
        self.show()
        self.raise_()

        self._animation.setDuration(max(1, duration_ms))
        self._animation.setStartValue(start_rect)
        self._animation.setEndValue(end_rect)
        self._animation.setEasingCurve(easing)
        self._animation.start()

    def stop(self) -> None:
        self._animation.stop()
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self._frame)
