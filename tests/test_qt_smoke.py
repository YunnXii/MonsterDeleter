import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.chibi_avatar import ChibiAvatar
from app.explosion import ExplosionWidget
from app.overlay import DesktopCleanerOverlay


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _config() -> CharacterConfig:
    path = Path(__file__).parents[1] / "characters" / "jiaqi" / "character.json"
    return CharacterConfig.load(path)


def test_avatar_can_render_offscreen() -> None:
    app = _app()
    avatar = ChibiAvatar(_config())
    avatar.show()
    app.processEvents()
    pixmap = avatar.grab()
    assert not pixmap.isNull()
    avatar.close()
    app.processEvents()


def test_overlay_can_construct_in_demo_mode() -> None:
    app = _app()
    overlay = DesktopCleanerOverlay(None, _config(), demo=True)
    app.processEvents()
    assert overlay.demo is True
    overlay.close()
    app.processEvents()


def test_explosion_can_render_offscreen() -> None:
    app = _app()
    explosion = ExplosionWidget()
    explosion.show()
    app.processEvents()
    pixmap = explosion.grab()
    assert not pixmap.isNull()
    explosion.close()
    app.processEvents()
