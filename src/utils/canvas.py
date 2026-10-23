"""
Kyoka Discord Bot - Ultra-Premium Canvas Image Rendering
Renders high-resolution, anti-aliased glassmorphic dynamic graphic cards (Passport/Profile, Audio Visualizers)
directly in memory using Pillow C-extensions with zero external API dependencies.
"""

from __future__ import annotations

import io
import math
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import discord


def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load high-fidelity TrueType system fonts across Windows and Linux environments."""
    if not HAS_PIL:
        raise RuntimeError("Pillow is not installed")
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_equalizer_bars(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple[int, int, int]) -> None:
    """Draw a miniature 5-bar dynamic audio equalizer."""
    heights = [12, 22, 10, 18, 14]
    bar_w = 3
    spacing = 3
    for i, h in enumerate(heights):
        bx = x + i * (bar_w + spacing)
        by = y + (22 - h)
        draw.rounded_rectangle([(bx, by), (bx + bar_w, by + h)], radius=1, fill=color)


def draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
    """Draw a sleek 4-pointed diamond star icon."""
    pts = [
        (cx, cy - r),
        (cx + r * 0.35, cy - r * 0.35),
        (cx + r, cy),
        (cx + r * 0.35, cy + r * 0.35),
        (cx, cy + r),
        (cx - r * 0.35, cy + r * 0.35),
        (cx - r, cy),
        (cx - r * 0.35, cy - r * 0.35),
    ]
    draw.polygon(pts, fill=color)


def render_profile_card(
    avatar_bytes: bytes | None,
    username: str,
    display_name: str,
    standing: str,
    tier: str,
    playlists_count: int,
    live_audio: str | None = None,
    live_vc: str | None = None,
    is_owner: bool = False,
    is_dev: bool = False,
) -> io.BytesIO | None:
    """
    Render a high-resolution, anti-aliased Ultra-Premium Glassmorphic Passport Card (920x360px).
    Features ambient avatar backdrop blur, glowing neon halo, dynamic badges, and audio stats grid.
    """
    if not HAS_PIL:
        return None

    w, h = 920, 360

    # 1. Accent Color Grading
    if is_owner:
        accent_rgb = (168, 85, 247)       # Royal Violet
        accent_secondary = (217, 70, 239) # Fuchsia
        tint_bg = (28, 20, 38)
    elif is_dev:
        accent_rgb = (59, 130, 246)       # Electric Blue
        accent_secondary = (14, 165, 233) # Sky Blue
        tint_bg = (18, 26, 42)
    elif "Dispatcher" in standing or "No-Prefix" in standing:
        accent_rgb = (16, 185, 129)       # Emerald Green
        accent_secondary = (52, 211, 153) # Mint
        tint_bg = (18, 32, 28)
    else:
        accent_rgb = (129, 140, 248)      # Sleek Indigo
        accent_secondary = (99, 102, 241)
        tint_bg = (20, 24, 38)

    # 2. Base Dark Slate Canvas with Gradient Mesh
    im = Image.new("RGBA", (w, h), (10, 13, 20, 255))

    # Ambient Backdrop from Avatar (Heavy Gaussian Blur)
    if avatar_bytes:
        try:
            av_raw = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            bg_ambient = av_raw.resize((w + 120, h + 120), Image.Resampling.BILINEAR)
            bg_ambient = bg_ambient.filter(ImageFilter.GaussianBlur(radius=42))
            bg_ambient = bg_ambient.crop((60, 60, 60 + w, 60 + h))
            
            # Dark luxury overlay
            darkener = Image.new("RGBA", (w, h), (8, 10, 16, 218))
            im = Image.alpha_composite(bg_ambient, darkener)
        except Exception:
            pass

    # Soft ambient radial glow near avatar
    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.ellipse([(0, -20), (300, 280)], fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 38))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=30))
    im = Image.alpha_composite(im, glow_layer)

    draw = ImageDraw.Draw(im, "RGBA")

    # 3. Outer Glass Border with Dual Accent Highlights
    draw.rounded_rectangle([(6, 6), (w - 7, h - 7)], radius=24, outline=(40, 48, 68, 180), width=1)
    draw.rounded_rectangle([(8, 8), (w - 9, h - 9)], radius=22, fill=(13, 17, 28, 165), outline=(255, 255, 255, 22), width=1)

    # Top Horizon Neon Line
    draw.rounded_rectangle([(30, 8), (w - 30, 10)], radius=1, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 230))
    draw.rounded_rectangle([(80, 10), (w - 80, 11)], radius=1, fill=(accent_secondary[0], accent_secondary[1], accent_secondary[2], 120))

    # 4. Avatar (Large, Anti-aliased, Glowing Halo)
    av_size = 130
    av_x, av_y = 42, 44

    # Halo shadow
    draw.ellipse([(av_x - 6, av_y - 6), (av_x + av_size + 6, av_y + av_size + 6)], outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 70), width=4)
    # Crisp accent ring
    draw.ellipse([(av_x - 3, av_y - 3), (av_x + av_size + 3, av_y + av_size + 3)], outline=accent_rgb, width=3)

    if avatar_bytes:
        try:
            av = av_raw.resize((av_size * 4, av_size * 4), Image.Resampling.LANCZOS)
            mask = Image.new("L", (av_size * 4, av_size * 4), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.ellipse([(0, 0), (av_size * 4, av_size * 4)], fill=255)
            av_circle = Image.new("RGBA", (av_size * 4, av_size * 4), (0, 0, 0, 0))
            av_circle.paste(av, (0, 0), mask)
            av_final = av_circle.resize((av_size, av_size), Image.Resampling.LANCZOS)
            im.paste(av_final, (av_x, av_y), av_final)
        except Exception:
            draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(28, 33, 48, 255))
    else:
        draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(28, 33, 48, 255))

    # Online / Activity status badge on avatar
    dot_x, dot_y = av_x + av_size - 18, av_y + av_size - 18
    draw.ellipse([(dot_x - 3, dot_y - 3), (dot_x + 21, dot_y + 21)], fill=(13, 17, 28, 255))
    draw.ellipse([(dot_x, dot_y), (dot_x + 18, dot_y + 18)], fill=(34, 197, 94, 255))

    # 5. Typography Hierarchy
    font_name = get_font(30, bold=True)
    font_tag = get_font(16, bold=False)
    font_badge = get_font(13, bold=True)
    font_tile_title = get_font(11, bold=True)
    font_tile_val = get_font(15, bold=True)
    font_sub = get_font(11, bold=False)

    text_x = av_x + av_size + 34
    name_y = 44

    # Display Name
    disp_clean = display_name[:22]
    draw.text((text_x, name_y), disp_clean, fill=(255, 255, 255, 255), font=font_name)

    # Username Tag
    tag_str = f"@{username[:24]}"
    tag_y = name_y + 38
    draw.text((text_x, tag_y), tag_str, fill=(148, 163, 184, 255), font=font_tag)

    # 6. Badges (Ultra Clean Glass Pills - NO CUTOFFS)
    badge_y = tag_y + 30
    curr_bx = text_x

    # Badge 1: Standing
    s_label = standing
    s_len = draw.textlength(s_label, font=font_badge)
    s_w = int(s_len) + 36
    draw.rounded_rectangle([(curr_bx, badge_y), (curr_bx + s_w, badge_y + 26)], radius=8, fill=tint_bg, outline=accent_rgb, width=1)
    draw.ellipse([(curr_bx + 10, badge_y + 9), (curr_bx + 18, badge_y + 17)], fill=accent_rgb)
    draw.text((curr_bx + 24, badge_y + 4), s_label, fill=(245, 247, 250, 255), font=font_badge)
    curr_bx += s_w + 12

    # Badge 2: Tier
    t_label = tier
    t_len = draw.textlength(t_label, font=font_badge)
    t_w = int(t_len) + 34
    draw.rounded_rectangle([(curr_bx, badge_y), (curr_bx + t_w, badge_y + 26)], radius=8, fill=(22, 28, 44, 230), outline=(71, 85, 105, 180), width=1)
    draw_star(draw, curr_bx + 14, badge_y + 13, 4, (147, 197, 253))
    draw.text((curr_bx + 24, badge_y + 4), t_label, fill=(226, 232, 240, 255), font=font_badge)
    curr_bx += t_w + 12

    # Badge 3: Playlists
    p_label = f"{playlists_count} Playlists"
    p_len = draw.textlength(p_label, font=font_badge)
    p_w = int(p_len) + 32
    if curr_bx + p_w < w - 30:
        draw.rounded_rectangle([(curr_bx, badge_y), (curr_bx + p_w, badge_y + 26)], radius=8, fill=(22, 28, 44, 230), outline=(71, 85, 105, 180), width=1)
        draw.ellipse([(curr_bx + 11, badge_y + 10), (curr_bx + 17, badge_y + 16)], fill=(167, 139, 250))
        draw.text((curr_bx + 22, badge_y + 4), p_label, fill=(226, 232, 240, 255), font=font_badge)

    # 7. Bottom Stats Cards / Tiles Grid
    tile_y = 196
    tile_h = 92
    tile_spacing = 16
    tile_w = (w - 76 - (tile_spacing * 2)) // 3

    # Tile 1: Playlists
    t1_x = 38
    draw.rounded_rectangle([(t1_x, tile_y), (t1_x + tile_w, tile_y + tile_h)], radius=12, fill=(18, 23, 37, 200), outline=(255, 255, 255, 24), width=1)
    draw.rounded_rectangle([(t1_x + 8, tile_y + 14), (t1_x + 11, tile_y + tile_h - 14)], radius=2, fill=(129, 140, 248))
    draw.text((t1_x + 20, tile_y + 14), "PLAYLISTS LIBRARY", fill=(148, 163, 184, 255), font=font_tile_title)
    draw.text((t1_x + 20, tile_y + 36), f"{playlists_count} Saved Cloud Playlists", fill=(255, 255, 255, 255), font=font_tile_val)
    draw.text((t1_x + 20, tile_y + 62), "Kyoka Cloud Storage Active", fill=(100, 116, 139, 255), font=font_sub)

    # Tile 2: Standing & Access
    t2_x = t1_x + tile_w + tile_spacing
    draw.rounded_rectangle([(t2_x, tile_y), (t2_x + tile_w, tile_y + tile_h)], radius=12, fill=(18, 23, 37, 200), outline=(255, 255, 255, 24), width=1)
    draw.rounded_rectangle([(t2_x + 8, tile_y + 14), (t2_x + 11, tile_y + tile_h - 14)], radius=2, fill=accent_rgb)
    draw.text((t2_x + 20, tile_y + 14), "IDENTITY & ACCESS", fill=(148, 163, 184, 255), font=font_tile_title)
    draw.text((t2_x + 20, tile_y + 36), standing[:22], fill=(255, 255, 255, 255), font=font_tile_val)
    draw.text((t2_x + 20, tile_y + 62), f"Tier: {tier} • Verified", fill=(100, 116, 139, 255), font=font_sub)

    # Tile 3: Live Audio
    t3_x = t2_x + tile_w + tile_spacing
    draw.rounded_rectangle([(t3_x, tile_y), (t3_x + tile_w, tile_y + tile_h)], radius=12, fill=(18, 23, 37, 200), outline=(255, 255, 255, 24), width=1)
    
    if live_audio:
        draw.rounded_rectangle([(t3_x + 8, tile_y + 14), (t3_x + 11, tile_y + tile_h - 14)], radius=2, fill=(34, 197, 94))
        draw.text((t3_x + 20, tile_y + 14), "LIVE AUDIO STREAM", fill=(34, 197, 94, 255), font=font_tile_title)
        draw.text((t3_x + 20, tile_y + 36), live_audio[:18] + ("..." if len(live_audio) > 18 else ""), fill=(255, 255, 255, 255), font=font_tile_val)
        draw.text((t3_x + 20, tile_y + 62), f"In {live_vc[:14]} • 320kbps" if live_vc else "Studio Master Audio", fill=(100, 116, 139, 255), font=font_sub)
        draw_equalizer_bars(draw, t3_x + tile_w - 38, tile_y + 35, (34, 197, 94))
    else:
        draw.rounded_rectangle([(t3_x + 8, tile_y + 14), (t3_x + 11, tile_y + tile_h - 14)], radius=2, fill=(100, 116, 139))
        draw.text((t3_x + 20, tile_y + 14), "LIVE AUDIO STREAM", fill=(148, 163, 184, 255), font=font_tile_title)
        draw.text((t3_x + 20, tile_y + 36), "Idle (Not Listening)", fill=(148, 163, 184, 255), font=font_tile_val)
        draw.text((t3_x + 20, tile_y + 62), "Ready to stream in VC", fill=(100, 116, 139, 255), font=font_sub)

    # 8. Footer Micro-Bar & Branding
    draw.line([(38, h - 38), (w - 38, h - 38)], fill=(255, 255, 255, 18), width=1)
    footer_text = "KYOKA STUDIO PASSPORT // ADVANCED AUDIO ENGINE"
    draw.text((38, h - 28), footer_text, fill=(100, 116, 139, 220), font=font_sub)

    status_pill = "HIGH-FIDELITY ACTIVE"
    s_pill_len = draw.textlength(status_pill, font=font_sub)
    draw.text((w - 38 - s_pill_len, h - 28), status_pill, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 230), font=font_sub)

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def render_rank_card(
    avatar_bytes: bytes | None,
    username: str,
    display_name: str,
    rank: int,
    level: int,
    current_xp: int,
    needed_xp: int,
    total_xp: int,
    accent_color: tuple[int, int, int] | None = None,
) -> io.BytesIO | None:
    """
    Render a high-resolution, anti-aliased Glassmorphic Level/Rank Card (900x260px).
    Features ambient blurred backdrop, glowing neon avatar ring, rank badges,
    and a sleek progress bar with percentage indicator.
    """
    if not HAS_PIL:
        return None

    w, h = 900, 260
    if isinstance(accent_color, int):
        accent_rgb = ((accent_color >> 16) & 0xFF, (accent_color >> 8) & 0xFF, accent_color & 0xFF)
    elif isinstance(accent_color, (tuple, list)) and len(accent_color) >= 3:
        accent_rgb = (int(accent_color[0]), int(accent_color[1]), int(accent_color[2]))
    else:
        accent_rgb = (124, 58, 237)      # Royal Purple / Violet (#7C3AED)
    accent_secondary = (59, 130, 246)     # Electric Blue (#3B82F6)

    # 1. Base Canvas
    im = Image.new("RGBA", (w, h), (12, 15, 24, 255))

    # Ambient Backdrop from Avatar
    if avatar_bytes:
        try:
            av_raw = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            bg_ambient = av_raw.resize((w + 80, h + 80), Image.Resampling.BILINEAR)
            bg_ambient = bg_ambient.filter(ImageFilter.GaussianBlur(radius=36))
            bg_ambient = bg_ambient.crop((40, 40, 40 + w, 40 + h))
            darkener = Image.new("RGBA", (w, h), (10, 13, 22, 225))
            im = Image.alpha_composite(bg_ambient, darkener)
        except Exception:
            av_raw = None
    else:
        av_raw = None

    # Ambient glow
    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.ellipse([(20, -10), (280, 250)], fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 40))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=25))
    im = Image.alpha_composite(im, glow_layer)

    draw = ImageDraw.Draw(im, "RGBA")

    # Outer Glass Borders
    draw.rounded_rectangle([(6, 6), (w - 7, h - 7)], radius=20, outline=(40, 48, 68, 160), width=1)
    draw.rounded_rectangle([(8, 8), (w - 9, h - 9)], radius=18, fill=(13, 17, 28, 170), outline=(255, 255, 255, 20), width=1)

    # Top Horizon Line
    draw.rounded_rectangle([(25, 8), (w - 25, 10)], radius=1, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 220))

    # Avatar (Circle crop with glowing border)
    av_size = 110
    av_x, av_y = 36, 40

    draw.ellipse([(av_x - 4, av_y - 4), (av_x + av_size + 4, av_y + av_size + 4)], outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 80), width=3)
    draw.ellipse([(av_x - 2, av_y - 2), (av_x + av_size + 2, av_y + av_size + 2)], outline=accent_rgb, width=2)

    if av_raw:
        try:
            av = av_raw.resize((av_size * 4, av_size * 4), Image.Resampling.LANCZOS)
            mask = Image.new("L", (av_size * 4, av_size * 4), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.ellipse([(0, 0), (av_size * 4, av_size * 4)], fill=255)
            av_circle = Image.new("RGBA", (av_size * 4, av_size * 4), (0, 0, 0, 0))
            av_circle.paste(av, (0, 0), mask)
            av_final = av_circle.resize((av_size, av_size), Image.Resampling.LANCZOS)
            im.paste(av_final, (av_x, av_y), av_final)
        except Exception:
            draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(28, 33, 48, 255))
    else:
        draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(28, 33, 48, 255))

    # Typography
    font_name = get_font(24, bold=True)
    font_tag = get_font(15, bold=False)
    font_badge = get_font(13, bold=True)
    font_num = get_font(26, bold=True)
    font_xp = get_font(14, bold=True)
    font_sub = get_font(11, bold=False)

    text_x = av_x + av_size + 26
    name_y = 42

    # Display Name & Tag
    clean_disp = display_name[:20]
    draw.text((text_x, name_y), clean_disp, fill=(255, 255, 255, 255), font=font_name)
    tag_str = f"@{username[:22]}"
    draw.text((text_x, name_y + 32), tag_str, fill=(148, 163, 184, 255), font=font_tag)

    # Rank & Level Badges on Right side
    badge_right = w - 40
    # Level display
    lvl_str = f"LEVEL {level}"
    lvl_len = draw.textlength(lvl_str, font=font_num)
    draw.text((badge_right - lvl_len, name_y), lvl_str, fill=(255, 255, 255, 255), font=font_num)

    # Rank display
    rank_str = f"RANK #{rank}"
    rank_len = draw.textlength(rank_str, font=font_badge)
    r_pill_w = int(rank_len) + 24
    r_pill_x = int(badge_right - lvl_len - 16 - r_pill_w)
    draw.rounded_rectangle([(r_pill_x, name_y + 4), (r_pill_x + r_pill_w, name_y + 30)], radius=8, fill=(24, 30, 48, 220), outline=accent_rgb, width=1)
    draw.text((r_pill_x + 12, name_y + 8), rank_str, fill=(226, 232, 240, 255), font=font_badge)

    # XP Text (Right above progress bar)
    prog_pct = min(1.0, max(0.0, current_xp / max(1, needed_xp)))
    pct_text = f"{int(prog_pct * 100)}%"
    xp_str = f"{current_xp:,} / {needed_xp:,} XP ({pct_text})"
    xp_len = draw.textlength(xp_str, font=font_xp)
    bar_y = 175
    draw.text((w - 40 - xp_len, bar_y - 24), xp_str, fill=(255, 255, 255, 255), font=font_xp)

    total_xp_str = f"Total XP: {total_xp:,}"
    draw.text((text_x, bar_y - 24), total_xp_str, fill=(148, 163, 184, 255), font=font_xp)

    # Progress Bar (Large, Rounded, Gradient-fill with Glow)
    bar_x = text_x
    bar_w = w - 40 - bar_x
    bar_h = 18

    # Background Track
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=9, fill=(24, 30, 46, 240), outline=(50, 60, 84, 180), width=1)

    # Filled portion
    fill_w = max(18, int(bar_w * prog_pct)) if prog_pct > 0.02 else (10 if prog_pct > 0 else 0)
    if fill_w > 0:
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h)], radius=9, fill=accent_rgb)
        # Inner gloss line
        if fill_w > 20:
            draw.rounded_rectangle([(bar_x + 2, bar_y + 2), (bar_x + fill_w - 2, bar_y + 5)], radius=2, fill=(255, 255, 255, 90))

    # Bottom Branding & Footer
    draw.line([(36, h - 36), (w - 36, h - 36)], fill=(255, 255, 255, 14), width=1)
    draw.text((36, h - 26), "KYOKA PROGRESSION // LEVEL & ACTIVITY METRICS", fill=(100, 116, 139, 220), font=font_sub)
    status_str = f"TOP {max(1, rank)} IN SERVER"
    s_len = draw.textlength(status_str, font=font_sub)
    draw.text((w - 36 - s_len, h - 26), status_str, fill=(accent_secondary[0], accent_secondary[1], accent_secondary[2], 230), font=font_sub)

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out

