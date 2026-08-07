from __future__ import annotations

from math import hypot
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from .character import CharacterConfig
from .flying_icon import FlyingIcon
from .overlay import (
    DialogMode,
    STOP_REQUEST_LEAD_MS,
    phase_aligned_walk_duration_ms,
    waiting_position_from_attack,
)
from .responsive_overlay import ResponsiveDesktopCleanerOverlay


def projectile_direction(target_x: int, avatar_left: int, avatar_width: int) -> int:
    """Return the physical kick direction from avatar body to impact target."""
    avatar_center_x = avatar_left + avatar_width // 2
    return 1 if target_x >= avatar_center_x else -1


class DirectTargetCleanerOverlay(ResponsiveDesktopCleanerOverlay):
    """Cleaner session with a real pre-resolved target position.

    The authored base overlay remains untouched for demo/calibration. This class
    only skips the old coordinate-only crosshair and starts the same animation
    from the resident pet position.
    """

    def __init__(
        self,
        target: Path,
        config: CharacterConfig,
        *,
        target_global_pos: QPoint,
        entry_global_pos: QPoint | None = None,
    ) -> None:
        super().__init__(target, config, demo=False)
        self._direct_target_global = QPoint(target_global_pos)
        self._direct_entry_global = QPoint(entry_global_pos) if entry_global_pos is not None else None
        self._direct_entry_local: QPoint | None = None
        self._direct_facing_right_hint: bool | None = None

        # Prevent the old dimmed crosshair stage from painting even for one frame.
        self._sequence_started = True
        self.title.hide()
        self.hint.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        QTimer.singleShot(0, self._begin_direct_sequence)

    def _begin_direct_sequence(self) -> None:
        screen = QApplication.screenAt(self._direct_target_global) or QApplication.primaryScreen()
        if screen is None:
            self._exit()
            return

        geometry = screen.geometry()
        self.setGeometry(geometry)
        self.target_pos = self._direct_target_global - geometry.topLeft()

        if self._direct_entry_global is not None:
            entry_screen = QApplication.screenAt(self._direct_entry_global)
            same_screen = entry_screen is not None and entry_screen.name() == screen.name()
            if same_screen:
                # Preserve the resident pet's exact foot anchor. A full-size body
                # may sit slightly outside the screen when the pet was dragged to
                # an edge; that is less distracting than a post-morph position snap.
                foot = self._direct_entry_global - geometry.topLeft()
                self._direct_entry_local = QPoint(
                    foot.x() - self.avatar.width() // 2,
                    foot.y() - self.avatar.height(),
                )
            else:
                # Cross-monitor walking with one side-facing sprite would look
                # stranger than entering from the nearest side of the target screen.
                self._direct_facing_right_hint = self._direct_entry_global.x() <= geometry.center().x()

        self.update()
        self._start_walk()

    def _avatar_stage_positions(self) -> tuple[QPoint, QPoint, bool]:
        assert self.target_pos is not None
        target_x, target_y = self.target_pos.x(), self.target_pos.y()

        if self._direct_entry_local is not None:
            entry_center_x = self._direct_entry_local.x() + self.avatar.width() // 2
            facing_right = target_x >= entry_center_x
        elif self._direct_facing_right_hint is not None:
            facing_right = self._direct_facing_right_hint
        else:
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

        if self._direct_entry_local is not None:
            start = QPoint(self._direct_entry_local)
        else:
            start_x = -self.avatar.width() - 30 if facing_right else self.width() + 30
            start = QPoint(start_x, waiting_pos.y())

        pre_stop = QPoint(
            waiting_pos.x() - direction * self.config.stop_distance,
            waiting_pos.y(),
        )

        self.avatar.set_facing_right(facing_right)
        self.avatar.move(start)
        self.avatar.show()
        self.avatar.raise_()

        distance = round(hypot(pre_stop.x() - start.x(), pre_stop.y() - start.y()))
        duration = phase_aligned_walk_duration_ms(distance, self.config.walk_speed)

        self.walk_animation = QPropertyAnimation(self.avatar, b"pos", self)
        self.walk_animation.setDuration(duration)
        self.walk_animation.setStartValue(start)
        self.walk_animation.setEndValue(pre_stop)
        self.walk_animation.setEasingCurve(QEasingCurve.Type.Linear)

        self.avatar.play_walk()
        self.walk_animation.start()
        self.walk_stop_timer.start(max(1, duration - STOP_REQUEST_LEAD_MS))

    def _launch_flying_icon(self, pixmap) -> None:
        """Launch from the actual kick direction, never from screen-half heuristics."""
        if self.target_pos is None:
            return
        self._stop_flying_icon()
        self.flying_icon = FlyingIcon(pixmap, self)
        direction = projectile_direction(
            self.target_pos.x(),
            self.avatar.x(),
            self.avatar.width(),
        )
        self.flying_icon.launch(self.target_pos, direction=direction)

    def _on_secondary_dialog_action(self) -> None:
        if self._dialog_mode is DialogMode.CONFIRM:
            # A direct-mode task already knows the path and deliberately has no
            # fake crosshair fallback. If the user says this is not the one,
            # leave the task gracefully instead of asking for a coordinate.
            self._bail_out()
            return
        super()._on_secondary_dialog_action()
