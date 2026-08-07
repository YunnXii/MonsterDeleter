from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeleteResult:
    ok: bool
    message: str


def move_to_recycle_bin(target: Path | None, *, demo: bool = False) -> DeleteResult:
    if demo:
        return DeleteResult(True, "演示模式：没有真的删除文件")
    if target is None:
        return DeleteResult(False, "没有收到要处理的文件路径")
    if not target.exists():
        return DeleteResult(False, "目标已经不在原位置了")

    try:
        from send2trash import send2trash

        send2trash(str(target))
        return DeleteResult(True, f"已移入回收站：{target.name}")
    except Exception as exc:
        return DeleteResult(False, f"没能处理它：{exc}")
