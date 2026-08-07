import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import AvatarAction, ChibiAvatar


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "characters" / "jiaqi" / "character.json"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _avatar() -> ChibiAvatar:
    _app()
    return ChibiAvatar(CharacterConfig.load(CONFIG_PATH))


def test_walk_sequences_match_source_art() -> None:
    assert ChibiAvatar.WALK_START == (0, 1, 2)
    assert ChibiAvatar.WALK_CRUISE == (3, 2)
    assert ChibiAvatar.WALK_STOP == (5, 6, 7, 8)


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
