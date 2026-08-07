import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import ChibiAvatar
from app.explosion import ExplosionWidget
from app.overlay import DesktopCleanerOverlay


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _config() -> CharacterConfig:
    path = Path(__file__).parents[1] / "characters" / "jiaqi" / "character.json"
    return CharacterConfig.load(path)


def test_avatar_can_render_offscreen() -> None:
    _app()
    avatar = ChibiAvatar(_config())
    avatar.show()
    pixmap = avatar.grab()
    assert not pixmap.isNull()
    avatar.close()


def test_overlay_can_construct_in_demo_mode() -> None:
    _app()
    overlay = DesktopCleanerOverlay(None, _config(), demo=True)
    assert overlay.demo is True
    overlay.close()


def test_explosion_can_render_offscreen() -> None:
    _app()
    explosion = ExplosionWidget()
    explosion.show()
    pixmap = explosion.grab()
    assert not pixmap.isNull()
    explosion.close()
