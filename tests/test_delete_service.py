from pathlib import Path

from app.delete_service import (
    DeleteFailureKind,
    _classify_exception,
    move_to_recycle_bin,
)


class FakeWindowsError(Exception):
    def __init__(
        self,
        *,
        winerror: int | None = None,
        errno: int | None = None,
        hresult: int | None = None,
    ) -> None:
        super().__init__(f"winerror={winerror}, errno={errno}, hresult={hresult}")
        self.winerror = winerror
        self.errno = errno
        self.hresult = hresult


def test_demo_delete_succeeds_without_target() -> None:
    result = move_to_recycle_bin(None, demo=True)
    assert result.ok is True
    assert result.kind is DeleteFailureKind.NONE


def test_missing_target_is_classified() -> None:
    result = move_to_recycle_bin(Path("definitely-does-not-exist-123456789.txt"))
    assert result.ok is False
    assert result.kind is DeleteFailureKind.NOT_FOUND
    assert result.retryable is False


def test_windows_sharing_violation_is_in_use() -> None:
    result = _classify_exception(FakeWindowsError(winerror=32))
    assert result is DeleteFailureKind.IN_USE


def test_hresult_sharing_violation_is_in_use() -> None:
    # HRESULT_FROM_WIN32(ERROR_SHARING_VIOLATION) == 0x80070020.
    result = _classify_exception(FakeWindowsError(hresult=0x80070020))
    assert result is DeleteFailureKind.IN_USE


def test_shell_copyengine_sharing_violation_is_in_use() -> None:
    # send2trash can surface COPYENGINE_E_SHARING_VIOLATION_SRC as a signed
    # WinError: 0x80270027 == -2144927705.
    result = _classify_exception(FakeWindowsError(winerror=-2144927705))
    assert result is DeleteFailureKind.IN_USE


def test_windows_access_denied_is_permission() -> None:
    result = _classify_exception(FakeWindowsError(winerror=5))
    assert result is DeleteFailureKind.PERMISSION


def test_shell_copyengine_access_denied_is_permission() -> None:
    result = _classify_exception(FakeWindowsError(hresult=0x80270021))
    assert result is DeleteFailureKind.PERMISSION


def test_windows_file_not_found_is_not_found() -> None:
    result = _classify_exception(FakeWindowsError(winerror=2))
    assert result is DeleteFailureKind.NOT_FOUND


def test_shell_copyengine_path_not_found_is_not_found() -> None:
    result = _classify_exception(FakeWindowsError(hresult=0x80270023))
    assert result is DeleteFailureKind.NOT_FOUND
