from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QWidget

from .character import CharacterConfig
from .chibi_avatar import ChibiAvatar


class KickCalibrationOverlay(QWidget):
    """Interactive visual calibrator for the kick impact anchor.

    The red crosshair is the desktop click/impact point. Arrow keys move the
    character artwork around that fixed point; the resulting impact_x/y values
    are shown live and printed on Enter. Nothing is written to disk.
    """

    def __init__(self, config: CharacterConfig) -> None:
        super().__init__()
        self.config = config
        self.impact_x = config.impact_x
        self.impact_y = config.impact_y

        self.setWindowTitle("家琦 Kick 命中校准")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())

        # Ghost: the exact walk frame used while waiting for confirmation.
        self.wait_pose = ChibiAvatar(config, self)
        self.wait_pose.play_waiting_front()
        self.wait_pose.stop()
        ghost = QGraphicsOpacityEffect(self.wait_pose)
        ghost.setOpacity(0.28)
        self.wait_pose.setGraphicsEffect(ghost)
        self.wait_pose.show()

        # Main pose: freeze Kick frame 5, the only impact frame in runtime.
        self.kick_pose = ChibiAvatar(config, self)
        self.kick_pose.play_kick()
        self.kick_pose._timer.stop()  # calibration-only freeze; no animation loop
        self.kick_pose._sprite_frame = 4  # source Kick frame 5
        self.kick_pose.update()
        self.kick_pose.show()

        self.info = QLabel(self)
        self.info.setStyleSheet(
            "color:white;background:rgba(10,14,20,210);border-radius:14px;"
            "padding:14px 18px;font-family:'Microsoft YaHei UI';font-size:16px;"
        )

        self._refresh_layout()

    def _target_point(self) -> QPoint:
        return QPoint(round(self.width() * 0.68), round(self.height() * 0.56))

    def _refresh_layout(self) -> None:
        target = self._target_point()
        top_left = QPoint(target.x() - self.impact_x, target.y() - self.impact_y)
        self.wait_pose.move(top_left)
        self.kick_pose.move(top_left)

        self.info.setText(
            "Kick 第5帧命中校准\n"
            f"impact_x = {self.impact_x}    impact_y = {self.impact_y}\n\n"
            "方向键：移动人物 1px    Shift + 方向键：10px\n"
            "红十字：目标点击位置    半透明：Walk 第9帧站姿参考\n"
            "Enter：打印最终值并退出    R：恢复当前配置    Esc：退出"
        )
        self.info.adjustSize()
        self.info.move(28, 28)
        self.info.raise_()
        self.kick_pose.raise_()
        self.info.raise_()
        self.update()

    def move_pose(self, dx: int, dy: int) -> None:
        """Move the artwork while keeping the target crosshair fixed."""
        # avatar_x = target_x - impact_x, so moving artwork right decreases X.
        self.impact_x = max(0, min(self.config.width, self.impact_x - dx))
        self.impact_y = max(0, min(self.config.height, self.impact_y - dy))
        self._refresh_layout()

    def reset_values(self) -> None:
        self.impact_x = self.config.impact_x
        self.impact_y = self.config.impact_y
        self._refresh_layout()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        key = event.key()

        if key == Qt.Key.Key_Left:
            self.move_pose(-step, 0)
        elif key == Qt.Key.Key_Right:
            self.move_pose(step, 0)
        elif key == Qt.Key.Key_Up:
            self.move_pose(0, -step)
        elif key == Qt.Key.Key_Down:
            self.move_pose(0, step)
        elif key == Qt.Key.Key_R:
            self.reset_values()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            print("=== Kick Calibration Result ===")
            print(f'  "impact_x": {self.impact_x},')
            print(f'  "impact_y": {self.impact_y},')
            QApplication.instance().quit()
        elif key == Qt.Key.Key_Escape:
            QApplication.instance().quit()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 12, 18, 205))

        target = self._target_point()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 66, 82), 3))
        painter.drawEllipse(target, 15, 15)
        painter.drawLine(target.x() - 30, target.y(), target.x() + 30, target.y())
        painter.drawLine(target.x(), target.y() - 30, target.x(), target.y() + 30)

        painter.setPen(QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine))
        painter.drawLine(target.x(), 0, target.x(), self.height())
        painter.drawLine(0, target.y(), self.width(), target.y())
