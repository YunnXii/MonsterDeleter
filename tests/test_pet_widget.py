import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.pet_widget import PET_HEIGHT, PetWidget


_APP = QApplication.instance() or QApplication([])


def test_resident_pet_loads_final_front_pose() -> None:
    pet = PetWidget()
    try:
        assert pet.height() >= PET_HEIGHT
        assert pet.width() > 40
        assert pet.bubble is not None
    finally:
        pet.close()
