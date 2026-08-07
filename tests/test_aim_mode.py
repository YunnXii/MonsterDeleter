import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.aim_overlay import AimOverlay
from app.aim_resolver import AimProbeResult, AimStatus, _matching_entries
from app.target_resolver import PhysicalTarget


_APP = QApplication.instance() or QApplication([])


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
