from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal


WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
VK_ESCAPE = 0x1B


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


_HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


def right_cancel_transition(message: int, pending: bool) -> tuple[bool, bool, bool]:
    """Return (consume, next_pending, emit_cancel) for an aim-mode right click.

    Cancellation deliberately fires on button-up, not button-down. The hook must
    remain installed long enough to swallow the complete right-click gesture;
    otherwise Windows can receive the orphaned RBUTTONUP after the controller
    tears the hook down and open the Desktop / Explorer context menu.
    """
    if int(message) == WM_RBUTTONDOWN:
        return True, True, False
    if int(message) == WM_RBUTTONUP:
        return True, False, bool(pending)
    return False, bool(pending), False


class AimInputHook(QObject):
    """Temporary low-level input hook used only while real aim mode is active.

    The visual aim overlay is transparent to input so UI Automation can still
    see Explorer underneath it. This hook captures the selection click before
    Explorer opens the file, and also provides right-click / Esc cancellation.
    """

    selected = pyqtSignal(int, int)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._installed = False
        self._stop_requested = threading.Event()
        self._mouse_proc = None
        self._keyboard_proc = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._installed)

    def start(self, timeout: float = 1.5) -> bool:
        if os.name != "nt":
            return False
        if self._thread and self._thread.is_alive():
            return self._installed

        self._ready.clear()
        self._stop_requested.clear()
        self._installed = False
        self._thread = threading.Thread(target=self._run, name="jiaqi-aim-hook", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self._installed

    def stop(self) -> None:
        self._stop_requested.set()
        if os.name == "nt" and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    int(self._thread_id), WM_QUIT, 0, 0
                )
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.8)
        self._thread = None
        self._thread_id = 0
        self._installed = False

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = int(kernel32.GetCurrentThreadId())

        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            _HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        right_cancel_pending = False

        def mouse_callback(code: int, wparam, lparam):
            nonlocal right_cancel_pending
            if code == HC_ACTION:
                message = int(wparam)
                if message in {WM_LBUTTONDOWN, WM_LBUTTONUP}:
                    if message == WM_LBUTTONDOWN:
                        data = ctypes.cast(
                            lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)
                        ).contents
                        self.selected.emit(int(data.pt.x), int(data.pt.y))
                    return 1

                consume, right_cancel_pending, emit_cancel = right_cancel_transition(
                    message,
                    right_cancel_pending,
                )
                if consume:
                    if emit_cancel:
                        self.cancelled.emit()
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def keyboard_callback(code: int, wparam, lparam):
            if code == HC_ACTION:
                message = int(wparam)
                data = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if int(data.vkCode) == VK_ESCAPE and message in {
                    WM_KEYDOWN,
                    WM_KEYUP,
                    WM_SYSKEYDOWN,
                    WM_SYSKEYUP,
                }:
                    if message in {WM_KEYDOWN, WM_SYSKEYDOWN}:
                        self.cancelled.emit()
                    return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._mouse_proc = _HOOKPROC(mouse_callback)
        self._keyboard_proc = _HOOKPROC(keyboard_callback)
        mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)
        keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_proc, None, 0)

        self._installed = bool(mouse_hook and keyboard_hook)
        self._ready.set()
        if not self._installed:
            if mouse_hook:
                user32.UnhookWindowsHookEx(mouse_hook)
            if keyboard_hook:
                user32.UnhookWindowsHookEx(keyboard_hook)
            return

        message = wintypes.MSG()
        try:
            while not self._stop_requested.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(mouse_hook)
            user32.UnhookWindowsHookEx(keyboard_hook)
            self._installed = False
            self._thread_id = 0
