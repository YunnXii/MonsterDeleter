import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from app.pet_widget import PetWidget
from app.resident_controller import RETURN_MAX_MS, RETURN_MIN_MS, return_duration_ms
from app.resident_transition import ResidentMorphWidget, foot_from_rect, rect_from_foot


_APP = QApplication.instance() or QApplication([])


def test_pet_visual_rect_uses_same_foot_anchor_as_task_entry() -> None:
    pet = PetWidget()
    try:
        pet.move(120, 180)
        assert foot_from_rect(pet.visual_rect_global()) == pet.foot_anchor_global()
    finally:
        pet.close()


def test_morph_rects_keep_bottom_centre_fixed() -> None:
    foot = QPoint(812, 706)
    pet_rect = rect_from_foot(foot, 114, 145)
    full_rect = rect_from_foot(foot, 280, 298)

    assert foot_from_rect(pet_rect) == foot
    assert foot_from_rect(full_rect) == foot


def test_resident_morph_widget_can_render_offscreen() -> None:
    morph = ResidentMorphWidget()
    try:
        foot = QPoint(400, 500)
        start = rect_from_foot(foot, 114, 145)
        end = rect_from_foot(foot, 280, 298)
        morph.start(start, end, duration_ms=10, easing=morph._animation.easingCurve().type())
        _APP.processEvents()
        assert not morph.grab().isNull()
    finally:
        morph.stop()
        morph.close()


def test_return_duration_is_fast_but_bounded() -> None:
    assert return_duration_ms(0) == RETURN_MIN_MS
    assert RETURN_MIN_MS < return_duration_ms(640) < RETURN_MAX_MS
    assert return_duration_ms(100000) == RETURN_MAX_MS
