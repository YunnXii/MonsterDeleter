from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QFileInfo, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QFileIconProvider, QStyle, QWidget


ICON_PIXELS = 58
CANVAS_PIXELS = 96
TICK_MS = 16
HORIZONTAL_SPEED = 1050.0
UPWARD_SPEED = 680.0
GRAVITY = 1650.0
ANGULAR_SPEED = 720.0
MAX_FLIGHT_SECONDS = 2.5


def system_icon_pixmap(target: Path | None, size: int = ICON_PIXELS) -> QPixmap:
    """Capture the Windows/system icon before the target is moved away.

    The effect is purely visual: Explorer remains responsible for the real
    desktop item. In demo mode (or when no path is available), use the normal
    generic file icon so the projectile can still be tested safely.
    """
    icon = None
    if target is not None and target.exists():
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(str(target)))

    if icon is None or icon.isNull():
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must exist before requesting a system icon")
        icon = app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    return icon.pixmap(size, size)


class FlyingIcon(QWidget):
    """A lightweight projectile sprite for the file/folder icon.

    Motion follows a simple ballistic model:
    - constant horizontal velocity;
    - constant downward gravity;
    - constant angular velocity.

    It never manipulates Explorer's actual desktop icon position.
    """

    finished = pyqtSignal()

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(CANVAS_PIXELS, CANVAS_PIXELS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._pixmap = pixmap.scaled(
            ICON_PIXELS,
            ICON_PIXELS,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()

        self._x = 0.0
        self._y = 0.0
        self._vx = 0.0
        self._vy = 0.0
        self._angle = 0.0
        self._angular_velocity = 0.0
        self._flight_seconds = 0.0
        self.hide()

    @property
    def velocity(self) -> tuple[float, float]:
        return self._vx, self._vy

    @property
    def angle(self) -> float:
        return self._angle

    def launch(self, center: QPoint, *, direction: int) -> None:
        direction = 1 if direction >= 0 else -1
        self._x = center.x() - self.width() / 2
        self._y = center.y() - self.height() / 2
        self._vx = HORIZONTAL_SPEED * direction
        self._vy = -UPWARD_SPEED
        self._angle = 0.0
        self._angular_velocity = ANGULAR_SPEED * direction
        self._flight_seconds = 0.0

        self.move(round(self._x), round(self._y))
        self.show()
        self.raise_()
        self._clock.start()
        self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        elapsed_ms = self._clock.restart()
        if elapsed_ms <= 0:
            return
        self._advance_physics(min(0.05, elapsed_ms / 1000.0))

    def _advance_physics(self, dt: float) -> None:
        """Advance one deterministic projectile step; kept separate for tests."""
        if dt <= 0:
            return

        self._flight_seconds += dt
        self._vy += GRAVITY * dt
        self._x += self._vx * dt
        self._y += self._vy * dt
        self._angle = (self._angle + self._angular_velocity * dt) % 360.0

        self.move(round(self._x), round(self._y))
        self.update()

        if self._is_outside_stage() or self._flight_seconds >= MAX_FLIGHT_SECONDS:
            self.stop()
            self.finished.emit()

    def _is_outside_stage(self) -> bool:
        parent = self.parentWidget()
        if parent is None:
            return False

        margin = self.width()
        return (
            self._x > parent.width() + margin
            or self._x + self.width() < -margin
            or self._y > parent.height() + margin
            or self._y + self.height() < -margin
        )

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.drawPixmap(
            -self._pixmap.width() // 2,
            -self._pixmap.height() // 2,
            self._pixmap,
        )
