#!/usr/bin/env python3
"""Generate SSHFerry brand assets used by the README and desktop app."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DOCS_ASSETS = ROOT / "docs" / "assets"
UI_ASSETS = ROOT / "src" / "ui" / "assets"
FRONTEND_PUBLIC = ROOT / "frontend" / "public"

NAVY = (29, 43, 52, 255)
BLUE = (23, 107, 143, 255)
SKY = (105, 167, 200, 255)
TEAL = (15, 138, 122, 255)
ORANGE = (216, 145, 47, 255)
ORANGE_LIGHT = (246, 190, 101, 255)
BG_TOP = (247, 249, 248, 255)
BG_BOTTOM = (231, 238, 242, 255)
PANEL_LINE = (23, 107, 143, 78)
GRID_DOT = (23, 107, 143, 32)
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _lerp_rgba(start: tuple[int, int, int, int], end: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    return tuple(_lerp(sa, ea, t) for sa, ea in zip(start, end))


def _gradient(size: tuple[int, int], start: tuple[int, int, int, int], end: tuple[int, int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, start)
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            mix = ((x / max(width - 1, 1)) * 0.35) + ((y / max(height - 1, 1)) * 0.65)
            pixels[x, y] = _lerp_rgba(start, end, mix)
    return image


def _downsample(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.resize(size, Image.Resampling.LANCZOS)


def _bbox(x: float, y: float, w: float, h: float, size: int, ox: int = 0, oy: int = 0) -> tuple[int, int, int, int]:
    return (
        ox + int(round(x * size)),
        oy + int(round(y * size)),
        ox + int(round((x + w) * size)),
        oy + int(round((y + h) * size)),
    )


def _pt(x: float, y: float, size: int, ox: int = 0, oy: int = 0) -> tuple[int, int]:
    return ox + int(round(x * size)), oy + int(round(y * size))


def _wave_points(x_start: float, x_end: float, base_y: float, amp: float, cycles: float, steps: int, size: int, ox: int = 0, oy: int = 0) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for index in range(steps + 1):
        t = index / steps
        x = x_start + (x_end - x_start) * t
        y = base_y + math.sin(t * math.pi * 2 * cycles) * amp
        points.append(_pt(x, y, size, ox, oy))
    return points


def _draw_motif(base: Image.Image, size: int, ox: int = 0, oy: int = 0, *, with_badge: bool = True) -> None:
    draw = ImageDraw.Draw(base)

    if with_badge:
        shadow = Image.new("RGBA", base.size, TRANSPARENT)
        shadow_draw = ImageDraw.Draw(shadow)
        badge_shadow = _bbox(0.08, 0.08, 0.84, 0.84, size, ox + int(size * 0.01), oy + int(size * 0.02))
        shadow_draw.rounded_rectangle(badge_shadow, radius=max(28, size // 5), fill=(21, 44, 57, 34))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, size // 60)))
        base.alpha_composite(shadow)

        badge_box = _bbox(0.08, 0.08, 0.84, 0.84, size, ox, oy)
        draw.rounded_rectangle(badge_box, radius=max(28, size // 5), fill=(250, 253, 253, 255), outline=NAVY, width=max(8, size // 42))
        draw.rounded_rectangle(_bbox(0.16, 0.16, 0.68, 0.68, size, ox, oy), radius=max(20, size // 7), outline=(105, 167, 200, 86), width=max(3, size // 90))

    route_line = [
        _pt(0.25, 0.34, size, ox, oy),
        _pt(0.39, 0.26, size, ox, oy),
        _pt(0.58, 0.26, size, ox, oy),
        _pt(0.75, 0.39, size, ox, oy),
    ]
    draw.line(route_line, fill=(105, 167, 200, 160), width=max(9, size // 56), joint="curve")
    for index, point in enumerate(route_line):
        radius = max(10, size // 42) if index in (0, len(route_line) - 1) else max(7, size // 58)
        draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=TEAL)

    shackle_box = _bbox(0.40, 0.20, 0.22, 0.30, size, ox, oy)
    draw.arc(shackle_box, start=180, end=360, fill=NAVY, width=max(14, size // 38))
    draw.arc(_bbox(0.435, 0.235, 0.15, 0.22, size, ox, oy), start=180, end=360, fill=SKY, width=max(5, size // 92))
    draw.line([_pt(0.40, 0.35, size, ox, oy), _pt(0.40, 0.43, size, ox, oy)], fill=NAVY, width=max(14, size // 38))
    draw.line([_pt(0.62, 0.35, size, ox, oy), _pt(0.62, 0.43, size, ox, oy)], fill=NAVY, width=max(14, size // 38))

    lock_box = _bbox(0.34, 0.38, 0.34, 0.24, size, ox, oy)
    draw.rounded_rectangle(lock_box, radius=max(12, size // 30), fill=(255, 255, 255, 255), outline=NAVY, width=max(9, size // 48))
    draw.rounded_rectangle(_bbox(0.38, 0.42, 0.26, 0.14, size, ox, oy), radius=max(7, size // 48), fill=(239, 246, 248, 255), outline=(105, 167, 200, 120), width=max(3, size // 115))

    hub = _pt(0.51, 0.50, size, ox, oy)
    for point in [_pt(0.42, 0.45, size, ox, oy), _pt(0.60, 0.45, size, ox, oy), _pt(0.51, 0.57, size, ox, oy)]:
        draw.line([hub, point], fill=NAVY, width=max(4, size // 108))
        radius = max(7, size // 54)
        draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=TEAL)
    hub_radius = max(13, size // 36)
    draw.ellipse((hub[0] - hub_radius, hub[1] - hub_radius, hub[0] + hub_radius, hub[1] + hub_radius), fill=NAVY)

    cabin = _bbox(0.25, 0.54, 0.11, 0.14, size, ox, oy)
    draw.rounded_rectangle(cabin, radius=max(5, size // 78), fill=BLUE, outline=NAVY, width=max(6, size // 70))
    draw.rounded_rectangle(_bbox(0.275, 0.57, 0.055, 0.07, size, ox, oy), radius=max(3, size // 96), fill=ORANGE_LIGHT)

    hull = [
        _pt(0.19, 0.66, size, ox, oy),
        _pt(0.74, 0.66, size, ox, oy),
        _pt(0.84, 0.58, size, ox, oy),
        _pt(0.78, 0.78, size, ox, oy),
        _pt(0.16, 0.78, size, ox, oy),
    ]
    draw.polygon(hull, fill=BLUE, outline=NAVY)
    draw.line(hull + [hull[0]], fill=NAVY, width=max(7, size // 64), joint="curve")
    draw.polygon(
        [
            _pt(0.20, 0.67, size, ox, oy),
            _pt(0.76, 0.67, size, ox, oy),
            _pt(0.81, 0.62, size, ox, oy),
            _pt(0.78, 0.72, size, ox, oy),
            _pt(0.18, 0.72, size, ox, oy),
        ],
        fill=TEAL,
    )

    wave_back = _wave_points(0.17, 0.80, 0.79, 0.012, 2.8, 80, size, ox, oy)
    wave_front = _wave_points(0.18, 0.78, 0.83, 0.011, 2.6, 80, size, ox, oy)
    draw.line(wave_back, fill=NAVY, width=max(6, size // 86))
    draw.line(wave_back, fill=SKY, width=max(2, size // 140))
    draw.line(wave_front, fill=(15, 138, 122, 210), width=max(5, size // 94))


def _draw_hero_overlay(base: Image.Image, motif_origin: tuple[int, int], motif_size: int) -> None:
    width, height = base.size
    draw = ImageDraw.Draw(base)

    glow = Image.new("RGBA", base.size, TRANSPARENT)
    glow_draw = ImageDraw.Draw(glow)
    glow_box = (
        motif_origin[0] - int(motif_size * 0.20),
        motif_origin[1] - int(motif_size * 0.16),
        motif_origin[0] + int(motif_size * 0.98),
        motif_origin[1] + int(motif_size * 1.02),
    )
    glow_draw.ellipse(glow_box, fill=(124, 188, 235, 56))
    glow = glow.filter(ImageFilter.GaussianBlur(38))
    base.alpha_composite(glow)

    for x in range(int(width * 0.62), width, 72):
        for y in range(88, height - 50, 72):
            radius = 4 if (x + y) % 144 == 0 else 3
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=GRID_DOT)

    panels = [
        (0.68, 0.18, 0.16, 0.17),
        (0.80, 0.31, 0.14, 0.16),
        (0.70, 0.53, 0.18, 0.15),
    ]
    for px, py, pw, ph in panels:
        box = (int(width * px), int(height * py), int(width * (px + pw)), int(height * (py + ph)))
        draw.rounded_rectangle(box, radius=22, outline=PANEL_LINE, width=3, fill=(255, 255, 255, 70))
        accent_y = int(box[1] + (box[3] - box[1]) * 0.24)
        draw.line([(box[0] + 18, accent_y), (box[2] - 18, accent_y)], fill=(146, 194, 229, 75), width=3)

    start = (motif_origin[0] + int(motif_size * 0.80), motif_origin[1] + int(motif_size * 0.47))
    mid = (int(width * 0.63), int(height * 0.46))
    end = (int(width * 0.82), int(height * 0.39))
    draw.line([start, mid, end], fill=(49, 129, 203, 108), width=5)
    draw.ellipse((mid[0] - 8, mid[1] - 8, mid[0] + 8, mid[1] + 8), fill=BLUE)
    draw.ellipse((end[0] - 8, end[1] - 8, end[0] + 8, end[1] + 8), fill=ORANGE)

    start2 = (motif_origin[0] + int(motif_size * 0.76), motif_origin[1] + int(motif_size * 0.62))
    mid2 = (int(width * 0.66), int(height * 0.61))
    end2 = (int(width * 0.78), int(height * 0.63))
    draw.line([start2, mid2, end2], fill=(241, 141, 53, 100), width=5)
    draw.ellipse((mid2[0] - 7, mid2[1] - 7, mid2[0] + 7, mid2[1] + 7), fill=ORANGE)
    draw.ellipse((end2[0] - 7, end2[1] - 7, end2[0] + 7, end2[1] + 7), fill=BLUE)

    lower_band = Image.new("RGBA", base.size, TRANSPARENT)
    lower_draw = ImageDraw.Draw(lower_band)
    lower_draw.line([(int(width * 0.08), int(height * 0.88)), (int(width * 0.92), int(height * 0.88))], fill=(84, 161, 220, 52), width=2)
    lower_draw.line([(int(width * 0.18), int(height * 0.92)), (int(width * 0.87), int(height * 0.92))], fill=(244, 140, 49, 54), width=2)
    lower_draw.line(_wave_points(0.05, 0.44, 0.80, 0.010, 4.3, 180, width), fill=(120, 184, 232, 58), width=3)
    base.alpha_composite(lower_band)


def build_logo() -> Image.Image:
    base_size = 2048
    base = Image.new("RGBA", (base_size, base_size), TRANSPARENT)
    _draw_motif(base, base_size, with_badge=True)
    return _downsample(base, (1024, 1024))


def build_app_icon() -> Image.Image:
    base_size = 1024
    base = Image.new("RGBA", (base_size, base_size), TRANSPARENT)
    _draw_motif(base, base_size, with_badge=True)
    return base


def build_hero() -> Image.Image:
    scale = 2
    size = (1600 * scale, 640 * scale)
    hero = _gradient(size, BG_TOP, BG_BOTTOM)

    accent = Image.new("RGBA", size, TRANSPARENT)
    accent_draw = ImageDraw.Draw(accent)
    accent_draw.ellipse((int(size[0] * 0.05), int(size[1] * 0.10), int(size[0] * 0.48), int(size[1] * 0.96)), fill=(255, 255, 255, 125))
    accent_draw.polygon(
        [
            (int(size[0] * 0.74), int(size[1] * 0.02)),
            (int(size[0] * 0.98), int(size[1] * 0.18)),
            (int(size[0] * 0.98), int(size[1] * 0.56)),
            (int(size[0] * 0.66), int(size[1] * 0.22)),
        ],
        fill=(255, 255, 255, 60),
    )
    accent = accent.filter(ImageFilter.GaussianBlur(18))
    hero.alpha_composite(accent)

    motif_size = 520
    motif_origin = (220, 90)
    _draw_motif(hero, motif_size, motif_origin[0], motif_origin[1], with_badge=True)
    _draw_hero_overlay(hero, motif_origin, motif_size)

    return _downsample(hero, (1600, 640))


def save_assets() -> None:
    DOCS_ASSETS.mkdir(parents=True, exist_ok=True)
    UI_ASSETS.mkdir(parents=True, exist_ok=True)
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)

    logo = build_logo()
    hero = build_hero()
    app_icon = build_app_icon()

    logo_path = DOCS_ASSETS / "logo.png"
    hero_path = DOCS_ASSETS / "hero.png"
    app_icon_png_path = UI_ASSETS / "app_icon.png"
    app_icon_ico_path = UI_ASSETS / "app_icon.ico"
    favicon_png_path = FRONTEND_PUBLIC / "favicon.png"
    favicon_ico_path = FRONTEND_PUBLIC / "favicon.ico"

    logo.save(logo_path)
    hero.save(hero_path)
    app_icon.save(app_icon_png_path)
    app_icon.save(
        app_icon_ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    _downsample(app_icon, (256, 256)).save(favicon_png_path)
    app_icon.save(
        favicon_ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"Wrote {logo_path}")
    print(f"Wrote {hero_path}")
    print(f"Wrote {app_icon_png_path}")
    print(f"Wrote {app_icon_ico_path}")
    print(f"Wrote {favicon_png_path}")
    print(f"Wrote {favicon_ico_path}")


if __name__ == "__main__":
    save_assets()
