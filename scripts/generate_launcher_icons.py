#!/usr/bin/env python3
"""Generate original white-label launcher icons for Android and iOS flavors."""

from __future__ import annotations

import json
import math
import os
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FLAVORS = {
    "coolshow": {
        "start": (6, 7, 10),
        "end": (31, 38, 54),
        "accent": (255, 178, 63),
        "accent2": (43, 121, 255),
        "mark": "coolshow",
    },
    "hongguo": {
        "start": (226, 58, 46),
        "end": (255, 138, 61),
        "accent": (255, 219, 135),
        "mark": "play",
    },
    "douyin": {
        "start": (5, 5, 7),
        "end": (17, 17, 22),
        "accent": (0, 212, 255),
        "accent2": (255, 45, 85),
        "mark": "pulse",
    },
    "hippo": {
        "start": (14, 165, 164),
        "end": (6, 95, 89),
        "accent": (201, 255, 249),
        "mark": "theater",
    },
    "reelshort": {
        "start": (16, 16, 16),
        "end": (91, 54, 28),
        "accent": (255, 178, 63),
        "accent2": (255, 90, 61),
        "mark": "cliff",
    },
}

ANDROID_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

IOS_IMAGES = [
    ("iphone", "20x20", "2x", "Icon-App-20x20@2x.png", 40),
    ("iphone", "20x20", "3x", "Icon-App-20x20@3x.png", 60),
    ("iphone", "29x29", "1x", "Icon-App-29x29@1x.png", 29),
    ("iphone", "29x29", "2x", "Icon-App-29x29@2x.png", 58),
    ("iphone", "29x29", "3x", "Icon-App-29x29@3x.png", 87),
    ("iphone", "40x40", "2x", "Icon-App-40x40@2x.png", 80),
    ("iphone", "40x40", "3x", "Icon-App-40x40@3x.png", 120),
    ("iphone", "60x60", "2x", "Icon-App-60x60@2x.png", 120),
    ("iphone", "60x60", "3x", "Icon-App-60x60@3x.png", 180),
    ("ipad", "20x20", "1x", "Icon-App-20x20@1x.png", 20),
    ("ipad", "20x20", "2x", "Icon-App-20x20@2x.png", 40),
    ("ipad", "29x29", "1x", "Icon-App-29x29@1x.png", 29),
    ("ipad", "29x29", "2x", "Icon-App-29x29@2x.png", 58),
    ("ipad", "40x40", "1x", "Icon-App-40x40@1x.png", 40),
    ("ipad", "40x40", "2x", "Icon-App-40x40@2x.png", 80),
    ("ipad", "76x76", "1x", "Icon-App-76x76@1x.png", 76),
    ("ipad", "76x76", "2x", "Icon-App-76x76@2x.png", 152),
    ("ipad", "83.5x83.5", "2x", "Icon-App-83.5x83.5@2x.png", 167),
    ("ios-marketing", "1024x1024", "1x", "Icon-App-1024x1024@1x.png", 1024),
]


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    rows = []
    offset = 0
    for _ in range(height):
        row = bytearray([0])
        for r, g, b in pixels[offset : offset + width]:
            row.extend((r, g, b))
        rows.append(bytes(row))
        offset += width

    raw = b"".join(rows)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += png_chunk(b"IDAT", zlib.compress(raw, 9))
    payload += png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def point_in_poly(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, point in enumerate(points):
        xi, yi = point
        xj, yj = points[j]
        intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def draw_polygon(
    pixels: list[tuple[int, int, int]],
    size: int,
    points: list[tuple[float, float]],
    color: tuple[int, int, int],
) -> None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x = max(0, math.floor(min(xs) * size))
    max_x = min(size - 1, math.ceil(max(xs) * size))
    min_y = max(0, math.floor(min(ys) * size))
    max_y = min(size - 1, math.ceil(max(ys) * size))
    for y in range(min_y, max_y + 1):
        ny = (y + 0.5) / size
        row = y * size
        for x in range(min_x, max_x + 1):
            if point_in_poly((x + 0.5) / size, ny, points):
                pixels[row + x] = color


def draw_circle(
    pixels: list[tuple[int, int, int]],
    size: int,
    cx: float,
    cy: float,
    radius: float,
    color: tuple[int, int, int],
) -> None:
    min_x = max(0, math.floor((cx - radius) * size))
    max_x = min(size - 1, math.ceil((cx + radius) * size))
    min_y = max(0, math.floor((cy - radius) * size))
    max_y = min(size - 1, math.ceil((cy + radius) * size))
    rr = radius * radius
    for y in range(min_y, max_y + 1):
        ny = (y + 0.5) / size
        row = y * size
        for x in range(min_x, max_x + 1):
            nx = (x + 0.5) / size
            if (nx - cx) ** 2 + (ny - cy) ** 2 <= rr:
                pixels[row + x] = color


def base_pixels(size: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    pixels: list[tuple[int, int, int]] = []
    for y in range(size):
        for x in range(size):
            tx = x / max(1, size - 1)
            ty = y / max(1, size - 1)
            t = min(1.0, max(0.0, 0.18 + 0.58 * tx + 0.36 * ty))
            color = mix(start, end, t)
            distance = math.sqrt((tx - 0.5) ** 2 + (ty - 0.5) ** 2)
            if distance > 0.42:
                color = mix(color, (10, 10, 12), min(0.35, (distance - 0.42) * 1.5))
            pixels.append(color)
    return pixels


def draw_mark(pixels: list[tuple[int, int, int]], size: int, flavor: str) -> None:
    spec = FLAVORS[flavor]
    accent = spec["accent"]
    accent2 = spec.get("accent2", (255, 255, 255))
    white = (255, 255, 255)

    if spec["mark"] == "play":
        draw_circle(pixels, size, 0.5, 0.5, 0.31, mix(accent, white, 0.2))
        draw_polygon(pixels, size, [(0.43, 0.33), (0.43, 0.67), (0.70, 0.50)], (226, 58, 46))
        draw_polygon(pixels, size, [(0.18, 0.18), (0.42, 0.13), (0.24, 0.34)], (255, 236, 171))
    elif spec["mark"] == "pulse":
        draw_polygon(pixels, size, [(0.32, 0.24), (0.32, 0.76), (0.72, 0.50)], accent2)
        draw_polygon(pixels, size, [(0.26, 0.20), (0.26, 0.72), (0.66, 0.46)], accent)
        draw_polygon(pixels, size, [(0.39, 0.33), (0.39, 0.67), (0.65, 0.50)], white)
    elif spec["mark"] == "theater":
        draw_circle(pixels, size, 0.5, 0.5, 0.34, accent)
        draw_circle(pixels, size, 0.5, 0.5, 0.24, (14, 165, 164))
        draw_polygon(pixels, size, [(0.36, 0.35), (0.36, 0.68), (0.64, 0.68), (0.64, 0.35)], white)
        draw_circle(pixels, size, 0.5, 0.36, 0.14, white)
        draw_polygon(pixels, size, [(0.46, 0.43), (0.46, 0.61), (0.61, 0.52)], (6, 95, 89))
    elif spec["mark"] == "cliff":
        draw_polygon(pixels, size, [(0.26, 0.18), (0.45, 0.18), (0.29, 0.82), (0.12, 0.82)], accent)
        draw_polygon(pixels, size, [(0.53, 0.18), (0.72, 0.18), (0.56, 0.82), (0.38, 0.82)], accent2)
        draw_polygon(pixels, size, [(0.43, 0.38), (0.43, 0.66), (0.67, 0.52)], white)
    elif spec["mark"] == "coolshow":
        draw_circle(pixels, size, 0.5, 0.5, 0.34, mix(accent2, white, 0.05))
        draw_polygon(pixels, size, [(0.38, 0.27), (0.38, 0.73), (0.72, 0.50)], (138, 60, 255))
        draw_polygon(pixels, size, [(0.30, 0.36), (0.30, 0.64), (0.52, 0.50)], accent)
        draw_circle(pixels, size, 0.31, 0.28, 0.055, accent)
        draw_circle(pixels, size, 0.68, 0.72, 0.046, accent2)


def render_icon(flavor: str, size: int) -> list[tuple[int, int, int]]:
    spec = FLAVORS[flavor]
    pixels = base_pixels(size, spec["start"], spec["end"])
    draw_mark(pixels, size, flavor)
    return pixels


def write_android_icons(flavor: str) -> None:
    for density, size in ANDROID_SIZES.items():
        target = ROOT / "android" / "app" / "src" / flavor / "res" / density / "ic_launcher.png"
        write_png(target, size, size, render_icon(flavor, size))


def ios_contents() -> dict[str, object]:
    return {
        "images": [
            {
                "size": size_label,
                "idiom": idiom,
                "filename": filename,
                "scale": scale,
            }
            for idiom, size_label, scale, filename, _ in IOS_IMAGES
        ],
        "info": {"version": 1, "author": "xcode"},
    }


def write_ios_icons(flavor: str) -> None:
    icon_set = ROOT / "ios" / "Runner" / "Assets.xcassets" / f"AppIcon-{flavor}.appiconset"
    icon_set.mkdir(parents=True, exist_ok=True)
    for _, _, _, filename, size in IOS_IMAGES:
        write_png(icon_set / filename, size, size, render_icon(flavor, size))
    (icon_set / "Contents.json").write_text(
        json.dumps(ios_contents(), indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    for flavor in FLAVORS:
        write_android_icons(flavor)
        write_ios_icons(flavor)
    print(f"Generated launcher icons for {', '.join(FLAVORS)}")


if __name__ == "__main__":
    os.umask(0o022)
    main()
