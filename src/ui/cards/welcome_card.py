"""
Kyoka 3.0 - Aizen Edition Welcome Image Generator & Compositor
Generates custom-designed, anime gaming community welcome cards in-memory using Pillow.
Enforces non-blocking execution, avatar safe-fetching, multi-ring aura glows, and Aizen dark-violet aesthetic.
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Optional, Union
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

logger = logging.getLogger("Kyoka.UI.WelcomeCard")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _draw_glowing_pill(
    draw: ImageDraw.ImageDraw,
    coords: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    glow_color: tuple[int, int, int, int],
    glow_width: int = 2,
) -> None:
    """Draw a rounded rectangle pill with a subtle neon aura."""
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


def generate_aizen_welcome_card(
    username: str,
    guild_name: str,
    member_count: int,
    avatar_bytes: Optional[bytes] = None,
    next_step: Optional[str] = "Read #rules & complete verification to begin",
    custom_bg_path: Optional[Union[str, Path]] = None,
) -> io.BytesIO:
    """
    Synchronous Pillow compositing function designed to be invoked inside asyncio.to_thread.
    Renders a 1000x360 premium anime gaming welcome graphic.
    """
    width, height = 1000, 360
    base = Image.new("RGBA", (width, height), (10, 6, 18, 255))

    # 1. Background image loading or procedural dark-violet gradient
    bg_loaded = False
    bg_candidates: list[Path] = []
    if custom_bg_path:
        bg_candidates.append(Path(custom_bg_path))
    bg_candidates.extend([
        BASE_DIR / "assets" / "kyoka" / "features" / "welcome_banner.png",
        BASE_DIR / "assets" / "kyoka" / "branding" / "kyoka_background.png",
        BASE_DIR / "assets" / "kyoka" / "branding" / "kyoka_banner.png",
    ])

    for bg_path in bg_candidates:
        if bg_path and bg_path.is_file():
            try:
                with Image.open(bg_path) as raw_bg:
                    raw_bg = raw_bg.convert("RGBA")
                    # Scale and center crop to 1000x360
                    bg_scaled = ImageOps.fit(raw_bg, (width, height), method=Image.Resampling.LANCZOS)
                    # Apply dark purple/obsidian atmospheric tint so text pop out
                    overlay = Image.new("RGBA", (width, height), (8, 4, 16, 180))
                    base = Image.alpha_composite(bg_scaled, overlay)
                    bg_loaded = True
                    break
            except Exception as e:
                logger.debug(f"Failed to load background candidate {bg_path}: {e}")

    draw = ImageDraw.Draw(base, "RGBA")

    if not bg_loaded:
        # Procedural fallback gradient (Obsidian #09040F to Royal Violet #1D0A35)
        for y in range(height):
            ratio = y / height
            r = int(9 + (29 - 9) * ratio)
            g = int(4 + (10 - 4) * ratio)
            b = int(15 + (53 - 15) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # 2. Spiritual pressure aura lines & diagonal cyber grid
    grid_color = (138, 43, 226, 18)
    for x in range(0, width + height, 45):
        draw.line([(x, 0), (x - height, height)], fill=grid_color, width=1)

    # Ambient spiritual vortex rings on right side
    center_x, center_y = 860, 180
    for radius in range(160, 30, -20):
        alpha = int(25 * (1.0 - (radius / 160)))
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            outline=(190, 75, 255, alpha),
            width=2,
        )

    # 3. Outer Neon Electric Border Frame & Corner Brackets
    border_color = (138, 43, 226, 210)
    draw.rectangle([(4, 4), (width - 5, height - 5)], outline=border_color, width=2)
    draw.rectangle([(8, 8), (width - 9, height - 9)], outline=(255, 0, 110, 80), width=1)

    # Cybernetic corner brackets
    c_len = 36
    corner_neon = (255, 0, 110, 255)
    # Top-Left
    draw.line([(0, 0), (c_len, 0)], fill=corner_neon, width=4)
    draw.line([(0, 0), (0, c_len)], fill=corner_neon, width=4)
    # Top-Right
    draw.line([(width - c_len, 0), (width - 1, 0)], fill=corner_neon, width=4)
    draw.line([(width - 1, 0), (width - 1, c_len)], fill=corner_neon, width=4)
    # Bottom-Left
    draw.line([(0, height - 1), (c_len, height - 1)], fill=corner_neon, width=4)
    draw.line([(0, height - c_len), (0, height - 1)], fill=corner_neon, width=4)
    # Bottom-Right
    draw.line([(width - c_len, height - 1), (width - 1, height - 1)], fill=corner_neon, width=4)
    draw.line([(width - 1, height - c_len), (width - 1, height - 1)], fill=corner_neon, width=4)

    # 4. Japanese Watermark: 鏡花水月 (Kyoka Suigetsu)
    try:
        kanji_font = ImageFont.truetype("msmincho.ttc", 72)
    except Exception:
        try:
            kanji_font = ImageFont.truetype("arial.ttf", 64)
        except Exception:
            kanji_font = ImageFont.load_default()
    draw.text((620, 25), "鏡花水月", fill=(140, 70, 255, 28), font=kanji_font)

    # 5. Circular Avatar Focal Point
    av_size = 180
    av_x = 55
    av_y = (height - av_size) // 2

    # Draw multi-ring glowing avatar aura
    for r_offset in (12, 8, 4, 2):
        aura_alpha = int(90 * (1.0 - (r_offset / 14)))
        draw.ellipse(
            [
                av_x - r_offset,
                av_y - r_offset,
                av_x + av_size + r_offset,
                av_y + av_size + r_offset,
            ],
            outline=(138, 43, 226, aura_alpha),
            width=2,
        )

    avatar_placed = False
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as av_raw:
                av_raw = av_raw.convert("RGBA")
                av_scaled = av_raw.resize((av_size, av_size), Image.Resampling.LANCZOS)

                # Antialiased high-quality circular mask
                mask = Image.new("L", (av_size * 2, av_size * 2), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, av_size * 2, av_size * 2), fill=255)
                mask = mask.resize((av_size, av_size), Image.Resampling.LANCZOS)

                base.paste(av_scaled, (av_x, av_y), mask)
                avatar_placed = True
        except Exception as e:
            logger.warning(f"Error processing avatar bytes: {e}")

    if not avatar_placed:
        # Fallback stylized initial avatar
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=(28, 12, 50, 255), outline=(138, 43, 226, 255), width=3)
        initial = (username[:1] or "K").upper()
        try:
            init_font = ImageFont.truetype("segoeuib.ttf", 72)
        except Exception:
            try:
                init_font = ImageFont.truetype("arialbd.ttf", 64)
            except Exception:
                init_font = ImageFont.load_default()
        draw.text((av_x + 65, av_y + 45), initial, fill=(255, 255, 255, 240), font=init_font)

    # Outer border circle on avatar
    draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], outline=(255, 0, 110, 220), width=3)

    # 6. Typography & Member Details
    try:
        title_font = ImageFont.truetype("segoeuib.ttf", 36)
        user_font = ImageFont.truetype("segoeuib.ttf", 30)
        badge_font = ImageFont.truetype("segoeuib.ttf", 13)
        sub_font = ImageFont.truetype("segoeui.ttf", 15)
        lore_font = ImageFont.truetype("segoeui.ttf", 13)
    except Exception:
        try:
            title_font = ImageFont.truetype("arialbd.ttf", 32)
            user_font = ImageFont.truetype("arialbd.ttf", 26)
            badge_font = ImageFont.truetype("arialbd.ttf", 13)
            sub_font = ImageFont.truetype("arial.ttf", 14)
            lore_font = ImageFont.truetype("arial.ttf", 13)
        except Exception:
            title_font = user_font = badge_font = sub_font = lore_font = ImageFont.load_default()

    text_x = 280

    # Top Pill: Server Realm Badge
    clean_guild = (guild_name[:32] + "...") if len(guild_name) > 35 else guild_name
    server_badge = f"⛩️ WELCOME TO {clean_guild.upper()}"
    s_bbox = badge_font.getbbox(server_badge) if hasattr(badge_font, "getbbox") else (0, 0, len(server_badge) * 8, 14)
    s_pill_w = (s_bbox[2] - s_bbox[0]) + 24
    _draw_glowing_pill(
        draw,
        (text_x, 42, text_x + s_pill_w, 42 + 26),
        radius=13,
        fill=(25, 10, 45, 220),
        outline=(160, 60, 255, 255),
        glow_color=(160, 60, 255, 100),
        glow_width=1,
    )
    draw.text((text_x + 12, 47), server_badge, fill=(235, 210, 255, 255), font=badge_font)

    # Main Welcome Header
    draw.text((text_x + 2, 80), "NEW ALLIANCE FORMED", fill=(138, 43, 226, 160), font=title_font)
    draw.text((text_x, 78), "NEW ALLIANCE FORMED", fill=(255, 255, 255, 255), font=title_font)

    # Username with Electric Violet Glow
    clean_user = (username[:22] + "...") if len(username) > 24 else username
    user_tag = f"@{clean_user}"
    draw.text((text_x + 2, 126), user_tag, fill=(255, 0, 110, 180), font=user_font)
    draw.text((text_x, 124), user_tag, fill=(215, 175, 255, 255), font=user_font)

    # Status Pills: Member Count & Next Step
    pill_y = 180
    pills = [
        (f"👥 MEMBER #{member_count:,}", (255, 215, 80, 255), (60, 45, 15, 220)),
        ("⚡ ACCESS GRANTED", (40, 220, 120, 255), (15, 55, 30, 220)),
    ]

    p_curr_x = text_x
    for label, text_col, bg_col in pills:
        bbox = badge_font.getbbox(label) if hasattr(badge_font, "getbbox") else (0, 0, len(label) * 8, 14)
        pw = (bbox[2] - bbox[0]) + 22
        ph = 26
        _draw_glowing_pill(
            draw,
            (p_curr_x, pill_y, p_curr_x + pw, pill_y + ph),
            radius=13,
            fill=bg_col,
            outline=text_col,
            glow_color=(text_col[0], text_col[1], text_col[2], 90),
            glow_width=1,
        )
        draw.text((p_curr_x + 11, pill_y + 5), label, fill=text_col, font=badge_font)
        p_curr_x += pw + 12

    # Configurable Next Step Text
    if next_step and str(next_step).strip():
        clean_step = str(next_step).strip()
        if len(clean_step) > 70:
            clean_step = clean_step[:67] + "..."
        draw.text((text_x, 228), f"Next Step: {clean_step}", fill=(200, 185, 235, 220), font=sub_font)

    # Motivational Aizen Lore Footer
    tagline = "“Since when were you under the impression that you were not already one of us?”"
    draw.text((text_x, 266), tagline, fill=(150, 130, 185, 190), font=lore_font)
    draw.text((text_x, 292), f"Kyoka 3.0 • Aizen Edition • Enjoy your stay in {clean_guild}", fill=(110, 95, 145, 170), font=lore_font)

    # Export to BytesIO buffer
    buffer = io.BytesIO()
    base.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer


async def fetch_avatar_bytes(avatar_url: str) -> Optional[bytes]:
    """Asynchronously download user avatar bytes with a strict 4-second timeout."""
    if not avatar_url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=4.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        logger.debug(f"Could not fetch avatar from {avatar_url}: {e}")
    return None


async def render_welcome_card_async(
    username: str,
    guild_name: str,
    member_count: int,
    avatar_url: Optional[str] = None,
    next_step: Optional[str] = "Read #rules & complete verification to begin",
    custom_bg_path: Optional[Union[str, Path]] = None,
) -> io.BytesIO:
    """Non-blocking wrapper that downloads avatar and composites welcome graphic off-thread."""
    avatar_bytes: Optional[bytes] = None
    if avatar_url:
        avatar_bytes = await fetch_avatar_bytes(avatar_url)

    # Render Pillow composite in threadpool so gateway event loop is never blocked
    return await asyncio.to_thread(
        generate_aizen_welcome_card,
        username=username,
        guild_name=guild_name,
        member_count=member_count,
        avatar_bytes=avatar_bytes,
        next_step=next_step,
        custom_bg_path=custom_bg_path,
    )
