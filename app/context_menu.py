from __future__ import annotations

import os
from dataclasses import dataclass

from .resources import executable_command


@dataclass(frozen=True)
class MenuRegistrationResult:
    ok: bool
    message: str


MENU_KEY = "JiaqiDesktopCleaner"


def _command_line() -> str:
    executable, script = executable_command()
    if script:
        return f'"{executable}" "{script}" "%1"'
    return f'"{executable}" "%1"'


def register_context_menu(label: str) -> MenuRegistrationResult:
    if os.name != "nt":
        return MenuRegistrationResult(False, "右键菜单仅在 Windows 上可注册")

    import winreg

    command = _command_line()
    roots = (
        rf"Software\Classes\*\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\shell\{MENU_KEY}",
    )

    try:
        for key_path in roots:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValue(key, "", winreg.REG_SZ, label)
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "shell32.dll,32")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as command_key:
                winreg.SetValue(command_key, "", winreg.REG_SZ, command)
        return MenuRegistrationResult(True, "右键菜单已注册")
    except OSError as exc:
        return MenuRegistrationResult(False, f"右键菜单注册失败：{exc}")


def unregister_context_menu() -> MenuRegistrationResult:
    if os.name != "nt":
        return MenuRegistrationResult(False, "右键菜单仅在 Windows 上可移除")

    import winreg

    roots = (
        rf"Software\Classes\*\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\shell\{MENU_KEY}",
    )

    try:
        for key_path in roots:
            for path in (key_path + r"\command", key_path):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
                except FileNotFoundError:
                    pass
        return MenuRegistrationResult(True, "右键菜单已移除")
    except OSError as exc:
        return MenuRegistrationResult(False, f"右键菜单移除失败：{exc}")
