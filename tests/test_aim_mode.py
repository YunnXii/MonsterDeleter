import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import app.aim_resolver as aim_resolver
import app.target_resolver as target_resolver
from app.aim_overlay import AimOverlay
from app.aim_resolver import (
    AimProbeResult,
    AimStatus,
    _hit_item_from_native,
    _matching_entries,
    _native_desktop_is_definitive_empty,
    _reset_probe_cache_for_tests,
    _resolve_desktop_name,
    point_hits_physical_target,
    probe_shell_item_at,
)
from app.native_desktop import NativeDesktopHit, NativeDesktopProbe
from app.target_resolver import PhysicalTarget


_APP = QApplication.instance() or QApplication([])


def _physical(name: str, left: int, top: int, right: int, bottom: int) -> PhysicalTarget:
    return PhysicalTarget(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        accessible_name=name,
        selected=False,
        root_class="WorkerW",
    )


def test_hidden_extension_name_resolves_to_real_file(tmp_path) -> None:
    target = tmp_path / "年度总结.docx"
    target.write_text("demo", encoding="utf-8")

    assert _matching_entries(tmp_path, "年度总结") == [target]
    assert _matching_entries(tmp_path, "年度总结.docx") == [target]


def test_hidden_extension_collision_stays_ambiguous(tmp_path) -> None:
    folder = tmp_path / "资料"
    folder.mkdir()
    file = tmp_path / "资料.docx"
    file.write_text("demo", encoding="utf-8")

    matches = _matching_entries(tmp_path, "资料")
    assert set(matches) == {folder, file}


def test_aimed_desktop_name_uses_redirected_windows_desktop(monkeypatch, tmp_path) -> None:
    redirected = tmp_path / "D-drive-desktop"
    redirected.mkdir()
    target = redirected / "桌面文件.docx"
    target.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(target_resolver, "desktop_roots", lambda: (redirected,))

    resolved, ambiguous = _resolve_desktop_name("桌面文件")
    assert ambiguous is False
    assert resolved == target


def test_native_desktop_hit_converts_to_shared_physical_target() -> None:
    native = NativeDesktopHit(
        listview_hwnd=0x1234,
        item_index=17,
        name="年度总结.docx",
        left=100,
        top=120,
        right=188,
        bottom=204,
    )

    hit = _hit_item_from_native(native)

    assert hit.desktop_root is True
    assert hit.control is None
    assert hit.root_handle == 0x1234
    assert hit.name == "年度总结.docx"
    assert hit.target.center == (144, 162)
    assert hit.target.root_class == "SysListView32"


def test_native_desktop_empty_is_definitive_only_for_clean_empty_hit() -> None:
    clean_empty = NativeDesktopProbe(
        available=True,
        visible=True,
        hit=None,
        diagnostic="desktop-empty",
    )
    native_error = NativeDesktopProbe(
        available=True,
        visible=True,
        hit=None,
        diagnostic="native-desktop-error: boom",
    )
    covered = NativeDesktopProbe(
        available=True,
        visible=False,
        hit=None,
        diagnostic="desktop-covered",
    )

    assert _native_desktop_is_definitive_empty(clean_empty) is True
    assert _native_desktop_is_definitive_empty(native_error) is False
    assert _native_desktop_is_definitive_empty(covered) is False


def test_hover_hysteresis_keeps_one_flaky_probe_then_expires(monkeypatch) -> None:
    _reset_probe_cache_for_tests()
    target = _physical("年度总结.docx", 100, 100, 180, 180)
    good = AimProbeResult(AimStatus.FOUND, name="年度总结.docx", target=target)
    miss = AimProbeResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")
    responses = iter((good, miss, miss))
    moments = iter((10.00, 10.14, 10.50))

    monkeypatch.setattr(aim_resolver, "_probe_shell_item_once", lambda _point: next(responses))
    monkeypatch.setattr(aim_resolver.time, "monotonic", lambda: next(moments))

    first = probe_shell_item_at((140, 140))
    second = probe_shell_item_at((142, 141))
    third = probe_shell_item_at((142, 141))

    assert first.status is AimStatus.FOUND
    assert second.status is AimStatus.FOUND
    assert second.name == "年度总结.docx"
    assert third.status is AimStatus.EMPTY
    _reset_probe_cache_for_tests()


def test_hover_cache_requires_cursor_to_stay_near_same_target(monkeypatch) -> None:
    _reset_probe_cache_for_tests()
    target = _physical("年度总结.docx", 100, 100, 180, 180)
    good = AimProbeResult(AimStatus.FOUND, name="年度总结.docx", target=target)
    miss = AimProbeResult(AimStatus.EMPTY, message="这儿没东西，瞄准点。")
    responses = iter((good, miss))
    moments = iter((20.00, 20.12))

    monkeypatch.setattr(aim_resolver, "_probe_shell_item_once", lambda _point: next(responses))
    monkeypatch.setattr(aim_resolver.time, "monotonic", lambda: next(moments))

    assert probe_shell_item_at((140, 140)).status is AimStatus.FOUND
    result = probe_shell_item_at((400, 400))
    assert result.status is AimStatus.EMPTY
    _reset_probe_cache_for_tests()


def test_point_target_padding_helper_remains_available_for_hover_hysteresis() -> None:
    target = _physical("demo.txt", 100, 100, 180, 180)
    assert point_hits_physical_target((190, 180), target, margin_x=12, margin_y=9)
    assert not point_hits_physical_target((193, 180), target, margin_x=12, margin_y=9)


def test_probe_result_reports_real_shell_item() -> None:
    target = PhysicalTarget(
        left=10,
        top=20,
        right=110,
        bottom=80,
        accessible_name="demo.txt",
        selected=False,
        root_class="CabinetWClass",
    )
    result = AimProbeResult(AimStatus.FOUND, name="demo.txt", target=target)

    assert result.ok is True
    assert result.name == "demo.txt"


def test_aim_overlay_can_render_preview_offscreen() -> None:
    overlay = AimOverlay()
    try:
        overlay.set_preview("年度总结.docx", valid=True)
        overlay.show()
        _APP.processEvents()
        assert not overlay.grab().isNull()
    finally:
        overlay.stop()
        overlay.close()
        _APP.processEvents()
