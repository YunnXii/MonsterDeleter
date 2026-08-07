from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.character import CharacterConfig
from app.context_menu import ensure_context_menu, register_context_menu, unregister_context_menu
from app.kick_calibrator import KickCalibrationOverlay
from app.launcher import LaunchAction, show_launch_prompt
from app.overlay import DesktopCleanerOverlay
from app.resources import resource_path


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


def show_status(title: str, message: str, ok: bool) -> int:
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
    box.exec()
    return 0 if ok else 1


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

    # Normal double-click: first run installs the menu; later runs verify and
    # repair stale EXE paths automatically. Do not surprise the user by starting
    # the full-screen animation unless they explicitly choose the demo button.
    if not args.target and not args.demo:
        menu_result = ensure_context_menu(config.menu_text)
        if not menu_result.ok:
            return show_status("叫家琦来", menu_result.message, False)

        action = show_launch_prompt(menu_result)
        if action is LaunchAction.UNINSTALL_MENU:
            result = unregister_context_menu()
            return show_status("叫家琦来", result.message, result.ok)
        if action is not LaunchAction.DEMO:
            return 0

    target = Path(args.target).expanduser().resolve() if args.target else None
    demo = args.demo or target is None
    overlay = DesktopCleanerOverlay(target, config, demo=demo)
    overlay.show()
    overlay.activateWindow()
    overlay.setFocus()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
