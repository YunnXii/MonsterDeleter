from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CharacterLook:
    skin: str
    hair: str
    shirt: str
    shirt_dark: str
    pants: str
    shoes: str
    glasses: str
    glasses_accent: str


@dataclass(frozen=True)
class CharacterConfig:
    name: str
    menu_text: str
    prompt_text: str
    confirm_text: str
    retry_text: str
    success_text: str
    failure_text: str
    width: int
    height: int
    fps: int
    impact_x: int
    impact_y: int
    walk_speed: int
    stop_distance: int
    look: CharacterLook

    @classmethod
    def load(cls, path: Path) -> "CharacterConfig":
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        look = CharacterLook(**data["look"])
        return cls(
            name=str(data["name"]),
            menu_text=str(data["menu_text"]),
            prompt_text=str(data["prompt_text"]),
            confirm_text=str(data["confirm_text"]),
            retry_text=str(data["retry_text"]),
            success_text=str(data["success_text"]),
            failure_text=str(data["failure_text"]),
            width=int(data.get("width", 320)),
            height=int(data.get("height", 340)),
            fps=int(data.get("fps", 12)),
            impact_x=int(data.get("impact_x", 257)),
            impact_y=int(data.get("impact_y", 151)),
            walk_speed=int(data.get("walk_speed", 430)),
            stop_distance=int(data.get("stop_distance", 88)),
            look=look,
        )
