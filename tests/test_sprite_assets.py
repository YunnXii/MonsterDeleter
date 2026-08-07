from pathlib import Path

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from app.character import CharacterConfig
from app.sprite_strip import detect_frame_spans, normalize_sprite_strip


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "characters" / "jiaqi" / "character.json"
SPRITE_DIR = ROOT / "characters" / "jiaqi" / "sprites"


def test_sprite_assets_can_be_repacked_into_uniform_frames() -> None:
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
        assert image.height() > 0
        assert image.hasAlphaChannel()

        spans = detect_frame_spans(image, frame_count)
        assert len(spans) == frame_count, filename
        assert all(span.width > 0 for span in spans), filename

        frames = normalize_sprite_strip(image, frame_count)
        assert len(frames) == frame_count, filename
        expected_width = round(image.width() / frame_count)
        assert all(frame.width() == expected_width for frame in frames), filename
        assert all(frame.height() == image.height() for frame in frames), filename
        assert all(frame.hasAlphaChannel() for frame in frames), filename


def test_uneven_transparent_spacing_is_detected_without_equal_slicing() -> None:
    """Regression test for the manually separated kick poses."""

    image = QImage(360, 100, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.fillRect(QRect(8, 15, 46, 78), QColor("black"))
    painter.fillRect(QRect(112, 12, 70, 81), QColor("black"))
    painter.fillRect(QRect(272, 18, 31, 75), QColor("black"))
    painter.end()

    spans = detect_frame_spans(image, 3)
    assert [(span.left, span.right) for span in spans] == [
        (8, 54),
        (112, 182),
        (272, 303),
    ]

    frames = normalize_sprite_strip(image, 3)
    assert len(frames) == 3
    assert all(frame.size().width() == 120 for frame in frames)
    assert all(frame.size().height() == 100 for frame in frames)


def test_animation_anchor_values_are_inside_canvas() -> None:
    config = CharacterConfig.load(CONFIG_PATH)
    assert 0 < config.impact_x < config.width
    assert 0 < config.impact_y < config.height
    assert config.walk_speed > 0
    assert config.stop_distance > 0
