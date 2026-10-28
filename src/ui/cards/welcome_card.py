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


THEME_PRESETS: dict[str, dict] = {
    "aizen_throne": {
        "filename": "welcome_aizen_throne.png",
        "title": "NEW ALLIANCE FORMED",
        "border_color": (147, 51, 234, 230),  # Electric Violet
        "corner_neon": (255, 0, 128, 255),    # Hot Pink
        "accent_halo": (168, 85, 247),
        "badge_border": (192, 132, 252, 240),
        "tagline": "“Since when were you under the impression that you were not already one of us?”",
        "kanji": "鏡花水月",
        "tint_rgb": (8, 4, 18),
    },
    "cyber_sakura": {
        "filename": "welcome_cyber_sakura.png",
        "title": "CYBER DOMAIN ENTERED",
        "border_color": (255, 60, 170, 230),  # Neon Pink
        "corner_neon": (0, 240, 255, 255),    # Cyber Cyan
        "accent_halo": (255, 90, 190),
        "badge_border": (0, 240, 255, 240),
        "tagline": "“Welcome to the neon realm. Sync your neural link and claim your seat.”",
        "kanji": "新東京",
        "tint_rgb": (14, 4, 24),
    },
    "celestial_nebula": {
        "filename": "welcome_celestial_nebula.png",
        "title": "CELESTIAL ARRIVAL",
        "border_color": (56, 189, 248, 230),  # Celestial Blue
        "corner_neon": (168, 85, 247, 255),   # Nebula Violet
        "accent_halo": (56, 189, 248),
        "badge_border": (125, 211, 252, 240),
        "tagline": "“Amongst ten billion stars, your presence illuminates our sovereign skies.”",
        "kanji": "天河星界",
        "tint_rgb": (6, 10, 28),
    },
    "hueco_las_noches": {
        "filename": "welcome_hueco_las_noches.png",
        "title": "PALACE GATES UNSEALED",
        "border_color": (203, 213, 225, 230), # Moonlight Silver
        "corner_neon": (147, 51, 234, 255),   # Las Noches Purple
        "accent_halo": (192, 132, 252),
        "badge_border": (226, 232, 240, 240),
        "tagline": "“Step across the obsidian sands and enter the throne of supreme power.”",
        "kanji": "虚夜宮",
        "tint_rgb": (10, 8, 22),
    },
}


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
    theme: Optional[str] = None,
) -> io.BytesIO:
    """
    Synchronous Pillow compositing function designed to be invoked inside asyncio.to_thread.
    Renders an ultra-op 1000x360 cinematic anime gaming welcome graphic.
    """
    import random

    width, height = 1000, 360

    # 1. Resolve theme preset
    theme_key = (theme or "aizen_throne").lower().strip()
    if theme_key == "random":
        chosen_key = random.choice(list(THEME_PRESETS.keys()))
        preset = THEME_PRESETS[chosen_key]
    elif theme_key in THEME_PRESETS:
        preset = THEME_PRESETS[theme_key]
    else:
        # Fuzzy match alias
        matched = False
        for k, p in THEME_PRESETS.items():
            if theme_key in k or k in theme_key:
                preset = p
                matched = True
                break
        if not matched:
            preset = THEME_PRESETS["aizen_throne"]

    base = Image.new("RGBA", (width, height), (10, 6, 18, 255))

    # 2. Background image loading with horizontal atmospheric glass mask
    bg_loaded = False
    bg_candidates: list[Path] = []
    if custom_bg_path:
        bg_candidates.append(Path(custom_bg_path))

    # Prefer the active theme's masterwork artwork
    theme_art = BASE_DIR / "assets" / "kyoka" / "features" / preset["filename"]
    bg_candidates.append(theme_art)
    bg_candidates.extend([
        BASE_DIR / "assets" / "kyoka" / "features" / "welcome_aizen_throne.png",
        BASE_DIR / "assets" / "kyoka" / "features" / "welcome_banner.png",
        BASE_DIR / "assets" / "kyoka" / "branding" / "kyoka_background.png",
    ])

    for bg_path in bg_candidates:
        if bg_path and bg_path.is_file():
            try:
                with Image.open(bg_path) as raw_bg:
                    raw_bg = raw_bg.convert("RGBA")
                    bg_scaled = ImageOps.fit(raw_bg, (width, height), method=Image.Resampling.LANCZOS)

                    # Dynamic atmospheric gradient mask:
                    # Dark obsidian glass on the left (x: 0-440) for 100% crystal-clear readability
                    # Gentle fade (x: 440-700)
                    # Light atmospheric tint on the right (x: 700-1000) so artwork shines in 8K brilliance!
                    tint_r, tint_g, tint_b = preset["tint_rgb"]
                    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    for x in range(width):
                        if x <= 420:
                            alpha = 168
                        elif x <= 720:
                            ratio = (x - 420) / (720 - 420)
                            alpha = int(168 - (168 - 38) * ratio)
                        else:
                            alpha = 38
                        overlay_draw.line([(x, 0), (x, height)], fill=(tint_r, tint_g, tint_b, alpha))

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

    # 3. Outer Neon Electric Border Frame & Corner Brackets
    border_color = preset["border_color"]
    draw.rectangle([(4, 4), (width - 5, height - 5)], outline=border_color, width=2)
    draw.rectangle([(8, 8), (width - 9, height - 9)], outline=(preset["accent_halo"][0], preset["accent_halo"][1], preset["accent_halo"][2], 60), width=1)

    # Cybernetic corner brackets
    c_len = 34
    c_neon = preset["corner_neon"]
    # Top-Left
    draw.line([(4, 4), (4 + c_len, 4)], fill=c_neon, width=3)
    draw.line([(4, 4), (4, 4 + c_len)], fill=c_neon, width=3)
    # Top-Right
    draw.line([(width - 5 - c_len, 4), (width - 5, 4)], fill=c_neon, width=3)
    draw.line([(width - 5, 4), (width - 5, 4 + c_len)], fill=c_neon, width=3)
    # Bottom-Left
    draw.line([(4, height - 5), (4 + c_len, height - 5)], fill=c_neon, width=3)
    draw.line([(4, height - 5 - c_len), (4, height - 5)], fill=c_neon, width=3)
    # Bottom-Right
    draw.line([(width - 5 - c_len, height - 5), (width - 5, height - 5)], fill=c_neon, width=3)
    draw.line([(width - 5, height - 5 - c_len), (width - 5, height - 5)], fill=c_neon, width=3)

    # 4. Japanese Watermark Kanji (e.g. 鏡花水月, 新東京, etc.)
    kanji_font = None
    for f_candidate in ["msgothic.ttc", "yugothib.ttc", "simsun.ttc", "malgun.ttf", "arialbd.ttf"]:
        try:
            kanji_font = ImageFont.truetype(f_candidate, 64)
            break
        except Exception:
            continue
    if not kanji_font:
        kanji_font = ImageFont.load_default()

    halo_r, halo_g, halo_b = preset["accent_halo"]
    draw.text((width - 260, 24), preset["kanji"], fill=(halo_r, halo_g, halo_b, 34), font=kanji_font)

    # 5. Circular Avatar Focal Point with Cybernetic HUD Halo
    av_size = 176
    av_x = 52
    av_y = (height - av_size) // 2

    # Draw multi-ring glowing avatar aura
    for r_offset in (14, 10, 6, 2):
        aura_alpha = int(120 * (1.0 - (r_offset / 16)))
        draw.ellipse(
            [
                av_x - r_offset,
                av_y - r_offset,
                av_x + av_size + r_offset,
                av_y + av_size + r_offset,
            ],
            outline=(halo_r, halo_g, halo_b, aura_alpha),
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
        # Stylized initial avatar placeholder
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=(28, 12, 50, 255), outline=border_color, width=3)
        initial = (username[:1] or "K").upper()
        try:
            init_font = ImageFont.truetype("segoeuib.ttf", 72)
        except Exception:
            try:
                init_font = ImageFont.truetype("arialbd.ttf", 64)
            except Exception:
                init_font = ImageFont.load_default()
        draw.text((av_x + 62, av_y + 44), initial, fill=(255, 255, 255, 240), font=init_font)

    # Outer border circle on avatar + HUD Crosshair ticks
    draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], outline=c_neon, width=3)

    c_mid_x = av_x + av_size // 2
    c_mid_y = av_y + av_size // 2
    draw.line([(c_mid_x, av_y - 10), (c_mid_x, av_y - 2)], fill=c_neon, width=2)
    draw.line([(c_mid_x, av_y + av_size + 2), (c_mid_x, av_y + av_size + 10)], fill=c_neon, width=2)
    draw.line([(av_x - 10, c_mid_y), (av_x - 2, c_mid_y)], fill=c_neon, width=2)
    draw.line([(av_x + av_size + 2, c_mid_y), (av_x + av_size + 10, c_mid_y)], fill=c_neon, width=2)

    # 6. Typography & Member Details
    try:
        title_font = ImageFont.truetype("segoeuib.ttf", 35)
        user_font = ImageFont.truetype("segoeuib.ttf", 29)
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

    text_x = 270

    # Top Pill: Server Realm Badge
    clean_guild = (guild_name[:30] + "...") if len(guild_name) > 32 else guild_name
    server_badge = f"⛩️ WELCOME TO {clean_guild.upper()}"
    s_bbox = badge_font.getbbox(server_badge) if hasattr(badge_font, "getbbox") else (0, 0, len(server_badge) * 8, 14)
    s_pill_w = (s_bbox[2] - s_bbox[0]) + 24
    _draw_glowing_pill(
        draw,
        (text_x, 40, text_x + s_pill_w, 40 + 26),
        radius=13,
        fill=(*preset["tint_rgb"], 225),
        outline=preset["badge_border"],
        glow_color=(halo_r, halo_g, halo_b, 100),
        glow_width=1,
    )
    draw.text((text_x + 12, 45), server_badge, fill=(245, 235, 255, 255), font=badge_font)

    # Main Welcome Header with Dark Drop Shadow
    title_text = preset["title"]
    draw.text((text_x + 2, 78), title_text, fill=(0, 0, 0, 200), font=title_font)
    draw.text((text_x, 76), title_text, fill=(255, 255, 255, 255), font=title_font)

    # Username with Electric Glow & Drop Shadow
    clean_user = (username[:22] + "...") if len(username) > 24 else username
    user_tag = f"@{clean_user}"
    draw.text((text_x + 2, 126), user_tag, fill=(0, 0, 0, 200), font=user_font)
    draw.text((text_x, 124), user_tag, fill=(halo_r, halo_g, halo_b, 255), font=user_font)

    # Status Pills: Member Count & Access Granted
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
        if len(clean_step) > 65:
            clean_step = clean_step[:62] + "..."
        draw.text((text_x + 1, 229), f"Next Step: {clean_step}", fill=(0, 0, 0, 180), font=sub_font)
        draw.text((text_x, 228), f"Next Step: {clean_step}", fill=(210, 195, 245, 235), font=sub_font)

    # Motivational Lore Footer
    tagline = preset["tagline"]
    draw.text((text_x + 1, 267), tagline, fill=(0, 0, 0, 180), font=lore_font)
    draw.text((text_x, 266), tagline, fill=(160, 145, 195, 210), font=lore_font)
    draw.text((text_x, 292), f"Kyoka 3.0 • Aizen Edition • Enjoy your stay in {clean_guild}", fill=(120, 105, 155, 180), font=lore_font)

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
    theme: Optional[str] = None,
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
        theme=theme,
    )

