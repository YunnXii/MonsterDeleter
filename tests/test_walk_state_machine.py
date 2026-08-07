import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import AvatarAction, ChibiAvatar
from app.overlay import (
    WALK_CRUISE_CYCLE_MS,
    WALK_FIRST_SAFE_STOP_MS,
    phase_aligned_walk_duration_ms,
)


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "characters" / "jiaqi" / "character.json"
_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _avatar() -> ChibiAvatar:
    _app()
    return ChibiAvatar(CharacterConfig.load(CONFIG_PATH))


def test_animation_director_constants_match_plan() -> None:
    assert ChibiAvatar.WALK_START == (0, 1, 2)
    assert ChibiAvatar.WALK_START_DURATIONS == (140, 120, 110)
    assert ChibiAvatar.WALK_CRUISE == (2, 5, 3, 1)
    assert ChibiAvatar.WALK_CRUISE_DURATIONS == (105, 85, 105, 85)
    assert ChibiAvatar.WALK_RENDER_OFFSETS == {
        2: QPoint(0, 0),
        5: QPoint(0, 0),
        3: QPoint(-1, 0),
        1: QPoint(1, -1),
    }
    assert ChibiAvatar.WALK_STOP == (5, 6, 7, 8)
    assert ChibiAvatar.WALK_STOP_DURATIONS == (120, 140, 160, 220)
    assert ChibiAvatar.WAIT_FRONT_FRAME == 8
    assert ChibiAvatar.TURN_TO_TARGET == (8, 7, 6)
    assert ChibiAvatar.TURN_TO_TARGET_DURATIONS == (90, 80, 80)
    assert ChibiAvatar.KICK_DURATIONS == (130, 100, 95, 75, 90, 85, 110, 160)
    assert ChibiAvatar.VICTORY_DURATIONS == (180, 180, 200, 220, 420, 300)


def test_phase_aligned_duration_lands_on_legal_frame_three_boundary() -> None:
    # 780 px at 390 px/s is nominally 2000 ms; the nearest legal frame-3
    # boundary is 1995 ms with the current animation director timings.
    duration = phase_aligned_walk_duration_ms(780, 390)
    assert duration == 1995
    assert (duration - WALK_FIRST_SAFE_STOP_MS) % WALK_CRUISE_CYCLE_MS == 0


def test_phase_alignment_prefers_smaller_effective_speed_change() -> None:
    # Around the midpoint between 855 and 1235 ms, using the later boundary
    # changes effective speed less than rushing to the earlier one.
    duration = phase_aligned_walk_duration_ms(408, 390)
    assert duration == 1235


def test_cruise_loops_source_frames_3_6_4_2() -> None:
    avatar = _avatar()
    try:
        avatar._action = AvatarAction.WALK
        avatar._begin_walk_cruise()
        assert avatar.current_sprite_index == 2  # source frame 3

        avatar._advance()
        assert avatar.current_sprite_index == 5  # source frame 6
        avatar._advance()
        assert avatar.current_sprite_index == 3  # source frame 4
        avatar._advance()
        assert avatar.current_sprite_index == 1  # source frame 2
        avatar._advance()
        assert avatar.current_sprite_index == 2  # source frame 3 again
    finally:
        avatar.stop()
        avatar.close()


def test_stop_request_waits_until_source_frame_three() -> None:
    avatar = _avatar()
    try:
        avatar._action = AvatarAction.WALK
        avatar._begin_walk_cruise()

        # Move from source frame 3 to source frame 6, then request braking.
        avatar._advance()
        assert avatar.current_sprite_index == 5
        avatar.request_walk_stop()

        # The cycle must keep going 6 -> 4 -> 2 -> 3.
        avatar._advance()
        assert avatar.walk_phase == "cruise"
        assert avatar.current_sprite_index == 3
        avatar._advance()
        assert avatar.walk_phase == "cruise"
        assert avatar.current_sprite_index == 1
        avatar._advance()
        assert avatar.walk_phase == "cruise"
        assert avatar.current_sprite_index == 2

        # Only after source frame 3 has finished may braking begin at frame 6.
        avatar._advance()
        assert avatar.walk_phase == "stop"
        assert avatar.current_sprite_index == 5
    finally:
        avatar.stop()
        avatar.close()


def test_stop_request_on_source_frame_three_brakes_immediately_after_it() -> None:
    avatar = _avatar()
    try:
        avatar._action = AvatarAction.WALK
        avatar._begin_walk_cruise()
        assert avatar.current_sprite_index == 2  # source frame 3
        avatar.request_walk_stop()

        avatar._advance()

        assert avatar.walk_phase == "stop"
        assert avatar.current_sprite_index == 5  # source frame 6
    finally:
        avatar.stop()
        avatar.close()


def test_waiting_pose_faces_user_then_turns_back_to_target() -> None:
    avatar = _avatar()
    try:
        avatar.play_waiting_front()
        assert avatar.current_action is AvatarAction.WAITING
        assert avatar.walk_phase == "waiting"
        assert avatar.current_sprite_index == 8  # source walk frame 9

        avatar.play_turn_to_target()
        assert avatar.current_action is AvatarAction.TURN
        assert avatar.current_sprite_index == 8

        avatar._advance()
        assert avatar.current_sprite_index == 7
        avatar._advance()
        assert avatar.current_sprite_index == 6
    finally:
        avatar.stop()
        avatar.close()


def test_waiting_bob_is_only_one_pixel() -> None:
    avatar = _avatar()
    try:
        avatar.play_waiting_front()
        assert avatar.bob_offset == 0
        avatar._toggle_idle_bob()
        assert avatar.bob_offset == -1
        avatar._toggle_idle_bob()
        assert avatar.bob_offset == 0
    finally:
        avatar.stop()
        avatar.close()
