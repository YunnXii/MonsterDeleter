from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    """Return the source root or PyInstaller extraction directory."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def executable_command() -> tuple[str, str]:
    """Return executable and optional script argument for menu registration."""
    executable = Path(sys.executable).resolve()
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        return str(executable), ""

    script = Path(sys.argv[0]).resolve()
    pythonw = executable.with_name("pythonw.exe")
    if os.name == "nt" and pythonw.exists():
        executable = pythonw
    return str(executable), str(script)
