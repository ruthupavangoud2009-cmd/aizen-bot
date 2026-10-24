"""
Kyoka 3.0 - Feature Artwork Generator
Generates distinct, high-resolution Aizen-themed 16:9 artwork for each Kyoka category & feature.
Features deep obsidian backgrounds, glowing spiritual pressure auras, Japanese kanji,
thematic vector iconography, and cyber-violet accents.
"""

from __future__ import annotations

import math
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH = 1280
HEIGHT = 720

# Colors
OBSIDIAN_DEEP = (10, 4, 18)
OBSIDIAN_MID = (22, 9, 38)
VIOLET_DEEP = (45, 14, 76)
PURPLE_GLOW = (147, 51, 234)
PURPLE_BRIGHT = (192, 132, 252)
CYAN_ACCENT = (140, 100, 255)
SILVER_WHITE = (240, 235, 255)
SILVER_MUTED = (160, 150, 180)


def create_base_canvas(color_shift: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    """Create a dark obsidian radial-gradient canvas with spiritual pressure aura."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), OBSIDIAN_DEEP)
    draw = ImageDraw.Draw(img)

    # 1. Subtle horizontal/diagonal gradient
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(OBSIDIAN_DEEP[0] + (OBSIDIAN_MID[0] - OBSIDIAN_DEEP[0]) * ratio + color_shift[0] * 0.2)
        g = int(OBSIDIAN_DEEP[1] + (OBSIDIAN_MID[1] - OBSIDIAN_DEEP[1]) * ratio + color_shift[1] * 0.2)
        b = int(OBSIDIAN_DEEP[2] + (OBSIDIAN_MID[2] - OBSIDIAN_DEEP[2]) * ratio + color_shift[2] * 0.2)
        draw.line([(0, y), (WIDTH, y)], fill=(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), 255))

    # 2. Glowing spiritual aura circles in the background
    aura = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    aura_draw = ImageDraw.Draw(aura)
    center_x, center_y = WIDTH // 2, HEIGHT // 2

    for radius in range(350, 50, -30):
        alpha = int(12 * (1.0 - radius / 350.0))
        glow_color = (
            min(255, PURPLE_GLOW[0] + color_shift[0]),
            min(255, PURPLE_GLOW[1] + color_shift[1]),
            min(255, PURPLE_GLOW[2] + color_shift[2]),
            alpha,
        )
        aura_draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=glow_color,
        )

    # Secondary offset aura for dynamic composition
    for radius in range(260, 40, -25):
        alpha = int(18 * (1.0 - radius / 260.0))
        glow_color = (
            min(255, PURPLE_BRIGHT[0] + color_shift[0]),
            min(255, PURPLE_BRIGHT[1] + color_shift[1]),
            min(255, PURPLE_BRIGHT[2] + color_shift[2]),
            alpha,
        )
        aura_draw.ellipse(
            [WIDTH - 250 - radius, 200 - radius, WIDTH - 250 + radius, 200 + radius],
            fill=glow_color,
        )

    aura = aura.filter(ImageFilter.GaussianBlur(radius=20))
    img.alpha_composite(aura)

    # 3. Geometric grid & spiritual pressure lines
    grid_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid_layer)

    # Diagonal spiritual pressure slash lines
    for i in range(-HEIGHT, WIDTH + HEIGHT, 90):
        gdraw.line([(i, 0), (i + HEIGHT, HEIGHT)], fill=(120, 50, 200, 12), width=1)

    # Subtle horizontal cyber guides
    for y in range(80, HEIGHT, 120):
        gdraw.line([(60, y), (WIDTH - 60, y)], fill=(147, 51, 234, 18), width=1)

    img.alpha_composite(grid_layer)

    # 4. Premium border with glowing corner brackets
    border_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(border_layer)

    # Outer thin border
    margin = 30
    bdraw.rectangle(
        [margin, margin, WIDTH - margin, HEIGHT - margin],
        outline=(147, 51, 234, 80),
        width=1,
    )
    # Inner border
    bdraw.rectangle(
        [margin + 8, margin + 8, WIDTH - margin - 8, HEIGHT - margin - 8],
        outline=(192, 132, 252, 45),
        width=1,
    )

    # Corner brackets (L-shapes)
    bracket_len = 36
    bracket_color = (216, 180, 254, 220)
    for cx, cy, dx, dy in [
        (margin, margin, 1, 1),
        (WIDTH - margin, margin, -1, 1),
        (margin, HEIGHT - margin, 1, -1),
        (WIDTH - margin, HEIGHT - margin, -1, -1),
    ]:
        bdraw.line([(cx, cy), (cx + dx * bracket_len, cy)], fill=bracket_color, width=3)
        bdraw.line([(cx, cy), (cx, cy + dy * bracket_len)], fill=bracket_color, width=3)

    img.alpha_composite(border_layer)
    return img


def draw_thematic_icon(draw: ImageDraw.ImageDraw, icon_type: str, cx: int, cy: int, size: int = 140) -> None:
    """Draw a vector glyph representing the specific module or feature."""
    half = size // 2

    # Outer glow ring
    for r in range(half + 25, half, -5):
        alpha = int(40 * (1.0 - (r - half) / 25.0))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(147, 51, 234, alpha), width=2)
    draw.ellipse([cx - half, cy - half, cx + half, cy + half], outline=PURPLE_BRIGHT, width=3)

    if icon_type == "blox_fruits":
        # Mystical Devil Fruit with swirls & stem
        draw.ellipse([cx - 45, cy - 35, cx + 45, cy + 50], fill=(70, 20, 110, 200), outline=PURPLE_BRIGHT, width=3)
        # Swirl curves
        draw.arc([cx - 30, cy - 15, cx + 10, cy + 25], start=0, end=270, fill=SILVER_WHITE, width=3)
        draw.arc([cx - 10, cy - 5, cx + 30, cy + 35], start=45, end=315, fill=SILVER_WHITE, width=3)
        # T-shaped curled stem
        draw.line([(cx, cy - 35), (cx, cy - 60)], fill=PURPLE_BRIGHT, width=5)
        draw.arc([cx - 20, cy - 75, cx + 15, cy - 50], start=180, end=360, fill=SILVER_WHITE, width=4)

    elif icon_type == "moderation":
        # Katana & Shield
        # Shield outline
        shield_pts = [
            (cx, cy - 55),
            (cx + 45, cy - 35),
            (cx + 40, cy + 25),
            (cx, cy + 55),
            (cx - 40, cy + 25),
            (cx - 45, cy - 35),
        ]
        draw.polygon(shield_pts, fill=(50, 15, 80, 200), outline=PURPLE_BRIGHT)
        # Crossed Katana blade
        draw.line([(cx - 50, cy - 50), (cx + 50, cy + 50)], fill=SILVER_WHITE, width=4)
        draw.line([(cx - 55, cy - 45), (cx - 45, cy - 55)], fill=PURPLE_BRIGHT, width=6)  # Tsuba (guard)

    elif icon_type == "automod":
        # Cyber eye & security lock
        draw.ellipse([cx - 50, cy - 30, cx + 50, cy + 30], outline=PURPLE_BRIGHT, width=3)
        draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(90, 25, 140, 220), outline=SILVER_WHITE, width=3)
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=SILVER_WHITE)
        # Radar scan lines
        draw.line([(cx, cy - 45), (cx, cy + 45)], fill=(192, 132, 252, 180), width=2)
        draw.line([(cx - 60, cy), (cx + 60, cy)], fill=(192, 132, 252, 180), width=2)

    elif icon_type == "tickets":
        # Portal Door & Support Ticket Ticket stub
        draw.rectangle([cx - 40, cy - 30, cx + 40, cy + 30], fill=(50, 18, 85, 200), outline=PURPLE_BRIGHT, width=3)
        # Perforated stub line
        for y_dash in range(cy - 24, cy + 25, 10):
            draw.line([(cx + 12, y_dash), (cx + 12, y_dash + 5)], fill=SILVER_WHITE, width=2)
        # Portal arch
        draw.arc([cx - 55, cy - 55, cx + 55, cy + 55], start=180, end=360, fill=SILVER_WHITE, width=3)

    elif icon_type == "vouches":
        # 5 Stars & Laurel Trust Crest
        # Big center star
        star_r = 38
        points = []
        for i in range(10):
            r = star_r if i % 2 == 0 else star_r // 2
            angle = i * math.pi / 5 - math.pi / 2
            points.append((cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle))))
        draw.polygon(points, fill=(130, 45, 210, 220), outline=SILVER_WHITE)
        # Surrounding mini stars
        for offset in (-50, 50):
            draw.ellipse([cx + offset - 6, cy - 25, cx + offset + 6, cy - 13], fill=PURPLE_BRIGHT)

    elif icon_type == "service_bills":
        # Invoice Scroll & Blox Fruit Diamond Seal
        draw.rectangle([cx - 35, cy - 48, cx + 35, cy + 48], fill=(45, 12, 75, 220), outline=PURPLE_BRIGHT, width=3)
        # Text lines on bill
        for ly in range(cy - 28, cy + 30, 14):
            draw.line([(cx - 22, ly), (cx + 22, ly)], fill=SILVER_WHITE, width=3)
        # Currency diamond badge at bottom corner
        draw.polygon(
            [(cx + 25, cy + 30), (cx + 40, cy + 45), (cx + 25, cy + 60), (cx + 10, cy + 45)],
            fill=(147, 51, 234, 255),
            outline=SILVER_WHITE,
        )

    elif icon_type == "verification":
        # Security Badge with checkmark
        shield_pts = [
            (cx, cy - 50),
            (cx + 40, cy - 30),
            (cx + 35, cy + 25),
            (cx, cy + 50),
            (cx - 35, cy + 25),
            (cx - 40, cy - 30),
        ]
        draw.polygon(shield_pts, fill=(40, 15, 70, 220), outline=PURPLE_BRIGHT)
        # Checkmark
        draw.line([(cx - 20, cy), (cx - 5, cy + 18)], fill=SILVER_WHITE, width=5)
        draw.line([(cx - 5, cy + 18), (cx + 22, cy - 15)], fill=SILVER_WHITE, width=5)

    elif icon_type == "welcome":
        # Torii gate silhouette under crescent moon
        draw.line([(cx - 48, cy - 20), (cx + 48, cy - 20)], fill=PURPLE_BRIGHT, width=6)
        draw.line([(cx - 40, cy - 8), (cx + 40, cy - 8)], fill=SILVER_WHITE, width=3)
        draw.line([(cx - 28, cy - 8), (cx - 28, cy + 45)], fill=PURPLE_BRIGHT, width=5)
        draw.line([(cx + 28, cy - 8), (cx + 28, cy + 45)], fill=PURPLE_BRIGHT, width=5)
        # Mini crescent moon
        draw.arc([cx - 15, cy - 55, cx + 25, cy - 15], start=60, end=280, fill=SILVER_WHITE, width=4)

    elif icon_type == "reaction_roles":
        # Role badge masks / selector buttons
        draw.ellipse([cx - 40, cy - 25, cx + 40, cy + 25], outline=PURPLE_BRIGHT, width=3)
        draw.ellipse([cx - 25, cy - 10, cx - 10, cy + 5], fill=SILVER_WHITE)
        draw.ellipse([cx + 10, cy - 10, cx + 25, cy + 5], fill=SILVER_WHITE)
        draw.arc([cx - 20, cy - 5, cx + 20, cy + 18], start=20, end=160, fill=PURPLE_BRIGHT, width=3)

    elif icon_type == "giveaways":
        # Gift Box bursting with rays
        draw.rectangle([cx - 35, cy - 15, cx + 35, cy + 45], fill=(55, 18, 90, 220), outline=PURPLE_BRIGHT, width=3)
        draw.rectangle([cx - 42, cy - 30, cx + 42, cy - 15], fill=(75, 25, 120, 220), outline=SILVER_WHITE, width=3)
        # Ribbon cross
        draw.line([(cx, cy - 30), (cx, cy + 45)], fill=SILVER_WHITE, width=4)
        # Sparks/Rays
        for angle_deg in (30, 60, 90, 120, 150):
            rad = math.radians(angle_deg + 180)
            x1 = cx + int(45 * math.cos(rad))
            y1 = cy - 30 + int(45 * math.sin(rad))
            x2 = cx + int(70 * math.cos(rad))
            y2 = cy - 30 + int(70 * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=PURPLE_BRIGHT, width=2)

    elif icon_type == "leveling":
        # Trophy & XP Rank Chevron
        draw.polygon([(cx - 30, cy - 30), (cx + 30, cy - 30), (cx + 15, cy + 10), (cx - 15, cy + 10)], fill=(70, 20, 110, 220), outline=SILVER_WHITE)
        draw.line([(cx, cy + 10), (cx, cy + 30)], fill=PURPLE_BRIGHT, width=5)
        draw.line([(cx - 25, cy + 30), (cx + 25, cy + 30)], fill=PURPLE_BRIGHT, width=5)
        # XP Chevron above
        draw.line([(cx - 25, cy - 40), (cx, cy - 55)], fill=PURPLE_BRIGHT, width=4)
        draw.line([(cx, cy - 55), (cx + 25, cy - 40)], fill=PURPLE_BRIGHT, width=4)

    elif icon_type == "premium":
        # Royal Diamond & Crown
        # Diamond
        dia_pts = [(cx, cy - 45), (cx + 45, cy), (cx, cy + 45), (cx - 45, cy)]
        draw.polygon(dia_pts, fill=(80, 25, 130, 220), outline=SILVER_WHITE)
        draw.line([(cx, cy - 45), (cx, cy + 45)], fill=SILVER_WHITE, width=2)
        draw.line([(cx - 45, cy), (cx + 45, cy)], fill=SILVER_WHITE, width=2)

    elif icon_type == "owner":
        # Overlord Crown & Terminal
        crown_pts = [
            (cx - 40, cy + 25),
            (cx - 40, cy - 15),
            (cx - 20, cy),
            (cx, cy - 35),
            (cx + 20, cy),
            (cx + 40, cy - 15),
            (cx + 40, cy + 25),
        ]
        draw.polygon(crown_pts, fill=(90, 20, 120, 220), outline=SILVER_WHITE)
        draw.line([(cx - 30, cy + 38), (cx + 30, cy + 38)], fill=PURPLE_BRIGHT, width=4)

    elif icon_type == "afk":
        # Crescent Moon & Zzz
        draw.arc([cx - 40, cy - 45, cx + 30, cy + 35], start=60, end=290, fill=SILVER_WHITE, width=5)
        draw.line([(cx + 10, cy - 35), (cx + 25, cy - 35)], fill=PURPLE_BRIGHT, width=3)
        draw.line([(cx + 25, cy - 35), (cx + 10, cy - 20)], fill=PURPLE_BRIGHT, width=3)
        draw.line([(cx + 10, cy - 20), (cx + 25, cy - 20)], fill=PURPLE_BRIGHT, width=3)

    elif icon_type == "config":
        # Master Cog Gear
        draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=PURPLE_BRIGHT, width=4)
        draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=SILVER_WHITE)
        for i in range(8):
            rad = i * math.pi / 4
            x1 = cx + int(38 * math.cos(rad))
            y1 = cy + int(38 * math.sin(rad))
            x2 = cx + int(52 * math.cos(rad))
            y2 = cy + int(52 * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=PURPLE_BRIGHT, width=6)

    else:
        # Default General / Star Compass
        draw.ellipse([cx - 45, cy - 45, cx + 45, cy + 45], outline=PURPLE_BRIGHT, width=3)
        draw.line([(cx, cy - 55), (cx, cy + 55)], fill=SILVER_WHITE, width=4)
        draw.line([(cx - 55, cy), (cx + 55, cy)], fill=SILVER_WHITE, width=4)


def render_feature_card(
    category_id: str,
    title: str,
    subtitle: str,
    icon_type: str,
    output_path: str,
    color_shift: tuple[int, int, int] = (0, 0, 0),
) -> None:
    """Render a complete, professional, distinct 16:9 banner card."""
    base = create_base_canvas(color_shift)
    draw = ImageDraw.Draw(base)

    # 1. Subtle Kyoka Suigetsu kanji watermark in upper right
    # (Drawn with geometry lines)
    kanji_x, kanji_y = WIDTH - 180, 80
    # "京" and "華" stylized glyph lines
    draw.line([(kanji_x - 30, kanji_y), (kanji_x + 30, kanji_y)], fill=(147, 51, 234, 40), width=3)
    draw.line([(kanji_x, kanji_y), (kanji_x, kanji_y + 40)], fill=(147, 51, 234, 40), width=3)
    draw.line([(kanji_x - 20, kanji_y + 40), (kanji_x + 20, kanji_y + 40)], fill=(147, 51, 234, 40), width=3)

    # 2. Draw thematic feature vector icon on the right side
    icon_cx, icon_cy = WIDTH - 260, HEIGHT // 2
    draw_thematic_icon(draw, icon_type, icon_cx, icon_cy, size=180)

    # 3. Typography & branding on the left
    # Load default or fallback font
    try:
        font_brand = ImageFont.truetype("arialbd.ttf", 26)
        font_title = ImageFont.truetype("arialbd.ttf", 52)
        font_sub = ImageFont.truetype("arial.ttf", 22)
        font_tag = ImageFont.truetype("arialbd.ttf", 16)
    except Exception:
        font_brand = font_title = font_sub = font_tag = ImageFont.load_default()

    start_x = 90
    start_y = 190

    # Brand badge: "KYOKA 3.0 • AIZEN EDITION"
    draw.rectangle([start_x, start_y, start_x + 260, start_y + 36], fill=(45, 14, 76, 180), outline=PURPLE_BRIGHT, width=1)
    draw.text((start_x + 14, start_y + 8), "KYOKA 3.0 • AIZEN ARCHITECTURE", fill=PURPLE_BRIGHT, font=font_tag)

    # Main Title
    draw.text((start_x, start_y + 55), title.upper(), fill=SILVER_WHITE, font=font_title)

    # Glowing underline under title
    title_width = 520
    draw.line([(start_x, start_y + 125), (start_x + title_width, start_y + 125)], fill=PURPLE_BRIGHT, width=3)
    draw.line([(start_x, start_y + 128), (start_x + title_width // 2, start_y + 128)], fill=CYAN_ACCENT, width=2)

    # Subtitle
    draw.text((start_x, start_y + 145), subtitle, fill=SILVER_MUTED, font=font_sub)

    # Command tip pills at bottom
    tip_y = start_y + 240
    pills = [
        ("PREFIX", "+"),
        ("DISCORD", "Slash [/] & Hybrid"),
        ("SYSTEM", "Modular Engine"),
    ]
    cur_x = start_x
    for label, val in pills:
        text_str = f"{label}: {val}"
        draw.rectangle([cur_x, tip_y, cur_x + 160, tip_y + 34], fill=(20, 8, 35, 200), outline=(147, 51, 234, 100), width=1)
        draw.text((cur_x + 12, tip_y + 8), text_str, fill=SILVER_WHITE, font=font_tag)
        cur_x += 175

    # Footer note
    draw.text((start_x, HEIGHT - 65), "Kyoka Suigetsu • Unrivaled Discord Bot Framework", fill=(120, 110, 140, 200), font=font_tag)

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    base.save(output_path, "PNG")
    print(f"Generated: {output_path}")


def main() -> None:
    categories = [
        # (id, title, subtitle, icon_type, relative_path, color_shift)
        ("general", "General & Utility", "Essential tools, calculators, reminders & server diagnostics", "general", "assets/kyoka/help/help_general.png", (0, 0, 0)),
        ("moderation", "Moderation System", "High-precision warnings, kicks, bans, locks & audit cases", "moderation", "assets/kyoka/help/help_moderation.png", (20, -10, 10)),
        ("automod", "Automod & Security", "Anti-spam, anti-raid, invite defense & server lockdown", "automod", "assets/kyoka/help/help_automod.png", (-10, 10, 20)),
        ("welcome", "Welcome & Goodbye", "Dynamic welcoming cards, farewell logs & autorole gateways", "welcome", "assets/kyoka/help/help_welcome.png", (15, 5, 25)),
        ("verification", "Verification Gateway", "Gatekeeper role isolation, challenge codes & button verifies", "verification", "assets/kyoka/help/help_verification.png", (5, -5, 30)),
        ("tickets", "Tickets & Support", "Enterprise support panels, staff claims & HTML transcripts", "tickets", "assets/kyoka/help/help_tickets.png", (10, 15, 35)),
        ("reaction_roles", "Reaction Roles", "Self-service menus, custom interactive panels & role bounds", "reaction_roles", "assets/kyoka/help/help_reaction_roles.png", (-5, 10, 15)),
        ("giveaways", "Giveaways & Events", "Fair randomizer, requirements validation & rerolls", "giveaways", "assets/kyoka/help/help_giveaways.png", (25, 20, 5)),
        ("afk", "AFK System", "Smart AFK status notices, mention alerts & auto-return logs", "afk", "assets/kyoka/help/help_afk.png", (-15, -10, 20)),
        ("vouches", "Vouches & Reputation", "Blox Fruits trust scores, verified transaction feedback & leaderboards", "vouches", "assets/kyoka/help/help_vouches.png", (30, 10, 40)),
        ("service_bills", "Blox Fruits Service Bills", "Itemized service invoices, proof uploads, fruits & Robux tracking", "service_bills", "assets/kyoka/help/help_service_bills.png", (20, 0, 30)),
        ("blox_fruits", "Blox Fruits AI & Guide", "Awakened fruit values, trade calculation, builds & notifier", "blox_fruits", "assets/kyoka/help/help_blox_fruits.png", (25, 5, 45)),
        ("leveling", "Leveling & Leaderboards", "XP progression curves, custom rank cards & server activity", "leveling", "assets/kyoka/help/help_leveling.png", (10, 20, 15)),
        ("premium", "Premium & Prime", "Tier licenses, neural voice allocation & unmetered AI access", "premium", "assets/kyoka/help/help_premium.png", (35, 15, 50)),
        ("config", "Server Configuration", "Custom prefixes, logging hubs, module toggles & system setup", "config", "assets/kyoka/help/help_config.png", (0, 15, 25)),
        ("owner", "Owner & Developer", "Core engine diagnostics, extension manager & system runtime", "owner", "assets/kyoka/help/help_owner.png", (40, 0, 20)),
    ]

    for cat_id, title, subtitle, icon, rel_path, shift in categories:
        render_feature_card(cat_id, title, subtitle, icon, rel_path, color_shift=shift)

    # Feature banners
    feature_banners = [
        ("welcome_banner", "Welcome Gateway", "Welcome to the server", "welcome", "assets/kyoka/features/welcome_banner.png"),
        ("goodbye_banner", "Departure Notice", "Member departure logged", "welcome", "assets/kyoka/features/goodbye_banner.png"),
        ("blox_fruits_ai", "Blox Fruits AI Engine", "Fruit valuations, trading & builds", "blox_fruits", "assets/kyoka/features/blox_fruits_ai.png"),
        ("ticket_panel", "Support Ticket Console", "Click below to create a private ticket", "tickets", "assets/kyoka/features/ticket_panel.png"),
        ("vouch_card_background", "Reputation & Trust Card", "Verified community transactions", "vouches", "assets/kyoka/features/vouch_card_background.png"),
        ("service_bill_background", "Service Invoice Console", "Official Blox Fruits service receipt", "service_bills", "assets/kyoka/features/service_bill_background.png"),
        ("verification_banner", "Verification Gatekeeper", "Verify your account to access channels", "verification", "assets/kyoka/features/verification_banner.png"),
        ("reaction_roles_banner", "Self Roles Station", "Select your roles with buttons below", "reaction_roles", "assets/kyoka/features/reaction_roles_banner.png"),
        ("giveaway_banner", "Community Giveaway", "Participate for exclusive rewards", "giveaways", "assets/kyoka/features/giveaway_banner.png"),
        ("rank_card_background", "Server Rank & Activity", "Level progression & leaderboard", "leveling", "assets/kyoka/features/rank_card_background.png"),
        ("announcement_banner", "Official Announcement", "Important server notice", "config", "assets/kyoka/features/announcement_banner.png"),
        ("afk_banner", "AFK Notice", "Member is currently away", "afk", "assets/kyoka/features/afk_banner.png"),
        ("moderation_banner", "Moderation Action", "Security protocol executed", "moderation", "assets/kyoka/features/moderation_banner.png"),
        ("premium_banner", "Kyoka Prime Portal", "Unlock exclusive features & benefits", "premium", "assets/kyoka/features/premium_banner.png"),
    ]

    for fid, title, subtitle, icon, rel_path in feature_banners:
        render_feature_card(fid, title, subtitle, icon, rel_path, color_shift=(15, 10, 25))

    print("All feature and help artworks successfully generated!")


if __name__ == "__main__":
    main()
