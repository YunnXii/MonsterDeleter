from pathlib import Path

from app.character import CharacterConfig


def test_character_config_loads() -> None:
    path = Path(__file__).parents[1] / "characters" / "jiaqi" / "character.json"
    config = CharacterConfig.load(path)
    assert config.name == "家琦"
    assert config.width > 0
    assert config.height > 0
    assert config.menu_text
