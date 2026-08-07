from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from enum import Enum, auto as enum_auto
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

from .native_desktop import NativeDesktopHit, NativeDesktopProbe, probe_native_desktop
from .target_resolver import (
    PhysicalTarget,
    _known_desktop_roots,
    _physical_target,
    _safe_int,
    _safe_text,
)


MAX_PARENT_HOPS = 14
HOVER_HOLD_SECONDS = 0.32
HOVER_HOLD_MARGIN_X = 12
HOVER_HOLD_MARGIN_Y = 9


class AimStatus(Enum):
    FOUND = enum_auto()
    EMPTY = enum_auto()
    AMBIGUOUS = enum_auto()
    UNSUPPORTED = enum_auto()
    ERROR = enum_auto()


@dataclass(frozen=True)
class AimProbeResult:
    status: AimStatus
    name: str = ""
    target: PhysicalTarget | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status is AimStatus.FOUND and self.target is not None


@dataclass(frozen=True)
class AimSelectionResult:
    status: AimStatus
    path: Path | None = None
    target: PhysicalTarget | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return (
            self.status is AimStatus.FOUND
            and self.path is not None
            and self.target is not None
        )


@dataclass(frozen=True)
class _HitItem:
    control: object | None
    target: PhysicalTarget
    name: str
    root_class: str
    root_handle: int
    desktop_root: bool


_LAST_PROBE_RESULT: AimProbeResult | None = None
_LAST_PROBE_AT = 0.0


class AimTaskSignals(QObject):
    finished = pyqtSignal(int, object)


class AimProbeTask(QRunnable):
    def __init__(self, attempt_id: int, point: tuple[int, int]) -> None:
        super().__init__()
        self.attempt_id = attempt_id
        self.point = point
        self.signals = AimTaskSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        self.signals.finished.emit(self.attempt_id, probe_shell_item_at(self.point))


class AimSelectTask(QRunnable):
    def __init__(self, attempt_id: int, point: tuple[int, int]) -> None:
        super().__init__()
        self.attempt_id = attempt_id
        self.point = point
        self.signals = AimTaskSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        self.signals.finished.emit(self.attempt_id, resolve_shell_item_at(self.point))


def physical_cursor_position() -> tuple[int, int]:
    """Return the current cursor in Windows physical pixels."""
    if os.name != "nt":
        return (0, 0)

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    point = POINT()
    user32 = ctypes.windll.user32
    getter = getattr(user32, "GetPhysicalCursorPos", None)
    if getter is not None and getter(ctypes.byref(point)):
        return int(point.x), int(point.y)
    if user32.GetCursorPos(ctypes.byref(point)):
        return int(point.x), int(point.y)
    return (0, 0)


def point_hits_physical_target(
    point: tuple[int, int],
    target: PhysicalTarget,
    *,
    margin_x: int = 0,
    margin_y: int = 0,
) -> bool:
    """Return whether a physical cursor point lies in an optionally padded rect."""
    x, y = int(point[0]), int(point[1])
    return (
        target.left - max(0, margin_x) <= x <= target.right + max(0, margin_x)
        and target.top - max(0, margin_y) <= y <= target.bottom + max(0, margin_y)
    )


def _load_auto():
    try:
        import uiautomation as auto
    except Exception:
        return None
    return auto


def _parent(control):
    try:
        return control.GetParentControl()
    except Exception:
        return None


def _root_is_desktop(root) -> bool:
    class_name = _safe_text(root, "ClassName")
    name = _safe_text(root, "Name").casefold()
    return class_name in {"Progman", "WorkerW"} or name in {
        "program manager",
        "desktop",
        "桌面",
    }


def _hit_item_from_native(hit: NativeDesktopHit) -> _HitItem:
    target = PhysicalTarget(
        left=int(hit.left),
        top=int(hit.top),
        right=int(hit.right),
        bottom=int(hit.bottom),
        accessible_name=hit.name,
        selected=False,
        root_class="SysListView32",
    )
    return _HitItem(
        control=None,
        target=target,
        name=hit.name,
        root_class="SysListView32",
        root_handle=int(hit.listview_hwnd),
        desktop_root=True,
    )


def _find_uia_hit_item(auto, point: tuple[int, int]) -> _HitItem | None:
    """UIA path used for Explorer and as a compatibility desktop fallback."""
    try:
        control = auto.ControlFromPoint(int(point[0]), int(point[1]))
    except Exception:
        return None
    if control is None:
        return None

    list_item = None
    root = None
    current = control
    for _ in range(MAX_PARENT_HOPS):
        if current is None:
            break
        try:
            if list_item is None and int(current.ControlType) == int(auto.ControlType.ListItemControl):
                list_item = current
        except Exception:
            pass

        class_name = _safe_text(current, "ClassName")
        if class_name in {"CabinetWClass", "ExploreWClass", "Progman", "WorkerW"}:
            root = current
        current = _parent(current)

    if list_item is None or root is None:
        return None

    root_class = _safe_text(root, "ClassName")
    physical = _physical_target(list_item, root_class=root_class, selected=False)
    if physical is None:
        return None

    name = _safe_text(list_item, "Name").strip()
    if not name:
        return None

    return _HitItem(
        control=list_item,
        target=physical,
        name=name,
        root_class=root_class,
        root_handle=_safe_int(root, "NativeWindowHandle"),
        desktop_root=_root_is_desktop(root),
    )


def _native_desktop_result(point: tuple[int, int]) -> tuple[_HitItem | None, NativeDesktopProbe]:
    probe = probe_native_desktop(point)
    if probe.hit is not None:
        return _hit_item_from_native(probe.hit), probe
    return None, probe


def _native_desktop_is_definitive_empty(probe: NativeDesktopProbe) -> bool:
    return (
        probe.available
        and probe.visible
        and probe.hit is None
        and probe.diagnostic == "desktop-empty"
    )


def _probe_shell_item_once(point: tuple[int, int]) -> AimProbeResult:
    if os.name != "nt":
        return AimProbeResult(AimStatus.UNSUPPORTED, message="真准星目前只支持 Windows。")

    # Desktop is deliberately native-first. Its UIA provider can expose only the
    # FolderView after an application is minimized even though the native view
    # still highlights icons correctly.
    native_hit, native_probe = _native_desktop_result(point)
    if native_hit is not None:
        return AimProbeResult(
            AimStatus.FOUND,
            name=native_hit.name,
            target=native_hit.target,
        )
    if _native_desktop_is_definitive_empty(native_probe):
        return AimProbeResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")

    auto = _load_auto()
    if auto is None:
        if native_probe.available and native_probe.visible:
            return AimProbeResult(AimStatus.ERROR, message="桌面这一下没看清，再晃一下准星。")
        return AimProbeResult(AimStatus.ERROR, message="我的眼镜没加载好。")

    try:
        auto.SetGlobalSearchTimeout(0.25)
        with auto.UIAutomationInitializerInThread():
            hit = _find_uia_hit_item(auto, point)
            if hit is None:
                return AimProbeResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")
            return AimProbeResult(AimStatus.FOUND, name=hit.name, target=hit.target)
    except Exception as exc:
        return AimProbeResult(AimStatus.ERROR, message=f"这儿有点看不清：{exc}")


def probe_shell_item_at(point: tuple[int, int]) -> AimProbeResult:
    """Hover probe with a short visual-only hysteresis window.

    A single flaky sample should not make a valid label flash red. The cache is
    never used for final click selection; resolve_shell_item_at probes again.
    """
    global _LAST_PROBE_RESULT, _LAST_PROBE_AT

    result = _probe_shell_item_once(point)
    now = time.monotonic()
    if result.ok and result.name:
        _LAST_PROBE_RESULT = result
        _LAST_PROBE_AT = now
        return result

    cached = _LAST_PROBE_RESULT
    if (
        cached is not None
        and cached.ok
        and cached.target is not None
        and now - _LAST_PROBE_AT <= HOVER_HOLD_SECONDS
        and point_hits_physical_target(
            point,
            cached.target,
            margin_x=HOVER_HOLD_MARGIN_X,
            margin_y=HOVER_HOLD_MARGIN_Y,
        )
    ):
        return cached

    if cached is not None and (
        now - _LAST_PROBE_AT > HOVER_HOLD_SECONDS
        or cached.target is None
        or not point_hits_physical_target(
            point,
            cached.target,
            margin_x=HOVER_HOLD_MARGIN_X,
            margin_y=HOVER_HOLD_MARGIN_Y,
        )
    ):
        _LAST_PROBE_RESULT = None
        _LAST_PROBE_AT = 0.0
    return result


def _reset_probe_cache_for_tests() -> None:
    global _LAST_PROBE_RESULT, _LAST_PROBE_AT
    _LAST_PROBE_RESULT = None
    _LAST_PROBE_AT = 0.0


def _matching_entries(folder: Path, accessible_name: str) -> list[Path]:
    """Match display names conservatively when Explorer may hide extensions."""
    folded = accessible_name.strip().casefold()
    if not folded or not folder.is_dir():
        return []

    try:
        entries = list(folder.iterdir())
    except OSError:
        return []

    matches: list[Path] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.name.casefold() != folded and entry.stem.casefold() != folded:
            continue
        key = os.path.normcase(os.path.abspath(str(entry)))
        if key in seen:
            continue
        seen.add(key)
        matches.append(entry)
    return matches


def _resolve_desktop_name(accessible_name: str) -> tuple[Path | None, bool]:
    matches: list[Path] = []
    seen: set[str] = set()
    for root in _known_desktop_roots():
        for entry in _matching_entries(root, accessible_name):
            key = os.path.normcase(os.path.abspath(str(entry)))
            if key in seen:
                continue
            seen.add(key)
            matches.append(entry)

    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def _explorer_folder_paths(hwnd: int) -> list[Path]:
    """Return all filesystem folders exposed for one Explorer HWND.

    Windows 11 tabs may share a top-level HWND. Resolve the clicked display name
    across all matching Shell windows and accept it only when unique.
    """
    if os.name != "nt" or hwnd <= 0:
        return []

    try:
        import pythoncom
        import win32com.client
    except Exception:
        return []

    folders: list[Path] = []
    seen: set[str] = set()
    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        for window in shell.Windows():
            try:
                if int(window.HWND) != int(hwnd):
                    continue
                raw = str(window.Document.Folder.Self.Path or "").strip()
                if not raw or raw.startswith("::{"):
                    continue
                folder = Path(raw)
                if not folder.is_dir():
                    continue
                key = os.path.normcase(os.path.abspath(str(folder)))
                if key in seen:
                    continue
                seen.add(key)
                folders.append(folder)
            except Exception:
                continue
    except Exception:
        return []
    finally:
        pythoncom.CoUninitialize()
    return folders


def _resolve_explorer_name(hwnd: int, accessible_name: str) -> tuple[Path | None, bool, bool]:
    folders = _explorer_folder_paths(hwnd)
    if not folders:
        return None, False, False

    matches: list[Path] = []
    seen: set[str] = set()
    for folder in folders:
        for entry in _matching_entries(folder, accessible_name):
            key = os.path.normcase(os.path.abspath(str(entry)))
            if key in seen:
                continue
            seen.add(key)
            matches.append(entry)

    if len(matches) == 1:
        return matches[0], False, True
    return None, len(matches) > 1, True


def _selection_from_desktop_hit(hit: _HitItem) -> AimSelectionResult:
    path, ambiguous = _resolve_desktop_name(hit.name)
    if ambiguous:
        return AimSelectionResult(
            AimStatus.AMBIGUOUS,
            target=hit.target,
            message="桌面上同名的家伙有点多，我没认准。",
        )
    if path is None:
        return AimSelectionResult(
            AimStatus.EMPTY,
            target=hit.target,
            message="我看见图标了，但没找到它真正住哪儿。",
        )
    return AimSelectionResult(AimStatus.FOUND, path=path, target=hit.target)


def resolve_shell_item_at(point: tuple[int, int]) -> AimSelectionResult:
    """Resolve one screen point to a real filesystem Path + visible item rect."""
    if os.name != "nt":
        return AimSelectionResult(AimStatus.UNSUPPORTED, message="真准星目前只支持 Windows。")

    # Final selection repeats the native desktop hit from the click coordinate.
    # Hover cache is intentionally irrelevant here.
    native_hit, native_probe = _native_desktop_result(point)
    if native_hit is not None:
        return _selection_from_desktop_hit(native_hit)
    if _native_desktop_is_definitive_empty(native_probe):
        return AimSelectionResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")

    auto = _load_auto()
    if auto is None:
        if native_probe.available and native_probe.visible:
            return AimSelectionResult(AimStatus.ERROR, message="桌面这一下没看清，再瞄一次。")
        return AimSelectionResult(AimStatus.ERROR, message="我的眼镜没加载好，暂时瞄不了。")

    try:
        auto.SetGlobalSearchTimeout(0.45)
        with auto.UIAutomationInitializerInThread():
            hit = _find_uia_hit_item(auto, point)
    except Exception as exc:
        return AimSelectionResult(AimStatus.ERROR, message=f"刚才那一下没看清：{exc}")

    if hit is None:
        return AimSelectionResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")

    if hit.desktop_root:
        return _selection_from_desktop_hit(hit)

    path, ambiguous, shell_supported = _resolve_explorer_name(hit.root_handle, hit.name)
    if not shell_supported:
        return AimSelectionResult(
            AimStatus.UNSUPPORTED,
            target=hit.target,
            message="这个位置不是普通文件夹，我暂时踹不了。",
        )
    if ambiguous:
        return AimSelectionResult(
            AimStatus.AMBIGUOUS,
            target=hit.target,
            message="这个 Explorer 窗口里有同名目标，我没敢乱踹。",
        )
    if path is not None:
        return AimSelectionResult(AimStatus.FOUND, path=path, target=hit.target)
    return AimSelectionResult(
        AimStatus.EMPTY,
        target=hit.target,
        message="我看见它了，但没解析出真实文件路径。",
    )
