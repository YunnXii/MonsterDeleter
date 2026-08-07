from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.character import CharacterConfig
from app.context_menu import register_context_menu, unregister_context_menu
from app.overlay import DesktopCleanerOverlay
from app.resources import resource_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="叫家琦来收拾桌面文件")
    parser.add_argument("target", nargs="?", help="要移入回收站的文件或文件夹")
    parser.add_argument("--demo", action="store_true", help="只播放动画，不删除任何内容")
    parser.add_argument("--install-menu", action="store_true", help="注册 Windows 右键菜单")
    parser.add_argument("--uninstall-menu", action="store_true", help="移除 Windows 右键菜单")
    return parser.parse_args(argv)


def load_character() -> CharacterConfig:
    return CharacterConfig.load(resource_path("characters", "jiaqi", "character.json"))


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
    config = load_character()

    if args.uninstall_menu:
        result = unregister_context_menu()
        return show_status("叫家琦来", result.message, result.ok)

    # A normal double-click installs the menu and then opens the safe demo.
    if args.install_menu or (not args.target and not args.demo):
        result = register_context_menu(config.menu_text)
        if args.install_menu:
            return show_status("叫家琦来", result.message, result.ok)
        if not result.ok:
            show_status("叫家琦来", result.message, False)

    target = Path(args.target).expanduser().resolve() if args.target else None
    demo = args.demo or target is None
    overlay = DesktopCleanerOverlay(target, config, demo=demo)
    overlay.show()
    overlay.activateWindow()
    overlay.setFocus()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
