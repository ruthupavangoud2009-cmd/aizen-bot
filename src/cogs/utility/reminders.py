"""
KYOKA — Persistent Reminders & Timer Utility Cog
Allows users to set countdown timers and personal task reminders persisted in PostgreSQL
so active reminders survive bot restarts, with list & cancel management.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.context import CustomContext
from src.ui.response import KyokaResponse, send_response
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.Reminders")


def parse_time_duration(time_str: str) -> int | None:
    """Parse time string like '10m', '2h', '30s', '1d' or compound '1h30m' into total seconds."""
    cleaned = time_str.strip().lower()
    if not cleaned:
        return None
    full_pattern = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", cleaned)
    if full_pattern and any(full_pattern.groups()):
        days = int(full_pattern.group(1) or 0)
        hours = int(full_pattern.group(2) or 0)
        minutes = int(full_pattern.group(3) or 0)
        seconds = int(full_pattern.group(4) or 0)
        total = days * 86400 + hours * 3600 + minutes * 60 + seconds
        return total if total > 0 else None
    return None


class Reminders(commands.Cog):
    """Persistent personal reminders and countdown timer utilities."""

    category = "🔧・UTILITIES"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._memory_reminders: list[dict[str, Any]] = []
        self._dispatching: set[int] = set()

    async def cog_load(self) -> None:
        """Start background reminder dispatch loop on cog load when bot is initialized."""
        is_ready_fn = getattr(self.bot, "is_ready", None)
        if callable(is_ready_fn) or getattr(self.bot, "_connection", None) is not None:
            if getattr(self.bot, "user", None) is not None and not self._reminder_loop.is_running():
                self._reminder_loop.start()

    async def cog_unload(self) -> None:
        """Stop background reminder dispatch loop cleanly."""
        if self._reminder_loop.is_running():
            self._reminder_loop.cancel()

    def _has_db(self) -> bool:
        db = getattr(self.bot, "db", None)
        return bool(db and getattr(db, "_connected_once", False))

    async def _deliver_reminder(self, row: dict[str, Any]) -> None:
        """Deliver a due reminder to its origin channel or fallback to user DM."""
        rid = int(row.get("id", 0))
        user_id = int(row["user_id"])
        channel_id = int(row["channel_id"])
        reason = str(row.get("reason") or "Reminder")
        dur_label = str(row.get("duration_label") or "earlier")

        e_reg = getattr(self.bot, "custom_emojis", None)
        spark = (getattr(e_reg, "sparkle", "") if e_reg else "") or "⏰"

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{spark} Reminder Alert**\n"
                f"> <@{user_id}>, you asked KYOKA to remind you:\n"
                f"> **{reason}**"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Set {dur_label} ago • Reminder ID `#{rid}`")

        delivered = False
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            try:
                await send_container_response(
                    channel,
                    container,
                    content=f"<@{user_id}>",
                )
                delivered = True
            except Exception:
                delivered = False

        if not delivered:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                if user:
                    await send_container_response(user, container)
            except Exception as dm_err:
                logger.debug("Could not deliver reminder #%s to user %s: %s", rid, user_id, dm_err)

    @tasks.loop(seconds=10)
    async def _reminder_loop(self) -> None:
        """Poll due reminders from PostgreSQL and in-memory buffer."""
        now = discord.utils.utcnow()

        # 1. Process PostgreSQL reminders
        if self._has_db():
            try:
                due_rows = await self.bot.db.fetch_all(
                    """
                    SELECT * FROM user_reminders
                    WHERE completed = FALSE AND remind_at <= ?
                    ORDER BY remind_at ASC
                    LIMIT 25;
                    """,
                    now,
                )
                for row in due_rows:
                    rid = int(row["id"])
                    if rid in self._dispatching:
                        continue
                    self._dispatching.add(rid)
                    try:
                        await self.bot.db.execute(
                            "UPDATE user_reminders SET completed = TRUE WHERE id = ?;",
                            rid,
                        )
                        await self._deliver_reminder(row)
                    finally:
                        self._dispatching.discard(rid)
            except Exception as exc:
                logger.debug("Reminder loop DB poll notice: %s", exc)

        # 2. Process offline/in-memory reminders
        if self._memory_reminders:
            still_pending = []
            for item in self._memory_reminders:
                if item["remind_at"] <= now:
                    try:
                        await self._deliver_reminder(item)
                    except Exception:
                        pass
                else:
                    still_pending.append(item)
            self._memory_reminders = still_pending

    @_reminder_loop.before_loop
    async def _before_reminder_loop(self) -> None:
        if hasattr(self.bot, "wait_until_ready"):
            try:
                await self.bot.wait_until_ready()
            except RuntimeError:
                return

    @commands.command(
        name="remind",
        aliases=["reminder", "timer"],
        description="Set a persistent countdown timer or reminder (e.g. 10m Take a break).",
    )
    @app_commands.describe(duration="Time until reminder (e.g. 30s, 10m, 1h30m, 2d)", reason="What to remind you about")
    async def remind(self, ctx: CustomContext, duration: str, *, reason: str = "Reminder") -> None:
        """Set a persistent countdown reminder."""
        seconds = parse_time_duration(duration)
        if not seconds:
            resp = KyokaResponse.warning(
                title="Invalid Time Format",
                description=(
                    "Use formats like `30s`, `10m`, `1h30m`, or `2d`.\n"
                    "**Example:** `+remind 15m Check the oven`"
                ),
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        if seconds < 5:
            resp = KyokaResponse.warning(
                title="Duration Too Short",
                description="Minimum reminder duration is `5s`.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return
        if seconds > 86400 * 30:
            resp = KyokaResponse.warning(
                title="Duration Too Long",
                description="Maximum reminder duration is `30d`.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        remind_at = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        clean_reason = reason.strip()[:500] or "Reminder"
        guild_id = ctx.guild.id if ctx.guild else None
        reminder_id: Optional[int] = None

        if self._has_db():
            try:
                row = await self.bot.db.fetch_one(
                    """
                    INSERT INTO user_reminders (guild_id, channel_id, user_id, reason, duration_label, remind_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    RETURNING id;
                    """,
                    guild_id,
                    ctx.channel.id,
                    ctx.author.id,
                    clean_reason,
                    duration.strip()[:32],
                    remind_at,
                )
                if row and row.get("id"):
                    reminder_id = int(row["id"])
            except Exception as exc:
                logger.warning("Falling back to in-memory reminder storage: %s", exc)

        if reminder_id is None:
            reminder_id = len(self._memory_reminders) + 1
            self._memory_reminders.append({
                "id": reminder_id,
                "guild_id": guild_id,
                "channel_id": ctx.channel.id,
                "user_id": ctx.author.id,
                "reason": clean_reason,
                "duration_label": duration.strip()[:32],
                "remind_at": remind_at,
            })

            # Schedule immediate fallback wakeup for short/offline reminders if loop isn't active
            if not self._reminder_loop.is_running() and seconds <= 3600:
                async def _fallback_fire(item_id: int, delay: int) -> None:
                    await asyncio.sleep(delay)
                    for idx, entry in enumerate(list(self._memory_reminders)):
                        if entry["id"] == item_id:
                            self._memory_reminders.pop(idx)
                            await self._deliver_reminder(entry)
                            break
                asyncio.create_task(_fallback_fire(reminder_id, seconds))

        resp = KyokaResponse.success(
            title=f"Reminder Scheduled (#{reminder_id})",
            description=f"I will remind you <t:{int(remind_at.timestamp())}:R> (<t:{int(remind_at.timestamp())}:t>).",
            fields=[
                ("Reminder", f"`{clean_reason}`", False),
                ("Duration", f"`{duration}`", True),
                ("ID", f"`#{reminder_id}`", True),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="reminders",
        aliases=["myreminders", "reminderlist"],
        description="List your active scheduled reminders.",
    )
    async def reminders_list(self, ctx: CustomContext) -> None:
        """List active reminders for the calling user."""
        rows: list[dict[str, Any]] = []
        if self._has_db():
            rows = await self.bot.db.fetch_all(
                """
                SELECT id, reason, remind_at
                FROM user_reminders
                WHERE user_id = ? AND completed = FALSE
                ORDER BY remind_at ASC
                LIMIT 15;
                """,
                ctx.author.id,
            )
        else:
            rows = [r for r in self._memory_reminders if r["user_id"] == ctx.author.id]

        if not rows:
            resp = KyokaResponse.info(
                title="No Active Reminders",
                description="You have no pending reminders. Use `+remind 10m Task` to schedule one.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        fields = []
        for r in rows[:10]:
            ts = r["remind_at"]
            ts_str = f"<t:{int(ts.timestamp())}:R>" if isinstance(ts, datetime.datetime) else "Soon"
            fields.append((f"#{r['id']} • {ts_str}", f"`{str(r['reason'])[:120]}`", False))

        resp = KyokaResponse.info(
            title=f"Active Reminders ({len(rows)})",
            description="Use `+remindcancel <id>` to cancel a reminder.",
            fields=fields,
            author=ctx.author,
        )
        await send_response(ctx, resp, ephemeral=True)

    @commands.command(
        name="remindcancel",
        aliases=["cancelreminder", "delreminder"],
        description="Cancel one of your active reminders by ID.",
    )
    @app_commands.describe(reminder_id="Numeric reminder ID to cancel")
    async def remind_cancel(self, ctx: CustomContext, reminder_id: int) -> None:
        """Cancel a scheduled reminder belonging to the author."""
        cancelled = False
        if self._has_db():
            row = await self.bot.db.fetch_one(
                "SELECT id FROM user_reminders WHERE id = ? AND user_id = ? AND completed = FALSE;",
                reminder_id,
                ctx.author.id,
            )
            if row:
                await self.bot.db.execute(
                    "UPDATE user_reminders SET completed = TRUE WHERE id = ?;",
                    reminder_id,
                )
                cancelled = True
        else:
            for idx, item in enumerate(self._memory_reminders):
                if item["id"] == reminder_id and item["user_id"] == ctx.author.id:
                    self._memory_reminders.pop(idx)
                    cancelled = True
                    break

        if not cancelled:
            resp = KyokaResponse.warning(
                title="Reminder Not Found",
                description=f"No active reminder `#{reminder_id}` belonging to you was found.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        resp = KyokaResponse.success(
            title="Reminder Cancelled",
            description=f"Reminder `#{reminder_id}` has been cancelled.",
            author=ctx.author,
        )
        await send_response(ctx, resp, ephemeral=True)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Reminders(bot))
