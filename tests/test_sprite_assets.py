from pathlib import Path

from PyQt6.QtGui import QImage

from app.character import CharacterConfig


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "characters" / "jiaqi" / "character.json"
SPRITE_DIR = ROOT / "characters" / "jiaqi" / "sprites"


def test_sprite_assets_are_valid_strips() -> None:
    config = CharacterConfig.load(CONFIG_PATH)
    expected = {
        "walk.png": 9,
        "kick.png": 8,
        "victory.png": 6,
    }

    for filename, frame_count in expected.items():
        path = SPRITE_DIR / filename
        assert path.exists(), f"missing sprite asset: {filename}"
        image = QImage(str(path))
        assert not image.isNull(), filename
        assert image.width() % frame_count == 0
        assert image.width() // frame_count > 0
        assert image.height() > 0
        assert image.hasAlphaChannel()
        # Source sprites may be smaller than the on-screen avatar; rendering scales smoothly.
        assert config.width >= image.width() // frame_count
        assert config.height >= image.height()


def test_animation_anchor_values_are_inside_canvas() -> None:
    config = CharacterConfig.load(CONFIG_PATH)
    assert 0 < config.impact_x < config.width
    assert 0 < config.impact_y < config.height
    assert config.walk_speed > 0
    assert config.stop_distance > 0
