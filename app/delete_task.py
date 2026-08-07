from __future__ import annotations

import ctypes
import os
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

from .delete_service import DeleteResult, move_to_recycle_bin


class DeleteTaskSignals(QObject):
    finished = pyqtSignal(int, object)


class DeleteTask(QRunnable):
    """Run the potentially slow Windows Shell recycle operation in a worker.

    Office/Shell sharing violations can take noticeable time to return. Keeping
    that OLE work off the Qt GUI thread means the kick animation can finish
    normally instead of freezing on its impact pose.
    """

    def __init__(
        self,
        attempt_id: int,
        target: Path | None,
        *,
        demo: bool = False,
    ) -> None:
        super().__init__()
        self.attempt_id = attempt_id
        self.target = target
        self.demo = demo
        self.signals = DeleteTaskSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        initialized_com = _initialize_com_sta()
        try:
            result = move_to_recycle_bin(self.target, demo=self.demo)
        finally:
            if initialized_com:
                _uninitialize_com()

        self.signals.finished.emit(self.attempt_id, result)


def _initialize_com_sta() -> bool:
    """Initialize a worker thread for Shell/OLE calls when running on Windows."""
    if os.name != "nt":
        return False

    try:
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        ole32.CoInitializeEx.restype = ctypes.c_long
        # COINIT_APARTMENTTHREADED. S_OK (0) and S_FALSE (1) both require a
        # matching CoUninitialize call. RPC_E_CHANGED_MODE does not.
        hr = int(ole32.CoInitializeEx(None, 0x2))
        return hr in (0, 1)
    except Exception:
        # send2trash may initialize COM internally; failure here is not fatal.
        return False


def _uninitialize_com() -> None:
    try:
        ctypes.windll.ole32.CoUninitialize()
    except Exception:
        pass
