from pathlib import Path

from app.delete_service import (
    DeleteFailureKind,
    _classify_exception,
    move_to_recycle_bin,
)


class FakeWindowsError(Exception):
    def __init__(self, *, winerror: int | None = None, errno: int | None = None) -> None:
        super().__init__(f"winerror={winerror}, errno={errno}")
        self.winerror = winerror
        self.errno = errno


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


def test_windows_access_denied_is_permission() -> None:
    result = _classify_exception(FakeWindowsError(winerror=5))
    assert result is DeleteFailureKind.PERMISSION


def test_windows_file_not_found_is_not_found() -> None:
    result = _classify_exception(FakeWindowsError(winerror=2))
    assert result is DeleteFailureKind.NOT_FOUND
