#!/usr/bin/env python3
"""Export an offline HTML gallery for the Flutter white-label UI previews."""

from __future__ import annotations

import argparse
import contextlib
import os
import hashlib
import html
import json
import struct
import zlib
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover - pure Python fallback below
    Image = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "ui-preview-gallery"
PACKAGE_NAME = "mobile-ui-preview-gallery"

FLAVORS = {
    "coolshow": {
        "name": "CoolShow Short",
        "styleTemplate": "coolshow",
        "summary": "Dark overseas short-drama UI with gold CTAs and CoolShow branding",
        "background": "#06070a",
        "surface": "#141820",
        "primary": "#ffb23f",
        "secondary": "#2b79ff",
        "foreground": "#f8fafc",
        "muted": "#a6adba",
    },
    "hongguo": {
        "name": "GoldFruit Drama",
        "styleTemplate": "hongguo_inspired",
        "summary": "Light theater, hot lists, store-safe IAP",
        "background": "#fff8f5",
        "surface": "#ffffff",
        "primary": "#e23a2e",
        "secondary": "#ff8a3d",
        "foreground": "#211819",
        "muted": "#7a6260",
    },
    "douyin": {
        "name": "Pulse Drama",
        "styleTemplate": "douyin_inspired",
        "summary": "Dark vertical feed and direct-distribution payments",
        "background": "#050507",
        "surface": "#111116",
        "primary": "#00d4ff",
        "secondary": "#ff2d55",
        "foreground": "#f7fbff",
        "muted": "#b8c0cc",
    },
    "hippo": {
        "name": "River Drama",
        "styleTemplate": "hippo_inspired",
        "summary": "Channel theater, category-first browsing, VIP clarity",
        "background": "#f3fbfa",
        "surface": "#ffffff",
        "primary": "#0ea5a4",
        "secondary": "#0f766e",
        "foreground": "#052f2c",
        "muted": "#607371",
    },
    "reelshort": {
        "name": "Cliff Drama",
        "styleTemplate": "reelshort_inspired",
        "summary": "Premium cliffhanger posters with coins/subscription pacing",
        "background": "#101010",
        "surface": "#1a1715",
        "primary": "#ffb23f",
        "secondary": "#ff5a3d",
        "foreground": "#fff8ed",
        "muted": "#d4c4aa",
    },
}

SCREENS = [
    ("01_splash", "Splash"),
    ("02_auth", "Login / Register"),
    ("03_home", "Home"),
    ("04_catalog", "Catalog / Theater"),
    ("05_detail", "Drama Detail"),
    ("06_player", "Vertical Player"),
    ("07_unlock", "Unlock / Recharge"),
    ("08_mine_wallet_card", "Mine / Wallet / Point Card"),
]

PROTOTYPE_SCREEN_TO_WYSIWYG_SCREEN = {
    "01_splash": "splash",
    "02_auth": "auth",
    "03_home": "home",
    "04_catalog": "catalog",
    "05_detail": "detail",
    "06_player": "player",
    "07_unlock": "unlock",
    "08_mine_wallet_card": "wallet",
}

WYSIWYG_CAPTURE_SOURCE_DIR = Path("build") / "wysiwyg-preview"
WYSIWYG_RUNTIME_CAPTURE_SOURCE = "flutter_web_release_runtime_capture"
WYSIWYG_HOME_BOARD_FILE = "wysiwyg-template-home-gallery.png"
WYSIWYG_COOLSHOW_BOARD_FILE = "wysiwyg-coolshow-eight-screen-gallery.png"
WYSIWYG_ALL_TEMPLATES_BOARD_FILE = "wysiwyg-all-template-eight-screen-gallery.png"
WYSIWYG_BOARD_FILES = [
    WYSIWYG_HOME_BOARD_FILE,
    WYSIWYG_COOLSHOW_BOARD_FILE,
    WYSIWYG_ALL_TEMPLATES_BOARD_FILE,
]

WYSIWYG_HOME_CAPTURE_SPECS = [
    ("coolshow", "home", "CoolShow Home", "coolshow-home.png"),
    ("hongguo", "home", "GoldFruit Home", "hongguo-home.png"),
    ("douyin", "home", "Pulse Home", "douyin-home.png"),
    ("hippo", "home", "River Home", "hippo-home.png"),
    ("reelshort", "home", "Cliff Home", "reelshort-home.png"),
]

WYSIWYG_COOLSHOW_CAPTURE_SPECS = [
    ("coolshow", "splash", "Splash", "coolshow-splash.png"),
    ("coolshow", "auth", "Login / Register", "coolshow-auth.png"),
    ("coolshow", "home", "Home", "coolshow-home.png"),
    ("coolshow", "catalog", "Catalog / Theater", "coolshow-catalog.png"),
    ("coolshow", "detail", "Drama Detail", "coolshow-detail.png"),
    ("coolshow", "player", "Vertical Player", "coolshow-player.png"),
    ("coolshow", "unlock", "Unlock / Recharge", "coolshow-unlock.png"),
    ("coolshow", "wallet", "Mine / Wallet / Point Card", "coolshow-wallet.png"),
]

WYSIWYG_SCREEN_CAPTURE_DEFS = [
    ("splash", "Splash"),
    ("auth", "Login / Register"),
    ("home", "Home"),
    ("catalog", "Catalog / Theater"),
    ("detail", "Drama Detail"),
    ("player", "Vertical Player"),
    ("unlock", "Unlock / Recharge"),
    ("wallet", "Mine / Wallet / Point Card"),
]

WYSIWYG_ALL_TEMPLATE_CAPTURE_SPECS = [
    (
        flavor,
        screen,
        label,
        f"{flavor}-{screen}.png",
    )
    for flavor in FLAVORS
    for screen, label in WYSIWYG_SCREEN_CAPTURE_DEFS
]

WYSIWYG_CAPTURE_SPECS = WYSIWYG_ALL_TEMPLATE_CAPTURE_SPECS

READABLE_OVERVIEW_SCREENS = [
    ("home", "Home"),
    ("detail", "Drama Detail"),
    ("player", "Vertical Player"),
    ("wallet", "Wallet / Recharge"),
]

READABLE_OVERVIEW_SCREENSHOT_MAP = {
    "home": "03_home",
    "detail": "05_detail",
    "player": "06_player",
    "wallet": "08_mine_wallet_card",
}

DISALLOWED_VALUE_MARKERS = [
    "cloudflare_api_token=",
    "cloudflare-api-token:",
    "bearer ey",
    "sk_live_",
    "sk_test_",
    "appsecret:",
    "secret_ciphertext:",
    "secretciphertext:",
    "x-signature:",
    "x-app-key:",
    "client_secret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "-----begin private key-----",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    with path.open("rb") as source:
        header = source.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def paeth_predictor(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def read_png_rgba(path: Path) -> tuple[int, int, bytearray]:
    if Image is not None:
        with Image.open(path) as image:
            rgba_image = image.convert("RGBA")
            width, height = rgba_image.size
            return width, height, bytearray(rgba_image.tobytes())

    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Not a PNG file: {path}")
    cursor = 8
    width = 0
    height = 0
    bit_depth = 0
    color_type = 0
    compressed = bytearray()
    while cursor < len(data):
        length = int.from_bytes(data[cursor:cursor + 4], "big")
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        cursor += 12 + length
        if kind == b"IHDR":
            width = int.from_bytes(payload[0:4], "big")
            height = int.from_bytes(payload[4:8], "big")
            bit_depth = payload[8]
            color_type = payload[9]
            if payload[10] != 0 or payload[11] != 0 or payload[12] != 0:
                raise ValueError(f"Unsupported PNG compression/filter/interlace: {path}")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if bit_depth != 8 or color_type not in {2, 6}:
        raise ValueError(f"Unsupported PNG color mode for preview contact sheet: {path}")
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scanline = bytearray(raw[offset:offset + stride])
        offset += stride
        row = bytearray(stride)
        for index, value in enumerate(scanline):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                restored = value
            elif filter_type == 1:
                restored = value + left
            elif filter_type == 2:
                restored = value + up
            elif filter_type == 3:
                restored = value + ((left + up) // 2)
            elif filter_type == 4:
                restored = value + paeth_predictor(left, up, upper_left)
            else:
                raise ValueError(f"Unsupported PNG filter {filter_type}: {path}")
            row[index] = restored & 0xFF
        rows.append(row)
        previous = row
    pixels = bytearray(width * height * 4)
    target = 0
    for row in rows:
        if color_type == 6:
            pixels[target:target + len(row)] = row
            target += len(row)
        else:
            for index in range(0, len(row), 3):
                pixels[target:target + 4] = bytes((row[index], row[index + 1], row[index + 2], 255))
                target += 4
    return width, height, pixels


def write_png_rgba(path: Path, width: int, height: int, pixels: bytearray) -> None:
    raw = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw.append(0)
        start = y * row_bytes
        raw.extend(pixels[start:start + row_bytes])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + png_chunk(b"IEND", b""),
    )


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = hex_color.lstrip("#")
    return (
        int(color[0:2], 16),
        int(color[2:4], 16),
        int(color[4:6], 16),
        alpha,
    )


def fill_rect(
    pixels: bytearray,
    canvas_width: int,
    canvas_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int, int],
) -> None:
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(canvas_width, x + width)
    y1 = min(canvas_height, y + height)
    if x0 >= x1 or y0 >= y1:
        return
    row = bytes(color) * (x1 - x0)
    for yy in range(y0, y1):
        offset = (yy * canvas_width + x0) * 4
        pixels[offset:offset + len(row)] = row


def resize_rgba(
    width: int,
    height: int,
    pixels: bytearray,
    target_width: int,
    target_height: int,
) -> bytearray:
    resized = bytearray(target_width * target_height * 4)
    for y in range(target_height):
        source_y = min(height - 1, (y * height) // target_height)
        for x in range(target_width):
            source_x = min(width - 1, (x * width) // target_width)
            source_offset = (source_y * width + source_x) * 4
            target_offset = (y * target_width + x) * 4
            resized[target_offset:target_offset + 4] = pixels[source_offset:source_offset + 4]
    return resized


def alpha_blit(
    canvas: bytearray,
    canvas_width: int,
    canvas_height: int,
    source: bytearray,
    source_width: int,
    source_height: int,
    target_x: int,
    target_y: int,
) -> None:
    for y in range(source_height):
        yy = target_y + y
        if yy < 0 or yy >= canvas_height:
            continue
        for x in range(source_width):
            xx = target_x + x
            if xx < 0 or xx >= canvas_width:
                continue
            source_offset = (y * source_width + x) * 4
            alpha = source[source_offset + 3]
            target_offset = (yy * canvas_width + xx) * 4
            if alpha == 255:
                canvas[target_offset:target_offset + 4] = source[source_offset:source_offset + 4]
            elif alpha:
                inverse = 255 - alpha
                canvas[target_offset] = (source[source_offset] * alpha + canvas[target_offset] * inverse) // 255
                canvas[target_offset + 1] = (source[source_offset + 1] * alpha + canvas[target_offset + 1] * inverse) // 255
                canvas[target_offset + 2] = (source[source_offset + 2] * alpha + canvas[target_offset + 2] * inverse) // 255
                canvas[target_offset + 3] = 255


def screenshot_path_by_screen(flavor: dict[str, Any]) -> dict[str, Path]:
    return {
        str(screenshot["screen"]): Path(str(screenshot["path"]))
        for screenshot in flavor.get("screenshots", [])
        if isinstance(screenshot, dict)
    }


def paste_phone_screenshot(
    canvas: bytearray,
    canvas_width: int,
    canvas_height: int,
    output_dir: Path,
    relative_path: Path,
    x: int,
    y: int,
    phone_width: int,
    phone_height: int,
) -> None:
    fill_rect(canvas, canvas_width, canvas_height, x, y, phone_width, phone_height, rgba("#111827"))
    source_width, source_height, source_pixels = read_png_rgba(output_dir / relative_path)
    inner_width = phone_width - 8
    inner_height = max(1, round(inner_width * source_height / source_width))
    if inner_height > phone_height - 8:
        inner_height = phone_height - 8
        inner_width = max(1, round(inner_height * source_width / source_height))
    resized = resize_rgba(source_width, source_height, source_pixels, inner_width, inner_height)
    alpha_blit(
        canvas,
        canvas_width,
        canvas_height,
        resized,
        inner_width,
        inner_height,
        x + (phone_width - inner_width) // 2,
        y + (phone_height - inner_height) // 2,
    )


def render_wysiwyg_runtime_board(
    output_dir: Path,
    path: Path,
    captures: list[dict[str, Any]],
    *,
    columns: int,
    phone_width: int,
) -> dict[str, Any]:
    if not captures:
        raise ValueError("WYSIWYG runtime board requires at least one capture")
    rows = (len(captures) + columns - 1) // columns
    phone_height = round(phone_width * 844 / 390)
    margin = 34
    top = 52
    gap_x = 22
    gap_y = 42
    width = margin * 2 + columns * phone_width + (columns - 1) * gap_x
    height = top + rows * phone_height + (rows - 1) * gap_y + margin
    canvas = bytearray(rgba("#f3f5f8") * (width * height))
    fill_rect(canvas, width, height, 18, 18, width - 36, height - 36, rgba("#ffffff"))
    for index, capture in enumerate(captures):
        row = index // columns
        column = index % columns
        x = margin + column * (phone_width + gap_x)
        y = top + row * (phone_height + gap_y)
        paste_phone_screenshot(
            canvas,
            width,
            height,
            output_dir,
            Path(str(capture["relativePath"])),
            x,
            y,
            phone_width,
            phone_height,
        )
    write_png_rgba(path, width, height, canvas)
    return {
        "path": str(path.relative_to(output_dir.parents[1])),
        "relativePath": path.name,
        "sha256": sha256_file(path),
        "width": width,
        "height": height,
    }


def render_png_sheet(
    flavors: list[dict[str, Any]],
    output_dir: Path,
    path: Path,
    selected_screens: list[tuple[str, str]],
    phone_width: int,
    screenshot_screen_map: dict[str, str] | None = None,
    top: int = 150,
) -> dict[str, Any]:
    phone_height = round(phone_width * 844 / 390)
    left = 170
    gap_x = 18
    gap_y = 78
    width = left + len(selected_screens) * phone_width + (len(selected_screens) - 1) * gap_x + 44
    height = top + len(flavors) * phone_height + (len(flavors) - 1) * gap_y + 70
    canvas = bytearray(rgba("#f3f5f8") * (width * height))
    fill_rect(canvas, width, height, 24, 22, width - 48, 60, rgba("#ffffff"))
    for row_index, flavor in enumerate(flavors):
        y = top + row_index * (phone_height + gap_y)
        fill_rect(canvas, width, height, 24, y - 16, width - 48, phone_height + 60, rgba("#ffffff"))
        screenshots = screenshot_path_by_screen(flavor)
        for column_index, (screen_id, _) in enumerate(selected_screens):
            screenshot_id = screenshot_screen_map.get(screen_id, screen_id) if screenshot_screen_map else screen_id
            relative_path = screenshots.get(screenshot_id)
            if relative_path is None:
                continue
            x = left + column_index * (phone_width + gap_x)
            paste_phone_screenshot(canvas, width, height, output_dir, relative_path, x, y, phone_width, phone_height)
    write_png_rgba(path, width, height, canvas)
    return {
        "path": str(path.relative_to(output_dir.parents[1])),
        "sha256": sha256_file(path),
        "width": width,
        "height": height,
    }


def clean_output_dir(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in sorted(output_dir.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()


@contextlib.contextmanager
def output_lock(output_dir: Path):
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir.parent / f".{output_dir.name}.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted({marker for marker in DISALLOWED_VALUE_MARKERS if marker in text})


def copy_screenshots(root: Path, output_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    screenshot_root = output_dir / "screenshots"
    for flavor, flavor_meta in FLAVORS.items():
        screenshots: list[dict[str, Any]] = []
        flavor_dir = screenshot_root / flavor
        flavor_dir.mkdir(parents=True, exist_ok=True)
        for screen_id, label in SCREENS:
            source = root / "test" / "goldens" / "prototypes" / f"{flavor}_{screen_id}.png"
            if not source.exists():
                raise SystemExit(f"Missing prototype screenshot: {source.relative_to(root)}")
            target = flavor_dir / f"{flavor}_{screen_id}.png"
            shutil.copyfile(source, target)
            dimensions = png_dimensions(target)
            screenshots.append(
                {
                    "screen": screen_id,
                    "label": label,
                    "path": str(target.relative_to(output_dir)),
                    "sourcePath": str(source.relative_to(root)),
                    "width": dimensions[0] if dimensions else None,
                    "height": dimensions[1] if dimensions else None,
                    "sizeBytes": target.stat().st_size,
                    "sha256": sha256_file(target),
                    "source": "publish_safe_prototype",
                },
            )
        entries.append(
            {
                "flavor": flavor,
                "appName": flavor_meta["name"],
                "styleTemplate": flavor_meta["styleTemplate"],
                "screenshots": screenshots,
            },
        )
    return entries


def copy_wysiwyg_runtime_previews(
    root: Path,
    output_dir: Path,
    final_output_dir: Path,
) -> dict[str, Any]:
    source_dir = root / WYSIWYG_CAPTURE_SOURCE_DIR
    source_manifest_path = source_dir / "wysiwyg-preview-manifest.json"
    source_manifest: dict[str, Any] | None = None
    if source_manifest_path.exists():
        try:
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            source_manifest = None
    if not source_dir.exists():
        raise SystemExit(
            f"Missing WYSIWYG runtime preview captures: {WYSIWYG_CAPTURE_SOURCE_DIR.as_posix()}",
        )

    missing: list[str] = []
    captures_by_filename: dict[str, dict[str, Any]] = {}
    for flavor, screen, label, source_name in WYSIWYG_CAPTURE_SPECS:
        source = source_dir / source_name
        if not source.exists():
            missing.append(str(source.relative_to(root)))
            continue
        target = output_dir / f"wysiwyg-{source_name}"
        shutil.copyfile(source, target)
        dimensions = png_dimensions(target)
        capture = {
            "flavor": flavor,
            "screen": screen,
            "label": label,
            "path": str((final_output_dir / target.name).relative_to(root)),
            "relativePath": target.name,
            "sourcePath": str(source.relative_to(root)),
            "width": dimensions[0] if dimensions else None,
            "height": dimensions[1] if dimensions else None,
            "sizeBytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "source": WYSIWYG_RUNTIME_CAPTURE_SOURCE,
        }
        captures_by_filename[source_name] = capture

    if missing:
        raise SystemExit(
            "Missing WYSIWYG runtime preview captures: "
            + ", ".join(missing),
        )

    home_captures = [
        captures_by_filename[source_name]
        for _, _, _, source_name in WYSIWYG_HOME_CAPTURE_SPECS
    ]
    coolshow_captures = [
        captures_by_filename[source_name]
        for _, _, _, source_name in WYSIWYG_COOLSHOW_CAPTURE_SPECS
    ]
    all_template_captures = [
        captures_by_filename[source_name]
        for _, _, _, source_name in WYSIWYG_ALL_TEMPLATE_CAPTURE_SPECS
    ]
    home_board_path = output_dir / WYSIWYG_HOME_BOARD_FILE
    coolshow_board_path = output_dir / WYSIWYG_COOLSHOW_BOARD_FILE
    all_template_board_path = output_dir / WYSIWYG_ALL_TEMPLATES_BOARD_FILE
    home_board = render_wysiwyg_runtime_board(
        output_dir,
        home_board_path,
        home_captures,
        columns=4,
        phone_width=210,
    )
    coolshow_board = render_wysiwyg_runtime_board(
        output_dir,
        coolshow_board_path,
        coolshow_captures,
        columns=4,
        phone_width=168,
    )
    all_template_board = render_wysiwyg_runtime_board(
        output_dir,
        all_template_board_path,
        all_template_captures,
        columns=8,
        phone_width=124,
    )
    home_board["path"] = str((final_output_dir / WYSIWYG_HOME_BOARD_FILE).relative_to(root))
    coolshow_board["path"] = str((final_output_dir / WYSIWYG_COOLSHOW_BOARD_FILE).relative_to(root))
    all_template_board["path"] = str((final_output_dir / WYSIWYG_ALL_TEMPLATES_BOARD_FILE).relative_to(root))
    boards = [
        {
            "id": "template_home_gallery",
            "label": "Template home runtime gallery",
            "screenCount": len(home_captures),
            "includedScreens": [
                f"{capture['flavor']}:{capture['screen']}"
                for capture in home_captures
            ],
            "source": WYSIWYG_RUNTIME_CAPTURE_SOURCE,
            **home_board,
        },
        {
            "id": "coolshow_core_flow_gallery",
            "label": "CoolShow template eight-screen runtime gallery",
            "screenCount": len(coolshow_captures),
            "includedScreens": [
                f"{capture['flavor']}:{capture['screen']}"
                for capture in coolshow_captures
            ],
            "source": WYSIWYG_RUNTIME_CAPTURE_SOURCE,
            **coolshow_board,
        },
        {
            "id": "all_template_core_flow_gallery",
            "label": "All template eight-screen runtime gallery",
            "screenCount": len(all_template_captures),
            "flavorCount": len(FLAVORS),
            "includedScreens": [
                f"{capture['flavor']}:{capture['screen']}"
                for capture in all_template_captures
            ],
            "source": WYSIWYG_RUNTIME_CAPTURE_SOURCE,
            **all_template_board,
        },
    ]

    return {
        "source": WYSIWYG_RUNTIME_CAPTURE_SOURCE,
        "sourceDirectory": str(WYSIWYG_CAPTURE_SOURCE_DIR),
        "sourceManifestPath": str(source_manifest_path.relative_to(root))
        if source_manifest_path.exists()
        else None,
        "sourceManifestSha256": sha256_file(source_manifest_path)
        if source_manifest_path.exists()
        else None,
        "captureCommand": (
            source_manifest.get("captureCommand")
            if isinstance(source_manifest, dict) and source_manifest.get("captureCommand")
            else "node scripts/capture_wysiwyg_previews.mjs"
        ),
        "requiredCaptureCount": len(WYSIWYG_CAPTURE_SPECS),
        "captureCount": len(captures_by_filename),
        "boardCount": len(boards),
        "captures": list(captures_by_filename.values()),
        "boards": boards,
        "publicBoundary": "Release-rendered Flutter Web screenshots only; generated from local demo assets with no tenant secrets, provider credentials, signing material, Cloudflare tokens, or private keys.",
    }


def svg_escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_readable_overview_svg(flavors: list[dict[str, Any]]) -> str:
    width = 1480
    header_height = 120
    row_height = 330
    height = header_height + len(flavors) * row_height + 42
    phone_width = 220
    phone_height = 262
    x_start = 300
    x_gap = 248
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Flutter Short Drama White-label UI Overview">',
        "<defs>",
        "  <filter id=\"shadow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\"><feDropShadow dx=\"0\" dy=\"12\" stdDeviation=\"14\" flood-color=\"#1f2937\" flood-opacity=\"0.16\"/></filter>",
        "  <style>text{font-family:Inter,Arial,sans-serif;letter-spacing:0}.title{font-size:34px;font-weight:800}.subtitle{font-size:16px}.row-title{font-size:20px;font-weight:800}.small{font-size:13px}.label{font-size:14px;font-weight:700}.phone-title{font-size:15px;font-weight:800}.phone-copy{font-size:11px}.chip{font-size:11px;font-weight:700}</style>",
        "</defs>",
        '<rect width="1480" height="100%" fill="#f3f5f8"/>',
        '<rect x="36" y="28" width="1408" height="70" rx="20" fill="#ffffff" stroke="#dce3ee"/>',
        '<text x="64" y="61" class="title" fill="#111827">Flutter Short Drama White-label UI Overview</text>',
        '<text x="64" y="86" class="subtitle" fill="#667085">Readable tenant review board generated from the same four Flutter template presets and publish-safe prototype scope.</text>',
    ]
    for row_index, flavor in enumerate(flavors):
        meta = FLAVORS[str(flavor["flavor"])]
        y = header_height + row_index * row_height
        bg = str(meta["background"])
        surface = str(meta["surface"])
        primary = str(meta["primary"])
        secondary = str(meta["secondary"])
        fg = str(meta["foreground"])
        muted = str(meta["muted"])
        row_fill = "#ffffff"
        lines.extend(
            [
                f'<rect x="48" y="{y}" width="1384" height="296" rx="22" fill="{row_fill}" stroke="#dce3ee"/>',
                f'<rect x="72" y="{y + 28}" width="14" height="14" rx="4" fill="{primary}"/>',
                f'<text x="98" y="{y + 41}" class="row-title" fill="#111827">{svg_escape(flavor["appName"])}</text>',
                f'<text x="98" y="{y + 67}" class="small" fill="#667085">{svg_escape(meta["styleTemplate"])}</text>',
            ],
        )
        for screen_index, (screen_id, screen_label) in enumerate(READABLE_OVERVIEW_SCREENS):
            x = x_start + screen_index * x_gap
            phone_y = y + 22
            content_x = x + 14
            content_y = phone_y + 22
            lines.extend(
                [
                    f'<rect x="{x}" y="{phone_y}" width="{phone_width}" height="{phone_height}" rx="30" fill="#111111" filter="url(#shadow)"/>',
                    f'<rect x="{x + 8}" y="{phone_y + 8}" width="{phone_width - 16}" height="{phone_height - 16}" rx="23" fill="{bg}"/>',
                    f'<rect x="{x + 82}" y="{phone_y + 16}" width="56" height="5" rx="3" fill="#252525"/>',
                    f'<text x="{content_x}" y="{content_y}" class="phone-copy" fill="{fg}">9:41</text>',
                    f'<text x="{x + phone_width / 2}" y="{phone_y + phone_height + 23}" text-anchor="middle" class="label" fill="#374151">{svg_escape(screen_label)}</text>',
                ],
            )
            if screen_id == "home":
                lines.extend(
                    [
                        f'<rect x="{content_x}" y="{content_y + 18}" width="24" height="24" rx="8" fill="{primary}"/>',
                        f'<text x="{content_x + 34}" y="{content_y + 35}" class="phone-title" fill="{fg}">{svg_escape(flavor["appName"])}</text>',
                        f'<text x="{content_x}" y="{content_y + 70}" class="phone-title" fill="{fg}">Today Hot</text>',
                        f'<text x="{content_x}" y="{content_y + 92}" class="phone-copy" fill="{muted}">Theater · Ranking · New</text>',
                        f'<rect x="{content_x}" y="{content_y + 108}" width="{phone_width - 44}" height="76" rx="14" fill="{secondary}"/>',
                        f'<rect x="{content_x}" y="{content_y + 156}" width="{phone_width - 44}" height="28" rx="0" fill="{primary}" opacity="0.75"/>',
                        f'<text x="{content_x + 12}" y="{content_y + 174}" class="chip" fill="#ffffff">Contract cliffhanger</text>',
                        f'<rect x="{content_x}" y="{content_y + 198}" width="42" height="20" rx="10" fill="{primary}"/>',
                        f'<text x="{content_x + 21}" y="{content_y + 212}" text-anchor="middle" class="chip" fill="#ffffff">Hot</text>',
                        f'<rect x="{content_x + 52}" y="{content_y + 198}" width="42" height="20" rx="10" fill="{surface}" stroke="#dce3ee"/>',
                        f'<rect x="{content_x + 104}" y="{content_y + 198}" width="42" height="20" rx="10" fill="{surface}" stroke="#dce3ee"/>',
                    ],
                )
            elif screen_id == "detail":
                lines.extend(
                    [
                        f'<text x="{content_x}" y="{content_y + 36}" class="phone-title" fill="{fg}">Drama Detail</text>',
                        f'<rect x="{content_x}" y="{content_y + 58}" width="68" height="92" rx="12" fill="{secondary}"/>',
                        f'<rect x="{content_x}" y="{content_y + 112}" width="68" height="38" fill="{primary}" opacity="0.72"/>',
                        f'<text x="{content_x + 82}" y="{content_y + 78}" class="phone-title" fill="{fg}">Midnight Deal</text>',
                        f'<text x="{content_x + 82}" y="{content_y + 102}" class="phone-copy" fill="{muted}">36 episodes · ready</text>',
                        f'<rect x="{content_x + 82}" y="{content_y + 120}" width="76" height="24" rx="12" fill="{primary}"/>',
                        f'<text x="{content_x + 120}" y="{content_y + 136}" text-anchor="middle" class="chip" fill="#ffffff">Watch now</text>',
                        f'<text x="{content_x}" y="{content_y + 178}" class="phone-title" fill="{fg}">Episodes</text>',
                    ],
                )
                for idx in range(8):
                    gx = content_x + (idx % 4) * 44
                    gy = content_y + 192 + (idx // 4) * 30
                    fill = primary if idx == 0 else surface
                    stroke = primary if idx == 0 else "#dce3ee"
                    text_fill = "#ffffff" if idx == 0 else fg
                    lines.append(f'<rect x="{gx}" y="{gy}" width="34" height="22" rx="7" fill="{fill}" stroke="{stroke}"/>')
                    lines.append(f'<text x="{gx + 17}" y="{gy + 15}" text-anchor="middle" class="chip" fill="{text_fill}">{idx + 1}</text>')
            elif screen_id == "player":
                lines.extend(
                    [
                        f'<rect x="{x + 8}" y="{phone_y + 8}" width="{phone_width - 16}" height="{phone_height - 16}" rx="23" fill="{secondary}"/>',
                        f'<rect x="{x + 8}" y="{phone_y + 8}" width="{phone_width - 16}" height="{phone_height - 16}" rx="23" fill="{primary}" opacity="0.48"/>',
                        f'<text x="{content_x}" y="{content_y + 170}" class="phone-title" fill="#ffffff">Midnight Deal · EP1</text>',
                        f'<text x="{content_x}" y="{content_y + 193}" class="phone-copy" fill="#ffffff">Vertical playback with gated unlock.</text>',
                        f'<rect x="{content_x}" y="{content_y + 214}" width="110" height="28" rx="14" fill="#ffffff"/>',
                        f'<text x="{content_x + 55}" y="{content_y + 232}" text-anchor="middle" class="chip" fill="{primary}">2 coins next</text>',
                    ],
                )
                for idx, label in enumerate(["Like", "Chat", "Share"]):
                    cy = content_y + 74 + idx * 44
                    lines.append(f'<circle cx="{x + phone_width - 34}" cy="{cy}" r="16" fill="{surface}"/>')
                    lines.append(f'<text x="{x + phone_width - 34}" y="{cy + 5}" text-anchor="middle" class="chip" fill="{fg}">{label[0]}</text>')
            else:
                lines.extend(
                    [
                        f'<text x="{content_x}" y="{content_y + 36}" class="phone-title" fill="{fg}">Wallet</text>',
                        f'<text x="{content_x}" y="{content_y + 55}" class="phone-copy" fill="{muted}">Membership · cards · recharge</text>',
                        f'<rect x="{content_x}" y="{content_y + 70}" width="{phone_width - 44}" height="58" rx="14" fill="{primary}"/>',
                        f'<text x="{content_x + 14}" y="{content_y + 94}" class="phone-copy" fill="#ffffff">Balance</text>',
                        f'<text x="{content_x + 14}" y="{content_y + 118}" class="phone-title" fill="#ffffff">48 coins</text>',
                        f'<text x="{content_x}" y="{content_y + 150}" class="phone-title" fill="{fg}">Payment options</text>',
                    ],
                )
                for idx, label in enumerate(["Store billing", "Stripe / PayPal", "Bank / wallet", "USDT / point card"]):
                    gy = content_y + 164 + idx * 20
                    lines.append(f'<rect x="{content_x}" y="{gy}" width="{phone_width - 44}" height="16" rx="8" fill="{surface}" stroke="#dce3ee"/>')
                    lines.append(f'<circle cx="{content_x + 12}" cy="{gy + 8}" r="4" fill="{primary}"/>')
                    lines.append(f'<text x="{content_x + 24}" y="{gy + 12}" class="phone-copy" fill="{fg}">{svg_escape(label)}</text>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_contact_sheet_svg(flavors: list[dict[str, Any]]) -> str:
    thumb_width = 138
    thumb_height = 298
    label_width = 210
    column_gap = 18
    row_gap = 46
    margin = 28
    header_height = 88
    screen_label_height = 34
    row_height = thumb_height + row_gap
    width = margin * 2 + label_width + len(SCREENS) * thumb_width + (len(SCREENS) - 1) * column_gap
    height = margin * 2 + header_height + screen_label_height + len(flavors) * row_height - row_gap + 22
    x_start = margin + label_width
    y_start = margin + header_height + screen_label_height
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Flutter Short Drama White-label App Full UI Contact Sheet">',
        "<defs>",
        "  <filter id=\"phoneShadow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\"><feDropShadow dx=\"0\" dy=\"8\" stdDeviation=\"10\" flood-color=\"#111827\" flood-opacity=\"0.16\"/></filter>",
        "  <style>text{font-family:Inter,Arial,sans-serif;letter-spacing:0}.title{font-size:26px;font-weight:800}.small{font-size:13px}.flavor{font-size:17px;font-weight:800}.screen{font-size:13px;font-weight:700}</style>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#f3f5f8"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="58" rx="18" fill="#ffffff" stroke="#d8dee8"/>',
        f'<text x="{margin + 24}" y="{margin + 37}" class="title" fill="#111827">Flutter Short Drama White-label App Full UI Contact Sheet</text>',
    ]
    for column_index, (_, label) in enumerate(SCREENS):
        x = x_start + column_index * (thumb_width + column_gap)
        lines.append(f'<text x="{x + 8}" y="{margin + header_height + 17}" class="screen" fill="#475467">{svg_escape(label)}</text>')
    for row_index, flavor in enumerate(flavors):
        flavor_key = str(flavor["flavor"])
        y = y_start + row_index * row_height
        row_bottom = y + thumb_height + 12
        lines.extend(
            [
                f'<rect x="{margin}" y="{y - 10}" width="{width - margin * 2}" height="{row_bottom - y + 10}" rx="18" fill="#ffffff" stroke="#dce3ee"/>',
                f'<text x="{margin + 20}" y="{y + 30}" class="flavor" fill="#111827">{svg_escape(flavor["appName"])}</text>',
                f'<text x="{margin + 20}" y="{y + 56}" class="small" fill="#667085">{svg_escape(flavor_key)} · {svg_escape(flavor["styleTemplate"])}</text>',
            ],
        )
        screenshot_by_screen = {
            str(screenshot["screen"]): screenshot
            for screenshot in flavor.get("screenshots", [])
            if isinstance(screenshot, dict)
        }
        for column_index, (screen_id, label) in enumerate(SCREENS):
            screenshot = screenshot_by_screen.get(screen_id)
            if not screenshot:
                continue
            x = x_start + column_index * (thumb_width + column_gap)
            href = svg_escape(screenshot["path"])
            lines.extend(
                [
                    f'<rect x="{x - 4}" y="{y - 4}" width="{thumb_width + 8}" height="{thumb_height + 8}" rx="16" fill="#111827" filter="url(#phoneShadow)"/>',
                    f'<image href="{href}" x="{x}" y="{y}" width="{thumb_width}" height="{thumb_height}" preserveAspectRatio="xMidYMid slice"/>',
                    f'<text x="{x + thumb_width / 2}" y="{y + thumb_height + 26}" text-anchor="middle" class="small" fill="#475467">{svg_escape(label)}</text>',
                ],
            )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_html(
    flavors: list[dict[str, Any]],
    overview_path: str,
    contact_sheet_path: str,
    overview_png_path: str,
    contact_sheet_png_path: str,
    wysiwyg_runtime: dict[str, Any],
) -> str:
    wysiwyg_boards: list[str] = []
    for board in wysiwyg_runtime.get("boards", []):
        if not isinstance(board, dict):
            continue
        wysiwyg_boards.append(
            "\n".join(
                [
                    '<article class="runtime-board">',
                    f'  <img src="{html.escape(str(board.get("relativePath", "")))}" alt="{html.escape(str(board.get("label", "WYSIWYG runtime board")))}" loading="lazy">',
                    "  <div>",
                    f'    <strong>{html.escape(str(board.get("label", "")))}</strong>',
                    f'    <span>{html.escape(str(board.get("screenCount", "")))} real Flutter runtime screens</span>',
                    "  </div>",
                    "</article>",
                ],
            ),
        )
    wysiwyg_cards: list[str] = []
    for capture in wysiwyg_runtime.get("captures", []):
        if not isinstance(capture, dict):
            continue
        wysiwyg_cards.append(
            "\n".join(
                [
                    '<article class="screen-card">',
                    f'  <img src="{html.escape(str(capture.get("relativePath", "")))}" alt="{html.escape(str(capture.get("flavor", "")))} {html.escape(str(capture.get("label", "")))} WYSIWYG runtime screenshot" loading="lazy">',
                    "  <div>",
                    f'    <strong>{html.escape(str(capture.get("label", "")))}</strong>',
                    f'    <span>{html.escape(str(capture.get("flavor", "")))} &middot; {capture.get("width")}x{capture.get("height")}</span>',
                    "  </div>",
                    "</article>",
                ],
            ),
        )
    sections: list[str] = []
    for flavor in flavors:
        cards: list[str] = []
        for shot in flavor["screenshots"]:
            cards.append(
                "\n".join(
                    [
                        '<article class="screen-card">',
                        f'  <img src="{html.escape(shot["path"])}" alt="{html.escape(flavor["flavor"])} {html.escape(shot["label"])}" loading="lazy">',
                        "  <div>",
                        f'    <strong>{html.escape(shot["label"])}</strong>',
                        f'    <span>{html.escape(shot["screen"])} &middot; {shot["width"]}x{shot["height"]}</span>',
                        "  </div>",
                        "</article>",
                    ],
                ),
            )
        sections.append(
            "\n".join(
                [
                    '<section class="flavor-section">',
                    "  <header>",
                    f'    <p>{html.escape(flavor["styleTemplate"])}</p>',
                    f'    <h2>{html.escape(flavor["appName"])}</h2>',
                    f'    <span>{html.escape(flavor["flavor"])}</span>',
                    "  </header>",
                    f'  <div class="screen-grid">{"".join(cards)}</div>',
                    "</section>",
                ],
            ),
        )

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            "  <title>Short Drama White-label App UI Preview</title>",
            "  <style>",
            "    * { box-sizing: border-box; }",
            "    body { margin: 0; font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f6f8; color: #17191f; }",
            "    main { max-width: 1480px; margin: 0 auto; padding: 32px 20px 48px; }",
            "    .hero { display: flex; justify-content: space-between; gap: 20px; align-items: end; border-bottom: 1px solid #d9dee7; padding-bottom: 22px; margin-bottom: 26px; }",
            "    .hero h1 { margin: 0; font-size: 30px; line-height: 1.15; letter-spacing: 0; }",
            "    .hero p { margin: 8px 0 0; max-width: 760px; color: #555d6d; line-height: 1.55; }",
            "    .badge { border: 1px solid #cfd6e2; border-radius: 999px; padding: 8px 12px; color: #3b4352; background: #fff; white-space: nowrap; }",
            "    .flavor-section { margin-top: 30px; }",
            "    .flavor-section header { display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; align-items: end; margin-bottom: 14px; }",
            "    .flavor-section h2 { margin: 0; font-size: 22px; letter-spacing: 0; }",
            "    .flavor-section p { grid-column: 1 / -1; margin: 0; color: #666f80; text-transform: uppercase; font-size: 12px; letter-spacing: .08em; }",
            "    .flavor-section header span { color: #586173; font-size: 13px; }",
            "    .screen-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }",
            "    .runtime-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }",
            "    .runtime-board { background: #fff; border: 1px solid #dfe4ec; border-radius: 8px; overflow: hidden; box-shadow: 0 10px 24px rgba(24, 32, 46, .08); }",
            "    .runtime-board img { display: block; width: 100%; background: #f3f5f8; }",
            "    .runtime-board div { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px 12px 12px; min-height: 48px; }",
            "    .runtime-board strong { font-size: 13px; line-height: 1.2; }",
            "    .runtime-board span { color: #6b7280; font-size: 12px; white-space: nowrap; }",
            "    .screen-card { background: #fff; border: 1px solid #dfe4ec; border-radius: 8px; overflow: hidden; box-shadow: 0 10px 24px rgba(24, 32, 46, .08); }",
            "    .screen-card img { display: block; width: 100%; aspect-ratio: 390 / 844; object-fit: cover; background: #111; }",
            "    .screen-card div { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px 12px 12px; min-height: 48px; }",
            "    .screen-card strong { font-size: 13px; line-height: 1.2; }",
            "    .screen-card span { color: #6b7280; font-size: 12px; white-space: nowrap; }",
            "    @media (max-width: 1100px) { .screen-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .runtime-grid { grid-template-columns: 1fr; } }",
            "    @media (max-width: 620px) { main { padding: 22px 12px 36px; } .hero { display: block; } .badge { display: inline-block; margin-top: 14px; } .screen-grid { grid-template-columns: 1fr; } .flavor-section header { grid-template-columns: 1fr; } .runtime-board div, .screen-card div { display: block; } .runtime-board span, .screen-card span { display: block; margin-top: 4px; } }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            '    <section class="hero">',
            "      <div>",
            "        <h1>Short Drama White-label App UI Preview</h1>",
            "        <p>Offline preview gallery for five style presets and eight MVP screens. The first section uses release-rendered Flutter Web screenshots captured from the running preview app; the lower contact sheets keep the publish-safe prototype coverage for every template and screen.</p>",
            "      </div>",
            f'      <span class="badge">{len(FLAVORS)} templates &middot; {len(FLAVORS) * len(SCREENS)} screens</span>',
            "    </section>",
            '    <section class="flavor-section">',
            "      <header>",
            "        <p>WYSIWYG runtime captures</p>",
            "        <h2>Real Flutter-rendered app preview</h2>",
            f'        <span>{wysiwyg_runtime.get("captureCount", 0)} captures</span>',
            "      </header>",
            f'      <div class="runtime-grid">{"".join(wysiwyg_boards)}</div>',
            f'      <div class="screen-grid" style="margin-top:16px">{"".join(wysiwyg_cards)}</div>',
            "    </section>",
            '    <section class="flavor-section">',
            "      <header>",
            "        <p>Readable tenant overview</p>",
            "        <h2>Template comparison board</h2>",
            "      </header>",
            f'      <img src="{html.escape(overview_path)}" alt="Readable white-label app template overview" style="width:100%;border:1px solid #dfe4ec;border-radius:8px;background:#fff;box-shadow:0 10px 24px rgba(24,32,46,.08)">',
            f'      <p><a href="{html.escape(overview_png_path)}">Download PNG overview</a></p>',
            "    </section>",
            '    <section class="flavor-section">',
            "      <header>",
            "        <p>Full screenshot contact sheet</p>",
            "        <h2>All templates and MVP screens</h2>",
            "      </header>",
            f'      <img src="{html.escape(contact_sheet_path)}" alt="Full white-label app UI contact sheet" style="width:100%;border:1px solid #dfe4ec;border-radius:8px;background:#fff;box-shadow:0 10px 24px rgba(24,32,46,.08)">',
            f'      <p><a href="{html.escape(contact_sheet_png_path)}">Download PNG contact sheet</a></p>',
            "    </section>",
            *sections,
            "  </main>",
            "</body>",
            "</html>",
            "",
        ],
    )


def write_zip(output_dir: Path, zip_path: Path) -> None:
    files = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file()
        and path != zip_path
        and path.name != "ui-preview-gallery-manifest.json"
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            relative = file_path.relative_to(output_dir)
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative.as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def build_gallery(root: Path, output_dir: Path) -> dict[str, Any]:
    with output_lock(output_dir):
        staging_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{output_dir.name}.",
                dir=str(output_dir.parent),
            ),
        )
        try:
            flavors = copy_screenshots(root, staging_dir)
            wysiwyg_runtime = copy_wysiwyg_runtime_previews(root, staging_dir, output_dir)
            staging_overview_path = staging_dir / "mobile-ui-readable-overview.svg"
            staging_overview_path.write_text(
                render_readable_overview_svg(flavors),
                encoding="utf-8",
            )
            staging_contact_sheet_path = staging_dir / "mobile-ui-preview-contact-sheet.svg"
            staging_contact_sheet_path.write_text(
                render_contact_sheet_svg(flavors),
                encoding="utf-8",
            )
            staging_overview_png_path = staging_dir / "mobile-ui-readable-overview.png"
            overview_png = render_png_sheet(
                flavors,
                staging_dir,
                staging_overview_png_path,
                READABLE_OVERVIEW_SCREENS,
                210,
                READABLE_OVERVIEW_SCREENSHOT_MAP,
            )
            staging_contact_sheet_png_path = staging_dir / "mobile-ui-preview-contact-sheet.png"
            contact_sheet_png = render_png_sheet(
                flavors,
                staging_dir,
                staging_contact_sheet_png_path,
                SCREENS,
                128,
                top=120,
            )
            staging_html_path = staging_dir / f"{PACKAGE_NAME}.html"
            staging_html_path.write_text(
                render_html(
                    flavors,
                    staging_overview_path.name,
                    staging_contact_sheet_path.name,
                    staging_overview_png_path.name,
                    staging_contact_sheet_png_path.name,
                    wysiwyg_runtime,
                ),
                encoding="utf-8",
            )
            staging_zip_path = staging_dir / f"{PACKAGE_NAME}.zip"
            write_zip(staging_dir, staging_zip_path)
            final_html_path = output_dir / f"{PACKAGE_NAME}.html"
            final_overview_path = output_dir / "mobile-ui-readable-overview.svg"
            final_contact_sheet_path = output_dir / "mobile-ui-preview-contact-sheet.svg"
            final_overview_png_path = output_dir / "mobile-ui-readable-overview.png"
            final_contact_sheet_png_path = output_dir / "mobile-ui-preview-contact-sheet.png"
            final_zip_path = output_dir / f"{PACKAGE_NAME}.zip"
            final_manifest_path = output_dir / "ui-preview-gallery-manifest.json"
            manifest = {
                "schemaVersion": 1,
                "generatedAt": utc_now(),
                "packageType": "mobile_ui_preview_gallery",
                "source": "flutter_prototype_goldens",
                "htmlPath": str(final_html_path.relative_to(root)),
                "htmlSha256": sha256_file(staging_html_path),
                "readableOverview": {
                    "path": str(final_overview_path.relative_to(root)),
                    "sha256": sha256_file(staging_overview_path),
                    "width": 1480,
                    "height": 1482,
                    "screenCount": len(FLAVORS) * len(READABLE_OVERVIEW_SCREENS),
                    "includedScreens": [
                        screen_id for screen_id, _ in READABLE_OVERVIEW_SCREENS
                    ],
                    "source": "publish_safe_readable_overview",
                },
                "readableOverviewPng": {
                    "path": str(final_overview_png_path.relative_to(root)),
                    "sha256": overview_png["sha256"],
                    "width": overview_png["width"],
                    "height": overview_png["height"],
                    "screenCount": len(FLAVORS) * len(READABLE_OVERVIEW_SCREENS),
                    "includedScreens": [
                        screen_id for screen_id, _ in READABLE_OVERVIEW_SCREENS
                    ],
                    "source": "publish_safe_readable_overview_png",
                },
                "contactSheet": {
                    "path": str(final_contact_sheet_path.relative_to(root)),
                    "sha256": sha256_file(staging_contact_sheet_path),
                    "width": 1496,
                    "height": 1530,
                    "flavorCount": len(FLAVORS),
                    "screenCount": len(FLAVORS) * len(SCREENS),
                    "includedScreens": [screen_id for screen_id, _ in SCREENS],
                    "source": "publish_safe_full_screenshot_contact_sheet",
                },
                "contactSheetPng": {
                    "path": str(final_contact_sheet_png_path.relative_to(root)),
                    "sha256": contact_sheet_png["sha256"],
                    "width": contact_sheet_png["width"],
                    "height": contact_sheet_png["height"],
                    "flavorCount": len(FLAVORS),
                    "screenCount": len(FLAVORS) * len(SCREENS),
                    "includedScreens": [screen_id for screen_id, _ in SCREENS],
                    "source": "publish_safe_full_screenshot_contact_sheet_png",
                },
                "wysiwygRuntimePreviews": wysiwyg_runtime,
                "packagePath": str(final_zip_path.relative_to(root)),
                "packageSha256": sha256_file(staging_zip_path),
                "packageSizeBytes": staging_zip_path.stat().st_size,
                "flavors": flavors,
                "screenshotCount": sum(len(flavor["screenshots"]) for flavor in flavors),
                "publicBoundary": "Offline HTML preview gallery, publish-safe prototype screenshots, and release-rendered WYSIWYG runtime screenshots only; no signing material, provider credentials, tenant secrets, Cloudflare tokens, or private keys.",
                "manifestPath": str(final_manifest_path.relative_to(root)),
            }
            manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
            staging_manifest_path = staging_dir / "ui-preview-gallery-manifest.json"
            staging_manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            if output_dir.exists():
                shutil.rmtree(output_dir)
            os.replace(staging_dir, output_dir)
            return manifest
        except BaseException:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for generated UI preview gallery",
    )
    args = parser.parse_args()

    manifest = build_gallery(ROOT, args.output_dir.resolve())
    print(f"Wrote UI preview gallery: {manifest['htmlPath']}")
    print(f"Wrote UI preview package: {manifest['packagePath']}")
    print(f"Screenshots: {manifest['screenshotCount']}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
