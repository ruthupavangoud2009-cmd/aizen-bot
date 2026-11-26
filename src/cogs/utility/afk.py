"""
Kyoka Discord Bot - AFK (Away From Keyboard) System
High-performance in-memory cached AFK notifications with database persistence,
smart mention notifications, nickname updates, and automatic status clearing.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import TYPE_CHECKING, Optional, Any
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.ui.response import KyokaResponse, ResponseType, send_response
from src.utils.containers import KyokaContainer, send_container_response
from src.utils.ui import AizenSymbols

def _afk_emoji(bot, *names: str) -> str:
    """Return a real KYOKA custom emoji; never substitute Unicode emoji."""
    registry = getattr(bot, "custom_emojis", None)
    if not registry:
        return ""
    for name in names:
        try:
            emoji = registry.get_emoji_obj(name)
            if emoji is not None and getattr(emoji, "animated", False):
                return str(emoji)
        except Exception:
            continue
    return ""


if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.AFK")


@dataclass
class AFKData:
    """In-memory representation of an AFK user's state."""
    user_id: int
    guild_id: int
    reason: str
    created_at: datetime.datetime
    nickname_changed: bool = False
    original_nickname: Optional[str] = None


def format_duration(seconds: float) -> str:
    """Convert elapsed seconds into a human-readable string (e.g. '2h 15m 30s')."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and len(parts) < 2:
        parts.append(f"{secs}s")
    return " ".join(parts)


class AFKNoteModal(discord.ui.Modal):
    """Modal to leave a private note for an AFK user."""

    def __init__(self, bot: KyokaBot, target_id: int, target_name: str, guild_id: int) -> None:
        super().__init__(title=f"Note for {target_name[:20]}")
        self.bot = bot
        self.target_id = target_id
        self.target_name = target_name
        self.guild_id = guild_id

        self.note_input = discord.ui.TextInput(
            label="Your Message / Note",
            style=discord.TextStyle.paragraph,
            placeholder="Write a message to be delivered when they return...",
            required=True,
            max_length=250,
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        note_text = self.note_input.value.strip()
        note_emoji = _afk_emoji(self.bot, "ticket", "icon_ticket")
        error_emoji = _afk_emoji(self.bot, "error", "icon_error")
        success_emoji = _afk_emoji(self.bot, "success", "icon_success")
        if not note_text:
            await interaction.response.send_message(f"{error_emoji} Note cannot be empty.", ephemeral=True)
            return

        try:
            await self.bot.db.execute(
                """
                INSERT INTO user_afk_notes (target_user_id, sender_id, sender_name, guild_id, note)
                VALUES ($1, $2, $3, $4, $5);
                """,
                self.target_id,
                interaction.user.id,
                interaction.user.display_name,
                self.guild_id,
                note_text,
            )
            await interaction.response.send_message(
                f"{success_emoji} Your note for **{self.target_name}** has been saved! They will receive it as soon as they return.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Failed to save AFK note: {e}")
            await interaction.response.send_message(f"{error_emoji} Failed to save note due to an internal error.", ephemeral=True)


class AFKLeaveNoteView(discord.ui.View):
    """Interactive button to leave a note for an AFK user."""

    def __init__(self, bot: KyokaBot, target_id: int, target_name: str, guild_id: int) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.target_id = target_id
        self.target_name = target_name
        self.guild_id = guild_id

    @discord.ui.button(label="Leave a Note", style=discord.ButtonStyle.secondary, custom_id="afk_leave_note_btn")
    async def leave_note_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        note_emoji = _afk_emoji(self.bot, "ticket", "icon_ticket")
        if interaction.user.id == self.target_id:
            await interaction.response.send_message(f"{note_emoji} You cannot leave a note for yourself.", ephemeral=True)
            return
        modal = AFKNoteModal(self.bot, self.target_id, self.target_name, self.guild_id)
        await interaction.response.send_modal(modal)


class AFKCog(commands.Cog, name="AFK"):
    """Away From Keyboard (AFK) status management."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        # In-memory fast cache: (user_id, guild_id) -> AFKData
        self._afk_cache: dict[tuple[int, int], AFKData] = {}
        # Global AFK applies across every server the bot shares with the user.
        self._global_afk_cache: dict[int, AFKData] = {}
        # Mention notification cooldown: (guild_id, user_id, channel_id) -> last_notified_timestamp
        self._mention_cooldowns: dict[tuple[int, int, int], float] = {}
        self._loaded = False

    async def cog_load(self) -> None:
        """Load persistent AFK states before the cog begins handling messages."""
        await self._load_afk_cache()

    async def _load_afk_cache(self) -> None:
        """Initialize AFK table and populate in-memory cache."""
        try:
            # Ensure tables exist in case migration hasn't executed
            await self.bot.db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_afk (
                    user_id BIGINT,
                    guild_id BIGINT,
                    reason TEXT DEFAULT 'AFK',
                    nickname_changed BOOLEAN DEFAULT FALSE,
                    original_nickname VARCHAR(64),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                );
                """
            )
            await self.bot.db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_afk_notes (
                    id SERIAL PRIMARY KEY,
                    target_user_id BIGINT NOT NULL,
                    sender_id BIGINT NOT NULL,
                    sender_name VARCHAR(64) NOT NULL,
                    guild_id BIGINT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            rows = await self.bot.db.fetch_all("SELECT * FROM user_afk;")
            await self.bot.db.execute("""
                CREATE TABLE IF NOT EXISTS user_global_afk (
                    user_id BIGINT PRIMARY KEY,
                    reason TEXT DEFAULT 'AFK',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            global_rows = await self.bot.db.fetch_all("SELECT * FROM user_global_afk;")
            for row in global_rows:
                raw_created = row.get("created_at")
                if isinstance(raw_created, datetime.datetime):
                    created_at = raw_created
                elif isinstance(raw_created, str):
                    try:
                        created_at = datetime.datetime.fromisoformat(raw_created)
                    except Exception:
                        created_at = discord.utils.utcnow()
                else:
                    created_at = discord.utils.utcnow()
                self._global_afk_cache[int(row["user_id"])] = AFKData(
                    user_id=int(row["user_id"]),
                    guild_id=0,
                    reason=row.get("reason") or "AFK",
                    created_at=created_at,
                )
            for row in rows:
                user_id = int(row["user_id"])
                guild_id = int(row["guild_id"])
                raw_created = row.get("created_at")
                if isinstance(raw_created, datetime.datetime):
                    created_at = raw_created
                elif isinstance(raw_created, str):
                    try:
                        created_at = datetime.datetime.fromisoformat(raw_created)
                    except Exception:
                        created_at = discord.utils.utcnow()
                else:
                    created_at = discord.utils.utcnow()

                self._afk_cache[(user_id, guild_id)] = AFKData(
                    user_id=user_id,
                    guild_id=guild_id,
                    reason=row.get("reason") or "AFK",
                    created_at=created_at,
                    nickname_changed=bool(row.get("nickname_changed", False)),
                    original_nickname=row.get("original_nickname"),
                )
            self._loaded = True
            logger.info(f"Loaded {len(self._afk_cache)} active AFK record(s) into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load AFK cache: {e}", exc_info=e)

    @commands.command(
        name="afk",
        help="Set a server-local AFK status with an optional reason.",
    )
    @app_commands.describe(reason="Reason for being AFK (optional)")
    @commands.guild_only()
    async def afk(
        self,
        ctx: CustomContext,
        *,
        reason: Optional[str] = None,
    ) -> None:
        """Set your AFK status in this server."""
        if not ctx.guild:
            return

        final_reason = reason.strip() if reason and reason.strip() else "AFK"
        if len(final_reason) > 250:
            final_reason = final_reason[:247] + "..."

        now = discord.utils.utcnow()
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        key = (user_id, guild_id)

        # AFK rule: NEVER modify any member's Discord username or server nickname.
        # AFK manages status only. Nicknames and usernames remain 100% untouched.
        nickname_changed = False
        original_nickname: Optional[str] = None

        # Update cache
        afk_entry = AFKData(
            user_id=user_id,
            guild_id=guild_id,
            reason=final_reason,
            created_at=now,
            nickname_changed=False,
            original_nickname=None,
        )
        self._afk_cache[key] = afk_entry

        # Persist to database
        try:
            await self.bot.db.execute(
                """
                INSERT INTO user_afk (user_id, guild_id, reason, nickname_changed, original_nickname, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET
                    reason = EXCLUDED.reason,
                    nickname_changed = EXCLUDED.nickname_changed,
                    original_nickname = EXCLUDED.original_nickname,
                    created_at = EXCLUDED.created_at;
                """,
                user_id,
                guild_id,
                final_reason,
                False,
                None,
                now,
            )
        except Exception as e:
            logger.error(f"Failed to persist AFK record for user {user_id}: {e}", exc_info=e)

        # Dispatch confirmation using unified KyokaResponse (Nyxium style - Image 2)
        dot = "💜"
        check = "✅"
        if self.bot and hasattr(self.bot, "custom_emojis"):
            dot = self.bot.custom_emojis.get("heart_dot", "💜")
            check = self.bot.custom_emojis.get("success", "✅")

        desc = (
            f"> {ctx.author.mention} Your AFK status is now activated in the Server\n"
            f"> **Reason:** {final_reason}\n"
            f"> **DM Notifications:** Enabled\n\n"
            f"{dot} You are now away from keyboard."
        )

        resp = KyokaResponse(
            response_type=ResponseType.SUCCESS,
            title="AFK Activated",
            custom_emoji=check,
            description=desc,
            thumbnail_url=ctx.author.display_avatar.url,
            footer_text=f"-# Requested by {ctx.author.display_name}",
        )
        await send_container_response(ctx, resp.to_container(bot=self.bot))

    @commands.command(name="gafk", help="Activate a global AFK status across all servers.")
    async def gafk(self, ctx: CustomContext, *, reason: Optional[str] = None) -> None:
        if not ctx.guild:
            return
        final_reason = reason.strip() if reason and reason.strip() else "AFK"
        final_reason = final_reason[:250]
        now = discord.utils.utcnow()
        entry = AFKData(user_id=ctx.author.id, guild_id=0, reason=final_reason, created_at=now)
        self._global_afk_cache[ctx.author.id] = entry
        try:
            await self.bot.db.execute(
                """
                INSERT INTO user_global_afk (user_id, reason, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    reason = EXCLUDED.reason, created_at = EXCLUDED.created_at;
                """,
                ctx.author.id, final_reason, now,
            )
        except Exception as error:
            logger.error("Could not persist global AFK for %s: %s", ctx.author.id, error)
        dot = "💜"
        check = "✅"
        if self.bot and hasattr(self.bot, "custom_emojis"):
            dot = self.bot.custom_emojis.get("heart_dot", "💜")
            check = self.bot.custom_emojis.get("success", "✅")

        desc = (
            f"> {ctx.author.mention} Your Global AFK status is now activated\n"
            f"> **Reason:** {final_reason}\n"
            f"> **Scope:** All Shared Servers\n\n"
            f"{dot} You are now away from keyboard."
        )
        resp = KyokaResponse(
            response_type=ResponseType.SUCCESS,
            title="Global AFK Activated",
            custom_emoji=check,
            description=desc,
            thumbnail_url=ctx.author.display_avatar.url,
            footer_text=f"-# Requested by {ctx.author.display_name}",
        )
        await send_container_response(ctx, resp.to_container(bot=self.bot))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Monitor messages for AFK authors returning or mentions of AFK members."""
        if message.author.bot or not message.guild:
            return

        author_id = message.author.id
        guild_id = message.guild.id
        now = discord.utils.utcnow()
        author_key = (author_id, guild_id)

        # Global AFK clears on the user's first message in any shared server.
        global_entry = self._global_afk_cache.get(author_id)
        if global_entry:
            try:
                ctx_check = await self.bot.get_context(message)
                if ctx_check.valid and ctx_check.command and ctx_check.command.name == "gafk":
                    global_entry = None
            except Exception:
                pass
        if global_entry:
            self._global_afk_cache.pop(author_id, None)
            asyncio.create_task(self.bot.db.execute(
                "DELETE FROM user_global_afk WHERE user_id = ?;", author_id
            ))
            elapsed = max((now - global_entry.created_at).total_seconds(), 0.0)
            embed = discord.Embed(
                title=f"{AizenSymbols.SUCCESS} Welcome Back, {message.author.display_name}!",
                description=f"**Global AFK removed**\nReason: {global_entry.reason}\nAway for: {format_duration(elapsed)}",
                color=0x22C55E,
            )
            await message.channel.send(embed=embed)

        # ----------------------------------------------------
        # check if the message author was AFK (Welcome back)
        # ----------------------------------------------------
        if author_key in self._afk_cache:
            # If this message is invoking the afk command, don't trigger welcome back
            if message.content:
                try:
                    ctx = await self.bot.get_context(message)
                    if ctx.valid and ctx.command and ctx.command.qualified_name == "afk":
                        return
                except Exception:
                    pass

            # Atomic pop: ensure welcome back only triggers once
            afk_data = self._afk_cache.pop(author_key, None)
            if not afk_data:
                return

            # AFK status only: Nicknames and server names remain 100% untouched.

            # Remove from database in background
            asyncio.create_task(
                self.bot.db.execute(
                    "DELETE FROM user_afk WHERE user_id = ? AND guild_id = ?;",
                    author_id,
                    guild_id,
                )
            )

            # Check and deliver pending AFK notes / voice mails
            pending_notes = []
            try:
                pending_notes = await self.bot.db.fetch_all(
                    "SELECT sender_name, note, created_at FROM user_afk_notes WHERE target_user_id = $1 AND guild_id = $2 ORDER BY created_at ASC LIMIT 8;",
                    author_id,
                    guild_id,
                )
                if pending_notes:
                    await self.bot.db.execute(
                        "DELETE FROM user_afk_notes WHERE target_user_id = $1 AND guild_id = $2;",
                        author_id,
                        guild_id,
                    )
            except Exception as e:
                logger.debug(f"Failed to fetch AFK notes: {e}")

            # Send welcome back card (Nyxium style)
            dot = "💜"
            if self.bot and hasattr(self.bot, "custom_emojis"):
                dot = self.bot.custom_emojis.get("heart_dot", "💜")

            elapsed_seconds = max((now - afk_data.created_at).total_seconds(), 0.0)
            duration_str = format_duration(elapsed_seconds)
            raw_reason = afk_data.reason.strip() if afk_data.reason else ""
            reason_val = raw_reason if (raw_reason and raw_reason.lower() != "afk") else "None"

            welcome_desc = (
                f"> Welcome back {message.author.mention}! Your AFK status has been removed.\n"
                f"> **Reason:** {reason_val}\n"
                f"> **Away For:** `{duration_str}`\n"
            )
            if pending_notes:
                notes_lines = "\n".join(f"> • **{n.get('sender_name', 'Someone')}:** {n.get('note', '')}" for n in pending_notes)
                welcome_desc += f"\n**Pending Notes ({len(pending_notes)}):**\n{notes_lines}\n"

            welcome_desc += f"\n{dot} Glad to have you back."

            resp = KyokaResponse(
                response_type=ResponseType.SUCCESS,
                title=f"Welcome Back, {message.author.name}!",
                custom_emoji="👋",
                description=welcome_desc,
                thumbnail_url=message.author.display_avatar.url,
                footer_text=f"-# Welcome back {message.author.name}",
            )
            try:
                await send_container_response(message.channel, resp.to_container(bot=self.bot))
            except Exception as e:
                logger.debug(f"Failed to send AFK welcome back notice: {e}")

        # Notify mentions of globally AFK users in any server.
        if message.mentions:
            for target in message.mentions:
                if target.bot or target.id == author_id:
                    continue
                target_afk = self._global_afk_cache.get(target.id)
                if target_afk:
                    dot = "💜"
                    if self.bot and hasattr(self.bot, "custom_emojis"):
                        dot = self.bot.custom_emojis.get("heart_dot", "💜")
                    resp = KyokaResponse(
                        response_type=ResponseType.INFO,
                        title=f"{target.display_name} is Globally AFK",
                        custom_emoji="💤",
                        description=(
                            f"> {target.mention} is currently globally AFK across all shared servers\n"
                            f"> **Reason:** {target_afk.reason}\n"
                            f"> **Away Since:** <t:{int(target_afk.created_at.timestamp())}:R>\n\n"
                            f"{dot} Please refrain from pinging unnecessarily."
                        ),
                        thumbnail_url=target.display_avatar.url,
                        footer_text=f"-# Mentioned by {message.author.name}",
                    )
                    try:
                        await send_container_response(message.channel, resp.to_container(bot=self.bot))
                    except Exception as error:
                        logger.debug("Global AFK mention notice failed: %s", error)

        # ----------------------------------------------------
        # check if any mentioned users are AFK
        # ----------------------------------------------------
        if message.mentions:
            now_ts = time.time()
            for mentioned_user in message.mentions:
                if mentioned_user.id == author_id or mentioned_user.bot:
                    continue

                mentioned_key = (mentioned_user.id, guild_id)
                if mentioned_key in self._afk_cache:
                    cooldown_key = (guild_id, mentioned_user.id, message.channel.id)
                    last_notified = self._mention_cooldowns.get(cooldown_key, 0.0)
                    # 10s cooldown per AFK user per channel to prevent notification spam
                    if now_ts - last_notified < 10.0:
                        continue
                    self._mention_cooldowns[cooldown_key] = now_ts

                    target_afk = self._afk_cache[mentioned_key]
                    raw_reason = target_afk.reason.strip() if target_afk.reason else ""
                    reason_val = raw_reason if (raw_reason and raw_reason.lower() != "afk") else "None"

                    dot = "💜"
                    if self.bot and hasattr(self.bot, "custom_emojis"):
                        dot = self.bot.custom_emojis.get("heart_dot", "💜")

                    mention_desc = (
                        f"> {mentioned_user.mention} is currently AFK in this server\n"
                        f"> **Reason:** {reason_val}\n"
                        f"> **Went AFK:** <t:{int(target_afk.created_at.timestamp())}:R>\n\n"
                        f"{dot} Leave a note using the button below."
                    )

                    resp = KyokaResponse(
                        response_type=ResponseType.INFO,
                        title=f"{mentioned_user.name} is AFK",
                        custom_emoji="💤",
                        description=mention_desc,
                        thumbnail_url=mentioned_user.display_avatar.url,
                        footer_text=f"-# Mentioned by {message.author.name}",
                    )
                    view = AFKLeaveNoteView(self.bot, mentioned_user.id, mentioned_user.display_name, guild_id)
                    try:
                        await send_container_response(message.channel, resp.to_container(bot=self.bot), view=view)
                    except Exception as e:
                        logger.debug(f"Failed to send AFK mention notification: {e}")


async def setup(bot: KyokaBot) -> None:
    """Load the AFKCog into KyokaBot."""
    await bot.add_cog(AFKCog(bot))
