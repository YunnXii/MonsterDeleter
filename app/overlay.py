from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
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
from .delete_service import DeleteFailureKind, DeleteResult, move_to_recycle_bin
from .explosion import ExplosionWidget
from .flying_icon import FlyingIcon, system_icon_pixmap


MIN_WALK_DURATION_MS = 900
STOP_REQUEST_LEAD_MS = 60
TURN_APPROACH_MS = sum(ChibiAvatar.TURN_TO_TARGET_DURATIONS)
WALK_FIRST_SAFE_STOP_MS = (
    sum(ChibiAvatar.WALK_START_DURATIONS)
    + ChibiAvatar.WALK_CRUISE_DURATIONS[0]
)
WALK_CRUISE_CYCLE_MS = sum(ChibiAvatar.WALK_CRUISE_DURATIONS)


class DialogMode(Enum):
    CONFIRM = auto()
    FAILURE = auto()
    RESULT = auto()


@dataclass(frozen=True)
class FailureCopy:
    message: str
    retry_label: str | None
    cancel_label: str = "不踹了"


def failure_copy(result: DeleteResult) -> FailureCopy:
    if result.kind is DeleteFailureKind.IN_USE:
        return FailureCopy(
            "这玩意正开着呢，踹不动。",
            "关了再踹一次",
        )
    if result.kind is DeleteFailureKind.PERMISSION:
        return FailureCopy(
            "这玩意权限挺大，我踹不动。\nWindows 没给删除权限。",
            "再踹一次",
        )
    if result.kind is DeleteFailureKind.NOT_FOUND:
        return FailureCopy(
            "……这玩意自己先跑了。\n它已经不在原来的位置。",
            None,
        )

    detail = result.technical_detail.strip()
    if len(detail) > 180:
        detail = detail[:177] + "..."
    message = "这玩意有点邪门，踹不动。"
    if detail:
        message += f"\n{detail}"
    return FailureCopy(message, "再踹一次")


def phase_aligned_walk_duration_ms(distance_px: int, walk_speed: int) -> int:
    """Choose a travel duration that ends on a legal source-frame-3 stop phase.

    The stop animation may only begin after source walk frame 3 finishes. Instead
    of reaching the pre-stop point first and then waiting up to a whole gait
    cycle, quantize the positional animation duration to the nearest legal stop
    phase before walking starts. When two phases bracket the nominal duration,
    choose the one that changes effective walking speed the least.
    """
    if walk_speed <= 0:
        raise ValueError("walk_speed must be positive")

    nominal_ms = max(
        MIN_WALK_DURATION_MS,
        round(max(0, distance_px) * 1000 / walk_speed),
    )
    if nominal_ms <= WALK_FIRST_SAFE_STOP_MS:
        return WALK_FIRST_SAFE_STOP_MS

    relative = nominal_ms - WALK_FIRST_SAFE_STOP_MS
    lower_cycles = max(0, relative // WALK_CRUISE_CYCLE_MS)
    lower = WALK_FIRST_SAFE_STOP_MS + lower_cycles * WALK_CRUISE_CYCLE_MS
    upper = lower + WALK_CRUISE_CYCLE_MS

    def speed_error(duration_ms: int) -> float:
        # Effective speed scales with nominal_ms / duration_ms.
        return abs(nominal_ms / duration_ms - 1.0)

    return min((lower, upper), key=speed_error)


def waiting_position_from_attack(
    attack_pos: QPoint,
    *,
    facing_right: bool,
    waiting_offset: int,
) -> QPoint:
    """Move the waiting pose away from the target without changing kick anchor."""
    direction = 1 if facing_right else -1
    return QPoint(
        attack_pos.x() - direction * max(0, waiting_offset),
        attack_pos.y(),
    )


class DesktopCleanerOverlay(QWidget):
    WALK_BRAKE_MS = sum(ChibiAvatar.WALK_STOP_DURATIONS)

    def __init__(self, target: Path | None, config: CharacterConfig, *, demo: bool = False) -> None:
        super().__init__()
        self.target = target
        self.config = config
        self.demo = demo
        self.target_pos: QPoint | None = None
        self._sequence_started = False
        self._deleted = False
        self._delete_result: DeleteResult | None = None
        self._attack_pos: QPoint | None = None
        self._waiting_pos: QPoint | None = None
        self._turn_complete = False
        self._approach_complete = False
        self._dialog_mode = DialogMode.CONFIRM
        self.flying_icon: FlyingIcon | None = None

        primary = QApplication.primaryScreen()
        if primary is None:
            raise RuntimeError("没有可用显示器")
        self._virtual_geometry = primary.virtualGeometry()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(self._virtual_geometry)

        self.avatar = ChibiAvatar(config, self)
        self.avatar.hide()
        self.avatar.impact.connect(self._on_impact)
        self.avatar.animation_finished.connect(self._on_avatar_animation_finished)
        self.avatar.walk_stop_started.connect(self._start_walk_brake)
        self.avatar.walk_stopped.connect(self._on_walk_stopped)

        # A dedicated precise one-shot timer requests braking shortly before the
        # precomputed legal frame-3 boundary. It can be cancelled safely on retry.
        self.walk_stop_timer = QTimer(self)
        self.walk_stop_timer.setSingleShot(True)
        self.walk_stop_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.walk_stop_timer.timeout.connect(self.avatar.request_walk_stop)

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
            return "点一下屏幕，看看家琦怎么收拾它"
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
        self.confirm_button.clicked.connect(self._on_primary_dialog_action)
        self.retry_button.clicked.connect(self._on_secondary_dialog_action)
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

    def _lock_stage_to_clicked_screen(self, local_point: QPoint) -> QPoint:
        """Shrink the post-click stage to the monitor that contains the target."""
        global_point = self.mapToGlobal(local_point)
        screen = QApplication.screenAt(global_point) or QApplication.primaryScreen()
        if screen is None:
            return local_point

        geometry = screen.geometry()
        self.setGeometry(geometry)
        return global_point - geometry.topLeft()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._sequence_started or event.button() != Qt.MouseButton.LeftButton:
            return

        self.target_pos = self._lock_stage_to_clicked_screen(event.position().toPoint())
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

    def _clamp_avatar_position(self, position: QPoint) -> QPoint:
        return QPoint(
            max(-24, min(self.width() - self.avatar.width() + 24, position.x())),
            max(-24, min(self.height() - self.avatar.height() + 24, position.y())),
        )

    def _avatar_stage_positions(self) -> tuple[QPoint, QPoint, bool]:
        """Return exact kick position and a more relaxed confirmation position."""
        assert self.target_pos is not None
        target_x, target_y = self.target_pos.x(), self.target_pos.y()
        facing_right = target_x >= self.width() // 2

        local_impact_x = (
            self.config.impact_x
            if facing_right
            else self.avatar.width() - self.config.impact_x
        )
        attack_pos = self._clamp_avatar_position(
            QPoint(
                target_x - local_impact_x,
                target_y - self.config.impact_y,
            )
        )
        waiting_pos = self._clamp_avatar_position(
            waiting_position_from_attack(
                attack_pos,
                facing_right=facing_right,
                waiting_offset=self.config.waiting_offset,
            )
        )
        return attack_pos, waiting_pos, facing_right

    def _start_walk(self) -> None:
        attack_pos, waiting_pos, facing_right = self._avatar_stage_positions()
        self._attack_pos = attack_pos
        self._waiting_pos = waiting_pos
        direction = 1 if facing_right else -1
        start_x = -self.avatar.width() - 30 if facing_right else self.width() + 30
        start = QPoint(start_x, waiting_pos.y())

        pre_stop_x = waiting_pos.x() - direction * self.config.stop_distance
        pre_stop = QPoint(pre_stop_x, waiting_pos.y())

        self.avatar.set_facing_right(facing_right)
        self.avatar.move(start)
        self.avatar.show()
        self.avatar.raise_()

        distance = abs(pre_stop.x() - start.x())
        duration = phase_aligned_walk_duration_ms(distance, self.config.walk_speed)

        self.walk_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.walk_animation.setDuration(duration)
        self.walk_animation.setStartValue(start)
        self.walk_animation.setEndValue(pre_stop)
        self.walk_animation.setEasingCurve(QEasingCurve.Type.Linear)

        # Start sprite timing and positional timing together. The stop request is
        # sent inside the final source-frame-3 hold, so the next avatar tick can
        # enter braking immediately rather than completing another gait cycle.
        self.avatar.play_walk()
        self.walk_animation.start()
        self.walk_stop_timer.start(max(1, duration - STOP_REQUEST_LEAD_MS))

    def _start_walk_brake(self) -> None:
        if self._waiting_pos is None:
            return

        self.walk_stop_timer.stop()
        walk_animation = getattr(self, "walk_animation", None)
        if walk_animation is not None:
            walk_animation.stop()

        self.brake_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.brake_animation.setDuration(self.WALK_BRAKE_MS)
        self.brake_animation.setStartValue(self.avatar.pos())
        self.brake_animation.setEndValue(self._waiting_pos)
        self.brake_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.brake_animation.start()

    def _on_walk_stopped(self) -> None:
        if self._waiting_pos is not None:
            self.avatar.move(self._waiting_pos)
        self._show_confirmation()

    def _show_confirmation(self) -> None:
        # Walk frame 9 is front-facing: the interaction target is now the user,
        # not the file, so hold eye contact while waiting for a decision.
        self._dialog_mode = DialogMode.CONFIRM
        self.avatar.play_waiting_front()
        name = "这个倒霉文件" if self.demo else (self.target.name if self.target else "这个文件")
        self.dialog_text.setText(f"就是「{name}」？")
        self.confirm_button.setText(self.config.confirm_text)
        self.retry_button.setText(self.config.retry_text)
        self.confirm_button.show()
        self.retry_button.show()
        self._place_dialog()

    def _show_failure(self, result: DeleteResult) -> None:
        self._dialog_mode = DialogMode.FAILURE
        copy = failure_copy(result)
        self.dialog_text.setText(copy.message)

        if copy.retry_label is None:
            self.confirm_button.hide()
        else:
            self.confirm_button.setText(copy.retry_label)
            self.confirm_button.show()

        self.retry_button.setText(copy.cancel_label)
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

    def _on_primary_dialog_action(self) -> None:
        if self._dialog_mode is DialogMode.CONFIRM:
            self._confirm()
        elif self._dialog_mode is DialogMode.FAILURE:
            self._retry_delete()

    def _on_secondary_dialog_action(self) -> None:
        if self._dialog_mode is DialogMode.CONFIRM:
            self._retry_selection()
        elif self._dialog_mode is DialogMode.FAILURE:
            self._exit()

    def _confirm(self) -> None:
        if self._attack_pos is None:
            return

        self.dialog.hide()
        self._turn_complete = False
        self._approach_complete = False

        # Turn back toward the target while stepping from the relaxed waiting
        # position into the exact kick anchor. Kick starts only after BOTH are
        # complete, so timer jitter cannot reintroduce an alignment snap.
        self.avatar.play_turn_to_target()
        self.approach_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.approach_animation.setDuration(TURN_APPROACH_MS)
        self.approach_animation.setStartValue(self.avatar.pos())
        self.approach_animation.setEndValue(self._attack_pos)
        self.approach_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.approach_animation.finished.connect(self._on_approach_finished)
        self.approach_animation.start()

    def _on_approach_finished(self) -> None:
        if self._attack_pos is not None:
            self.avatar.move(self._attack_pos)
        self._approach_complete = True
        self._maybe_start_kick()

    def _maybe_start_kick(self) -> None:
        if (
            self._turn_complete
            and self._approach_complete
            and self.avatar.current_action is AvatarAction.TURN
        ):
            if self._attack_pos is not None:
                self.avatar.move(self._attack_pos)
            self.avatar.play_kick()

    def _retry_delete(self) -> None:
        """Retry from the exact attack position without replaying the walk-in."""
        if self._attack_pos is None:
            return
        self.dialog.hide()
        self._deleted = False
        self._delete_result = None
        self.avatar.move(self._attack_pos)
        self.avatar.play_kick()

    def _stop_motion_animations(self) -> None:
        self.walk_stop_timer.stop()
        for name in (
            "walk_animation",
            "brake_animation",
            "approach_animation",
            "exit_animation",
        ):
            animation = getattr(self, name, None)
            if animation is not None:
                animation.stop()

    def _stop_flying_icon(self) -> None:
        if self.flying_icon is not None:
            self.flying_icon.stop()
            self.flying_icon.deleteLater()
            self.flying_icon = None

    def _retry_selection(self) -> None:
        self.dialog.hide()
        self._stop_motion_animations()
        self._stop_flying_icon()
        self.avatar.stop()
        self.avatar.hide()

        # Selection may move to another monitor, so restore the virtual desktop
        # overlay before asking for another click.
        self.setGeometry(self._virtual_geometry)
        self.target_pos = None
        self._attack_pos = None
        self._waiting_pos = None
        self._turn_complete = False
        self._approach_complete = False
        self._sequence_started = False
        self._deleted = False
        self._delete_result = None
        self._dialog_mode = DialogMode.CONFIRM
        self.title.setText(self._selection_prompt())
        self.title.adjustSize()
        self.hint.adjustSize()
        self._position_headers()
        self.title.show()
        self.hint.show()
        self._set_crosshair_cursor()
        self.update()

    def _launch_flying_icon(self, pixmap: QPixmap) -> None:
        if self.target_pos is None:
            return
        self._stop_flying_icon()
        self.flying_icon = FlyingIcon(pixmap, self)
        direction = 1 if self.target_pos.x() >= self.width() // 2 else -1
        self.flying_icon.launch(self.target_pos, direction=direction)

    def _on_impact(self) -> None:
        if self._deleted or self.target_pos is None:
            return
        self._deleted = True

        # Capture the system icon before send2trash moves the target away.
        icon_pixmap = system_icon_pixmap(self.target)
        self._delete_result = move_to_recycle_bin(self.target, demo=self.demo)

        # Failure must not sell a fake success: no explosion and no flying icon.
        if not self._delete_result.ok:
            return

        self.explosion.move(
            self.target_pos.x() - self.explosion.width() // 2,
            self.target_pos.y() - self.explosion.height() // 2,
        )
        self.explosion.play()
        self._launch_flying_icon(icon_pixmap)

    def _on_avatar_animation_finished(self) -> None:
        if self.avatar.current_action is AvatarAction.TURN:
            self._turn_complete = True
            self._maybe_start_kick()
        elif self.avatar.current_action is AvatarAction.KICK:
            self._show_result()
        elif self.avatar.current_action is AvatarAction.VICTORY:
            self._slide_out()

    def _show_result(self) -> None:
        result = self._delete_result or DeleteResult(
            False,
            "删除动作没有完成",
            DeleteFailureKind.OTHER,
        )

        if not result.ok:
            # No smug victory after a failed delete. Hold the cold side pose and
            # let the user close the offending program, then retry in place.
            self.avatar.play_idle()
            self._show_failure(result)
            return

        self._dialog_mode = DialogMode.RESULT
        self.dialog_text.setText(self.config.success_text)
        self.confirm_button.hide()
        self.retry_button.hide()
        self._place_dialog()
        self.avatar.play_victory()

    def _slide_out(self) -> None:
        self.dialog.hide()
        facing_right = self.avatar.x() < self.width() // 2
        end_x = self.width() + 80 if facing_right else -self.avatar.width() - 80
        self.avatar.set_facing_right(facing_right)
        self.avatar.play_walk_cruise()
        self.exit_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.exit_animation.setDuration(1150)
        self.exit_animation.setStartValue(self.avatar.pos())
        self.exit_animation.setEndValue(QPoint(end_x, self.avatar.y()))
        self.exit_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.exit_animation.finished.connect(self._exit)
        self.exit_animation.start()

    def _exit(self) -> None:
        self._stop_motion_animations()
        self._stop_flying_icon()
        self.avatar.stop()
        self.close()
        QTimer.singleShot(0, QApplication.instance().quit)
