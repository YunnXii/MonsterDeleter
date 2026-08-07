import os

import pytest

from app.context_menu import (
    context_menu_status,
    register_context_menu,
    unregister_context_menu,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows registry only")


def test_context_menu_registration_round_trip() -> None:
    label = "叫家琦来收拾它"
    unregister_context_menu()
    try:
        before = context_menu_status(label)
        assert before.current is False

        result = register_context_menu(label)
        assert result.ok is True

        after = context_menu_status(label)
        assert after.installed is True
        assert after.current is True
    finally:
        unregister_context_menu()
