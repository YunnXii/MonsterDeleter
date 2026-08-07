from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import Enum, auto as enum_auto
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRunnable, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from .desktop_paths import desktop_roots


MAX_TREE_DEPTH = 12
MAX_VISITED_CONTROLS = 7000


class ResolveStatus(Enum):
    FOUND = enum_auto()
    NOT_VISIBLE = enum_auto()
    AMBIGUOUS = enum_auto()
    UNSUPPORTED = enum_auto()
    ERROR = enum_auto()


@dataclass(frozen=True)
class PhysicalTarget:
    left: int
    top: int
    right: int
    bottom: int
    accessible_name: str
    selected: bool
    root_class: str

    @property
    def center(self) -> tuple[int, int]:
        return (
            round((self.left + self.right) / 2),
            round((self.top + self.bottom) / 2),
        )


@dataclass(frozen=True)
class ResolveResult:
    status: ResolveStatus
    target: PhysicalTarget | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ResolveStatus.FOUND and self.target is not None


@dataclass(frozen=True)
class _Candidate:
    target: PhysicalTarget
    score: int
    exact_name: bool
    foreground_root: bool
    desktop_root: bool


class TargetResolveSignals(QObject):
    finished = pyqtSignal(int, object)


class TargetResolveTask(QRunnable):
    """Resolve a known filesystem path to its visible Explorer/Desktop item."""

    def __init__(self, attempt_id: int, target: Path) -> None:
        super().__init__()
        self.attempt_id = attempt_id
        self.target = target
        self.signals = TargetResolveSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        result = resolve_visible_target(self.target)
        self.signals.finished.emit(self.attempt_id, result)


def _candidate_names(target: Path) -> tuple[str, ...]:
    """Names Explorer may expose when file extensions are hidden."""
    names: list[str] = []
    for value in (target.name, target.stem):
        value = value.strip()
        if value and value.casefold() not in {item.casefold() for item in names}:
            names.append(value)
    return tuple(names)


def _known_desktop_roots() -> tuple[Path, ...]:
    """Compatibility shim shared by path-to-screen and aim-to-path resolvers."""
    return desktop_roots()


def _is_desktop_target(target: Path) -> bool:
    parent = os.path.normcase(os.path.abspath(str(target.parent)))
    return any(parent == os.path.normcase(os.path.abspath(str(root))) for root in _known_desktop_roots())


def _process_name(pid: int) -> str:
    if os.name != "nt" or pid <= 0:
        return ""

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""

    try:
        size = ctypes.c_uint32(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        query = kernel32.QueryFullProcessImageNameW
        query.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
        query.restype = ctypes.c_int
        if not query(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return Path(buffer.value).name.casefold()
    finally:
        kernel32.CloseHandle(handle)


def _safe_text(control, attr: str) -> str:
    try:
        value = getattr(control, attr)
    except Exception:
        return ""
    return str(value or "")


def _safe_int(control, attr: str) -> int:
    try:
        return int(getattr(control, attr) or 0)
    except Exception:
        return 0


def _safe_children(control):
    try:
        return control.GetChildren()
    except Exception:
        return []


def _is_selected(control) -> bool:
    try:
        pattern = control.GetSelectionItemPattern()
        return bool(pattern and pattern.IsSelected)
    except Exception:
        return False


def _physical_target(control, *, root_class: str, selected: bool) -> PhysicalTarget | None:
    try:
        rect = control.BoundingRectangle
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
    except Exception:
        return None

    if right <= left or bottom <= top:
        return None

    try:
        if bool(control.IsOffscreen):
            return None
    except Exception:
        pass

    return PhysicalTarget(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        accessible_name=_safe_text(control, "Name"),
        selected=selected,
        root_class=root_class,
    )


def _shell_roots(auto):
    """Return visible top-level Explorer/desktop UIA roots only."""
    try:
        root = auto.GetRootControl()
        top_level = root.GetChildren()
    except Exception:
        return []

    roots = []
    seen_handles: set[int] = set()
    explorer_pids: dict[int, bool] = {}

    for control in top_level:
        class_name = _safe_text(control, "ClassName")
        name = _safe_text(control, "Name")
        pid = _safe_int(control, "ProcessId")
        handle = _safe_int(control, "NativeWindowHandle")

        if pid not in explorer_pids:
            explorer_pids[pid] = _process_name(pid) == "explorer.exe"

        shellish_class = class_name in {
            "CabinetWClass",
            "ExploreWClass",
            "Progman",
            "WorkerW",
        }
        shellish_name = name.casefold() in {"program manager", "desktop", "桌面"}
        if not explorer_pids.get(pid, False) and not shellish_class and not shellish_name:
            continue
        if class_name == "Shell_TrayWnd":
            continue
        if handle and handle in seen_handles:
            continue
        if handle:
            seen_handles.add(handle)
        roots.append(control)

    return roots


def _collect_candidates(auto, target: Path) -> list[_Candidate]:
    names = _candidate_names(target)
    folded = {name.casefold(): name for name in names}
    if not folded:
        return []

    expected_desktop = _is_desktop_target(target)
    foreground = 0
    try:
        foreground = int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        pass

    candidates: list[_Candidate] = []
    visited = 0

    for root in _shell_roots(auto):
        root_class = _safe_text(root, "ClassName")
        root_handle = _safe_int(root, "NativeWindowHandle")
        foreground_root = bool(root_handle and foreground and root_handle == foreground)
        desktop_root = root_class in {"Progman", "WorkerW"} or _safe_text(root, "Name").casefold() in {
            "program manager",
            "desktop",
            "桌面",
        }

        try:
            iterator = auto.WalkTree(
                root,
                getChildren=_safe_children,
                includeTop=True,
                maxDepth=MAX_TREE_DEPTH,
            )
            for item in iterator:
                control = item[0]
                visited += 1
                if visited > MAX_VISITED_CONTROLS:
                    return candidates

                try:
                    if int(control.ControlType) != int(auto.ControlType.ListItemControl):
                        continue
                except Exception:
                    continue

                name = _safe_text(control, "Name")
                if name.casefold() not in folded:
                    continue

                selected = _is_selected(control)
                physical = _physical_target(control, root_class=root_class, selected=selected)
                if physical is None:
                    continue

                exact_name = name.casefold() == target.name.casefold()
                score = 0
                if selected:
                    score += 1000
                score += 90 if exact_name else 65
                if foreground_root:
                    score += 120
                if desktop_root == expected_desktop:
                    score += 55

                candidates.append(
                    _Candidate(
                        target=physical,
                        score=score,
                        exact_name=exact_name,
                        foreground_root=foreground_root,
                        desktop_root=desktop_root,
                    )
                )
        except Exception:
            continue

    return candidates


def _choose_candidate(candidates: list[_Candidate]) -> ResolveResult:
    if not candidates:
        return ResolveResult(
            ResolveStatus.NOT_VISIBLE,
            message="我知道要踹谁，但没看见它站哪儿。把文件所在的桌面或文件夹窗口露出来，再叫我一次。",
        )

    selected = [candidate for candidate in candidates if candidate.target.selected]
    pool = selected or candidates
    pool.sort(key=lambda item: item.score, reverse=True)

    best = pool[0]
    if len(pool) == 1:
        return ResolveResult(ResolveStatus.FOUND, best.target)

    second = pool[1]
    if best.score - second.score >= 40:
        return ResolveResult(ResolveStatus.FOUND, best.target)

    exact = [candidate for candidate in pool if candidate.exact_name]
    if len(exact) == 1:
        return ResolveResult(ResolveStatus.FOUND, exact[0].target)

    foreground = [candidate for candidate in pool if candidate.foreground_root]
    if len(foreground) == 1:
        return ResolveResult(ResolveStatus.FOUND, foreground[0].target)

    return ResolveResult(
        ResolveStatus.AMBIGUOUS,
        message="同名的家伙有点多，我没认准。把要踹的那个文件夹窗口放到前面，再试一次。",
    )


def resolve_visible_target(target: Path) -> ResolveResult:
    """Resolve a known path to one visible Desktop/Explorer item rectangle."""
    if os.name != "nt":
        return ResolveResult(ResolveStatus.UNSUPPORTED, message="自动找文件位置目前只支持 Windows。")

    try:
        import uiautomation as auto
    except Exception as exc:
        return ResolveResult(
            ResolveStatus.ERROR,
            message=f"我的眼镜没加载好，暂时看不清文件在哪儿。{exc}",
        )

    try:
        auto.SetGlobalSearchTimeout(0.7)
        with auto.UIAutomationInitializerInThread():
            return _choose_candidate(_collect_candidates(auto, target))
    except Exception as exc:
        return ResolveResult(
            ResolveStatus.ERROR,
            message=f"我找它的时候眼镜起雾了：{exc}",
        )


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_uint32),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def physical_to_qt_global(point: tuple[int, int]) -> QPoint:
    """Convert UI Automation physical pixels to Qt global logical coordinates."""
    x, y = int(point[0]), int(point[1])
    if os.name != "nt":
        return QPoint(x, y)

    try:
        user32 = ctypes.windll.user32
        MONITOR_DEFAULTTONEAREST = 2
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        monitor = user32.MonitorFromPoint(_POINT(x, y), MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return QPoint(x, y)

        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return QPoint(x, y)

        device = str(info.szDevice).casefold()
        screens = QApplication.screens()
        screen = next((item for item in screens if item.name().casefold() == device), None)
        if screen is None:
            return QPoint(x, y)

        ratio = float(screen.devicePixelRatio()) or 1.0
        geometry = screen.geometry()
        logical_x = geometry.left() + round((x - info.rcMonitor.left) / ratio)
        logical_y = geometry.top() + round((y - info.rcMonitor.top) / ratio)
        return QPoint(logical_x, logical_y)
    except Exception:
        return QPoint(x, y)
