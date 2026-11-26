from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import re
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response
from src.utils.emojis import resolve_emoji

logger = logging.getLogger("Kyoka.Ping")


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


def _format_latency_status(ms: float) -> str:
    """Format numeric latency with qualitative health indicator."""
    if ms <= 0:
        return "⚪ `N/A`"
    if ms < 80:
        return f"🟢 `{ms:.1f}ms` *(Fast)*"
    if ms < 160:
        return f"🟡 `{ms:.1f}ms` *(Normal)*"
    if ms < 250:
        return f"🟠 `{ms:.1f}ms` *(Intercontinental)*"
    return f"🔴 `{ms:.1f}ms` *(High Latency)*"


class Ping(commands.Cog):
    """General utility and diagnostics commands."""
    category: str = "Utility"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._mention_ping_at: dict[int, float] = {}

    @commands.hybrid_command(
        name="ping",
        aliases=["pong", "pung", "latency"],
        description="Check KYOKA's websocket, REST API, event-loop, and database response speed.",
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
            return await ctx.send(f"🔔 **KYOKA ping test ({count}/5):** {mentions}", allowed_mentions=discord.AllowedMentions(users=[target]))

        cmd_start = time.perf_counter()

        # Measure real Discord HTTP REST round-trip latency via typing indicator
        rest_ms: float | None = None
        try:
            t_api_start = time.perf_counter()
            await ctx.typing()
            rest_ms = (time.perf_counter() - t_api_start) * 1000
        except Exception:
            msg_dt = getattr(getattr(ctx, "message", None), "created_at", None) or getattr(getattr(ctx, "interaction", None), "created_at", None)
            if msg_dt:
                rest_ms = max(0.0, (discord.utils.utcnow() - msg_dt).total_seconds() * 1000)

        # Measure asyncio event-loop lag
        loop_start = time.perf_counter()
        await asyncio.sleep(0)
        loop_lag = (time.perf_counter() - loop_start) * 1000

        # Measure DB ping & health with timeout resilience
        db_str = "Offline"
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                start_db = time.perf_counter()
                await asyncio.wait_for(self.bot.db.fetch_one("SELECT 1;"), timeout=0.45)
                db_ms = (time.perf_counter() - start_db) * 1000
                db_str = f"Healthy (`{db_ms:.2f}ms`)"
            except Exception:
                db_str = "Unavailable"

        # Measure Discord Gateway WebSocket heartbeat latency
        ws_latency = (self.bot.latency * 1000) if (self.bot.latency and not math.isnan(self.bot.latency)) else 0.0

        # Calculate Uptime
        now = discord.utils.utcnow()
        start = getattr(self.bot, "start_time", now)
        delta = int((now - start).total_seconds())
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

        cmd_latency = (time.perf_counter() - cmd_start) * 1000

        # Record telemetry if command took long
        if cmd_latency > 250.0 and hasattr(self.bot, "record_slow_operation"):
            self.bot.record_slow_operation("ping", cmd_latency, f"Guild {ctx.guild.id if ctx.guild else 0}")

        dot = resolve_emoji(self.bot, "ARROW", fallback="•")
        ping_em = resolve_emoji(self.bot, "PING")

        # Identify current hosting region
        reg_env = (os.getenv("RENDER_REGION") or os.getenv("REGION") or "virginia").strip().lower()
        if "singapore" in reg_env or "asia" in reg_env:
            host_region = "Singapore (Asia)"
        elif "frankfurt" in reg_env or "eu" in reg_env:
            host_region = "Frankfurt (Europe)"
        elif "oregon" in reg_env:
            host_region = "Oregon (US West)"
        elif "virginia" in reg_env or "us" in reg_env:
            host_region = "Virginia (US East)"
        else:
            host_region = reg_env.title()

        # Check Lavalink audio engine status
        ll_status = "Offline"
        try:
            import wavelink
            node = wavelink.Pool.get_node()
            if node and node.status == wavelink.NodeStatus.CONNECTED:
                ll_status = "Online (Lossless Cluster)"
            elif node:
                ll_status = f"{node.status.name.title()}"
        except Exception:
            pass

        rest_display = f"`{rest_ms:.1f}ms`" if rest_ms is not None else "`N/A`"
        shard_id = ctx.guild.shard_id if ctx.guild else 0

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{ping_em} KYOKA Latency & Diagnostics**\n"
                "> Real-time telemetry for Discord Gateway, REST API, Event Loop, Database, and Audio Engine."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Gateway:** `{ws_latency:.2f}ms` ({_format_latency_status(ws_latency)})\n"
            f"{dot} **REST API:** {rest_display} | **Bot Processing:** `{cmd_latency:.1f}ms`\n"
            f"{dot} **Event-Loop Lag:** `{loop_lag:.2f}ms` | **Database:** {db_str}\n"
            f"{dot} **Uptime:** `{uptime_str}` | **Shard:** `#{shard_id}` | **Region:** `{host_region}`\n"
            f"{dot} **Audio Engine:** `{ll_status}`"
        )
        container.add_separator(divider=True)

        if ws_latency > 150.0 or (rest_ms and rest_ms > 200.0):
            container.add_text(
                "💡 **Regional Latency Insight:**\n"
                f"> Hosted in **{host_region}**. Switch region closer to your server if transatlantic latency is high."
            )
            container.add_separator(divider=True)

        container.add_text(f"-# Requested by {ctx.author.display_name}")

        try:
            await send_container_response(ctx, container)
        except Exception as e:
            logger.warning(f"Could not send container ping response ({e}), falling back to standard embed")
            try:
                emb = container.to_embed()
                await ctx.send(embed=emb)
            except Exception:
                await ctx.send(
                    f"🏓 **Pong!** Gateway: `{ws_latency:.1f}ms` | Host: {host_region}"
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ping(bot))
