import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.character import CharacterConfig
from app.delete_service import DeleteFailureKind
from app.delete_task import DeleteTask
from app.responsive_overlay import ResponsiveDesktopCleanerOverlay


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _config() -> CharacterConfig:
    path = Path(__file__).parents[1] / "characters" / "jiaqi" / "character.json"
    return CharacterConfig.load(path)


def test_delete_task_demo_emits_success() -> None:
    received: list[tuple[int, object]] = []
    task = DeleteTask(7, None, demo=True)
    task.signals.finished.connect(lambda attempt, result: received.append((attempt, result)))

    # Run directly here to make the worker result deterministic; production sends
    # this exact QRunnable through QThreadPool.
    task.run()

    assert len(received) == 1
    attempt, result = received[0]
    assert attempt == 7
    assert result.ok is True
    assert result.kind is DeleteFailureKind.NONE


def test_responsive_overlay_constructs_in_demo_mode() -> None:
    app = _app()
    overlay = ResponsiveDesktopCleanerOverlay(None, _config(), demo=True)
    app.processEvents()

    assert overlay.demo is True
    assert overlay.delete_pending is False

    overlay.close()
    app.processEvents()
