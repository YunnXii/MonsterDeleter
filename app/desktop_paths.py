from __future__ import annotations

import ctypes
import os
import uuid
from pathlib import Path


# Windows Known Folder identifiers.
FOLDERID_DESKTOP = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
FOLDERID_PUBLIC_DESKTOP = uuid.UUID("C4AA340D-F20F-4863-AFEF-F87EF2E6BA25")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_uuid(cls, value: uuid.UUID) -> "_GUID":
        return cls.from_buffer_copy(value.bytes_le)


def _known_folder_path(folder_id: uuid.UUID) -> Path | None:
    """Ask Windows for a Known Folder's current filesystem location.

    This is the authoritative source for folders that users may redirect via
    Explorer's Location tab, OneDrive Known Folder Move, or enterprise policy.
    """
    if os.name != "nt":
        return None

    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        function = shell32.SHGetKnownFolderPath
        function.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        function.restype = ctypes.c_long

        guid = _GUID.from_uuid(folder_id)
        raw_path = ctypes.c_void_p()
        hr = int(function(ctypes.byref(guid), 0, None, ctypes.byref(raw_path)))
        if hr != 0 or not raw_path.value:
            return None

        try:
            value = ctypes.wstring_at(raw_path.value).strip()
            return Path(value) if value else None
        finally:
            ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ole32.CoTaskMemFree.restype = None
            ole32.CoTaskMemFree(raw_path)
    except Exception:
        return None


def _registry_user_desktop() -> Path | None:
    """Fallback for old/broken Known Folder registrations."""
    if os.name != "nt":
        return None

    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            raw, _value_type = winreg.QueryValueEx(key, "Desktop")
        value = os.path.expandvars(str(raw or "")).strip()
        return Path(value) if value else None
    except Exception:
        return None


def _fallback_paths() -> tuple[Path, ...]:
    values: list[Path] = []

    public = os.environ.get("PUBLIC")
    if public:
        values.append(Path(public) / "Desktop")

    # Last-resort compatibility only. On a healthy Windows installation the
    # Known Folder or registry paths above should win, including D:\ redirects.
    values.append(Path.home() / "Desktop")
    return tuple(values)


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.path.expandvars(str(path))))


def desktop_roots() -> tuple[Path, ...]:
    """Return real filesystem roots represented by the Windows desktop.

    Order matters: authoritative Known Folder paths come first, followed by the
    registry fallback and finally conventional compatibility paths. Duplicate
    locations are removed without requiring them to exist yet.
    """
    values: list[Path] = []

    user_known = _known_folder_path(FOLDERID_DESKTOP)
    if user_known is not None:
        values.append(user_known)

    public_known = _known_folder_path(FOLDERID_PUBLIC_DESKTOP)
    if public_known is not None:
        values.append(public_known)

    registry_user = _registry_user_desktop()
    if registry_user is not None:
        values.append(registry_user)

    values.extend(_fallback_paths())

    result: list[Path] = []
    seen: set[str] = set()
    for path in values:
        expanded = Path(os.path.expandvars(str(path)))
        key = _path_key(expanded)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(expanded)
    return tuple(result)
