from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtWidgets import QMessageBox

from .context_menu import MenuRegistrationResult


class LaunchAction(Enum):
    CLOSE = auto()
    DEMO = auto()
    UNINSTALL_MENU = auto()


def show_launch_prompt(menu_result: MenuRegistrationResult) -> LaunchAction:
    """Show a tiny first-run / maintenance prompt instead of auto-playing demo."""
    box = QMessageBox()
    box.setWindowTitle("叫家琦来")
    box.setIcon(QMessageBox.Icon.Information)

    if menu_result.changed:
        box.setText("部署完成。以后看哪个文件不顺眼，右键叫我。")
    else:
        box.setText("我已经在右键菜单里待命了。")

    box.setInformativeText(
        f"{menu_result.message}\n\n"
        "右键文件或文件夹，选择“叫家琦来收拾它”即可。"
    )

    demo_button = box.addButton("先演示一下", QMessageBox.ButtonRole.ActionRole)
    uninstall_button = box.addButton("移除右键菜单", QMessageBox.ButtonRole.DestructiveRole)
    close_button = box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(close_button)
    box.exec()

    clicked = box.clickedButton()
    if clicked is demo_button:
        return LaunchAction.DEMO
    if clicked is uninstall_button:
        return LaunchAction.UNINSTALL_MENU
    return LaunchAction.CLOSE
