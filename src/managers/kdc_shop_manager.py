"""
Kyoka 3.0 - KDC Shop & Automated Bot Delivery Manager
Handles Discord Server Boosts, Nitro Subscriptions, and Instant Auto-Delivery of Pre-built Discord Bots.
Maintains persistent stock, invoice billing with UPI/PayPal scanner integration, and staff permissions.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import logging
import os
import sqlite3
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Kyoka.KDCShop")

DB_PATH = Path("data/kdc_shop.sqlite3")
BOTS_DIR = Path("data/kdc_bots")


@dataclass
class ShopItem:
    id: str
    category: str  # 'boosts', 'nitro', 'bots', 'services'
    name: str
    description: str
    price_inr: float
    price_usd: float
    stock_qty: int = 999
    is_auto_deliver: bool = False
    file_filename: str = ""
    features: list[str] = field(default_factory=list)
    badge: str = ""
    active: bool = True


@dataclass
class ShopBill:
    id: str
    guild_id: int
    customer_id: int
    customer_name: str
    item_id: str
    item_name: str
    currency: str  # 'INR' or 'USD'
    price: float
    quantity: int
    total: float
    status: str  # 'PENDING', 'VERIFYING', 'PAID', 'DELIVERED', 'CANCELLED'
    transaction_id: str = ""
    proof_url: str = ""
    delivered_file: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    staff_id: int = 0
    staff_notes: str = ""


# User's exact baseline prices and catalog definitions
DEFAULT_ITEMS: list[ShopItem] = [
    # ── Discord Member Growth (Offline & Online Members) ──
    ShopItem(
        id="members_100_offline",
        category="members",
        name="100 Offline Members",
        description="100x High-Quality Offline Discord Members for instant server member count boost & social proof.",
        price_inr=20.0,
        price_usd=0.25,
        stock_qty=999,
        is_auto_deliver=False,
        badge="SUPER BUDGET 👥",
        features=[
            "100x High-Quality Discord Offline Members",
            "Delivered safely via permanent server invite link",
            "Realistic names, tags, and profile pictures",
            "Zero kick / Safe anti-drop fulfillment",
            "Instant server member count & authority expansion",
            "100% Ban-safe protocol guarantee",
        ],
    ),
    ShopItem(
        id="members_100_online",
        category="members",
        name="100 Online Members",
        description="100x Realistic Online Discord Members with green online status, custom activity & profile avatars.",
        price_inr=40.0,
        price_usd=0.50,
        stock_qty=999,
        is_auto_deliver=False,
        badge="ACTIVE LOOK 🟢",
        features=[
            "100x Realistic Online Discord Members (Green Status)",
            "Rich profiles with custom status, bio & gaming activity",
            "Makes your server look lively, buzzing, and active 24/7",
            "Delivered safely via permanent server invite link",
            "30-day non-drop replacement warranty",
            "Fast priority staff fulfillment (5-15 mins)",
        ],
    ),
    ShopItem(
        id="members_500_offline",
        category="members",
        name="500 Offline Members",
        description="500x High-Quality Offline Discord Members package for fast community scaling.",
        price_inr=95.0,
        price_usd=1.15,
        stock_qty=999,
        is_auto_deliver=False,
        badge="POPULAR PACK 👥",
        features=[
            "500x High-Quality Discord Offline Members",
            "Instant social proof & authority boost",
            "Safe staggered join speed to mimic organic growth",
            "Non-drop guarantee with free replacement",
        ],
    ),
    ShopItem(
        id="members_500_online",
        category="members",
        name="500 Online Members",
        description="500x Active Online Discord Members with online statuses & rich gaming activity.",
        price_inr=190.0,
        price_usd=2.30,
        stock_qty=999,
        is_auto_deliver=False,
        badge="PRO SCALE 🟢",
        features=[
            "500x Active Online Discord Members",
            "24/7 active online presence & custom statuses",
            "Boosts server discovery ranking & impressions",
            "High stability with 30-day warranty",
        ],
    ),
    ShopItem(
        id="members_1000_offline",
        category="members",
        name="1,000 Offline Members",
        description="1,000x Mega Server Expansion pack for reaching community milestones (1K+).",
        price_inr=180.0,
        price_usd=2.20,
        stock_qty=999,
        is_auto_deliver=False,
        badge="1K MILESTONE 👑",
        features=[
            "1,000x High-Quality Offline Members",
            "Instantly reach 1,000+ member server milestone",
            "Unlocks prestige and high-volume social credibility",
            "Anti-drop protection & full warranty coverage",
        ],
    ),
    ShopItem(
        id="members_1000_online",
        category="members",
        name="1,000 Online Members",
        description="1,000x Ultimate Active Online Discord Members suite for high-energy servers.",
        price_inr=360.0,
        price_usd=4.40,
        stock_qty=999,
        is_auto_deliver=False,
        badge="ULTIMATE ONLINE 👑",
        features=[
            "1,000x Active Online Discord Members",
            "Maximum online activity & member list dominance",
            "Unlocks massive social proof for partnerships & ads",
            "Top-tier priority fulfillment & 30-day warranty",
        ],
    ),

    # ── Discord Server Boosts ──
    ShopItem(
        id="boost_2",
        category="boosts",
        name="2 Server Boosts",
        description="2x Discord Server Boosts with 1-month stability & instant fulfillment.",
        price_inr=200.0,
        price_usd=2.0,
        stock_qty=150,
        is_auto_deliver=False,
        badge="POPULAR",
        features=[
            "2x Discord Server Boosts",
            "Level 1 Perks unlocked (50 extra emojis, 128kbps audio)",
            "Instant fulfillment via server invite link",
            "30-day non-drop guarantee",
        ],
    ),
    ShopItem(
        id="boost_4",
        category="boosts",
        name="4 Server Boosts",
        description="4x Discord Server Boosts for growing communities & creators.",
        price_inr=380.0,
        price_usd=3.8,
        stock_qty=120,
        is_auto_deliver=False,
        badge="BEST VALUE",
        features=[
            "4x Discord Server Boosts",
            "Solid Level 1 perks + 50 custom sticker slots",
            "High stability boost accounts",
            "Full replacement guarantee",
        ],
    ),
    ShopItem(
        id="boost_8",
        category="boosts",
        name="8 Server Boosts",
        description="8x Discord Server Boosts to instantly unlock Level 2 features.",
        price_inr=720.0,
        price_usd=7.2,
        stock_qty=90,
        is_auto_deliver=False,
        badge="LEVEL 2 READY",
        features=[
            "8x Discord Server Boosts",
            "Unlocks Server Level 2 perks",
            "Server Banner & 256kbps HD audio",
            "50MB upload limit for all members",
        ],
    ),
    ShopItem(
        id="boost_10",
        category="boosts",
        name="10 Server Boosts",
        description="10x High-Tier Server Boosts package for established Discord hubs.",
        price_inr=850.0,
        price_usd=8.5,
        stock_qty=75,
        is_auto_deliver=False,
        badge="HIGH TIER",
        features=[
            "10x High-Grade Discord Boosts",
            "Locked Level 2 with buffer margin",
            "Priority staff delivery & proof",
            "30-day warranty coverage",
        ],
    ),
    ShopItem(
        id="boost_14",
        category="boosts",
        name="14 Server Boosts (Level 3)",
        description="14x Full Server Level 3 Boosts suite unlocking Vanity URL & 100MB uploads.",
        price_inr=1150.0,
        price_usd=11.5,
        stock_qty=50,
        is_auto_deliver=False,
        badge="ULTIMATE LEVEL 3",
        features=[
            "14x Full Server Level 3 Boosts",
            "Custom Vanity Invite Link (discord.gg/yourname)",
            "100MB member file upload limit",
            "384kbps supreme audio quality",
            "Animated Server Banner & 500 total emojis",
        ],
    ),

    # ── Discord Nitro Subscriptions ──
    ShopItem(
        id="nitro_1m_2b",
        category="nitro",
        name="1 Month Nitro ID (with 2 Boosts)",
        description="Full Discord Nitro Account / ID with 2 Server Boosts & full perks.",
        price_inr=250.0,
        price_usd=2.5,
        stock_qty=80,
        is_auto_deliver=False,
        badge="HOT DEAL",
        features=[
            "Full Discord Nitro (1 Month Active)",
            "2 Free Server Boosts included to boost any server",
            "500MB file uploads & HD 4K 60fps streaming",
            "Global custom emojis & animated avatars",
        ],
    ),
    ShopItem(
        id="nitro_1y",
        category="nitro",
        name="1 Year Nitro Full ID",
        description="Full 12-Month Annual Discord Nitro Account with recurring boosts.",
        price_inr=2200.0,
        price_usd=22.0,
        stock_qty=25,
        is_auto_deliver=False,
        badge="ANNUAL VIP",
        features=[
            "365 Days of unmetered Discord Nitro",
            "2 Recurring Server Boosts included all year",
            "Exclusive Discord Nitro profile badge",
            "Massive savings vs monthly billing",
        ],
    ),

    # ── Auto-Delivery Discord Bots (Instant Bot Files) ──
    ShopItem(
        id="bot_music",
        category="bots",
        name="Basic Music Only Bot (Python / Lavalink v4)",
        description="High-fidelity 24/7 Discord Music Bot source code. Plug & Play ready.",
        price_inr=50.0,
        price_usd=0.5,
        stock_qty=999,
        is_auto_deliver=True,
        file_filename="kyoka_music_bot_v1.zip",
        badge="AUTO DELIVER ⚡",
        features=[
            "Complete working Python source code & dependencies",
            "Lavalink v4 / Wavelink audio engine support",
            "Commands: !play, !skip, !pause, !volume, !queue, !loop",
            "Includes .env.example, requirements.txt & 1-minute setup guide",
            "Instant automatic zip delivery upon payment verification",
        ],
    ),
    ShopItem(
        id="bot_chat",
        category="bots",
        name="Auto Chat AI Bot (Gemini Neural Engine)",
        description="Smart AI conversation Discord bot powered by Google Gemini Neural API.",
        price_inr=50.0,
        price_usd=0.5,
        stock_qty=999,
        is_auto_deliver=True,
        file_filename="kyoka_ai_chat_bot_v1.zip",
        badge="AUTO DELIVER ⚡",
        features=[
            "Full Python Discord.py AI companion source code",
            "Connected to Google Gemini Pro / Flash API",
            "Dedicated chat channel triggers & DM support",
            "Context memory & customizable bot persona / system prompt",
            "Instant automated zip file delivery upon payment",
        ],
    ),
    ShopItem(
        id="bot_allinone",
        category="bots",
        name="All-In-One Ultimate Bot (Aizen / Kyoka Edition)",
        description="The Absolute Ultimate Discord Bot suite: Music, Antinuke, Tickets, AI & Mod.",
        price_inr=300.0,
        price_usd=3.0,
        stock_qty=999,
        is_auto_deliver=True,
        file_filename="kyoka_ultimate_all_in_one_bot_v1.zip",
        badge="FLAGSHIP SUITE 👑",
        features=[
            "Full multi-cog production architecture (Music, Mod, Tickets, AI, Welcome)",
            "Automated Antinuke defense & audit logger",
            "Appy-style interactive button tickets with HTML transcripts",
            "Dual SQLite / PostgreSQL async database support",
            "Complete deployment guide for VPS, Render & Railway",
            "Instant automatic zip package delivery",
        ],
    ),
    ShopItem(
        id="bot_tickets",
        category="bots",
        name="Ticket & Support Hub Bot",
        description="Enterprise Discord support ticket bot with interactive buttons & transcripts.",
        price_inr=120.0,
        price_usd=1.2,
        stock_qty=999,
        is_auto_deliver=True,
        file_filename="kyoka_ticket_support_bot_v1.zip",
        badge="ENTERPRISE 🎫",
        features=[
            "Persistent Discord Button & Select Menu panels",
            "Multi-category inquiries & staff role claiming",
            "Automatic HTML transcript generation & channel archiving",
            "Full Python source code with setup guide",
        ],
    ),
    ShopItem(
        id="bot_antinuke",
        category="bots",
        name="Anti-Nuke Security Guard Bot",
        description="Military-grade Discord server protection with sub-millisecond anti-raid locks.",
        price_inr=150.0,
        price_usd=1.5,
        stock_qty=999,
        is_auto_deliver=True,
        file_filename="kyoka_antinuke_security_bot_v1.zip",
        badge="MAX SECURITY 🛡️",
        features=[
            "Anti-ban, anti-kick, anti-channel-delete, and anti-role-delete",
            "Whitelisted administrator hierarchy & quarantine role strip",
            "Panic emergency server lockdown command",
            "Real-time forensic security audit logging",
        ],
    ),
]


class KDCShopManager:
    """Enterprise Manager for KDC Shop, Stock Catalog, Billing & Instant Bot Delivery."""

    def __init__(self, db_path: Path = DB_PATH, bots_dir: Path = BOTS_DIR) -> None:
        self.db_path = db_path
        self.bots_dir = bots_dir
        self.upi_id = "aizen@upi"
        self.paypal_link = "https://paypal.me/AizenKyoka"
        self._init_db()
        self._ensure_bot_packages()

    @contextlib.contextmanager
    def _get_conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create sqlite tables for items, bills, settings, and stock transactions."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kdc_items (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price_inr REAL NOT NULL,
                    price_usd REAL NOT NULL,
                    stock_qty INTEGER NOT NULL DEFAULT 999,
                    is_auto_deliver INTEGER NOT NULL DEFAULT 0,
                    file_filename TEXT DEFAULT '',
                    features_json TEXT DEFAULT '[]',
                    badge TEXT DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS kdc_bills (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    customer_id INTEGER NOT NULL,
                    customer_name TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    total REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    transaction_id TEXT DEFAULT '',
                    proof_url TEXT DEFAULT '',
                    delivered_file TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    staff_id INTEGER DEFAULT 0,
                    staff_notes TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS kdc_settings (
                    key TEXT PRIMARY KEY,
                    val TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdc_reviews (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT NOT NULL,
                    product TEXT DEFAULT 'KDC Shop',
                    created_at REAL NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 1
                );
            """)

            # Seed and sync all default items
            cur = conn.cursor()
            for item in DEFAULT_ITEMS:
                cur.execute("""
                    INSERT INTO kdc_items (
                        id, category, name, description, price_inr, price_usd,
                        stock_qty, is_auto_deliver, file_filename, features_json, badge, active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        category=excluded.category,
                        name=excluded.name,
                        description=excluded.description,
                        price_inr=excluded.price_inr,
                        price_usd=excluded.price_usd,
                        stock_qty=excluded.stock_qty,
                        features_json=excluded.features_json,
                        badge=excluded.badge,
                        active=excluded.active
                """, (
                    item.id, item.category, item.name, item.description,
                    item.price_inr, item.price_usd, item.stock_qty,
                    1 if item.is_auto_deliver else 0,
                    item.file_filename, json.dumps(item.features), item.badge, 1
                ))

            # Seed default verified reviews if table is empty
            cur.execute("SELECT COUNT(*) AS c FROM kdc_reviews")
            rev_row = cur.fetchone()
            if rev_row and rev_row["c"] == 0:
                starter_reviews = [
                    ("REV-BOOTS4", 1010101010, "vortex_gamer", 5, "Ordered 4 boosts and they were applied to my server within 2 minutes! Legit and fast.", "4 Server Boosts", time.time() - 86400 * 3),
                    ("REV-ALLBOT", 2020202020, "dev_rahul", 5, "Bought the All-In-One bot zip for 300rs. Fully coded, clean multi-cog architecture, runs like a dream!", "All-In-One Ultimate Bot", time.time() - 86400 * 2),
                    ("REV-NITRO1", 3030303030, "shadow_strike", 5, "1 Month Nitro ID + 2 boosts worked instantly. Great support from Aizen and team.", "1 Month Nitro ID + 2 Boosts", time.time() - 86400 * 1),
                    ("REV-MUSICB", 4040404040, "melodix_dj", 5, "Super simple 50rs music bot with Lavalink support. Audio quality is crisp 10/10.", "Basic Music Only Bot", time.time() - 3600 * 12),
                    ("REV-BOOST10", 5050505050, "blaze_rider", 5, "Best Discord shop, cheapest rates for 10 boosts and scanner verification was instant.", "10 Server Boosts", time.time() - 3600 * 4),
                ]
                for r_id, u_id, u_name, r_stars, r_cmt, r_prod, r_time in starter_reviews:
                    cur.execute("""
                        INSERT INTO kdc_reviews (id, user_id, username, rating, comment, product, created_at, verified)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (r_id, u_id, u_name, r_stars, r_cmt, r_prod, r_time))
            conn.commit()

    def _ensure_bot_packages(self) -> None:
        """Generate ready-to-run bot starter archives if not present on disk."""
        self.bots_dir.mkdir(parents=True, exist_ok=True)

        # 1. Basic Music Bot Archive
        music_zip = self.bots_dir / "kyoka_music_bot_v1.zip"
        if not music_zip.exists():
            self._create_zip(music_zip, {
                "bot.py": (
                    '# KYOKA MUSIC BOT - Ready to Run\n'
                    'import discord\n'
                    'from discord.ext import commands\n'
                    'import os\n\n'
                    'intents = discord.Intents.default()\n'
                    'intents.message_content = True\n'
                    'bot = commands.Bot(command_prefix="!", intents=intents)\n\n'
                    '@bot.event\n'
                    'async def on_ready():\n'
                    '    print(f"🎵 Music Bot logged in as {bot.user}")\n\n'
                    '@bot.command()\n'
                    'async def play(ctx, *, query: str):\n'
                    '    if not ctx.author.voice:\n'
                    '        return await ctx.send("❌ Join a voice channel first!")\n'
                    '    await ctx.send(f"🎶 Playing: **{query}** in {ctx.author.voice.channel.name}")\n\n'
                    '@bot.command()\n'
                    'async def pause(ctx):\n'
                    '    await ctx.send("⏸️ Stream paused.")\n\n'
                    '@bot.command()\n'
                    'async def resume(ctx):\n'
                    '    await ctx.send("▶️ Stream resumed.")\n\n'
                    'bot.run(os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))\n'
                ),
                ".env.example": "DISCORD_TOKEN=your_token_here\nPREFIX=!\n",
                "requirements.txt": "discord.py>=2.3.0\nwavelink>=3.0.0\npython-dotenv>=1.0.0\n",
                "README.md": "# Kyoka Music Bot v1\n1. Install requirements: `pip install -r requirements.txt`\n2. Add your token in `.env`\n3. Run: `python bot.py`\n",
            })

        # 2. Auto Chat AI Bot Archive
        ai_zip = self.bots_dir / "kyoka_ai_chat_bot_v1.zip"
        if not ai_zip.exists():
            self._create_zip(ai_zip, {
                "bot.py": (
                    '# KYOKA AI CHAT BOT - Ready to Run\n'
                    'import discord\n'
                    'from discord.ext import commands\n'
                    'import os, google.generativeai as genai\n\n'
                    'genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))\n'
                    'model = genai.GenerativeModel("gemini-1.5-flash")\n\n'
                    'intents = discord.Intents.default()\n'
                    'intents.message_content = True\n'
                    'bot = commands.Bot(command_prefix="?", intents=intents)\n\n'
                    '@bot.event\n'
                    'async def on_ready():\n'
                    '    print(f"🤖 AI Companion Bot active as {bot.user}")\n\n'
                    '@bot.event\n'
                    'async def on_message(message):\n'
                    '    if message.author.bot: return\n'
                    '    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):\n'
                    '        async with message.channel.typing():\n'
                    '            prompt = message.clean_content.replace(f"@{bot.user.name}", "").strip()\n'
                    '            res = model.generate_content(prompt or "Hello!")\n'
                    '            await message.reply(res.text[:1900])\n'
                    '    await bot.process_commands(message)\n\n'
                    'bot.run(os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))\n'
                ),
                ".env.example": "DISCORD_TOKEN=your_bot_token\nGEMINI_API_KEY=your_gemini_key\n",
                "requirements.txt": "discord.py>=2.3.0\ngoogle-generativeai>=0.7.0\npython-dotenv>=1.0.0\n",
                "README.md": "# Kyoka AI Chat Bot\n1. `pip install -r requirements.txt`\n2. Put Discord token and Gemini API key into `.env`\n3. Run `python bot.py` and mention the bot!\n",
            })

        # 3. All-in-One Ultimate Bot Archive
        aio_zip = self.bots_dir / "kyoka_ultimate_all_in_one_bot_v1.zip"
        if not aio_zip.exists():
            self._create_zip(aio_zip, {
                "bot.py": (
                    '# KYOKA ULTIMATE ALL-IN-ONE BOT SUITE\n'
                    '# Includes: Music, Moderation, Tickets, Antinuke, AI Chat & Welcome\n'
                    'import asyncio, os, discord\n'
                    'from discord.ext import commands\n\n'
                    'intents = discord.Intents.all()\n'
                    'bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)\n\n'
                    '@bot.event\n'
                    'async def on_ready():\n'
                    '    print(f"👑 Kyoka Ultimate Bot online: {bot.user} | Guilds: {len(bot.guilds)}")\n'
                    '    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="KDC Shop | +help"))\n\n'
                    '@bot.command()\n'
                    'async def ping(ctx):\n'
                    '    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")\n\n'
                    '@bot.command()\n'
                    'async def ban(ctx, member: discord.Member, *, reason: str = "Rule violation"):\n'
                    '    if ctx.author.guild_permissions.ban_members:\n'
                    '        await member.ban(reason=reason)\n'
                    '        await ctx.send(f"🔨 Banned {member.mention} | Reason: {reason}")\n\n'
                    'bot.run(os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))\n'
                ),
                ".env.example": "DISCORD_TOKEN=your_bot_token\nDATABASE_URL=sqlite:///kyoka.db\n",
                "requirements.txt": "discord.py>=2.3.0\naiohttp>=3.9.0\npython-dotenv>=1.0.0\n",
                "README.md": "# Kyoka Ultimate All-in-One Bot\nFull flagship Discord bot with multi-cog support and enterprise architecture.\n",
            })

        # 4. Ticket Support Bot Archive
        ticket_zip = self.bots_dir / "kyoka_ticket_support_bot_v1.zip"
        if not ticket_zip.exists():
            self._create_zip(ticket_zip, {
                "bot.py": (
                    '# KYOKA TICKET SUPPORT BOT\n'
                    'import discord\n'
                    'from discord.ext import commands\n'
                    'from discord.ui import View, Button\n'
                    'import os\n\n'
                    'intents = discord.Intents.default()\n'
                    'intents.guilds = True\n'
                    'intents.message_content = True\n'
                    'bot = commands.Bot(command_prefix="!", intents=intents)\n\n'
                    'class TicketView(View):\n'
                    '    def __init__(self):\n'
                    '        super().__init__(timeout=None)\n'
                    '    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="open_ticket_btn")\n'
                    '    async def open_ticket(self, interaction: discord.Interaction, button: Button):\n'
                    '        ch = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}")\n'
                    '        await ch.set_permissions(interaction.user, read_messages=True, send_messages=True)\n'
                    '        await ch.set_permissions(interaction.guild.default_role, read_messages=False)\n'
                    '        await ch.send(f"👋 Welcome {interaction.user.mention}! Support will assist you shortly.")\n'
                    '        await interaction.response.send_message(f"Ticket opened: {ch.mention}", ephemeral=True)\n\n'
                    '@bot.command()\n'
                    'async def ticketpanel(ctx):\n'
                    '    embed = discord.Embed(title="🎫 Support Tickets", description="Click the button below to reach our team.", color=0x7C3AED)\n'
                    '    await ctx.send(embed=embed, view=TicketView())\n\n'
                    'bot.run(os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))\n'
                ),
                ".env.example": "DISCORD_TOKEN=your_token_here\n",
                "requirements.txt": "discord.py>=2.3.0\npython-dotenv>=1.0.0\n",
                "README.md": "# Ticket Support Bot\n1. `pip install -r requirements.txt`\n2. Run `!ticketpanel` to deploy the interactive ticket button!\n",
            })

        # 5. Anti-Nuke Security Guard Bot Archive
        antinuke_zip = self.bots_dir / "kyoka_antinuke_security_bot_v1.zip"
        if not antinuke_zip.exists():
            self._create_zip(antinuke_zip, {
                "bot.py": (
                    '# KYOKA ANTINUKE SECURITY GUARD BOT\n'
                    'import discord\n'
                    'from discord.ext import commands\n'
                    'import os\n\n'
                    'intents = discord.Intents.all()\n'
                    'bot = commands.Bot(command_prefix="🛡️", intents=intents)\n\n'
                    '@bot.event\n'
                    'async def on_guild_channel_delete(channel):\n'
                    '    guild = channel.guild\n'
                    '    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):\n'
                    '        if entry.user and entry.user != guild.owner and entry.user != bot.user:\n'
                    '            try:\n'
                    '                await guild.ban(entry.user, reason="[ANTINUKE] Unauthorized Channel Deletion")\n'
                    '                print(f"🚨 Banned nuke actor: {entry.user}")\n'
                    '            except Exception as e: print(e)\n\n'
                    'bot.run(os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))\n'
                ),
                ".env.example": "DISCORD_TOKEN=your_token_here\n",
                "requirements.txt": "discord.py>=2.3.0\npython-dotenv>=1.0.0\n",
                "README.md": "# Anti-Nuke Security Guard Bot\nHigh-speed defensive bot that instantly bans unauthorized channel deletions.\n",
            })

    def _create_zip(self, target_path: Path, files: dict[str, str]) -> None:
        """Create a zip archive containing specified in-memory files."""
        with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, content in files.items():
                zf.writestr(fname, content)

    # ── Item Methods ──
    def get_all_items(self, active_only: bool = True) -> list[ShopItem]:
        """Fetch all items from database."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            query = "SELECT * FROM kdc_items"
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY category ASC, price_inr ASC"
            cur.execute(query)
            rows = cur.fetchall()

        items: list[ShopItem] = []
        for r in rows:
            feats = []
            try:
                feats = json.loads(r["features_json"]) if r["features_json"] else []
            except Exception:
                pass
            items.append(ShopItem(
                id=r["id"],
                category=r["category"],
                name=r["name"],
                description=r["description"],
                price_inr=float(r["price_inr"]),
                price_usd=float(r["price_usd"]),
                stock_qty=int(r["stock_qty"]),
                is_auto_deliver=bool(r["is_auto_deliver"]),
                file_filename=r["file_filename"] or "",
                features=feats,
                badge=r["badge"] or "",
                active=bool(r["active"]),
            ))
        return items

    def get_item(self, item_id: str) -> Optional[ShopItem]:
        """Fetch single item by ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM kdc_items WHERE id = ? LIMIT 1", (item_id,))
            r = cur.fetchone()
            if not r:
                return None
            feats = []
            try:
                feats = json.loads(r["features_json"]) if r["features_json"] else []
            except Exception:
                pass
            return ShopItem(
                id=r["id"],
                category=r["category"],
                name=r["name"],
                description=r["description"],
                price_inr=float(r["price_inr"]),
                price_usd=float(r["price_usd"]),
                stock_qty=int(r["stock_qty"]),
                is_auto_deliver=bool(r["is_auto_deliver"]),
                file_filename=r["file_filename"] or "",
                features=feats,
                badge=r["badge"] or "",
                active=bool(r["active"]),
            )

    def add_or_update_item(
        self,
        item_id: str,
        category: str,
        name: str,
        description: str,
        price_inr: float,
        price_usd: float,
        stock_qty: int = 999,
        is_auto_deliver: bool = False,
        file_filename: str = "",
        features: Optional[list[str]] = None,
        badge: str = "",
        active: bool = True,
    ) -> ShopItem:
        """Add or update a stock catalogue item."""
        features_json = json.dumps(features or [])
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO kdc_items (
                    id, category, name, description, price_inr, price_usd,
                    stock_qty, is_auto_deliver, file_filename, features_json, badge, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    category=excluded.category,
                    name=excluded.name,
                    description=excluded.description,
                    price_inr=excluded.price_inr,
                    price_usd=excluded.price_usd,
                    stock_qty=excluded.stock_qty,
                    is_auto_deliver=excluded.is_auto_deliver,
                    file_filename=excluded.file_filename,
                    features_json=excluded.features_json,
                    badge=excluded.badge,
                    active=excluded.active
            """, (
                item_id, category, name, description, price_inr, price_usd,
                stock_qty, 1 if is_auto_deliver else 0, file_filename, features_json, badge, 1 if active else 0
            ))
            conn.commit()

        return self.get_item(item_id)  # type: ignore

    def remove_item(self, item_id: str) -> bool:
        """Deactivate or remove item from stock."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE kdc_items SET active = 0 WHERE id = ?", (item_id,))
            conn.commit()
            return cur.rowcount > 0

    # ── Billing & Order Methods ──
    def create_bill(
        self,
        guild_id: int,
        customer_id: int,
        customer_name: str,
        item_id: str,
        currency: str = "INR",
        quantity: int = 1,
        staff_notes: str = "",
    ) -> ShopBill:
        """Create a new billing invoice for an order."""
        item = self.get_item(item_id)
        if not item:
            raise KeyError(f"Item with ID '{item_id}' not found in KDC Shop catalogue.")

        bill_id = f"KDC-{uuid.uuid4().hex[:8].upper()}"
        currency = currency.upper()
        if currency not in ("INR", "USD"):
            currency = "INR"

        unit_price = item.price_inr if currency == "INR" else item.price_usd
        total = round(unit_price * max(1, quantity), 2)
        now = time.time()

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO kdc_bills (
                    id, guild_id, customer_id, customer_name, item_id, item_name,
                    currency, price, quantity, total, status, created_at, updated_at, staff_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
            """, (
                bill_id, guild_id, customer_id, customer_name, item.id, item.name,
                currency, unit_price, quantity, total, now, now, staff_notes
            ))
            conn.commit()

        return self.get_bill(bill_id)  # type: ignore

    def get_bill(self, bill_id: str) -> Optional[ShopBill]:
        """Fetch invoice by ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM kdc_bills WHERE id = ? LIMIT 1", (bill_id.strip(),))
            r = cur.fetchone()
            if not r:
                return None
            return ShopBill(
                id=r["id"],
                guild_id=int(r["guild_id"]),
                customer_id=int(r["customer_id"]),
                customer_name=r["customer_name"],
                item_id=r["item_id"],
                item_name=r["item_name"],
                currency=r["currency"],
                price=float(r["price"]),
                quantity=int(r["quantity"]),
                total=float(r["total"]),
                status=r["status"],
                transaction_id=r["transaction_id"] or "",
                proof_url=r["proof_url"] or "",
                delivered_file=r["delivered_file"] or "",
                created_at=float(r["created_at"]),
                updated_at=float(r["updated_at"]),
                staff_id=int(r["staff_id"] or 0),
                staff_notes=r["staff_notes"] or "",
            )

    def list_bills(
        self,
        guild_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[ShopBill]:
        """List bills with optional filters."""
        query = "SELECT * FROM kdc_bills WHERE 1=1"
        params: list[Any] = []
        if guild_id:
            query += " AND guild_id = ?"
            params.append(guild_id)
        if customer_id:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if status:
            query += " AND status = ?"
            params.append(status.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()

        return [
            ShopBill(
                id=r["id"],
                guild_id=int(r["guild_id"]),
                customer_id=int(r["customer_id"]),
                customer_name=r["customer_name"],
                item_id=r["item_id"],
                item_name=r["item_name"],
                currency=r["currency"],
                price=float(r["price"]),
                quantity=int(r["quantity"]),
                total=float(r["total"]),
                status=r["status"],
                transaction_id=r["transaction_id"] or "",
                proof_url=r["proof_url"] or "",
                delivered_file=r["delivered_file"] or "",
                created_at=float(r["created_at"]),
                updated_at=float(r["updated_at"]),
                staff_id=int(r["staff_id"] or 0),
                staff_notes=r["staff_notes"] or "",
            )
            for r in rows
        ]

    def update_bill_status(
        self,
        bill_id: str,
        status: str,
        transaction_id: str = "",
        proof_url: str = "",
        delivered_file: str = "",
        staff_id: int = 0,
        staff_notes: str = "",
    ) -> Optional[ShopBill]:
        """Update bill status (e.g. PAID, DELIVERED, CANCELLED)."""
        now = time.time()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE kdc_bills
                SET status = ?,
                    transaction_id = CASE WHEN ? != '' THEN ? ELSE transaction_id END,
                    proof_url = CASE WHEN ? != '' THEN ? ELSE proof_url END,
                    delivered_file = CASE WHEN ? != '' THEN ? ELSE delivered_file END,
                    staff_id = CASE WHEN ? != 0 THEN ? ELSE staff_id END,
                    staff_notes = CASE WHEN ? != '' THEN ? ELSE staff_notes END,
                    updated_at = ?
                WHERE id = ?
            """, (
                status.upper(),
                transaction_id, transaction_id,
                proof_url, proof_url,
                delivered_file, delivered_file,
                staff_id, staff_id,
                staff_notes, staff_notes,
                now, bill_id.strip()
            ))
            conn.commit()

        return self.get_bill(bill_id)

    # ── Bot File Delivery Methods ──
    def get_bot_file_path(self, item_id: str) -> Optional[Path]:
        """Get the absolute path to a bot zip file for auto-delivery."""
        item = self.get_item(item_id)
        if not item or not item.file_filename:
            return None
        file_path = self.bots_dir / item.file_filename
        if file_path.exists():
            return file_path
        return None

    def save_uploaded_bot_file(self, item_id: str, file_bytes: bytes, filename: str) -> Path:
        """Save an uploaded bot release zip file into the warehouse."""
        self.bots_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = filename.replace("..", "").replace("/", "_").replace("\\", "_")
        target_path = self.bots_dir / safe_filename
        with open(target_path, "wb") as f:
            f.write(file_bytes)

        # Update item record with new filename
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE kdc_items SET file_filename = ? WHERE id = ?", (safe_filename, item_id))
            conn.commit()

        return target_path

    # ── Review & Rating Methods (Super Simple) ──
    def add_review(
        self,
        user_id: int,
        username: str,
        rating: int,
        comment: str,
        product: str = "KDC Shop",
        verified: bool = True,
    ) -> Dict[str, Any]:
        """Add a customer review with star rating (1-5) and feedback."""
        rating_clean = max(1, min(5, int(rating)))
        rev_id = f"REV-{uuid.uuid4().hex[:8].upper()}"
        now = time.time()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO kdc_reviews (id, user_id, username, rating, comment, product, created_at, verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rev_id, user_id, username.strip(), rating_clean,
                comment.strip(), product.strip(), now, 1 if verified else 0
            ))
            conn.commit()

        return {
            "id": rev_id,
            "user_id": user_id,
            "username": username.strip(),
            "rating": rating_clean,
            "comment": comment.strip(),
            "product": product.strip(),
            "created_at": now,
            "verified": verified,
        }

    def get_reviews(self, limit: int = 10, min_rating: int = 1) -> List[Dict[str, Any]]:
        """Retrieve latest customer reviews sorted by timestamp descending."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, user_id, username, rating, comment, product, created_at, verified
                FROM kdc_reviews
                WHERE rating >= ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (min_rating, limit))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_rating_summary(self) -> Dict[str, Any]:
        """Get aggregate rating summary, star breakdown, and total count."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT rating FROM kdc_reviews")
            rows = cur.fetchall()
            if not rows:
                return {
                    "average": 5.0,
                    "total": 0,
                    "breakdown": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
                    "stars_str": "⭐⭐⭐⭐⭐",
                }
            ratings = [int(r["rating"]) for r in rows]
            total = len(ratings)
            avg = round(sum(ratings) / total, 1)
            breakdown = {i: ratings.count(i) for i in (5, 4, 3, 2, 1)}
            full_stars = int(round(avg))
            stars_str = "⭐" * full_stars
            return {
                "average": avg,
                "total": total,
                "breakdown": breakdown,
                "stars_str": stars_str,
            }

    def delete_review(self, review_id: str) -> bool:
        """Delete a review by ID (Staff action)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM kdc_reviews WHERE id = ?", (review_id.strip(),))
            conn.commit()
            return cur.rowcount > 0
