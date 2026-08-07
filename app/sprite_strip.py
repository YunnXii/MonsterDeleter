from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter


@dataclass(frozen=True)
class FrameSpan:
    """Horizontal source interval containing one animation pose."""

    left: int
    right: int  # exclusive

    @property
    def width(self) -> int:
        return self.right - self.left


def _rgba_bytes(image: QImage) -> tuple[QImage, bytes, int]:
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    raw = rgba.constBits().asstring(rgba.sizeInBytes())
    return rgba, raw, rgba.bytesPerLine()


def _column_alpha_mass(
    image: QImage,
    *,
    alpha_threshold: int = 10,
) -> tuple[QImage, bytes, int, list[int]]:
    """Count visible pixels in every x column without changing source alpha."""

    rgba, raw, stride = _rgba_bytes(image)
    width, height = rgba.width(), rgba.height()
    masses = [0] * width

    # Scan every pixel. The source sheets are small enough (~2k x 340) that
    # doing this once at startup is cheap and avoids an image-processing dep.
    for y in range(height):
        alpha = y * stride + 3
        for x in range(width):
            if raw[alpha + x * 4] >= alpha_threshold:
                masses[x] += 1
    return rgba, raw, stride, masses


def _active_runs(masses: list[int], *, min_column_pixels: int = 2) -> list[FrameSpan]:
    runs: list[FrameSpan] = []
    start: int | None = None

    for x, mass in enumerate(masses):
        active = mass >= min_column_pixels
        if active and start is None:
            start = x
        elif not active and start is not None:
            runs.append(FrameSpan(start, x))
            start = None

    if start is not None:
        runs.append(FrameSpan(start, len(masses)))
    return runs


def _merge_nearest_runs(runs: list[FrameSpan], expected: int) -> list[FrameSpan]:
    """Merge detached effects/specks into their nearest character pose."""

    merged = list(runs)
    while len(merged) > expected:
        gaps = [merged[i + 1].left - merged[i].right for i in range(len(merged) - 1)]
        index = min(range(len(gaps)), key=gaps.__getitem__)
        merged[index : index + 2] = [
            FrameSpan(merged[index].left, merged[index + 1].right)
        ]
    return merged


def detect_frame_spans(image: QImage, frame_count: int) -> list[FrameSpan]:
    """Find poses by transparent gaps instead of assuming equal source spacing.

    The manually cleaned sheets may contain frames that are not distributed at
    equal x intervals. Each person is separated by transparent space, so the
    alpha projection is a much safer splitter. If a detached impact star creates
    an extra run, the closest runs are merged back together.
    """

    if image.isNull():
        raise ValueError("sprite image is null")
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")

    _rgba, _raw, _stride, masses = _column_alpha_mass(image)
    runs = _active_runs(masses)
    runs = _merge_nearest_runs(runs, frame_count)

    if len(runs) == frame_count:
        return runs

    # Defensive fallback for artwork where two poses still touch after manual
    # editing. It keeps the app usable; the normal path above is used whenever
    # the frames are truly separated by transparency.
    width = image.width()
    boundaries = [round(i * width / frame_count) for i in range(frame_count + 1)]
    return [
        FrameSpan(boundaries[i], boundaries[i + 1])
        for i in range(frame_count)
    ]


def _head_center_x(
    rgba: QImage,
    raw: bytes,
    stride: int,
    span: FrameSpan,
    *,
    alpha_threshold: int = 10,
) -> float:
    """Use the chibi head as a stable horizontal animation anchor."""

    head_bottom = max(1, round(rgba.height() * 0.48))
    left: int | None = None
    right: int | None = None

    for y in range(head_bottom):
        alpha = y * stride + 3
        for x in range(span.left, span.right):
            if raw[alpha + x * 4] >= alpha_threshold:
                left = x if left is None else min(left, x)
                right = x if right is None else max(right, x)

    if left is None or right is None:
        return (span.left + span.right - 1) / 2
    return (left + right) / 2


def normalize_sprite_strip(image: QImage, frame_count: int) -> list[QImage]:
    """Repack uneven poses into equal transparent frames.

    - source transparency/RGB is preserved exactly; no new background removal;
    - feet keep their original y position;
    - the head center is locked to one x anchor across all frames;
    - detached kick effects stay with the closest pose.
    """

    if image.isNull():
        raise ValueError("sprite image is null")

    spans = detect_frame_spans(image, frame_count)
    rgba, raw, stride = _rgba_bytes(image)
    frame_width = round(image.width() / frame_count)
    frame_height = image.height()
    padding = 2

    head_centers = [_head_center_x(rgba, raw, stride, span) for span in spans]
    left_extents = [center - span.left for center, span in zip(head_centers, spans)]
    right_extents = [span.right - center for center, span in zip(head_centers, spans)]

    # Pick a single head anchor that keeps the widest poses inside the frame.
    min_anchor = max(left_extents) + padding
    max_anchor = frame_width - max(right_extents) - padding
    if min_anchor <= max_anchor:
        anchor_x = (min_anchor + max_anchor) / 2
    else:
        # A pose wider than one nominal frame is unusual but not fatal: keep the
        # head stable and let QPainter clip only the extreme transparent/effect
        # edge rather than shifting the whole body between frames.
        anchor_x = frame_width / 2

    frames: list[QImage] = []
    for span, head_center in zip(spans, head_centers):
        source_left = max(0, span.left - padding)
        source_right = min(rgba.width(), span.right + padding)
        crop = rgba.copy(source_left, 0, source_right - source_left, frame_height)

        canvas = QImage(
            frame_width,
            frame_height,
            QImage.Format.Format_RGBA8888,
        )
        canvas.fill(Qt.GlobalColor.transparent)
        target_x = round(anchor_x - (head_center - source_left))

        painter = QPainter(canvas)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(target_x, 0, crop)
        painter.end()
        frames.append(canvas)

    return frames
