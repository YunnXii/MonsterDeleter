import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import AvatarAction, ChibiAvatar
from app.delete_service import DeleteFailureKind, DeleteResult
from app.overlay import (
    QUICK_EXIT_MAX_MS,
    QUICK_EXIT_MIN_MS,
    DesktopCleanerOverlay,
    TurnPurpose,
    failure_copy,
)


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "characters" / "jiaqi" / "character.json"
_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _config() -> CharacterConfig:
    return CharacterConfig.load(CONFIG_PATH)


def test_in_use_copy_matches_product_wording() -> None:
    copy = failure_copy(
        DeleteResult(
            False,
            "文件正在被其他程序占用",
            DeleteFailureKind.IN_USE,
        )
    )
    assert copy.message == "这玩意正开着呢，踹不动。"
    assert copy.retry_label == "关了再踹一次"
    assert copy.cancel_label == "不踹了"


def test_failed_kick_recovers_to_front_pose() -> None:
    _app()
    avatar = ChibiAvatar(_config())
    try:
        avatar.play_failure_wait()
        assert avatar.current_action is AvatarAction.WAITING
        assert avatar.walk_phase == "failure_recover"
        assert avatar.current_sprite_index == 6  # source walk frame 7

        avatar._advance()
        assert avatar.current_sprite_index == 7  # source walk frame 8
        avatar._advance()
        assert avatar.current_sprite_index == 8  # source walk frame 9
        avatar._advance()

        assert avatar.walk_phase == "waiting"
        assert avatar.current_sprite_index == 8
    finally:
        avatar.stop()
        avatar.close()


def test_failure_cancel_turns_then_starts_fast_exit() -> None:
    app = _app()
    overlay = DesktopCleanerOverlay(None, _config(), demo=True)
    try:
        overlay.resize(1200, 700)
        overlay.avatar.move(250, 300)
        overlay.avatar.show()
        overlay.avatar.play_failure_wait()
        overlay._show_failure(
            DeleteResult(False, "busy", DeleteFailureKind.IN_USE)
        )

        overlay._bail_out()
        assert overlay._turn_purpose is TurnPurpose.BAIL_OUT
        assert overlay.avatar.current_action is AvatarAction.TURN

        # Simulate the turn sequence finishing; the overlay should immediately
        # switch to the fast cruise-out rather than closing in place.
        overlay._on_avatar_animation_finished()
        assert overlay.avatar.current_action is AvatarAction.WALK
        assert QUICK_EXIT_MIN_MS <= overlay.exit_animation.duration() <= QUICK_EXIT_MAX_MS
        assert overlay.exit_animation.endValue().x() < 0
    finally:
        overlay._stop_motion_animations()
        overlay.avatar.stop()
        overlay.close()
        app.processEvents()
