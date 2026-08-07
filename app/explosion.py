from __future__ import annotations

import math

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


class ExplosionWidget(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(190, 190)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def play(self) -> None:
        self._frame = 0
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def _advance(self) -> None:
        self._frame += 1
        if self._frame >= 14:
            self._timer.stop()
            self.hide()
            self.finished.emit()
            return
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center_x = self.width() / 2
        center_y = self.height() / 2
        progress = self._frame / 13
        radius = 22 + progress * 63
        alpha = int(255 * (1 - progress * 0.72))

        path = QPainterPath()
        points = 24
        for i in range(points):
            angle = math.tau * i / points
            spike = 1.0 if i % 2 == 0 else 0.54
            wobble = 1 + math.sin(i * 2.7 + self._frame) * 0.08
            r = radius * spike * wobble
            x = center_x + math.cos(angle) * r
            y = center_y + math.sin(angle) * r
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()

        painter.setPen(QPen(QColor(255, 115, 0, alpha), 5))
        painter.setBrush(QColor(255, 210, 55, alpha))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(255, 245, 220, alpha), 5))
        painter.drawEllipse(
            int(center_x - radius * 0.24),
            int(center_y - radius * 0.24),
            int(radius * 0.48),
            int(radius * 0.48),
        )
