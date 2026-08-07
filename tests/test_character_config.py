from pathlib import Path

from app.character import CharacterConfig


def test_character_config_loads() -> None:
    path = Path(__file__).parents[1] / "characters" / "jiaqi" / "character.json"
    config = CharacterConfig.load(path)
    assert config.name == "家琦"
    assert config.width > 0
    assert config.height > 0
    assert config.menu_text
    assert config.confirm_text == "嘤嘤嘤，就是这个！"
    assert config.retry_text == "不是不是"
    assert config.success_text == "这倒霉文件已经踹飞了。"
    assert config.impact_x == 234
    assert config.impact_y == 136
    assert config.walk_speed == 640
    assert config.waiting_offset == 40
