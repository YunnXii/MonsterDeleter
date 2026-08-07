from __future__ import annotations

import math
from enum import Enum, auto

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from .character import CharacterConfig


class AvatarAction(Enum):
    IDLE = auto()
    WALK = auto()
    KICK = auto()
    VICTORY = auto()


class ChibiAvatar(QWidget):
    animation_finished = pyqtSignal()
    impact = pyqtSignal()

    def __init__(self, config: CharacterConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setFixedSize(config.width, config.height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._action = AvatarAction.IDLE
        self._frame = 0
        self._duration = 1
        self._loop = True
        self._facing_right = True
        self._impact_sent = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.setInterval(max(1, 1000 // config.fps))

    @property
    def current_action(self) -> AvatarAction:
        return self._action

    def set_facing_right(self, value: bool) -> None:
        self._facing_right = value
        self.update()

    def play_idle(self) -> None:
        self._start(AvatarAction.IDLE, duration=24, loop=True)

    def play_walk(self) -> None:
        self._start(AvatarAction.WALK, duration=16, loop=True)

    def play_kick(self) -> None:
        self._impact_sent = False
        self._start(AvatarAction.KICK, duration=18, loop=False)

    def play_victory(self) -> None:
        self._start(AvatarAction.VICTORY, duration=18, loop=False)

    def stop(self) -> None:
        self._timer.stop()

    def _start(self, action: AvatarAction, *, duration: int, loop: bool) -> None:
        self._action = action
        self._frame = 0
        self._duration = max(1, duration)
        self._loop = loop
        self._timer.start()
        self.update()

    def _advance(self) -> None:
        self._frame += 1
        if self._action is AvatarAction.KICK and self._frame >= 10 and not self._impact_sent:
            self._impact_sent = True
            self.impact.emit()

        if self._frame >= self._duration:
            if self._loop:
                self._frame = 0
            else:
                self._timer.stop()
                self._frame = self._duration - 1
                self.update()
                self.animation_finished.emit()
                return
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self._facing_right:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        self._draw_avatar(painter)

    def _pose(self) -> tuple[float, float, float, float, float, float]:
        phase = (self._frame / max(1, self._duration)) * math.tau
        if self._action is AvatarAction.WALK:
            swing = math.sin(phase) * 20
            return abs(math.sin(phase * 2)) * 3, -swing, swing, swing, -swing, 0
        if self._action is AvatarAction.KICK:
            t = self._frame / max(1, self._duration - 1)
            if t < 0.35:
                anticipation = t / 0.35
                return anticipation * 4, -12, 20, -8, 20, 0
            if t < 0.65:
                strike = (t - 0.35) / 0.30
                return 3 - strike * 2, 15, -20, -15, -70 * strike, 70 * strike
            recover = (t - 0.65) / 0.35
            return 1, 5, -5, -5, -70 * (1 - recover), 70 * (1 - recover)
        if self._action is AvatarAction.VICTORY:
            bounce = abs(math.sin(phase)) * 5
            return -bounce, -55, -35, 3, -3, 0
        return math.sin(phase) * 1.5, -4, 4, 2, -2, 0

    @staticmethod
    def _rotate(point: QPointF, origin: QPointF, degrees: float) -> QPointF:
        radians = math.radians(degrees)
        sin_v, cos_v = math.sin(radians), math.cos(radians)
        px, py = point.x() - origin.x(), point.y() - origin.y()
        return QPointF(origin.x() + px * cos_v - py * sin_v, origin.y() + px * sin_v + py * cos_v)

    def _draw_limb(
        self,
        painter: QPainter,
        start: QPointF,
        length: float,
        angle: float,
        color: QColor,
        width: float,
    ) -> QPointF:
        end = self._rotate(QPointF(start.x(), start.y() + length), start, angle)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(start, end)
        return end

    def _draw_avatar(self, painter: QPainter) -> None:
        look = self.config.look
        skin = QColor(look.skin)
        hair = QColor(look.hair)
        shirt = QColor(look.shirt)
        shirt_dark = QColor(look.shirt_dark)
        pants = QColor(look.pants)
        shoes = QColor(look.shoes)
        glasses = QColor(look.glasses)
        glasses_accent = QColor(look.glasses_accent)

        bob, arm_l, arm_r, leg_l, leg_r, kick_extension = self._pose()
        painter.translate(0, bob)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 42))
        painter.drawEllipse(QRectF(64, 286, 150 + kick_extension * 0.35, 18))

        hip_left = QPointF(116, 230)
        hip_right = QPointF(158, 230)
        left_foot = self._draw_limb(painter, hip_left, 58, leg_l, pants, 18)
        right_foot = self._draw_limb(painter, hip_right, 58 + kick_extension, leg_r, pants, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shoes)
        painter.drawRoundedRect(QRectF(left_foot.x() - 14, left_foot.y() - 5, 31, 16), 8, 8)
        painter.drawRoundedRect(QRectF(right_foot.x() - 14, right_foot.y() - 5, 34, 16), 8, 8)

        body = QPainterPath()
        body.moveTo(91, 143)
        body.quadTo(137, 124, 184, 143)
        body.lineTo(177, 235)
        body.quadTo(137, 248, 98, 235)
        body.closeSubpath()
        painter.setBrush(shirt)
        painter.setPen(QPen(shirt_dark, 3))
        painter.drawPath(body)

        left_hand = self._draw_limb(painter, QPointF(99, 155), 62, arm_l, shirt, 20)
        right_hand = self._draw_limb(painter, QPointF(176, 155), 62, arm_r, shirt, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(skin)
        painter.drawEllipse(QRectF(left_hand.x() - 8, left_hand.y() - 7, 16, 16))
        painter.drawEllipse(QRectF(right_hand.x() - 8, right_hand.y() - 7, 16, 16))

        painter.setBrush(shirt_dark)
        collar_l = QPainterPath()
        collar_l.moveTo(118, 137)
        collar_l.lineTo(136, 157)
        collar_l.lineTo(119, 166)
        collar_l.closeSubpath()
        collar_r = QPainterPath()
        collar_r.moveTo(156, 137)
        collar_r.lineTo(137, 157)
        collar_r.lineTo(155, 166)
        collar_r.closeSubpath()
        painter.drawPath(collar_l)
        painter.drawPath(collar_r)
        painter.setBrush(QColor("#D7DBDD"))
        painter.drawEllipse(QRectF(134, 168, 6, 6))
        painter.drawEllipse(QRectF(134, 181, 6, 6))
        painter.setPen(QPen(shirt_dark, 2))
        painter.drawArc(QRectF(110, 190, 18, 10), 0, 180 * 16)
        painter.drawLine(QPointF(116, 195), QPointF(121, 188))

        painter.setPen(QPen(QColor("#B98167"), 2))
        painter.setBrush(skin)
        painter.drawEllipse(QRectF(62, 30, 151, 132))
        painter.drawEllipse(QRectF(54, 80, 20, 33))
        painter.drawEllipse(QRectF(202, 80, 20, 33))

        hair_path = QPainterPath()
        hair_path.moveTo(67, 91)
        hair_path.cubicTo(63, 47, 91, 19, 132, 18)
        hair_path.cubicTo(171, 13, 205, 36, 211, 78)
        hair_path.cubicTo(192, 60, 174, 53, 154, 56)
        hair_path.cubicTo(130, 58, 117, 47, 92, 66)
        hair_path.cubicTo(80, 74, 74, 85, 67, 91)
        hair_path.closeSubpath()
        painter.setPen(QPen(hair, 2))
        painter.setBrush(hair)
        painter.drawPath(hair_path)
        painter.setPen(QPen(QColor("#454545"), 3))
        painter.drawArc(QRectF(92, 29, 90, 48), 10 * 16, 135 * 16)
        painter.drawArc(QRectF(107, 25, 78, 54), 15 * 16, 128 * 16)

        painter.setBrush(QColor(255, 255, 255, 22))
        painter.setPen(QPen(glasses, 4))
        painter.drawRoundedRect(QRectF(78, 79, 53, 38), 10, 10)
        painter.drawRoundedRect(QRectF(145, 79, 53, 38), 10, 10)
        painter.setPen(QPen(glasses_accent, 3))
        painter.drawLine(QPointF(131, 92), QPointF(145, 92))
        painter.drawLine(QPointF(78, 86), QPointF(67, 82))
        painter.drawLine(QPointF(198, 86), QPointF(210, 82))

        blink = self._action is AvatarAction.VICTORY and self._frame % 8 in (0, 1)
        painter.setPen(QPen(QColor("#2A211E"), 3))
        if blink:
            painter.drawLine(QPointF(95, 97), QPointF(112, 97))
            painter.drawLine(QPointF(163, 97), QPointF(180, 97))
        else:
            painter.setBrush(QColor("#2A211E"))
            painter.drawEllipse(QRectF(100, 92, 8, 8))
            painter.drawEllipse(QRectF(168, 92, 8, 8))
        painter.setPen(QPen(QColor("#9B5E58"), 3))
        if self._action is AvatarAction.KICK:
            painter.drawLine(QPointF(125, 128), QPointF(151, 126))
        else:
            painter.drawArc(QRectF(119, 112, 38, 24), 200 * 16, 140 * 16)
