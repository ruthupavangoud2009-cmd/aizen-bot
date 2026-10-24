"""
Kyoka 3.0 - Aizen Hero Banner & Visual Card Generator.
Generates high-definition, Aizen-inspired anime command center graphics in-memory using Pillow.
Enforces the signature Kyoka visual identity: Obsidian black (#0A0612), Deep Violet (#1A0B2E),
Electric Purple (#8A2BE2), and Neon Crimson (#FF0055).
"""

from __future__ import annotations

import io
import math
import time
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


def _draw_glowing_rounded_rect(
    draw: ImageDraw.ImageDraw,
    coords: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    glow_color: tuple[int, int, int, int],
    glow_width: int = 2,
) -> None:
    """Draw a rounded rectangle with an electric neon glow aura."""
    x1, y1, x2, y2 = coords
    for i in range(glow_width, 0, -1):
        alpha = int(glow_color[3] * (1.0 - (i / (glow_width + 1))))
        c = (glow_color[0], glow_color[1], glow_color[2], alpha)
        draw.rounded_rectangle(
            (x1 - i, y1 - i, x2 + i, y2 + i),
            radius=radius + i,
            outline=c,
            width=1,
        )
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill, outline=outline, width=1)


def generate_kyoka_hero_banner(
    bot_name: str = "KYOKA 3.0",
    latency_ms: int = 15,
    prefix: str = "+",
    total_commands: int = 150,
    category_title: Optional[str] = None,
    guild_name: Optional[str] = None,
    **kwargs: Any,
) -> io.BytesIO:
    """
    Render a 900x260 high-definition anime command dashboard banner.
    Returns a BytesIO containing PNG bytes for native Discord attachment.
    """
    width, height = 900, 260
    base = Image.new("RGBA", (width, height), (10, 6, 18, 255))
    draw = ImageDraw.Draw(base, "RGBA")

    # 1. Background: Deep obsidian to royal violet gradient
    for y in range(height):
        ratio = y / height
        r = int(10 + (28 - 10) * ratio)
        g = int(6 + (11 - 6) * ratio)
        b = int(18 + (60 - 18) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # 2. Futuristic cybernetic grid / diagonal aura lines
    grid_color = (138, 43, 226, 22)
    for x in range(0, width + height, 40):
        draw.line([(x, 0), (x - height, height)], fill=grid_color, width=1)

    # 3. Ambient atmospheric glow rings (Aizen Spiritual Pressure)
    center_x, center_y = 780, 130
    for radius in range(120, 20, -15):
        alpha = int(24 * (1.0 - (radius / 120)))
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            outline=(180, 70, 255, alpha),
            width=2,
        )

    # 4. Outer Electric Border Frame
    border_color = (138, 43, 226, 220)
    draw.rectangle([(3, 3), (width - 4, height - 4)], outline=border_color, width=2)
    draw.rectangle([(7, 7), (width - 8, height - 8)], outline=(255, 0, 128, 80), width=1)

    # Corner cybernetic tech brackets
    corner_len = 32
    accent_glow = (255, 0, 100, 255)
    # Top-Left
    draw.line([(0, 0), (corner_len, 0)], fill=accent_glow, width=3)
    draw.line([(0, 0), (0, corner_len)], fill=accent_glow, width=3)
    # Top-Right
    draw.line([(width - corner_len, 0), (width, 0)], fill=accent_glow, width=3)
    draw.line([(width - 1, 0), (width - 1, corner_len)], fill=accent_glow, width=3)
    # Bottom-Left
    draw.line([(0, height - 1), (corner_len, height - 1)], fill=accent_glow, width=3)
    draw.line([(0, height - corner_len), (0, height - 1)], fill=accent_glow, width=3)
    # Bottom-Right
    draw.line([(width - corner_len, height - 1), (width - 1, height - 1)], fill=accent_glow, width=3)
    draw.line([(width - 1, height - corner_len), (width - 1, height - 1)], fill=accent_glow, width=3)

    # 5. Kanji Watermark: 鏡花水月 (Mirror Flower, Water Moon)
    try:
        kanji_font = ImageFont.truetype("msmincho.ttc", 76)
    except Exception:
        try:
            kanji_font = ImageFont.truetype("arial.ttf", 68)
        except Exception:
            kanji_font = ImageFont.load_default()

    draw.text((580, 40), "鏡花水月", fill=(140, 70, 255, 38), font=kanji_font)

    # 6. Typography
    try:
        title_font = ImageFont.truetype("segoeuib.ttf", 40)
        subtitle_font = ImageFont.truetype("segoeui.ttf", 17)
        badge_font = ImageFont.truetype("segoeuib.ttf", 13)
        stat_font = ImageFont.truetype("segoeui.ttf", 15)
    except Exception:
        try:
            title_font = ImageFont.truetype("arialbd.ttf", 36)
            subtitle_font = ImageFont.truetype("arial.ttf", 16)
            badge_font = ImageFont.truetype("arialbd.ttf", 13)
            stat_font = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            title_font = subtitle_font = badge_font = stat_font = ImageFont.load_default()

    # Brand Title with Electric Violet Shadow
    draw.text((47, 37), bot_name.upper(), fill=(138, 43, 226, 180), font=title_font)
    draw.text((45, 35), bot_name.upper(), fill=(255, 255, 255, 255), font=title_font)

    # System Sub-badge
    header_tag = f"AIZEN ARCHITECTURE • {category_title.upper() if category_title else 'COMMAND CONSOLE'}"
    draw.text((46, 88), header_tag, fill=(210, 170, 255, 230), font=subtitle_font)

    # 7. Modern Status Indicator Pills
    pills = [
        ("● ONLINE", (40, 200, 100, 255), (20, 60, 35, 220)),
        (f"WS: {latency_ms}ms", (200, 200, 255, 255), (35, 25, 65, 220)),
        (f"PREFIX: {prefix}", (255, 200, 80, 255), (65, 50, 20, 220)),
        (f"CMDS: {total_commands}", (255, 120, 200, 255), (60, 20, 50, 220)),
    ]

    pill_x = 46
    pill_y = 135
    for label, text_col, bg_col in pills:
        bbox = badge_font.getbbox(label) if hasattr(badge_font, "getbbox") else (0, 0, len(label) * 8, 14)
        text_w = bbox[2] - bbox[0]
        pill_w = text_w + 24
        pill_h = 28
        _draw_glowing_rounded_rect(
            draw,
            (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
            radius=14,
            fill=bg_col,
            outline=text_col,
            glow_color=(text_col[0], text_col[1], text_col[2], 90),
            glow_width=1,
        )
        draw.text((pill_x + 12, pill_y + 6), label, fill=text_col, font=badge_font)
        pill_x += pill_w + 14

    # 8. Motivational / lore tagline at bottom
    tagline = "“Since when were you under the impression that you were not using Kyoka?”"
    draw.text((46, 195), tagline, fill=(180, 160, 215, 200), font=stat_font)
    draw.text((46, 220), "Type +help <cmd> for syntax • Use +hca for public all-command directory", fill=(130, 115, 170, 180), font=stat_font)

    # Export to memory buffer
    buffer = io.BytesIO()
    base.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
