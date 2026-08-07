from __future__ import annotations

from enum import Enum, auto
from typing import Callable

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .character import CharacterConfig
from .resources import resource_path
from .sprite_strip import normalize_sprite_strip


class AvatarAction(Enum):
    IDLE = auto()
    WALK = auto()
    KICK = auto()
    VICTORY = auto()


class ChibiAvatar(QWidget):
    animation_finished = pyqtSignal()
    impact = pyqtSignal()
    walk_stop_started = pyqtSignal()
    walk_stopped = pyqtSignal()

    # Source art is numbered 1..9. Runtime indices are zero-based.
    # Start: 1 -> 2 -> 3
    # Cruise: 4 <-> 3 (alternate legs)
    # Stop: after frame 3 finishes, jump to 6 -> 7 -> 8 -> 9.
    WALK_START = (0, 1, 2)
    WALK_CRUISE = (3, 2)
    WALK_STOP = (5, 6, 7, 8)

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

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

    @property
    def current_action(self) -> AvatarAction:
        return self._action

    @property
    def walk_phase(self) -> str:
        return self._walk_phase

    @property
    def current_sprite_index(self) -> int:
        return self._sprite_frame

    def _load_strip(self, filename: str, frame_count: int) -> list[QPixmap]:
        path = resource_path("characters", "jiaqi", "sprites", filename)
        if not path.exists():
            raise RuntimeError(f"找不到角色精灵图：{path}")

        sheet = QImage(str(path))
        if sheet.isNull():
            raise RuntimeError(f"无法加载角色精灵图：{path}")

        # The Photoshop-cleaned artwork keeps the original transparency, but
        # some poses (especially kick) are no longer evenly distributed on x.
        # Re-detect each pose from transparent gaps and repack it into equal
        # frame canvases before scaling for display. This step never re-keys or
        # modifies alpha, so restored white eyes/shoes remain opaque.
        normalized = normalize_sprite_strip(sheet, frame_count)
        return [
            QPixmap.fromImage(frame).scaled(
                self.width(),
                self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            for frame in normalized
        ]

    def set_facing_right(self, value: bool) -> None:
        self._facing_right = value
        self.update()

    def play_idle(self) -> None:
        self.stop()
        self._action = AvatarAction.IDLE
        self._walk_phase = "idle"
        # Victory sheet frame 6 is the stable side-facing cold expression.
        self._sprite_frame = 5
        self.update()

    def play_walk(self) -> None:
        self._action = AvatarAction.WALK
        self._walk_phase = "start"
        self._pending_walk_stop = False
        self._play_sequence(
            self.WALK_START,
            (145, 115, 95),
            loop=False,
            on_end=self._begin_walk_cruise,
        )

    def request_walk_stop(self) -> None:
        if self._action is AvatarAction.WALK:
            self._pending_walk_stop = True

    def play_walk_cruise(self) -> None:
        """Use only the two alternating leg frames when leaving the screen."""
        self._action = AvatarAction.WALK
        self._walk_phase = "cruise"
        self._pending_walk_stop = False
        self._play_sequence(
            self.WALK_CRUISE,
            (95, 95),
            loop=True,
            on_end=None,
        )

    def play_kick(self) -> None:
        self._action = AvatarAction.KICK
        self._walk_phase = "idle"
        self._impact_sent = False
        self._play_sequence(
            tuple(range(8)),
            (140, 95, 90, 80, 115, 95, 125, 165),
            loop=False,
            on_end=self.animation_finished.emit,
        )

    def play_victory(self) -> None:
        self._action = AvatarAction.VICTORY
        self._walk_phase = "idle"
        self._play_sequence(
            tuple(range(6)),
            (180, 150, 190, 150, 260, 220),
            loop=False,
            on_end=self.animation_finished.emit,
        )

    def stop(self) -> None:
        self._timer.stop()
        self._pending_walk_stop = False

    def _begin_walk_cruise(self) -> None:
        if self._action is not AvatarAction.WALK:
            return
        self._walk_phase = "cruise"
        self._play_sequence(
            self.WALK_CRUISE,
            (95, 95),
            loop=True,
            on_end=None,
        )

    def _begin_walk_stop(self) -> None:
        self._pending_walk_stop = False
        self._walk_phase = "stop"
        self.walk_stop_started.emit()
        self._play_sequence(
            self.WALK_STOP,
            (105, 115, 135, 180),
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
        # Stop requests are phase-locked: frame 4 can never jump directly into the
        # braking artwork. We finish source frame 3 (zero-based index 2) first.
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
        # Kick sheet frame 5 is the single fully extended impact pose.
        if (
            self._action is AvatarAction.KICK
            and frame_index == 4
            and not self._impact_sent
        ):
            self._impact_sent = True
            self.impact.emit()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        if self._action is AvatarAction.WALK:
            frame = self._frames["walk"][self._sprite_frame]
        elif self._action is AvatarAction.KICK:
            frame = self._frames["kick"][self._sprite_frame]
        else:
            frame = self._frames["victory"][self._sprite_frame]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self._facing_right:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        painter.drawPixmap(0, 0, frame)
