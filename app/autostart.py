from __future__ import annotations

import os

from .resources import executable_command


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "JiaqiCleaner"


def autostart_command() -> str:
    executable, script = executable_command()
    if script:
        return f'"{executable}" "{script}"'
    return f'"{executable}"'


def is_autostart_enabled() -> bool:
    if os.name != "nt":
        return False

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value) == autostart_command()
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "开机启动仅支持 Windows"

    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    autostart_command(),
                )
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True, "开机启动已开启" if enabled else "开机启动已关闭"
    except OSError as exc:
        return False, f"开机启动设置失败：{exc}"
