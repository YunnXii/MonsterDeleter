from __future__ import annotations

from pathlib import Path

from PIL import Image


FRAME_COUNT = 9
SOURCE_FRAME = 9  # front-facing final walk pose
HEAD_REGION_RATIO = 0.46
ICON_CANVAS = 256


def _alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError("walk 第9帧是空的，无法生成图标")
    return bbox


def build_icon(walk_path: Path, output_ico: Path, output_png: Path) -> None:
    sheet = Image.open(walk_path).convert("RGBA")
    if sheet.width % FRAME_COUNT != 0:
        raise RuntimeError("walk.png 不是标准 9 帧等宽精灵图")

    frame_width = sheet.width // FRAME_COUNT
    index = SOURCE_FRAME - 1
    frame = sheet.crop(
        (index * frame_width, 0, (index + 1) * frame_width, sheet.height)
    )

    x0, y0, x1, y1 = _alpha_bbox(frame)
    visible_height = y1 - y0
    head_bottom = min(frame.height, y0 + round(visible_height * HEAD_REGION_RATIO))

    head = frame.crop((0, y0, frame.width, head_bottom))
    hx0, hy0, hx1, hy1 = _alpha_bbox(head)

    head_w = hx1 - hx0
    head_h = hy1 - hy0
    side = max(head_w, head_h)
    margin = max(8, round(side * 0.12))
    side += margin * 2

    center_x = (hx0 + hx1) / 2
    center_y = (hy0 + hy1) / 2
    crop_left = round(center_x - side / 2)
    crop_top = round(center_y - side / 2)

    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    src_left = max(0, crop_left)
    src_top = max(0, crop_top)
    src_right = min(head.width, crop_left + side)
    src_bottom = min(head.height, crop_top + side)

    patch = head.crop((src_left, src_top, src_right, src_bottom))
    dest_x = src_left - crop_left
    dest_y = src_top - crop_top
    square.alpha_composite(patch, (dest_x, dest_y))

    icon = square.resize((ICON_CANVAS, ICON_CANVAS), Image.Resampling.LANCZOS)

    output_ico.parent.mkdir(parents=True, exist_ok=True)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    icon.save(output_png, "PNG")
    icon.save(
        output_ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"应用图标已生成：{output_ico}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build_icon(
        root / "characters" / "jiaqi" / "sprites" / "walk.png",
        root / "build" / "app.ico",
        root / "build" / "app_icon_preview.png",
    )


if __name__ == "__main__":
    main()
