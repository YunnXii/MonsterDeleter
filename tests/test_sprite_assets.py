from pathlib import Path

from PyQt6.QtGui import QImage

from app.character import CharacterConfig


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "characters" / "jiaqi" / "character.json"
SPRITE_DIR = ROOT / "characters" / "jiaqi" / "sprites"


def test_sprite_assets_are_final_uniform_strips() -> None:
    expected = {
        "walk.png": 9,
        "kick.png": 8,
        "victory.png": 6,
    }

    frame_sizes: set[tuple[int, int]] = set()

    for filename, frame_count in expected.items():
        path = SPRITE_DIR / filename
        assert path.exists(), f"missing sprite asset: {filename}"

        image = QImage(str(path))
        assert not image.isNull(), filename
        assert image.height() > 0
        assert image.hasAlphaChannel()
        assert image.width() % frame_count == 0, (
            f"{filename} must be an evenly packed {frame_count}-frame strip"
        )

        frame_sizes.add((image.width() // frame_count, image.height()))

    # The offline authoring script normalizes all three actions to the same
    # per-frame canvas, so switching actions cannot make the character jump in
    # apparent size or baseline.
    assert len(frame_sizes) == 1, f"sprite frame canvases differ: {frame_sizes}"


def test_animation_anchor_values_are_inside_canvas() -> None:
    config = CharacterConfig.load(CONFIG_PATH)
    assert 0 < config.impact_x < config.width
    assert 0 < config.impact_y < config.height
    assert config.walk_speed > 0
    assert config.stop_distance > 0
