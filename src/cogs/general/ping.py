from __future__ import annotations

import time
import re
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response


def parse_repeated_ping(value: str) -> tuple[int, int]:
    """Parse one user ID/mention and one count, in either argument order."""
    match = re.search(r"<@!?(\d{15,20})>|(?<!\d)(\d{15,20})(?!\d)", value)
    if not match:
        raise ValueError("Include one user mention and a count from 1 to 5.")
    target_id = int(match.group(1) or match.group(2))
    count_text = (value[:match.start()] + value[match.end():]).strip()
    if not count_text.isdecimal():
        raise ValueError("Use `&ping @user 3` or `&ping 3 @user`.")
    if len(count_text) > 5 or int(count_text) > 5:
        raise ValueError("Repeated-user pings are capped at **5** per command.")
    count = int(count_text)
    if count < 1:
        raise ValueError("Count must be at least 1.")
    return target_id, count


class Ping(commands.Cog):
    """General utility and diagnostics commands."""
    category: str = "Moderation"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._mention_ping_at: dict[int, float] = {}

    @commands.hybrid_command(
        name="ping",
        aliases=["pong", "pung", "latency"],
        description="Check Kyoka Bot's websocket, latency, and database response speed.",
    )
    async def ping(self, ctx: CustomContext, *, target_and_count: str = "") -> None:
        """Check latency, or make a small, allowlisted test ping with a target and count."""
        if target_and_count.strip():
            # Repeated mentions are restricted to explicitly authorized no-prefix users
            # and hard-capped to prevent mass-mention spam and Discord rate-limit abuse.
            authorized = (
                ctx.author.id in getattr(self.bot, "no_prefix_users", set())
                or self.bot.perm_mgr.is_developer_sync(ctx.author.id)
            )
            if not authorized:
                return await ctx.send("Repeated-user ping is restricted to authorized no-prefix users. Use `&ping` for latency.")
            try:
                target_id, count = parse_repeated_ping(target_and_count)
            except ValueError as exc:
                return await ctx.send(str(exc))
            target = ctx.guild.get_member(target_id) if ctx.guild else None
            if target is None:
                return await ctx.send("I couldn't find that user in this server.")
            now = time.monotonic()
            last_ping = self._mention_ping_at.get(ctx.author.id, 0.0)
            if now - last_ping < 10:
                return await ctx.send("Repeated-user pings are on cooldown. Please wait a few seconds.")
            self._mention_ping_at = {
                user_id: timestamp
                for user_id, timestamp in self._mention_ping_at.items()
                if now - timestamp < 60
            }
            self._mention_ping_at[ctx.author.id] = now
            mentions = " ".join(target.mention for _ in range(count))
            return await ctx.send(f"🔔 **Aizen ping test ({count}/5):** {mentions}", allowed_mentions=discord.AllowedMentions(users=[target]))
        # measure DB ping
        start_db = time.perf_counter()
        await self.bot.db.fetch_one("SELECT 1;")
        db_latency = (time.perf_counter() - start_db) * 1000

        # measure Discord Websocket latency
        ws_latency = self.bot.latency * 1000

        # calculate Uptime
        now = discord.utils.utcnow()
        start = getattr(self.bot, "start_time", now)
        delta = int((now - start).total_seconds())
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

        shard_id = ctx.guild.shard_id if ctx.guild else 0

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Kyoka Latency**\n"
                f"> Current gateway latency, database response speed, and system uptime."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Gateway:** `{ws_latency:.2f}ms` | **Database:** `{db_latency:.2f}ms`\n"
            f"{dot} **Uptime:** `{uptime_str}` | **Shard:** `#{shard_id}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ping(bot))
