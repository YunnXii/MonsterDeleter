import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import AvatarAction, ChibiAvatar


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
    assert ChibiAvatar.WALK_CRUISE == (3, 2)
    assert ChibiAvatar.WALK_CRUISE_DURATIONS == (120, 120)
    assert ChibiAvatar.WALK_STOP == (5, 6, 7, 8)
    assert ChibiAvatar.WALK_STOP_DURATIONS == (120, 140, 160, 220)
    assert ChibiAvatar.WAIT_FRONT_FRAME == 8
    assert ChibiAvatar.TURN_TO_TARGET == (8, 7, 6)
    assert ChibiAvatar.TURN_TO_TARGET_DURATIONS == (90, 80, 80)
    assert ChibiAvatar.KICK_DURATIONS == (130, 100, 95, 75, 90, 85, 110, 160)
    assert ChibiAvatar.VICTORY_DURATIONS == (180, 180, 200, 220, 420, 300)


def test_stop_request_waits_for_source_frame_three() -> None:
    avatar = _avatar()
    try:
        avatar._action = AvatarAction.WALK
        avatar._begin_walk_cruise()
        assert avatar.walk_phase == "cruise"
        assert avatar.current_sprite_index == 3  # source frame 4

        avatar.request_walk_stop()
        avatar._advance()

        # A stop request received on source frame 4 must first advance to frame 3.
        assert avatar.walk_phase == "cruise"
        assert avatar.current_sprite_index == 2

        avatar._advance()

        # Only after source frame 3 has finished may braking begin at frame 6.
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
        avatar._sequence_pos = 1
        avatar._show_frame(2)  # source frame 3
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
