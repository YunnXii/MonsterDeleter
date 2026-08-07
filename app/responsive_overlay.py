from __future__ import annotations

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QPixmap

from .chibi_avatar import AvatarAction
from .delete_service import DeleteResult
from .delete_task import DeleteTask
from .flying_icon import system_icon_pixmap
from .overlay import DesktopCleanerOverlay


class ResponsiveDesktopCleanerOverlay(DesktopCleanerOverlay):
    """Desktop overlay whose recycle-bin operation never blocks animation.

    The base overlay owns the authored animation/state machine. This thin layer
    only separates slow Windows Shell work from the GUI thread and joins the two
    timelines again when both the kick and delete attempt have finished.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._delete_pending = False
        self._kick_finished = False
        self._delete_attempt_id = 0
        self._delete_task: DeleteTask | None = None
        self._pending_icon_pixmap: QPixmap | None = None

    @property
    def delete_pending(self) -> bool:
        return self._delete_pending

    def _on_impact(self) -> None:
        if self._deleted or self.target_pos is None:
            return

        self._deleted = True
        self._delete_result = None
        self._delete_pending = True
        self._kick_finished = False
        self._pending_icon_pixmap = system_icon_pixmap(self.target)

        self._delete_attempt_id += 1
        task = DeleteTask(
            self._delete_attempt_id,
            self.target,
            demo=self.demo,
        )
        task.signals.finished.connect(self._on_delete_finished)
        self._delete_task = task
        QThreadPool.globalInstance().start(task)

    def _on_delete_finished(self, attempt_id: int, result: DeleteResult) -> None:
        # Ignore a late result from an obsolete attempt. Normally attempts never
        # overlap, but this makes Esc/reselection/retry races harmless.
        if attempt_id != self._delete_attempt_id:
            return

        self._delete_pending = False
        self._delete_result = result
        self._delete_task = None

        if result.ok:
            self._play_success_impact_effects()

        if self._kick_finished:
            self._finish_kick_result()

    def _play_success_impact_effects(self) -> None:
        if self.target_pos is None:
            return

        self.explosion.move(
            self.target_pos.x() - self.explosion.width() // 2,
            self.target_pos.y() - self.explosion.height() // 2,
        )
        self.explosion.play()

        pixmap = self._pending_icon_pixmap
        if pixmap is not None and not pixmap.isNull():
            self._launch_flying_icon(pixmap)
        self._pending_icon_pixmap = None

    def _on_avatar_animation_finished(self) -> None:
        if self.avatar.current_action is AvatarAction.KICK:
            self._kick_finished = True

            if self._delete_pending:
                # The Shell can take seconds to report that an Office document
                # is locked. Never hold a dynamic kick frame while it decides:
                # settle on the stable side pose and wait without blocking Qt.
                self.avatar.play_idle()
                return

            self._finish_kick_result()
            return

        # TURN / VICTORY behaviour remains exactly the authored base flow.
        super()._on_avatar_animation_finished()

    def _finish_kick_result(self) -> None:
        if self._delete_result is None:
            return
        super()._show_result()

    def _retry_delete(self) -> None:
        self._reset_async_attempt_state()
        super()._retry_delete()

    def _retry_selection(self) -> None:
        self._invalidate_async_attempt()
        super()._retry_selection()

    def _invalidate_async_attempt(self) -> None:
        # A running QRunnable cannot be force-cancelled safely. Bumping the token
        # makes any late completion a no-op while the worker finishes by itself.
        self._delete_attempt_id += 1
        self._delete_pending = False
        self._delete_task = None
        self._pending_icon_pixmap = None
        self._kick_finished = False

    def _reset_async_attempt_state(self) -> None:
        self._delete_pending = False
        self._delete_task = None
        self._pending_icon_pixmap = None
        self._kick_finished = False
