#!/usr/bin/env python3
"""Generate SSHFerry brand assets used by the README and desktop app."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DOCS_ASSETS = ROOT / "docs" / "assets"
UI_ASSETS = ROOT / "src" / "ui" / "assets"

NAVY = (18, 52, 92, 255)
BLUE = (52, 134, 217, 255)
SKY = (111, 191, 242, 255)
ORANGE = (245, 140, 49, 255)
ORANGE_LIGHT = (255, 185, 89, 255)
BG_TOP = (249, 252, 255, 255)
BG_BOTTOM = (231, 241, 250, 255)
PANEL_LINE = (68, 124, 178, 82)
GRID_DOT = (91, 146, 198, 34)
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
        shadow_draw.ellipse(_bbox(0.08, 0.08, 0.84, 0.84, size, ox + int(size * 0.01), oy + int(size * 0.02)), fill=(37, 70, 108, 26))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, size // 60)))
        base.alpha_composite(shadow)

        draw.ellipse(_bbox(0.08, 0.08, 0.84, 0.84, size, ox, oy), fill=(243, 249, 254, 255), outline=NAVY, width=max(8, size // 42))
        draw.ellipse(_bbox(0.16, 0.16, 0.68, 0.68, size, ox, oy), outline=(156, 204, 238, 78), width=max(3, size // 90))

    hull = [
        _pt(0.22, 0.59, size, ox, oy),
        _pt(0.33, 0.59, size, ox, oy),
        _pt(0.36, 0.69, size, ox, oy),
        _pt(0.77, 0.69, size, ox, oy),
        _pt(0.83, 0.63, size, ox, oy),
        _pt(0.80, 0.79, size, ox, oy),
        _pt(0.18, 0.79, size, ox, oy),
        _pt(0.22, 0.67, size, ox, oy),
    ]
    draw.polygon(hull, fill=BLUE, outline=NAVY)
    draw.line(hull + [hull[0]], fill=NAVY, width=max(6, size // 70), joint="curve")

    draw.rounded_rectangle(_bbox(0.26, 0.48, 0.08, 0.12, size, ox, oy), radius=max(5, size // 80), fill=BLUE, outline=NAVY, width=max(5, size // 88))
    draw.rounded_rectangle(_bbox(0.275, 0.505, 0.036, 0.07, size, ox, oy), radius=max(3, size // 120), fill=ORANGE_LIGHT)

    stripe = [
        _pt(0.21, 0.69, size, ox, oy),
        _pt(0.78, 0.69, size, ox, oy),
        _pt(0.81, 0.64, size, ox, oy),
        _pt(0.81, 0.70, size, ox, oy),
        _pt(0.79, 0.74, size, ox, oy),
        _pt(0.20, 0.74, size, ox, oy),
    ]
    draw.polygon(stripe, fill=ORANGE)

    draw.arc(_bbox(0.42, 0.17, 0.18, 0.26, size, ox, oy), start=180, end=360, fill=NAVY, width=max(10, size // 48))
    draw.line([_pt(0.42, 0.30, size, ox, oy), _pt(0.42, 0.37, size, ox, oy)], fill=NAVY, width=max(10, size // 48))
    draw.line([_pt(0.60, 0.30, size, ox, oy), _pt(0.60, 0.37, size, ox, oy)], fill=NAVY, width=max(10, size // 48))
    draw.arc(_bbox(0.45, 0.20, 0.12, 0.20, size, ox, oy), start=180, end=360, fill=SKY, width=max(5, size // 90))

    lock_box = _bbox(0.36, 0.32, 0.30, 0.30, size, ox, oy)
    draw.rounded_rectangle(lock_box, radius=max(12, size // 28), fill=(250, 252, 255, 255), outline=NAVY, width=max(8, size // 52))
    draw.rounded_rectangle(_bbox(0.39, 0.35, 0.24, 0.24, size, ox, oy), radius=max(8, size // 40), outline=(148, 201, 239, 96), width=max(3, size // 115))

    hub = _pt(0.51, 0.47, size, ox, oy)
    network_points = [
        _pt(0.43, 0.40, size, ox, oy),
        _pt(0.60, 0.40, size, ox, oy),
        _pt(0.41, 0.53, size, ox, oy),
        _pt(0.62, 0.53, size, ox, oy),
        _pt(0.51, 0.58, size, ox, oy),
    ]
    for point in network_points:
        draw.line([hub, point], fill=NAVY, width=max(4, size // 110))
        radius = max(7, size // 55)
        draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=BLUE)
    hub_radius = max(14, size // 34)
    draw.ellipse((hub[0] - hub_radius, hub[1] - hub_radius, hub[0] + hub_radius, hub[1] + hub_radius), fill=NAVY)
    draw.rounded_rectangle(
        (hub[0] - max(5, size // 120), hub[1] + max(12, size // 65), hub[0] + max(5, size // 120), hub[1] + max(64, size // 16)),
        radius=max(3, size // 120),
        fill=NAVY,
    )

    wave_back = _wave_points(0.18, 0.81, 0.80, 0.014, 3.2, 90, size, ox, oy)
    wave_front = _wave_points(0.19, 0.80, 0.84, 0.013, 3.0, 90, size, ox, oy)
    draw.line(wave_back, fill=NAVY, width=max(6, size // 82))
    draw.line(wave_back, fill=SKY, width=max(2, size // 140))
    draw.line(wave_front, fill=(93, 169, 226, 215), width=max(5, size // 90))


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

    logo = build_logo()
    hero = build_hero()
    app_icon = build_app_icon()

    logo_path = DOCS_ASSETS / "logo.png"
    hero_path = DOCS_ASSETS / "hero.png"
    app_icon_png_path = UI_ASSETS / "app_icon.png"
    app_icon_ico_path = UI_ASSETS / "app_icon.ico"

    logo.save(logo_path)
    hero.save(hero_path)
    app_icon.save(app_icon_png_path)
    app_icon.save(
        app_icon_ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"Wrote {logo_path}")
    print(f"Wrote {hero_path}")
    print(f"Wrote {app_icon_png_path}")
    print(f"Wrote {app_icon_ico_path}")


if __name__ == "__main__":
    save_assets()
