from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DeleteFailureKind(str, Enum):
    NONE = "none"
    IN_USE = "in_use"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    OTHER = "other"


@dataclass(frozen=True)
class DeleteResult:
    ok: bool
    message: str
    kind: DeleteFailureKind = DeleteFailureKind.NONE
    technical_detail: str = ""

    @property
    def retryable(self) -> bool:
        return self.kind in {
            DeleteFailureKind.IN_USE,
            DeleteFailureKind.PERMISSION,
            DeleteFailureKind.OTHER,
        }


def _exception_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _classify_exception(exc: BaseException) -> DeleteFailureKind:
    """Map low-level Windows/Python errors to a stable product-facing category."""
    for item in _exception_chain(exc):
        winerror = getattr(item, "winerror", None)
        error_no = getattr(item, "errno", None)

        if winerror in {32, 33}:  # sharing / lock violation
            return DeleteFailureKind.IN_USE
        if winerror in {5, 65}:  # access denied / network access denied
            return DeleteFailureKind.PERMISSION
        if winerror in {2, 3}:  # file/path not found
            return DeleteFailureKind.NOT_FOUND

        if error_no in {errno.EBUSY, getattr(errno, "ETXTBSY", -1)}:
            return DeleteFailureKind.IN_USE
        if error_no in {errno.EACCES, errno.EPERM}:
            return DeleteFailureKind.PERMISSION
        if error_no == errno.ENOENT:
            return DeleteFailureKind.NOT_FOUND

        if isinstance(item, FileNotFoundError):
            return DeleteFailureKind.NOT_FOUND
        if isinstance(item, PermissionError):
            return DeleteFailureKind.PERMISSION

    return DeleteFailureKind.OTHER


def _message_for_kind(kind: DeleteFailureKind) -> str:
    return {
        DeleteFailureKind.IN_USE: "文件正在被其他程序占用",
        DeleteFailureKind.PERMISSION: "Windows 拒绝了删除权限",
        DeleteFailureKind.NOT_FOUND: "目标已经不在原位置了",
        DeleteFailureKind.OTHER: "Windows 没能把它移入回收站",
        DeleteFailureKind.NONE: "",
    }[kind]


def _notify_shell_deleted(target: Path, *, was_directory: bool) -> None:
    """Tell Explorer that a successfully trashed path disappeared.

    send2trash normally triggers a shell refresh on its own, but Explorer can
    occasionally lag behind the overlay animation. This notification is best
    effort only; a refresh failure must never turn a successful delete into an
    application error.
    """
    if os.name != "nt":
        return

    try:
        import ctypes

        SHCNE_DELETE = 0x00000004
        SHCNE_RMDIR = 0x00000010
        SHCNF_PATHW = 0x0005
        SHCNF_FLUSH = 0x1000

        event = SHCNE_RMDIR if was_directory else SHCNE_DELETE
        ctypes.windll.shell32.SHChangeNotify(
            event,
            SHCNF_PATHW | SHCNF_FLUSH,
            str(target),
            None,
        )
    except Exception:
        # Cosmetic shell refresh only; the recycle-bin operation already won.
        pass


def move_to_recycle_bin(target: Path | None, *, demo: bool = False) -> DeleteResult:
    if demo:
        return DeleteResult(True, "演示模式：没有真的删除文件")
    if target is None:
        return DeleteResult(
            False,
            "没有收到要处理的文件路径",
            DeleteFailureKind.OTHER,
        )
    if not target.exists() and not target.is_symlink():
        return DeleteResult(
            False,
            _message_for_kind(DeleteFailureKind.NOT_FOUND),
            DeleteFailureKind.NOT_FOUND,
        )

    was_directory = target.is_dir()

    try:
        from send2trash import send2trash

        send2trash(str(target))
        _notify_shell_deleted(target, was_directory=was_directory)
        return DeleteResult(True, f"已移入回收站：{target.name}")
    except Exception as exc:
        kind = _classify_exception(exc)
        return DeleteResult(
            False,
            _message_for_kind(kind),
            kind,
            str(exc),
        )
