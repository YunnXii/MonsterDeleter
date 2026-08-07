from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .character import CharacterConfig
from .chibi_avatar import AvatarAction, ChibiAvatar
from .delete_service import DeleteResult, move_to_recycle_bin
from .explosion import ExplosionWidget


class DesktopCleanerOverlay(QWidget):
    def __init__(self, target: Path | None, config: CharacterConfig, *, demo: bool = False) -> None:
        super().__init__()
        self.target = target
        self.config = config
        self.demo = demo
        self.target_pos: QPoint | None = None
        self._sequence_started = False
        self._deleted = False
        self._delete_result: DeleteResult | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())

        self.avatar = ChibiAvatar(config, self)
        self.avatar.hide()
        self.avatar.impact.connect(self._on_impact)
        self.avatar.animation_finished.connect(self._on_avatar_animation_finished)

        self.explosion = ExplosionWidget(self)
        self.explosion.hide()

        self.title = QLabel(self)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(
            "color:white;font-family:'Microsoft YaHei UI';font-size:28px;font-weight:700;"
        )
        self.title.setText(self._selection_prompt())
        self.title.adjustSize()

        self.hint = QLabel("点击目标所在位置 · Esc 退出", self)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet(
            "color:rgba(255,255,255,190);font-family:'Microsoft YaHei UI';font-size:15px;"
        )
        self.hint.adjustSize()

        self.dialog = self._build_dialog()
        self.dialog.hide()
        self._position_headers()
        self._set_crosshair_cursor()

    def _selection_prompt(self) -> str:
        if self.demo:
            return "点一下桌面，看看家琦怎么收拾它"
        name = self.target.name if self.target else "这个文件"
        return self.config.prompt_text.format(target=name)

    def _build_dialog(self) -> QWidget:
        container = QWidget(self)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.dialog_text = QLabel(container)
        self.dialog_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dialog_text.setWordWrap(True)
        self.dialog_text.setStyleSheet(
            "color:#1f252b;background:rgba(255,255,255,246);border-radius:18px;"
            "padding:14px 24px;font-family:'Microsoft YaHei UI';font-size:18px;font-weight:650;"
        )
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.dialog_text.setGraphicsEffect(shadow)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.confirm_button = QPushButton(self.config.confirm_text, container)
        self.retry_button = QPushButton(self.config.retry_text, container)
        button_css = (
            "QPushButton{background:white;color:#20262d;border:1px solid #dfe4e8;border-radius:16px;"
            "padding:10px 18px;font-family:'Microsoft YaHei UI';font-size:15px;font-weight:650;}"
            "QPushButton:hover{background:#20262d;color:white;}"
            "QPushButton:pressed{background:#000;color:white;}"
        )
        self.confirm_button.setStyleSheet(button_css)
        self.retry_button.setStyleSheet(button_css)
        self.confirm_button.clicked.connect(self._confirm)
        self.retry_button.clicked.connect(self._retry)
        buttons.addWidget(self.confirm_button)
        buttons.addWidget(self.retry_button)

        layout.addWidget(self.dialog_text)
        layout.addLayout(buttons)
        container.adjustSize()
        return container

    def _position_headers(self) -> None:
        center_x = self.width() // 2
        self.title.move(center_x - self.title.width() // 2, max(40, self.height() // 5))
        self.hint.move(center_x - self.hint.width() // 2, self.title.y() + self.title.height() + 16)

    def _set_crosshair_cursor(self) -> None:
        size = 48
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 77, 77), 2))
        center = size // 2
        painter.drawEllipse(center - 13, center - 13, 26, 26)
        painter.drawLine(center, 0, center, center - 5)
        painter.drawLine(center, center + 5, center, size)
        painter.drawLine(0, center, center - 5, center)
        painter.drawLine(center + 5, center, size, center)
        painter.end()
        self.setCursor(QCursor(pixmap, center, center))

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        if self._sequence_started:
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(9, 13, 18, 150))
        painter.setPen(QPen(QColor(255, 255, 255, 32), 1))
        for x in range(0, self.width(), 48):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 48):
            painter.drawLine(0, y, self.width(), y)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._sequence_started or event.button() != Qt.MouseButton.LeftButton:
            return
        self.target_pos = event.position().toPoint()
        self._sequence_started = True
        self.title.hide()
        self.hint.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        self._start_walk()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape:
            self._exit()
            return
        super().keyPressEvent(event)

    def _avatar_end_position(self) -> tuple[QPoint, bool]:
        assert self.target_pos is not None
        target_x, target_y = self.target_pos.x(), self.target_pos.y()
        avatar_w, avatar_h = self.avatar.width(), self.avatar.height()
        stand_y = max(-20, min(self.height() - avatar_h, target_y - avatar_h + 72))

        if target_x >= self.width() // 2:
            end_x = target_x - avatar_w + 58
            return QPoint(max(-20, end_x), stand_y), True
        end_x = target_x - 58
        return QPoint(min(self.width() - avatar_w + 20, end_x), stand_y), False

    def _start_walk(self) -> None:
        assert self.target_pos is not None
        end, facing_right = self._avatar_end_position()
        start_x = -self.avatar.width() - 30 if facing_right else self.width() + 30
        start = QPoint(start_x, end.y())
        self.avatar.set_facing_right(facing_right)
        self.avatar.move(start)
        self.avatar.show()
        self.avatar.raise_()
        self.avatar.play_walk()

        distance = abs(end.x() - start.x())
        duration = max(1100, min(3300, int(distance * 2.15)))
        self.walk_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.walk_animation.setDuration(duration)
        self.walk_animation.setStartValue(start)
        self.walk_animation.setEndValue(end)
        self.walk_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.walk_animation.finished.connect(self._show_confirmation)
        self.walk_animation.start()

    def _show_confirmation(self) -> None:
        self.avatar.play_idle()
        name = "这个倒霉文件" if self.demo else (self.target.name if self.target else "这个文件")
        self.dialog_text.setText(f"就是「{name}」？")
        self.confirm_button.show()
        self.retry_button.show()
        self._place_dialog()

    def _place_dialog(self) -> None:
        self.dialog.adjustSize()
        x = self.avatar.x() + self.avatar.width() // 2 - self.dialog.width() // 2
        y = max(10, self.avatar.y() - self.dialog.height() + 54)
        x = max(8, min(self.width() - self.dialog.width() - 8, x))
        self.dialog.move(x, y)
        self.dialog.show()
        self.dialog.raise_()

    def _confirm(self) -> None:
        self.dialog.hide()
        self.avatar.play_kick()

    def _retry(self) -> None:
        self.dialog.hide()
        self.avatar.stop()
        self.avatar.hide()
        self.target_pos = None
        self._sequence_started = False
        self._deleted = False
        self._delete_result = None
        self.title.setText(self._selection_prompt())
        self.title.adjustSize()
        self.hint.adjustSize()
        self._position_headers()
        self.title.show()
        self.hint.show()
        self._set_crosshair_cursor()
        self.update()

    def _on_impact(self) -> None:
        if self._deleted or self.target_pos is None:
            return
        self._deleted = True
        self._delete_result = move_to_recycle_bin(self.target, demo=self.demo)
        self.explosion.move(
            self.target_pos.x() - self.explosion.width() // 2,
            self.target_pos.y() - self.explosion.height() // 2,
        )
        self.explosion.play()

    def _on_avatar_animation_finished(self) -> None:
        if self.avatar.current_action is AvatarAction.KICK:
            self._show_result()
        elif self.avatar.current_action is AvatarAction.VICTORY:
            self._slide_out()

    def _show_result(self) -> None:
        result = self._delete_result or DeleteResult(False, "删除动作没有完成")
        message = self.config.success_text if result.ok else self.config.failure_text
        self.dialog_text.setText(message.format(detail=result.message))
        self.confirm_button.hide()
        self.retry_button.hide()
        self._place_dialog()
        self.avatar.play_victory()

    def _slide_out(self) -> None:
        self.dialog.hide()
        facing_right = self.avatar.x() < self.width() // 2
        end_x = self.width() + 80 if facing_right else -self.avatar.width() - 80
        self.avatar.set_facing_right(facing_right)
        self.avatar.play_walk()
        self.exit_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.exit_animation.setDuration(1150)
        self.exit_animation.setStartValue(self.avatar.pos())
        self.exit_animation.setEndValue(QPoint(end_x, self.avatar.y()))
        self.exit_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.exit_animation.finished.connect(self._exit)
        self.exit_animation.start()

    def _exit(self) -> None:
        self.avatar.stop()
        self.close()
        QTimer.singleShot(0, QApplication.instance().quit)
