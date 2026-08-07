import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import app.aim_resolver as aim_resolver
import app.target_resolver as target_resolver
from app.aim_overlay import AimOverlay
from app.aim_resolver import (
    AimProbeResult,
    AimStatus,
    _HitItem,
    _choose_geometric_hit,
    _matching_entries,
    _reset_probe_cache_for_tests,
    _resolve_desktop_name,
    point_hits_physical_target,
    probe_shell_item_at,
)
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


def _hit(name: str, left: int, top: int, right: int, bottom: int) -> _HitItem:
    return _HitItem(
        control=object(),
        target=_physical(name, left, top, right, bottom),
        name=name,
        root_class="WorkerW",
        root_handle=1,
        desktop_root=True,
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


def test_geometric_desktop_hit_recovers_when_direct_uia_hit_is_only_container() -> None:
    wanted = _hit("年度总结.docx", 100, 100, 180, 180)
    other = _hit("别的文件.txt", 240, 100, 320, 180)

    # A few pixels outside the raw rectangle are deliberately tolerated because
    # desktop UIA bounds can exclude tiny hover edges that Explorer itself treats
    # as belonging to the icon.
    point = (184, 140)
    assert point_hits_physical_target(point, wanted.target, margin_x=7, margin_y=5)

    chosen = _choose_geometric_hit([other, wanted], point)
    assert chosen is wanted


def test_hover_hysteresis_keeps_one_flaky_desktop_probe_then_expires(monkeypatch) -> None:
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
