from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QSettings, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .autostart import is_autostart_enabled, set_autostart
from .character import CharacterConfig
from .direct_overlay import DirectTargetCleanerOverlay
from .interactions import InteractionProvider, RandomQuipProvider
from .pet_widget import PetWidget
from .single_instance import LocalCommandServer
from .target_resolver import (
    ResolveResult,
    TargetResolveTask,
    physical_to_qt_global,
)


SETTINGS_ORG = "YunnXii"
SETTINGS_APP = "JiaqiCleaner"
PET_X_KEY = "pet/x"
PET_Y_KEY = "pet/y"


class ResidentTaskOverlay(DirectTargetCleanerOverlay):
    """A direct cleaner session that returns control to the resident app."""

    session_finished = pyqtSignal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._resident_exit_emitted = False

    def _exit(self) -> None:
        if self._resident_exit_emitted:
            return
        self._resident_exit_emitted = True

        self._invalidate_async_attempt()
        self._stop_motion_animations()
        self._stop_flying_icon()
        self.avatar.stop()
        self.close()
        QTimer.singleShot(0, self.session_finished.emit)


class ResidentController:
    """Own the long-lived desktop pet, tray, IPC, target resolver, and sessions."""

    def __init__(
        self,
        app: QApplication,
        config: CharacterConfig,
        command_server: LocalCommandServer,
        *,
        interaction_provider: InteractionProvider | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.command_server = command_server
        self.provider = interaction_provider or RandomQuipProvider()
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.active_overlay: ResidentTaskOverlay | None = None
        self._quitting = False

        self._resolving = False
        self._resolve_attempt_id = 0
        self._resolve_task: TargetResolveTask | None = None
        self._resolve_target_path: Path | None = None

        self.pet = PetWidget()
        self.pet.interaction_requested.connect(self._on_pet_interaction)
        self.pet.context_menu_requested.connect(self._show_context_menu)
        self.pet.position_committed.connect(self._save_pet_position)
        self.pet.restore_or_default(self._saved_pet_position())

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._refresh_menu)
        self.aim_action = QAction("瞄一个倒霉文件", self.menu)
        self.aim_action.triggered.connect(self._request_aim_mode)
        self.menu.addAction(self.aim_action)
        self.menu.addSeparator()

        self.return_action = QAction("回到右下角", self.menu)
        self.return_action.triggered.connect(self._return_pet_home)
        self.menu.addAction(self.return_action)

        self.autostart_action = QAction("开机启动", self.menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(self._toggle_autostart)
        self.menu.addAction(self.autostart_action)
        self.menu.addSeparator()

        self.visibility_action = QAction("隐藏家琦", self.menu)
        self.visibility_action.triggered.connect(self._toggle_pet_visibility)
        self.menu.addAction(self.visibility_action)

        self.exit_action = QAction("退出", self.menu)
        self.exit_action.triggered.connect(self.quit)
        self.menu.addAction(self.exit_action)

        self.tray = QSystemTrayIcon(app.windowIcon(), app)
        self.tray.setToolTip("叫家琦来")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.command_server.command_received.connect(self.handle_command)
        self.pet.show()

    @property
    def busy(self) -> bool:
        return self._resolving or self.active_overlay is not None

    @staticmethod
    def _tray_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def handle_command(self, command: object) -> None:
        if not isinstance(command, dict):
            return

        command_type = command.get("type")
        if command_type == "activate":
            self.show_pet()
            return

        if command_type != "target":
            return
        raw_path = command.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return

        if self.busy:
            self.notify("手上正踹着一个呢，等等。")
            return

        target = Path(raw_path).expanduser().resolve()
        self.resolve_and_start(target)

    def resolve_and_start(self, target: Path) -> None:
        """Resolve a visible Explorer/Desktop item before starting any overlay."""
        if self.busy:
            self.notify("手上正踹着一个呢，等等。")
            return

        self._resolving = True
        self._resolve_attempt_id += 1
        attempt_id = self._resolve_attempt_id
        self._resolve_target_path = target

        self.show_pet()
        self.pet.show_message("我看看它站哪儿。")

        task = TargetResolveTask(attempt_id, target)
        task.signals.finished.connect(self._on_target_resolved)
        self._resolve_task = task
        QThreadPool.globalInstance().start(task)

    def _on_target_resolved(self, attempt_id: int, result: ResolveResult) -> None:
        if attempt_id != self._resolve_attempt_id:
            return

        target = self._resolve_target_path
        self._resolving = False
        self._resolve_task = None
        self._resolve_target_path = None

        if self._quitting:
            self._shutdown()
            return

        if target is None:
            return

        if not result.ok or result.target is None:
            self.pet.show_message(result.message or "这文件会隐身，我没找着它。")
            return

        target_global = physical_to_qt_global(result.target.center)
        self.start_task(target, target_global=target_global)

    def start_task(self, target: Path, *, target_global: QPoint) -> None:
        if self.busy:
            self.notify("手上正踹着一个呢，等等。")
            return

        entry_global = self.pet.foot_anchor_global()
        self.pet.bubble.hide()
        self.pet.hide()

        overlay = ResidentTaskOverlay(
            target,
            self.config,
            target_global_pos=target_global,
            entry_global_pos=entry_global,
        )
        self.active_overlay = overlay
        overlay.session_finished.connect(self._on_task_finished)
        overlay.show()
        overlay.activateWindow()
        overlay.setFocus()

    def show_pet(self) -> None:
        if self.active_overlay is not None:
            return
        self.pet.show()
        self.pet.raise_()

    def notify(self, message: str) -> None:
        if self._tray_available():
            self.tray.showMessage(
                "叫家琦来",
                message,
                QSystemTrayIcon.MessageIcon.Information,
                2400,
            )
        elif self.active_overlay is None:
            self.pet.show_message(message)

    def _on_pet_interaction(self, click_streak: int) -> None:
        if self.busy:
            return
        self.pet.show_message(self.provider.next_message(click_streak))

    def _show_context_menu(self, global_pos: QPoint) -> None:
        self._refresh_menu()
        self.menu.exec(global_pos)

    def _refresh_menu(self) -> None:
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(is_autostart_enabled())
        self.autostart_action.blockSignals(False)
        self.visibility_action.setText("隐藏家琦" if self.pet.isVisible() else "显示家琦")
        self.aim_action.setEnabled(not self.busy)
        self.return_action.setEnabled(not self.busy)

    def _request_aim_mode(self) -> None:
        # Still deliberately disabled until the next slice has real hit-testing.
        self.pet.show_message("真准星正在接线。先用文件右键叫我。")

    def _return_pet_home(self) -> None:
        if self.busy:
            return
        self.pet.snap_to_default()
        self.show_pet()

    def _toggle_autostart(self, checked: bool) -> None:
        ok, message = set_autostart(bool(checked))
        if not ok:
            self.autostart_action.blockSignals(True)
            self.autostart_action.setChecked(is_autostart_enabled())
            self.autostart_action.blockSignals(False)
        self.notify(message)

    def _toggle_pet_visibility(self) -> None:
        if self.pet.isVisible():
            if not self._tray_available():
                self.pet.show_message("托盘没站稳，先不让我隐身。")
                return
            self.pet.hide()
        else:
            self.show_pet()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason not in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            return
        if self.pet.isVisible():
            self.pet.raise_()
            self.pet.show_message("我在这儿呢。")
        else:
            self.show_pet()

    def _saved_pet_position(self) -> QPoint | None:
        if not self.settings.contains(PET_X_KEY) or not self.settings.contains(PET_Y_KEY):
            return None
        try:
            return QPoint(
                int(self.settings.value(PET_X_KEY)),
                int(self.settings.value(PET_Y_KEY)),
            )
        except (TypeError, ValueError):
            return None

    def _save_pet_position(self, point: QPoint) -> None:
        self.settings.setValue(PET_X_KEY, point.x())
        self.settings.setValue(PET_Y_KEY, point.y())
        self.settings.sync()

    def _on_task_finished(self) -> None:
        overlay = self.active_overlay
        self.active_overlay = None
        if overlay is not None:
            overlay.deleteLater()

        if self._quitting:
            self._shutdown()
            return
        self.show_pet()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True

        if self._resolving:
            self._resolve_attempt_id += 1
            self._resolving = False
            self._resolve_task = None
            self._resolve_target_path = None

        if self.active_overlay is not None:
            self.active_overlay._exit()
            return
        self._shutdown()

    def _shutdown(self) -> None:
        self.settings.sync()
        self.tray.hide()
        self.pet.close()
        self.command_server.close()
        self.app.quit()
