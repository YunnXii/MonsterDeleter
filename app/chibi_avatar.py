from __future__ import annotations

from enum import Enum, auto
from typing import Callable

from PyQt6.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .character import CharacterConfig
from .resources import resource_path


class AvatarAction(Enum):
    IDLE = auto()
    WALK = auto()
    WAITING = auto()
    TURN = auto()
    KICK = auto()
    VICTORY = auto()


class ChibiAvatar(QWidget):
    animation_finished = pyqtSignal()
    impact = pyqtSignal()
    walk_stop_started = pyqtSignal()
    walk_stopped = pyqtSignal()

    # Source art is numbered 1..9. Runtime indices are zero-based.
    # Start: 1 -> 2 -> 3
    # Cruise: 3 -> 6 -> 4 -> 2, then loop.
    # Stop: after frame 3 finishes, continue 6 -> 7 -> 8 -> 9.
    WALK_START = (0, 1, 2)
    WALK_START_DURATIONS = (140, 120, 110)
    WALK_CRUISE = (2, 5, 3, 1)
    # Main stride poses get a little more screen time; compact transition poses
    # pass more quickly. This makes the four-keyframe cycle feel less mechanical.
    WALK_CRUISE_DURATIONS = (105, 85, 105, 85)
    WALK_STOP = (5, 6, 7, 8)
    WALK_STOP_DURATIONS = (120, 140, 160, 220)

    # Offline measurement of the final walk.png showed only tiny head-centre
    # differences. Keep the authoring-time result as four constants instead of
    # doing any image analysis at runtime. These offsets apply to cruise only.
    WALK_RENDER_OFFSETS = {
        2: QPoint(0, 0),   # source frame 3
        5: QPoint(0, 0),   # source frame 6
        3: QPoint(-1, 0),  # source frame 4
        1: QPoint(1, -1),  # source frame 2
    }

    # Walk frame 9 faces the user. When the user confirms, briefly reverse the
    # final turn so the character looks back at the target before kicking.
    WAIT_FRONT_FRAME = 8
    TURN_TO_TARGET = (8, 7, 6)
    TURN_TO_TARGET_DURATIONS = (90, 80, 80)

    KICK_DURATIONS = (130, 100, 95, 75, 90, 85, 110, 160)
    VICTORY_DURATIONS = (180, 180, 200, 220, 420, 300)

    def __init__(self, config: CharacterConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setFixedSize(config.width, config.height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._frames = {
            "walk": self._load_strip("walk.png", 9),
            "kick": self._load_strip("kick.png", 8),
            "victory": self._load_strip("victory.png", 6),
        }
        self._action = AvatarAction.IDLE
        self._facing_right = True
        self._sprite_frame = 5
        self._sequence: tuple[int, ...] = (5,)
        self._durations: tuple[int, ...] = (100,)
        self._sequence_pos = 0
        self._loop = False
        self._on_sequence_end: Callable[[], None] | None = None
        self._walk_phase = "idle"
        self._pending_walk_stop = False
        self._impact_sent = False
        self._bob_offset = 0

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

        self._idle_bob_timer = QTimer(self)
        self._idle_bob_timer.setInterval(700)
        self._idle_bob_timer.timeout.connect(self._toggle_idle_bob)

    @property
    def current_action(self) -> AvatarAction:
        return self._action

    @property
    def walk_phase(self) -> str:
        return self._walk_phase

    @property
    def current_sprite_index(self) -> int:
        return self._sprite_frame

    @property
    def bob_offset(self) -> int:
        return self._bob_offset

    def _load_strip(self, filename: str, frame_count: int) -> list[QPixmap]:
        """Load a finalized, uniformly packed sprite strip.

        Sprite cleanup and repacking are deliberately offline authoring steps.
        Runtime code only validates the finished PNG and slices equal frames.
        """
        path = resource_path("characters", "jiaqi", "sprites", filename)
        if not path.exists():
            raise RuntimeError(f"找不到角色精灵图：{path}")

        sheet = QImage(str(path))
        if sheet.isNull():
            raise RuntimeError(f"无法加载角色精灵图：{path}")
        if sheet.width() % frame_count != 0:
            raise RuntimeError(
                f"角色精灵图不是标准等宽帧：{filename} "
                f"({sheet.width()}px / {frame_count} 帧)"
            )

        frame_width = sheet.width() // frame_count
        frames: list[QPixmap] = []
        for index in range(frame_count):
            frame = sheet.copy(index * frame_width, 0, frame_width, sheet.height())
            frames.append(
                QPixmap.fromImage(frame).scaled(
                    self.width(),
                    self.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return frames

    def set_facing_right(self, value: bool) -> None:
        self._facing_right = value
        self.update()

    def play_idle(self) -> None:
        self.stop()
        self._action = AvatarAction.IDLE
        self._walk_phase = "idle"
        # Victory frame 6 is the stable side-facing cold expression.
        self._sprite_frame = 5
        self.update()

    def play_waiting_front(self) -> None:
        """Face the user while waiting for the confirmation click."""
        self.stop()
        self._action = AvatarAction.WAITING
        self._walk_phase = "waiting"
        self._sprite_frame = self.WAIT_FRONT_FRAME
        self._bob_offset = 0
        self._idle_bob_timer.start()
        self.update()

    def play_turn_to_target(self) -> None:
        """Turn from the front-facing wait pose back toward the target."""
        self._stop_idle_bob()
        self._action = AvatarAction.TURN
        self._walk_phase = "idle"
        self._play_sequence(
            self.TURN_TO_TARGET,
            self.TURN_TO_TARGET_DURATIONS,
            loop=False,
            on_end=self.animation_finished.emit,
        )

    def play_walk(self) -> None:
        self._stop_idle_bob()
        self._action = AvatarAction.WALK
        self._walk_phase = "start"
        self._pending_walk_stop = False
        self._play_sequence(
            self.WALK_START,
            self.WALK_START_DURATIONS,
            loop=False,
            on_end=self._begin_walk_cruise,
        )

    def request_walk_stop(self) -> None:
        if self._action is AvatarAction.WALK:
            self._pending_walk_stop = True

    def play_walk_cruise(self) -> None:
        """Loop the four-pose walk cycle when leaving the screen."""
        self._stop_idle_bob()
        self._action = AvatarAction.WALK
        self._walk_phase = "cruise"
        self._pending_walk_stop = False
        self._play_sequence(
            self.WALK_CRUISE,
            self.WALK_CRUISE_DURATIONS,
            loop=True,
            on_end=None,
        )

    def play_kick(self) -> None:
        self._stop_idle_bob()
        self._action = AvatarAction.KICK
        self._walk_phase = "idle"
        self._impact_sent = False
        self._play_sequence(
            tuple(range(8)),
            self.KICK_DURATIONS,
            loop=False,
            on_end=self.animation_finished.emit,
        )

    def play_victory(self) -> None:
        self._stop_idle_bob()
        self._action = AvatarAction.VICTORY
        self._walk_phase = "idle"
        self._play_sequence(
            tuple(range(6)),
            self.VICTORY_DURATIONS,
            loop=False,
            on_end=self.animation_finished.emit,
        )

    def stop(self) -> None:
        self._timer.stop()
        self._stop_idle_bob()
        self._pending_walk_stop = False

    def _stop_idle_bob(self) -> None:
        self._idle_bob_timer.stop()
        if self._bob_offset != 0:
            self._bob_offset = 0
            self.update()

    def _toggle_idle_bob(self) -> None:
        if self._action is not AvatarAction.WAITING:
            self._stop_idle_bob()
            return
        self._bob_offset = -1 if self._bob_offset == 0 else 0
        self.update()

    def _begin_walk_cruise(self) -> None:
        if self._action is not AvatarAction.WALK:
            return
        self._walk_phase = "cruise"
        self._play_sequence(
            self.WALK_CRUISE,
            self.WALK_CRUISE_DURATIONS,
            loop=True,
            on_end=None,
        )

    def _begin_walk_stop(self) -> None:
        self._pending_walk_stop = False
        self._walk_phase = "stop"
        self.walk_stop_started.emit()
        self._play_sequence(
            self.WALK_STOP,
            self.WALK_STOP_DURATIONS,
            loop=False,
            on_end=self._finish_walk_stop,
        )

    def _finish_walk_stop(self) -> None:
        self._walk_phase = "stopped"
        self.walk_stopped.emit()

    def _play_sequence(
        self,
        frames: tuple[int, ...],
        durations: tuple[int, ...],
        *,
        loop: bool,
        on_end: Callable[[], None] | None,
    ) -> None:
        if len(frames) != len(durations) or not frames:
            raise ValueError("frames 与 durations 必须非空且长度一致")
        self._timer.stop()
        self._sequence = frames
        self._durations = durations
        self._sequence_pos = 0
        self._loop = loop
        self._on_sequence_end = on_end
        self._show_frame(frames[0])
        self._timer.start(durations[0])

    def _advance(self) -> None:
        # Stop requests are phase-locked: regardless of which cruise pose is
        # showing, source frame 3 (zero-based index 2) must finish before the
        # braking artwork begins.
        if (
            self._action is AvatarAction.WALK
            and self._walk_phase == "cruise"
            and self._pending_walk_stop
            and self._sprite_frame == 2
        ):
            self._begin_walk_stop()
            return

        next_pos = self._sequence_pos + 1
        if next_pos >= len(self._sequence):
            if self._loop:
                next_pos = 0
            else:
                callback = self._on_sequence_end
                self._timer.stop()
                if callback is not None:
                    callback()
                return

        self._sequence_pos = next_pos
        self._show_frame(self._sequence[next_pos])
        self._timer.start(self._durations[next_pos])

    def _show_frame(self, frame_index: int) -> None:
        self._sprite_frame = frame_index
        # Kick frame 5 is the single fully extended impact pose.
        if (
            self._action is AvatarAction.KICK
            and frame_index == 4
            and not self._impact_sent
        ):
            self._impact_sent = True
            self.impact.emit()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        if self._action in (AvatarAction.WALK, AvatarAction.WAITING, AvatarAction.TURN):
            frame = self._frames["walk"][self._sprite_frame]
        elif self._action is AvatarAction.KICK:
            frame = self._frames["kick"][self._sprite_frame]
        else:
            frame = self._frames["victory"][self._sprite_frame]

        render_offset = QPoint(0, self._bob_offset)
        if self._action is AvatarAction.WALK and self._walk_phase == "cruise":
            cruise_offset = self.WALK_RENDER_OFFSETS.get(self._sprite_frame, QPoint())
            render_offset += cruise_offset

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self._facing_right:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        painter.drawPixmap(render_offset.x(), render_offset.y(), frame)
