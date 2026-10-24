"""
Kyoka 3.0 - Help Command Archive (HCA) Directory Banner Generator.
Generates a dedicated, futuristic anime directory banner for the public +hca command.
"""

from __future__ import annotations

import io
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


def generate_hca_banner(
    category_name: Optional[str] = None,
    total_commands: int = 150,
    prefix: str = "+",
    page: int = 1,
    total_pages: int = 1,
    **kwargs: Any,
) -> io.BytesIO:
    """
    Render a 900x260 high-definition HCA archive directory banner.
    Returns a BytesIO containing PNG bytes for native Discord attachment.
    """
    width, height = 900, 260
    base = Image.new("RGBA", (width, height), (8, 5, 15, 255))
    draw = ImageDraw.Draw(base, "RGBA")

    # Gradient background: deep obsidian into electric midnight violet
    for y in range(height):
        ratio = y / height
        r = int(8 + (22 - 8) * ratio)
        g = int(5 + (10 - 5) * ratio)
        b = int(15 + (50 - 15) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Hexagonal / circuit line motifs
    line_col = (111, 67, 190, 25)
    for i in range(-height, width, 50):
        draw.line([(i, 0), (i + height, height)], fill=line_col, width=1)
        draw.line([(i + height, 0), (i, height)], fill=line_col, width=1)

    # Outer Neon Frame with Dual Glow
    draw.rectangle([(3, 3), (width - 4, height - 4)], outline=(111, 67, 190, 240), width=2)
    draw.rectangle([(7, 7), (width - 8, height - 8)], outline=(0, 220, 255, 70), width=1)

    # Cyan / Violet Corner Accents
    corner = 28
    c_accent = (0, 230, 255, 255)
    draw.line([(0, 0), (corner, 0)], fill=c_accent, width=3)
    draw.line([(0, 0), (0, corner)], fill=c_accent, width=3)
    draw.line([(width - corner, 0), (width, 0)], fill=c_accent, width=3)
    draw.line([(width - 1, 0), (width - 1, corner)], fill=c_accent, width=3)
    draw.line([(0, height - 1), (corner, height - 1)], fill=c_accent, width=3)
    draw.line([(0, height - corner), (0, height - 1)], fill=c_accent, width=3)
    draw.line([(width - corner, height - 1), (width - 1, height - 1)], fill=c_accent, width=3)
    draw.line([(width - 1, height - corner), (width - 1, height - 1)], fill=c_accent, width=3)

    # Kanji watermark: 百科事典 (Encyclopedia / Archive)
    try:
        kanji_font = ImageFont.truetype("msmincho.ttc", 76)
    except Exception:
        try:
            kanji_font = ImageFont.truetype("arial.ttf", 68)
        except Exception:
            kanji_font = ImageFont.load_default()

    draw.text((580, 40), "全集録", fill=(0, 220, 255, 30), font=kanji_font)

    # Typography
    try:
        title_font = ImageFont.truetype("segoeuib.ttf", 38)
        subtitle_font = ImageFont.truetype("segoeuib.ttf", 16)
        pill_font = ImageFont.truetype("segoeuib.ttf", 13)
        body_font = ImageFont.truetype("segoeui.ttf", 14)
    except Exception:
        try:
            title_font = ImageFont.truetype("arialbd.ttf", 34)
            subtitle_font = ImageFont.truetype("arialbd.ttf", 15)
            pill_font = ImageFont.truetype("arialbd.ttf", 13)
            body_font = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            title_font = subtitle_font = pill_font = body_font = ImageFont.load_default()

    # Title
    draw.text((47, 36), "KYOKA 3.0 • COMMAND ARCHIVE", fill=(111, 67, 190, 180), font=title_font)
    draw.text((45, 34), "KYOKA 3.0 • COMMAND ARCHIVE", fill=(255, 255, 255, 255), font=title_font)

    scope_title = f"DIRECTORY: {category_name.upper()}" if category_name else "FULL REGISTRY • PUBLIC REPOSITORY"
    draw.text((46, 86), scope_title, fill=(0, 220, 255, 240), font=subtitle_font)

    # Status Pills
    pills = [
        ("PUBLIC DIRECTORY", (0, 230, 255, 255), (10, 45, 60, 220)),
        (f"INDEXED: {total_commands}", (255, 180, 80, 255), (60, 40, 15, 220)),
        (f"PAGE: {page}/{max(1, total_pages)}", (200, 150, 255, 255), (45, 20, 70, 220)),
        ("PREFIX & SLASH", (120, 255, 170, 255), (20, 60, 35, 220)),
    ]

    px = 46
    py = 132
    for label, text_c, bg_c in pills:
        bbox = pill_font.getbbox(label) if hasattr(pill_font, "getbbox") else (0, 0, len(label) * 8, 14)
        pw = (bbox[2] - bbox[0]) + 24
        ph = 28
        draw.rounded_rectangle((px, py, px + pw, py + ph), radius=14, fill=bg_c, outline=text_c, width=1)
        draw.text((px + 12, py + 6), label, fill=text_c, font=pill_font)
        px += pw + 12

    # Usage guide line
    draw.text((46, 192), f"Usage: {prefix}hca <category> (e.g. {prefix}hca music, {prefix}hca tickets, {prefix}hca bloxai)", fill=(220, 210, 240, 220), font=body_font)
    draw.text((46, 218), "All commands discovered live from runtime registry • Accessible to all members", fill=(150, 140, 180, 180), font=body_font)

    buf = io.BytesIO()
    base.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
