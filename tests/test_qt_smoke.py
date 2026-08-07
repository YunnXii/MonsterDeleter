import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from app.character import CharacterConfig
from app.chibi_avatar import ChibiAvatar
from app.explosion import ExplosionWidget
from app.flying_icon import FlyingIcon
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


def test_flying_icon_uses_ballistic_motion_and_rotation() -> None:
    app = _app()
    stage = QWidget()
    stage.resize(1000, 700)

    source = QPixmap(48, 48)
    source.fill(QColor("white"))
    flying = FlyingIcon(source, stage)
    flying.launch(QPoint(250, 500), direction=1)

    # Freeze the real timer so this test can advance one deterministic step.
    flying._timer.stop()
    start = flying.pos()
    start_vx, start_vy = flying.velocity
    flying._advance_physics(0.1)
    vx, vy = flying.velocity

    assert start_vx > 0
    assert start_vy < 0
    assert flying.x() > start.x()
    assert flying.y() < start.y()
    assert vx == start_vx
    assert vy > start_vy  # gravity pulls downward, making vy less negative
    assert flying.angle > 0

    flying.stop()
    stage.close()
    app.processEvents()
