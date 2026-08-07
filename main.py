from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.character import CharacterConfig
from app.context_menu import ensure_context_menu, register_context_menu, unregister_context_menu
from app.kick_calibrator import KickCalibrationOverlay
from app.resident_controller import ResidentController
from app.responsive_overlay import ResponsiveDesktopCleanerOverlay
from app.resources import resource_path
from app.single_instance import (
    LocalCommandServer,
    ResidentAlreadyRunning,
    make_command,
    send_command,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="叫家琦来收拾文件")
    parser.add_argument("target", nargs="?", help="要移入回收站的文件或文件夹")
    parser.add_argument("--demo", action="store_true", help="只播放动画，不删除任何内容")
    parser.add_argument("--calibrate-kick", action="store_true", help="可视化校准踢击命中锚点")
    parser.add_argument("--install-menu", action="store_true", help="注册 Windows 右键菜单")
    parser.add_argument("--uninstall-menu", action="store_true", help="移除 Windows 右键菜单")
    return parser.parse_args(argv)


def load_character() -> CharacterConfig:
    return CharacterConfig.load(resource_path("characters", "jiaqi", "character.json"))


def _set_app_icon(app: QApplication) -> None:
    for candidate in (
        resource_path("assets", "app.ico"),
        resource_path("build", "app.ico"),
    ):
        if candidate.exists():
            app.setWindowIcon(QIcon(str(candidate)))
            return

    walk_path = resource_path("characters", "jiaqi", "sprites", "walk.png")
    sheet = QImage(str(walk_path))
    if not sheet.isNull() and sheet.width() % 9 == 0:
        frame_width = sheet.width() // 9
        frame = sheet.copy(frame_width * 8, 0, frame_width, sheet.height())
        app.setWindowIcon(QIcon(QPixmap.fromImage(frame)))


def show_status(title: str, message: str, ok: bool) -> int:
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
    box.exec()
    return 0 if ok else 1


def _run_standalone_demo(app: QApplication, config: CharacterConfig) -> int:
    overlay = ResponsiveDesktopCleanerOverlay(None, config, demo=True)
    overlay.show()
    overlay.activateWindow()
    overlay.setFocus()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("叫家琦来")
    _set_app_icon(app)
    config = load_character()

    if args.calibrate_kick:
        calibrator = KickCalibrationOverlay(config)
        calibrator.show()
        calibrator.activateWindow()
        calibrator.setFocus()
        return app.exec()

    if args.uninstall_menu:
        result = unregister_context_menu()
        return show_status("叫家琦来", result.message, result.ok)

    if args.install_menu:
        result = register_context_menu(config.menu_text)
        return show_status("叫家琦来", result.message, result.ok)

    if args.demo:
        return _run_standalone_demo(app, config)

    target = Path(args.target).expanduser().resolve() if args.target else None
    initial_command = make_command(target)

    if send_command(initial_command):
        return 0

    app.setQuitOnLastWindowClosed(False)

    command_server = LocalCommandServer(app)
    try:
        command_server.start()
    except ResidentAlreadyRunning:
        if send_command(initial_command, timeout_ms=1000):
            return 0
        return show_status("叫家琦来", "已有常驻实例，但这次没联系上它。", False)
    except RuntimeError as exc:
        return show_status("叫家琦来", str(exc), False)

    menu_result = ensure_context_menu(config.menu_text)
    controller = ResidentController(app, config, command_server)

    if not menu_result.ok:
        QTimer.singleShot(0, lambda: controller.notify(menu_result.message))
    elif menu_result.changed:
        QTimer.singleShot(
            0,
            lambda: controller.notify("部署完成。以后看哪个文件不顺眼，右键叫我。"),
        )

    if target is not None:
        QTimer.singleShot(0, lambda: controller.resolve_and_start(target))

    app._resident_controller = controller  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
