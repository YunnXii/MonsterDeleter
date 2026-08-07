from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import Enum, auto as enum_auto
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

from .target_resolver import (
    PhysicalTarget,
    _known_desktop_roots,
    _physical_target,
    _safe_children,
    _safe_int,
    _safe_text,
)


MAX_PARENT_HOPS = 14
MAX_DESKTOP_HIT_CONTROLS = 3000
DESKTOP_HIT_MARGIN_X = 7
DESKTOP_HIT_MARGIN_Y = 5


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
    control: object
    target: PhysicalTarget
    name: str
    root_class: str
    root_handle: int
    desktop_root: bool


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
    """Return whether a physical cursor point lies in an optionally padded UIA rect."""
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


def _choose_geometric_hit(
    items: list[_HitItem],
    point: tuple[int, int],
) -> _HitItem | None:
    """Choose the closest desktop item whose padded UIA rect covers the point."""
    hits = [
        item
        for item in items
        if point_hits_physical_target(
            point,
            item.target,
            margin_x=DESKTOP_HIT_MARGIN_X,
            margin_y=DESKTOP_HIT_MARGIN_Y,
        )
    ]
    if not hits:
        return None

    x, y = int(point[0]), int(point[1])

    def score(item: _HitItem) -> tuple[float, int]:
        center_x, center_y = item.target.center
        distance_sq = float((center_x - x) ** 2 + (center_y - y) ** 2)
        area = max(1, item.target.right - item.target.left) * max(
            1, item.target.bottom - item.target.top
        )
        return distance_sq, area

    return min(hits, key=score)


def _desktop_geometric_hit(
    auto,
    root,
    point: tuple[int, int],
    *,
    root_class: str,
    root_handle: int,
) -> _HitItem | None:
    """Fallback for flaky Desktop ControlFromPoint providers.

    Windows' desktop sometimes returns FolderView / SysListView32 rather than the
    ListItem under the cursor after focus changes. The shell itself still knows
    the item geometry, so enumerate visible desktop ListItems and perform the
    final hit-test locally instead of declaring the point empty.
    """
    items: list[_HitItem] = []
    visited = 0
    try:
        iterator = auto.WalkTree(
            root,
            getChildren=_safe_children,
            includeTop=True,
            maxDepth=MAX_PARENT_HOPS,
        )
        for entry in iterator:
            control = entry[0]
            visited += 1
            if visited > MAX_DESKTOP_HIT_CONTROLS:
                break

            try:
                if int(control.ControlType) != int(auto.ControlType.ListItemControl):
                    continue
            except Exception:
                continue

            name = _safe_text(control, "Name").strip()
            if not name:
                continue
            physical = _physical_target(control, root_class=root_class, selected=False)
            if physical is None:
                continue

            if not point_hits_physical_target(
                point,
                physical,
                margin_x=DESKTOP_HIT_MARGIN_X,
                margin_y=DESKTOP_HIT_MARGIN_Y,
            ):
                continue

            items.append(
                _HitItem(
                    control=control,
                    target=physical,
                    name=name,
                    root_class=root_class,
                    root_handle=root_handle,
                    desktop_root=True,
                )
            )
    except Exception:
        return None

    return _choose_geometric_hit(items, point)


def _find_hit_item(auto, point: tuple[int, int]) -> _HitItem | None:
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

    if root is None:
        return None

    root_class = _safe_text(root, "ClassName")
    root_handle = _safe_int(root, "NativeWindowHandle")
    desktop_root = _root_is_desktop(root)

    if list_item is None:
        if desktop_root:
            return _desktop_geometric_hit(
                auto,
                root,
                point,
                root_class=root_class,
                root_handle=root_handle,
            )
        return None

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
        root_handle=root_handle,
        desktop_root=desktop_root,
    )


def probe_shell_item_at(point: tuple[int, int]) -> AimProbeResult:
    """Lightweight hover probe: identify a Desktop/Explorer ListItem by name only."""
    if os.name != "nt":
        return AimProbeResult(AimStatus.UNSUPPORTED, message="真准星目前只支持 Windows。")

    auto = _load_auto()
    if auto is None:
        return AimProbeResult(AimStatus.ERROR, message="我的眼镜没加载好。")

    try:
        auto.SetGlobalSearchTimeout(0.25)
        with auto.UIAutomationInitializerInThread():
            hit = _find_hit_item(auto, point)
            if hit is None:
                return AimProbeResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")
            return AimProbeResult(AimStatus.FOUND, name=hit.name, target=hit.target)
    except Exception as exc:
        return AimProbeResult(AimStatus.ERROR, message=f"这儿有点看不清：{exc}")


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

    Windows 11 tabs may share a top-level HWND. Enumerating every matching Shell
    window and resolving the clicked display name across them is safer than
    trusting whichever tab Shell.Application happens to return first.
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


def resolve_shell_item_at(point: tuple[int, int]) -> AimSelectionResult:
    """Resolve one screen point to a real filesystem Path + UIA rectangle."""
    if os.name != "nt":
        return AimSelectionResult(AimStatus.UNSUPPORTED, message="真准星目前只支持 Windows。")

    auto = _load_auto()
    if auto is None:
        return AimSelectionResult(AimStatus.ERROR, message="我的眼镜没加载好，暂时瞄不了。")

    try:
        auto.SetGlobalSearchTimeout(0.45)
        with auto.UIAutomationInitializerInThread():
            hit = _find_hit_item(auto, point)
    except Exception as exc:
        return AimSelectionResult(AimStatus.ERROR, message=f"刚才那一下没看清：{exc}")

    if hit is None:
        return AimSelectionResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")

    if hit.desktop_root:
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
