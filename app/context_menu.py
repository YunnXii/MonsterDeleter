from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .resources import executable_command


@dataclass(frozen=True)
class MenuRegistrationResult:
    ok: bool
    message: str
    changed: bool = False


@dataclass(frozen=True)
class MenuRegistrationStatus:
    installed: bool
    current: bool
    expected_command: str


# Reuse the original key so installing this branch replaces the old monster item.
MENU_KEY = "SummonMonster"


def _roots() -> tuple[str, str]:
    return (
        rf"Software\Classes\*\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\shell\{MENU_KEY}",
    )


def _command_line() -> str:
    executable, script = executable_command()
    if script:
        return f'"{executable}" "{script}" "%1"'
    return f'"{executable}" "%1"'


def _icon_value() -> str:
    executable, script = executable_command()
    # A frozen EXE carries the generated Jiaqi head icon. During source-mode
    # development Python has no product icon, so keep a harmless shell fallback.
    if not script:
        return executable
    return "shell32.dll,32"


def _read_default_value(key_path: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return str(value)
    except FileNotFoundError:
        return None


def _read_named_value(key_path: str, name: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except (FileNotFoundError, OSError):
        return None


def context_menu_status(label: str) -> MenuRegistrationStatus:
    if os.name != "nt":
        return MenuRegistrationStatus(False, False, _command_line())

    command = _command_line()
    icon = _icon_value()
    roots = _roots()

    installed = False
    current = True
    for key_path in roots:
        existing_label = _read_default_value(key_path)
        existing_command = _read_default_value(key_path + r"\command")
        existing_icon = _read_named_value(key_path, "Icon")
        if existing_label is not None or existing_command is not None:
            installed = True
        if (
            existing_label != label
            or existing_command != command
            or existing_icon != icon
        ):
            current = False

    return MenuRegistrationStatus(installed, current and installed, command)


def register_context_menu(label: str) -> MenuRegistrationResult:
    if os.name != "nt":
        return MenuRegistrationResult(False, "右键菜单仅在 Windows 上可注册")

    import winreg

    command = _command_line()
    icon = _icon_value()

    try:
        for key_path in _roots():
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, label)
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as command_key:
                winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, command)
        return MenuRegistrationResult(True, "右键菜单已注册", True)
    except OSError as exc:
        return MenuRegistrationResult(False, f"右键菜单注册失败：{exc}")


def ensure_context_menu(label: str) -> MenuRegistrationResult:
    """Install the menu on first run and repair stale EXE/script paths later."""
    if os.name != "nt":
        return MenuRegistrationResult(False, "右键菜单仅在 Windows 上可注册")

    status = context_menu_status(label)
    if status.current:
        return MenuRegistrationResult(True, "右键菜单已经就位", False)

    result = register_context_menu(label)
    if not result.ok:
        return result

    if status.installed:
        return MenuRegistrationResult(True, "右键菜单路径已自动修复", True)
    return MenuRegistrationResult(True, "右键菜单已安装", True)


def unregister_context_menu() -> MenuRegistrationResult:
    if os.name != "nt":
        return MenuRegistrationResult(False, "右键菜单仅在 Windows 上可移除")

    import winreg

    try:
        for key_path in _roots():
            for path in (key_path + r"\command", key_path):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
                except FileNotFoundError:
                    pass
        return MenuRegistrationResult(True, "右键菜单已移除", True)
    except OSError as exc:
        return MenuRegistrationResult(False, f"右键菜单移除失败：{exc}")
