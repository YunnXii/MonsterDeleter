import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import AvatarAction
from app.direct_overlay import DirectTargetCleanerOverlay, projectile_direction
from app.overlay import DialogMode, TurnPurpose


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


def test_projectile_direction_follows_avatar_to_target_not_screen_half() -> None:
    # Reproduces the desktop bug: both avatar and target can live on the left
    # half of the screen while the actual kick still points to the right.
    assert projectile_direction(target_x=420, avatar_left=120, avatar_width=280) == 1
    assert projectile_direction(target_x=120, avatar_left=260, avatar_width=280) == -1


def test_direct_overlay_skips_crosshair_and_starts_from_entry() -> None:
    app = _app()
    screen = app.primaryScreen()
    assert screen is not None
    geometry = screen.geometry()

    target_global = geometry.center()
    entry_global = QPoint(
        geometry.right() - 40,
        geometry.bottom() - 40,
    )
    overlay = DirectTargetCleanerOverlay(
        Path(r"C:\temp\demo.txt"),
        _config(),
        target_global_pos=target_global,
        entry_global_pos=entry_global,
    )
    try:
        overlay.show()
        app.processEvents()

        assert overlay._sequence_started is True
        assert overlay.title.isHidden()
        assert overlay.hint.isHidden()
        assert overlay.target_pos is not None
        assert overlay._direct_entry_local is not None
        assert overlay.avatar.current_action is AvatarAction.WALK

        expected_foot = entry_global - geometry.topLeft()
        actual_foot = QPoint(
            overlay._direct_entry_local.x() + overlay.avatar.width() // 2,
            overlay._direct_entry_local.y() + overlay.avatar.height(),
        )
        assert actual_foot == expected_foot
    finally:
        overlay._stop_motion_animations()
        overlay.avatar.stop()
        overlay.close()
        app.processEvents()


def test_direct_mode_no_button_does_not_restore_fake_crosshair() -> None:
    app = _app()
    screen = app.primaryScreen()
    assert screen is not None
    geometry = screen.geometry()

    overlay = DirectTargetCleanerOverlay(
        Path(r"C:\temp\demo.txt"),
        _config(),
        target_global_pos=geometry.center(),
        entry_global_pos=QPoint(geometry.right() - 40, geometry.bottom() - 40),
    )
    try:
        overlay.show()
        app.processEvents()
        overlay._stop_motion_animations()
        overlay.avatar.play_waiting_front()
        overlay._dialog_mode = DialogMode.CONFIRM

        overlay._on_secondary_dialog_action()

        assert overlay._sequence_started is True
        assert overlay._turn_purpose is TurnPurpose.BAIL_OUT
        assert overlay.title.isHidden()
    finally:
        overlay._stop_motion_animations()
        overlay.avatar.stop()
        overlay.close()
        app.processEvents()
