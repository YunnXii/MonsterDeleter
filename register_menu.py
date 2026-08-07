"""Compatibility wrapper for users of the original project."""

from app.character import CharacterConfig
from app.context_menu import register_context_menu
from app.resources import resource_path


def add_context_menu() -> None:
    config = CharacterConfig.load(resource_path("characters", "jiaqi", "character.json"))
    result = register_context_menu(config.menu_text)
    print(result.message)


if __name__ == "__main__":
    add_context_menu()
