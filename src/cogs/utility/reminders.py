"""
KYOKA 3.0 — Reminders and Timer Utility Cog.
Allows users to set countdown timers and personal task reminders.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


def parse_time_duration(time_str: str) -> int | None:
    """Parse time string like '10m', '2h', '30s', '1d' into total seconds."""
    match = re.fullmatch(r"(\d+)([smhd])", time_str.strip().lower())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers[unit]


class Reminders(commands.Cog):
    """Personal reminders and countdown timer utilities."""

    category = "🔧・UTILITIES"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.command(
        name="remind",
        aliases=["reminder", "timer"],
        description="Set a personal countdown timer or reminder (e.g. 10m Take a break).",
    )
    async def remind(self, ctx: CustomContext, duration: str, *, reason: str = "Reminder") -> None:
        """Set a countdown reminder."""
        seconds = parse_time_duration(duration)
        if not seconds:
            return await ctx.send(
                "❌ **Invalid time format!**\n"
                "> Examples: `30s`, `10m`, `1h`, `2d`\n"
                "> Usage: `+remind 15m Check the oven`"
            )

        if seconds < 5:
            return await ctx.send("❌ Minimum reminder duration is `5s`.")
        if seconds > 86400 * 7:  # 7 days max
            return await ctx.send("❌ Maximum reminder duration is `7d`.")

        embed = discord.Embed(
            title="⏰ Reminder Scheduled",
            description=f"I will remind you in **{duration}** for:\n> `{reason}`",
            color=0x7C3AED,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

        async def _trigger_reminder() -> None:
            await asyncio.sleep(seconds)
            remind_embed = discord.Embed(
                title="⏰ Reminder Alert!",
                description=f"Hey {ctx.author.mention}, you asked me to remind you:\n> **{reason}**",
                color=0xF59E0B,
                timestamp=discord.utils.utcnow(),
            )
            remind_embed.set_footer(text=f"Set {duration} ago")
            try:
                await ctx.channel.send(content=ctx.author.mention, embed=remind_embed)
            except Exception:
                try:
                    await ctx.author.send(embed=remind_embed)
                except Exception:
                    pass

        asyncio.create_task(_trigger_reminder())


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Reminders(bot))
