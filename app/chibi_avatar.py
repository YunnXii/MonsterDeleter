from __future__ import annotations

import base64
from enum import Enum, auto
from typing import Callable

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .character import CharacterConfig
from .resources import resource_path


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

    WALK_START = (0, 1, 2)
    WALK_CRUISE = (3, 2)  # 原图第4帧 ↔ 第3帧：左右腿交替
    WALK_STOP = (5, 6, 7, 8)  # 只能从第3帧接第6帧开始收步

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
        sprite_dir = resource_path("characters", "jiaqi", "sprites")
        path = sprite_dir / filename
        sheet = QPixmap(str(path)) if path.exists() else QPixmap()

        # Web 端修改仓库时二进制素材以有序 base64 分片保存；
        # 如果以后直接放入同名 PNG，这段会自动优先使用 PNG。
        if sheet.isNull():
            part_paths = sorted(sprite_dir.glob(f"{filename}.b64.*"))
            if part_paths:
                encoded = "".join(
                    part.read_text(encoding="ascii").strip() for part in part_paths
                )
                sheet.loadFromData(base64.b64decode(encoded), "PNG")

        if sheet.isNull():
            raise RuntimeError(f"无法加载角色精灵图：{path}")
        if sheet.width() % frame_count != 0:
            raise RuntimeError(
                f"精灵图宽度不能被帧数整除：{path} ({sheet.width()}x{sheet.height()})"
            )

        source_width = sheet.width() // frame_count
        source_height = sheet.height()
        frames: list[QPixmap] = []
        for index in range(frame_count):
            frame = sheet.copy(index * source_width, 0, source_width, source_height)
            frames.append(
                frame.scaled(
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
        # 收尾图最后一帧：稳定的侧身冷脸站姿。
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
        """Directly use the two-frame walk cycle when leaving the screen."""
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
        # 用户指定的剪辑点：巡航收到停车请求后，必须等到原图第3帧
        # （零基索引 2）播放结束，再接原图第6帧开始收步。
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
        # 踢击图第5帧是脚完全伸直且带冲击星芒的唯一命中帧。
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
