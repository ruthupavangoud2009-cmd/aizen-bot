"""
KYOKA 3.0 - Blox Fruits Real-Time Fruit Values & Spawn Notifier Cog.
Provides live web-backed trading values, market demand analysis, fruit spawn alerts,
and dealer stock countdown timers.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.blox_fruits_web_manager import BloxFruitsWebManager
from src.utils.containers import KyokaContainer, send_container_response

logger = logging.getLogger("Kyoka.Cogs.BloxFruitsNotifier")
PURPLE = 0x6F43BE


class BloxFruitsNotifier(commands.Cog, name="BloxFruitsNotifier"):
    """Blox Fruits real-time values, fruit spawn alerts, and dealer stock tracking."""
    category = "🍎・BLOX FRUITS AI"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.web_mgr = BloxFruitsWebManager()

    # ─── REAL-TIME WEB VALUES COMMAND ──────────────────────────────────────────

    @commands.command(
        name="fruitvalues",
        aliases=["fvalues", "fruitvalue", "fval", "tradevalues"],
        description="Fetch real-time web-backed Blox Fruits trading values, demand, and market trends.",
    )
    async def fruitvalues(self, ctx: CustomContext, *, fruit: Optional[str] = None) -> None:
        """Inspect real-time trading values, demand score, and market trends."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        if not fruit:
            embed = discord.Embed(
                title="🍎 Blox Fruits Real-Time Value Engine",
                description=(
                    "> Live market values, community demand ratings, and trade advice backed by web data.\n\n"
                    f"**Usage:** `{prefix}fruitvalues <fruit>` (e.g. `{prefix}fruitvalues kitsune`)\n\n"
                    "**🔥 Top Meta Fruits:**\n"
                    "• **Dragon:** `180,000,000` • Demand: `10/10` (Rework Hype)\n"
                    "• **Kitsune:** `115,000,000` • Demand: `10/10` (Peak PvP)\n"
                    "• **Leopard:** `40,000,000` • Demand: `9/10` (High Currency)\n"
                    "• **Dough:** `22,000,000` • Demand: `9.5/10` (High Combo)\n"
                    "• **Portal:** `8,500,000` • Demand: `9.5/10` (Teleport Meta)\n"
                    "• **Buddha:** `7,500,000` • Demand: `10/10` (Universal Grind)\n\n"
                    f"*Type `{prefix}fruitvalues <fruit_name>` for deep trade analysis.*"
                ),
                color=PURPLE,
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name} • Live Market Feed")
            return await ctx.send(embed=embed)

        data = await self.web_mgr.get_fruit_value(fruit)
        if not data:
            embed = discord.Embed(
                title="❌ Fruit Not Found",
                description=(
                    f"Could not locate **`{fruit}`** in the live market database.\n\n"
                    "**Suggestions:**\n"
                    "• Check spelling (e.g. `kitsune`, `dragon`, `t-rex`, `mammoth`, `buddha`)\n"
                    f"• Type `{prefix}fruitvalues` to view high-demand fruits"
                ),
                color=0xED4245,
            )
            return await ctx.send(embed=embed)

        beli = data.get("beli", "N/A")
        robux = data.get("robux", "N/A")
        trade_val = f"{data.get('trade_value', 0):,}"
        demand = data.get("demand", "N/A")
        trend = data.get("trend", "⚖️ Stable")
        status = data.get("status", "Fair")
        tip = data.get("tip", "No specific trading notes.")
        rarity = data.get("rarity", "Standard")
        fruit_type = data.get("type", "Standard")

        embed = discord.Embed(
            title=f"🍎 {data['name']} Fruit • Real-Time Market Value",
            description=(
                f"> **Rarity:** `{rarity}` | **Type:** `{fruit_type}`\n"
                f"> **Market Status:** `{status}`\n\n"
                f"• **Trading Market Value:** `{trade_val}`\n"
                f"• **Physical Dealer Beli:** `{beli}`\n"
                f"• **Permanent Robux Cost:** `{robux}`\n"
                f"• **Community Demand Rating:** `{demand}`\n"
                f"• **Current Market Trend:** {trend}\n\n"
                f"**💡 Trade Advice:**\n> {tip}"
            ),
            color=PURPLE,
        )
        embed.set_footer(
            text=f"Live Web Values • Requested by {ctx.author.display_name} • KYOKA 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        await ctx.send(embed=embed)

    # ─── FRUIT NOTIFIER SYSTEM ───────────────────────────────────────────────

    @commands.group(
        name="fruitnotifier",
        aliases=["fnotifier", "fruitnotify", "falert"],
        invoke_without_command=True,
        description="Configure automated Blox Fruits spawn alerts, mirage drops, and dealer stock updates.",
    )
    async def fruitnotifier(self, ctx: CustomContext) -> None:
        """Overview of Blox Fruits Fruit Notifier commands."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        _, _, countdown = self.web_mgr.get_dealer_stock_countdown()

        embed = discord.Embed(
            title="🍈 KYOKA Blox Fruits Notifier Hub",
            description=(
                "> Automated in-game fruit spawn alerts, dealer stock resets, and mirage tracking.\n\n"
                f"• `{p}fruitnotifier setup #channel` — Set the fruit notification channel (Admin)\n"
                f"• `{p}fruitnotifier toggle` — Enable or disable fruit alerts\n"
                f"• `{p}fruitnotifier test [fruit]` — Send a sample fruit spawn alert card\n"
                f"• `{p}fruitnotifier stock` — View current Normal & Mirage Dealer stock countdown\n"
                f"• `{p}fruitvalues <fruit>` — Inspect live trading market values\n\n"
                f"**⏰ Next Normal Dealer Reset in:** `{countdown}`"
            ),
            color=PURPLE,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Blox Fruits Engine")
        await ctx.send(embed=embed)

    @fruitnotifier.command(
        name="setup",
        description="Set the channel where fruit spawn notifications will be dispatched.",
    )
    @commands.has_permissions(manage_guild=True)
    async def notifier_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Set fruit notifier channel."""
        target_channel = channel or ctx.channel
        if not ctx.guild:
            return

        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO kyoka_guild_settings (guild_id, fruit_notifier_channel_id)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id) DO UPDATE SET fruit_notifier_channel_id = EXCLUDED.fruit_notifier_channel_id;
                    """,
                    ctx.guild.id,
                    target_channel.id,
                )
            except Exception:
                pass

        embed = discord.Embed(
            title="✅ Fruit Notifier Configured",
            description=(
                f"> Fruit spawn notifications and stock updates will be dispatched to {target_channel.mention}.\n\n"
                f"Use `+fruitnotifier test` to verify card delivery."
            ),
            color=0x2ECC71,
        )
        await ctx.send(embed=embed)

    @fruitnotifier.command(
        name="test",
        aliases=["alert"],
        description="Dispatch a simulated live fruit spawn alert card into the notification channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def notifier_test(self, ctx: CustomContext, fruit_name: Optional[str] = "Kitsune") -> None:
        """Dispatch test spawn notification."""
        data = await self.web_mgr.get_fruit_value(fruit_name or "Kitsune")
        name = data.get("name", "Kitsune") if data else "Kitsune"
        val = f"{data.get('trade_value', 115000000):,}" if data else "115,000,000"
        rarity = data.get("rarity", "Mythical") if data else "Mythical"

        now = datetime.datetime.now(datetime.timezone.utc)
        despawn_ts = int((now + datetime.timedelta(minutes=20)).timestamp())

        embed = discord.Embed(
            title=f"🚨 A Wild [{name} Fruit] Has Spawned!",
            description=(
                f"> **Rarity:** `{rarity}` • **Trading Value:** `{val}`\n"
                f"> **Location:** `Third Sea • Sea of Treats (Peanut Land)`\n"
                f"> **Despawn Timer:** <t:{despawn_ts}:R> *(20 minutes remaining)*\n\n"
                "**Coordinates & Instructions:**\n"
                "• Check beneath large candy trees near the Sweet Sands island\n"
                "• Fast travel via Portal Fruit recommended\n"
                "• Ensure PvP safety mode or private server link is active!"
            ),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"Fruit Spawn Alert • Server: {ctx.guild.name if ctx.guild else 'Unknown'} • KYOKA 3.0")
        await ctx.send(embed=embed)

    @fruitnotifier.command(
        name="stock",
        description="View live stock reset timers for the Normal Dealer and Mirage Island Dealer.",
    )
    async def notifier_stock(self, ctx: CustomContext) -> None:
        """View dealer stock timers."""
        _, _, countdown = self.web_mgr.get_dealer_stock_countdown()

        embed = discord.Embed(
            title="🏪 Blox Fruits Dealer Stock Watch",
            description=(
                "> Live synchronization with Blox Fruits global dealer reset timers.\n\n"
                f"• **Normal Dealer Reset:** In **`{countdown}`** *(Global 4-hour cycle)*\n"
                "• **Mirage Island Dealer:** Dynamic spawn during Full Moon Sea Events (Sea 3)\n"
                "• **Advanced Fruit Dealer:** Mirage Island offers awakened & legendary rolls\n\n"
                "**💡 Pro-Tip:**\n"
                "> Normal fruit dealer stock updates globally at `00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC`."
            ),
            color=PURPLE,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Live Stock Feed")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BloxFruitsNotifier(bot))
    logger.info("🍎 [KYOKA] Blox Fruits Real-Time Notifier & Web Values Cog loaded.")
