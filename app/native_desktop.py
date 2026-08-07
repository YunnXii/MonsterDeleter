from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


LVM_FIRST = 0x1000
LVM_GETITEMRECT = LVM_FIRST + 14
LVM_HITTEST = LVM_FIRST + 18
LVM_GETITEMTEXTW = LVM_FIRST + 115
LVIF_TEXT = 0x0001
LVIR_BOUNDS = 0

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

GA_ROOT = 2
GW_HWNDNEXT = 2
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
SMTO_ABORTIFHUNG = 0x0002
MESSAGE_TIMEOUT_MS = 140
TEXT_CAPACITY = 520

_DEBUG_LOCK = threading.Lock()


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _LVHITTESTINFO(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("flags", ctypes.c_uint),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("iGroup", ctypes.c_int),
    ]


class _LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", ctypes.c_uint),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("stateMask", ctypes.c_uint),
        ("pszText", ctypes.c_void_p),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", ctypes.c_ssize_t),
        ("iIndent", ctypes.c_int),
        ("iGroupId", ctypes.c_int),
        ("cColumns", ctypes.c_uint),
        ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p),
        ("iGroup", ctypes.c_int),
    ]


@dataclass(frozen=True)
class NativeDesktopHit:
    listview_hwnd: int
    item_index: int
    name: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int, int]:
        return (
            round((self.left + self.right) / 2),
            round((self.top + self.bottom) / 2),
        )


@dataclass(frozen=True)
class NativeDesktopProbe:
    available: bool
    visible: bool
    hit: NativeDesktopHit | None = None
    diagnostic: str = ""


@dataclass(frozen=True)
class _DesktopView:
    host_hwnd: int
    defview_hwnd: int
    listview_hwnd: int
    explorer_pid: int


def _debug(message: str) -> None:
    """Optional developer-only diagnostics enabled with JIAQI_AIM_DEBUG=1."""
    if os.environ.get("JIAQI_AIM_DEBUG", "").strip().casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    try:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "JiaqiCleaner"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "aim-debug.log"
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with _DEBUG_LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _window_class(hwnd: int) -> str:
    if os.name != "nt" or not hwnd:
        return ""
    try:
        user32 = ctypes.windll.user32
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        buffer = ctypes.create_unicode_buffer(256)
        if user32.GetClassNameW(wintypes.HWND(hwnd), buffer, len(buffer)) <= 0:
            return ""
        return buffer.value
    except Exception:
        return ""


def _window_pid(hwnd: int) -> int:
    if os.name != "nt" or not hwnd:
        return 0
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def _find_desktop_view() -> _DesktopView | None:
    if os.name != "nt":
        return None

    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND

    defview = 0
    progman = int(user32.FindWindowW("Progman", None) or 0)
    if progman:
        defview = int(
            user32.FindWindowExW(
                wintypes.HWND(progman),
                None,
                "SHELLDLL_DefView",
                None,
            )
            or 0
        )

    if not defview:
        found: list[int] = []
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @enum_proc_type
        def enum_proc(hwnd, _lparam):
            child = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if child:
                found.append(int(child))
                return False
            return True

        user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.EnumWindows(enum_proc, 0)
        if found:
            defview = found[0]

    if not defview:
        return None

    listview = int(
        user32.FindWindowExW(
            wintypes.HWND(defview),
            None,
            "SysListView32",
            "FolderView",
        )
        or 0
    )
    if not listview:
        listview = int(
            user32.FindWindowExW(
                wintypes.HWND(defview),
                None,
                "SysListView32",
                None,
            )
            or 0
        )
    if not listview:
        return None

    host = int(user32.GetAncestor(wintypes.HWND(defview), GA_ROOT) or 0)
    if not host:
        return None
    pid = _window_pid(listview)
    if not pid:
        return None
    return _DesktopView(host, defview, listview, pid)


def _window_rect_contains(hwnd: int, point: tuple[int, int]) -> bool:
    if not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        rect = _RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return False
        x, y = int(point[0]), int(point[1])
        return rect.left <= x < rect.right and rect.top <= y < rect.bottom
    except Exception:
        return False


def _window_exstyle(hwnd: int) -> int:
    try:
        user32 = ctypes.windll.user32
        getter = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        getter.argtypes = [wintypes.HWND, ctypes.c_int]
        getter.restype = ctypes.c_ssize_t
        return int(getter(wintypes.HWND(hwnd), GWL_EXSTYLE))
    except Exception:
        return 0


def _top_root_at_point(point: tuple[int, int]) -> int:
    """Return the first non-input-transparent top-level window at the point."""
    if os.name != "nt":
        return 0

    try:
        user32 = ctypes.windll.user32
        user32.WindowFromPoint.argtypes = [_POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL

        raw = int(user32.WindowFromPoint(_POINT(int(point[0]), int(point[1]))) or 0)
        if not raw:
            return 0
        current = int(user32.GetAncestor(wintypes.HWND(raw), GA_ROOT) or raw)

        for _ in range(96):
            if not current:
                break
            if (
                user32.IsWindowVisible(wintypes.HWND(current))
                and not user32.IsIconic(wintypes.HWND(current))
                and _window_rect_contains(current, point)
                and not (_window_exstyle(current) & WS_EX_TRANSPARENT)
            ):
                return current
            current = int(user32.GetWindow(wintypes.HWND(current), GW_HWNDNEXT) or 0)
    except Exception:
        return 0
    return 0


def _desktop_is_visible_at_point(view: _DesktopView, point: tuple[int, int]) -> bool:
    top = _top_root_at_point(point)
    if not top:
        return False
    if top == view.host_hwnd:
        return True

    # Windows may place another WorkerW/Progman shell layer above the actual
    # SHELLDLL_DefView host. Accept it only when it belongs to the same Explorer
    # process; ordinary application windows must never reveal icons behind them.
    return (
        _window_pid(top) == view.explorer_pid
        and _window_class(top) in {"Progman", "WorkerW"}
    )


class _RemoteProcess:
    def __init__(self, pid: int) -> None:
        self.pid = int(pid)
        self.handle = 0
        self._allocations: list[int] = []

    def __enter__(self) -> "_RemoteProcess":
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        access = (
            PROCESS_VM_OPERATION
            | PROCESS_VM_READ
            | PROCESS_VM_WRITE
            | PROCESS_QUERY_LIMITED_INFORMATION
        )
        self.handle = int(kernel32.OpenProcess(access, False, self.pid) or 0)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess(explorer.exe) failed")
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        kernel32 = ctypes.windll.kernel32
        if self.handle:
            kernel32.VirtualFreeEx.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                ctypes.c_size_t,
                wintypes.DWORD,
            ]
            kernel32.VirtualFreeEx.restype = wintypes.BOOL
            for address in reversed(self._allocations):
                kernel32.VirtualFreeEx(
                    wintypes.HANDLE(self.handle),
                    ctypes.c_void_p(address),
                    0,
                    MEM_RELEASE,
                )
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle(wintypes.HANDLE(self.handle))
        self._allocations.clear()
        self.handle = 0

    def alloc(self, size: int) -> int:
        kernel32 = ctypes.windll.kernel32
        kernel32.VirtualAllocEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_size_t,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.VirtualAllocEx.restype = ctypes.c_void_p
        address = int(
            kernel32.VirtualAllocEx(
                wintypes.HANDLE(self.handle),
                None,
                max(1, int(size)),
                MEM_COMMIT | MEM_RESERVE,
                PAGE_READWRITE,
            )
            or 0
        )
        if not address:
            raise OSError(ctypes.get_last_error(), "VirtualAllocEx failed")
        self._allocations.append(address)
        return address

    def write_bytes(self, address: int, data: bytes) -> None:
        kernel32 = ctypes.windll.kernel32
        kernel32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel32.WriteProcessMemory.restype = wintypes.BOOL
        source = ctypes.create_string_buffer(data)
        written = ctypes.c_size_t()
        if not kernel32.WriteProcessMemory(
            wintypes.HANDLE(self.handle),
            ctypes.c_void_p(address),
            ctypes.cast(source, ctypes.c_void_p),
            len(data),
            ctypes.byref(written),
        ) or written.value != len(data):
            raise OSError(ctypes.get_last_error(), "WriteProcessMemory failed")

    def read_bytes(self, address: int, size: int) -> bytes:
        kernel32 = ctypes.windll.kernel32
        kernel32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel32.ReadProcessMemory.restype = wintypes.BOOL
        buffer = ctypes.create_string_buffer(max(1, int(size)))
        read = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            wintypes.HANDLE(self.handle),
            ctypes.c_void_p(address),
            ctypes.cast(buffer, ctypes.c_void_p),
            size,
            ctypes.byref(read),
        ):
            raise OSError(ctypes.get_last_error(), "ReadProcessMemory failed")
        return bytes(buffer.raw[: read.value])

    def write_struct(self, address: int, value: ctypes.Structure) -> None:
        self.write_bytes(
            address,
            ctypes.string_at(ctypes.byref(value), ctypes.sizeof(value)),
        )

    def read_struct(self, address: int, struct_type):
        data = self.read_bytes(address, ctypes.sizeof(struct_type))
        if len(data) < ctypes.sizeof(struct_type):
            raise OSError("ReadProcessMemory returned a short structure")
        return struct_type.from_buffer_copy(data)


def _send_message(hwnd: int, message: int, wparam: int, lparam: int) -> int | None:
    user32 = ctypes.windll.user32
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    ok = user32.SendMessageTimeoutW(
        wintypes.HWND(hwnd),
        int(message),
        wintypes.WPARAM(int(wparam)),
        wintypes.LPARAM(int(lparam)),
        SMTO_ABORTIFHUNG,
        MESSAGE_TIMEOUT_MS,
        ctypes.byref(result),
    )
    if not ok:
        return None
    return int(ctypes.c_ssize_t(result.value).value)


def _screen_to_client(hwnd: int, point: tuple[int, int]) -> tuple[int, int] | None:
    user32 = ctypes.windll.user32
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(_POINT)]
    user32.ScreenToClient.restype = wintypes.BOOL
    value = _POINT(int(point[0]), int(point[1]))
    if not user32.ScreenToClient(wintypes.HWND(hwnd), ctypes.byref(value)):
        return None
    return int(value.x), int(value.y)


def _client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int] | None:
    user32 = ctypes.windll.user32
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(_POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    value = _POINT(int(x), int(y))
    if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(value)):
        return None
    return int(value.x), int(value.y)


def _native_item_index(
    process: _RemoteProcess,
    listview_hwnd: int,
    client_point: tuple[int, int],
) -> int | None:
    info = _LVHITTESTINFO()
    info.pt = _POINT(int(client_point[0]), int(client_point[1]))
    info.iItem = -1
    remote = process.alloc(ctypes.sizeof(info))
    process.write_struct(remote, info)
    result = _send_message(listview_hwnd, LVM_HITTEST, 0, remote)
    if result is None or result < 0:
        return None
    return int(result)


def _native_item_name(
    process: _RemoteProcess,
    listview_hwnd: int,
    item_index: int,
) -> str:
    text_size = TEXT_CAPACITY * ctypes.sizeof(ctypes.c_wchar)
    remote_text = process.alloc(text_size)
    remote_item = process.alloc(ctypes.sizeof(_LVITEMW))

    item = _LVITEMW()
    item.mask = LVIF_TEXT
    item.iItem = int(item_index)
    item.iSubItem = 0
    item.pszText = remote_text
    item.cchTextMax = TEXT_CAPACITY
    process.write_struct(remote_item, item)

    count = _send_message(
        listview_hwnd,
        LVM_GETITEMTEXTW,
        int(item_index),
        remote_item,
    )
    if count is None or count <= 0:
        return ""
    raw = process.read_bytes(remote_text, min(TEXT_CAPACITY - 1, count) * 2 + 2)
    try:
        return raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0].strip()
    except Exception:
        return ""


def _native_item_rect(
    process: _RemoteProcess,
    listview_hwnd: int,
    item_index: int,
) -> tuple[int, int, int, int] | None:
    rect = _RECT()
    rect.left = LVIR_BOUNDS
    remote = process.alloc(ctypes.sizeof(rect))
    process.write_struct(remote, rect)
    ok = _send_message(
        listview_hwnd,
        LVM_GETITEMRECT,
        int(item_index),
        remote,
    )
    if not ok:
        return None
    rect = process.read_struct(remote, _RECT)
    top_left = _client_to_screen(listview_hwnd, rect.left, rect.top)
    bottom_right = _client_to_screen(listview_hwnd, rect.right, rect.bottom)
    if top_left is None or bottom_right is None:
        return None
    left, top = top_left
    right, bottom = bottom_right
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def probe_native_desktop(point: tuple[int, int]) -> NativeDesktopProbe:
    """Hit-test the visible Windows desktop without relying on UI Automation.

    The desktop's UIA provider can stop exposing ListItems after focus changes
    even while the native FolderView still highlights icons. This talks directly
    to the shell's SysListView32 so the result follows the view that actually
    paints that hover rectangle.
    """
    if os.name != "nt":
        return NativeDesktopProbe(False, False, diagnostic="not-windows")

    view = _find_desktop_view()
    if view is None:
        return NativeDesktopProbe(False, False, diagnostic="desktop-listview-not-found")

    if not _desktop_is_visible_at_point(view, point):
        return NativeDesktopProbe(True, False, diagnostic="desktop-covered")

    client = _screen_to_client(view.listview_hwnd, point)
    if client is None:
        return NativeDesktopProbe(True, True, diagnostic="screen-to-client-failed")

    try:
        with _RemoteProcess(view.explorer_pid) as process:
            item_index = _native_item_index(process, view.listview_hwnd, client)
            if item_index is None:
                _debug(
                    f"point={point} desktop=visible hwnd=0x{view.listview_hwnd:X} native_hit=none"
                )
                return NativeDesktopProbe(True, True, diagnostic="desktop-empty")

            name = _native_item_name(process, view.listview_hwnd, item_index)
            rect = _native_item_rect(process, view.listview_hwnd, item_index)
            if not name or rect is None:
                diagnostic = (
                    f"native-item-incomplete index={item_index} "
                    f"name={name!r} rect={rect!r}"
                )
                _debug(f"point={point} {diagnostic}")
                return NativeDesktopProbe(True, True, diagnostic=diagnostic)

            hit = NativeDesktopHit(
                listview_hwnd=view.listview_hwnd,
                item_index=item_index,
                name=name,
                left=rect[0],
                top=rect[1],
                right=rect[2],
                bottom=rect[3],
            )
            _debug(
                f"point={point} desktop=visible hwnd=0x{view.listview_hwnd:X} "
                f"native_hit={item_index} name={name!r} rect={rect!r}"
            )
            return NativeDesktopProbe(True, True, hit=hit, diagnostic="native-hit")
    except Exception as exc:
        diagnostic = f"native-desktop-error: {type(exc).__name__}: {exc}"
        _debug(f"point={point} {diagnostic}")
        return NativeDesktopProbe(True, True, diagnostic=diagnostic)
