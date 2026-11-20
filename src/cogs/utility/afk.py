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
            if emoji:
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
        """Load persistent AFK states from database into memory on cog startup."""
        asyncio.create_task(self._load_afk_cache())

    async def _load_afk_cache(self) -> None:
        """Initialize AFK table and populate in-memory cache."""
        try:
            # Ensure table exists in case migration hasn't executed
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

        # Dispatch confirmation container
        e_reg = getattr(self.bot, "custom_emojis", None)
        heart_dot = _afk_emoji(self.bot, "heart_dot", "success", "kyoka")
        status_emoji = _afk_emoji(self.bot, "afk", "loading", "kyoka")
        dot_str = f"{heart_dot} " if heart_dot else ""

        container = KyokaContainer(accent_color=None)
        # Title: Username AFK (no @tag)
        container.add_text(f"### {status_emoji} {ctx.author.name} AFK".strip())
        container.add_separator(divider=True)

        # Description: Reason, Went AFK, Tag with heart_dot
        reason_emoji = _afk_emoji(self.bot, "command", "icon_info")
        time_emoji = _afk_emoji(self.bot, "ping", "icon_ping")
        user_emoji = _afk_emoji(self.bot, "members", "icon_users")
        body_lines = [
            f"{reason_emoji} **Reason:** {final_reason}",
            f"{time_emoji} **Went AFK:** <t:{int(now.timestamp())}:R>",
            f"{user_emoji} **Tag:** {ctx.author.mention}",
        ]
        container.add_section(content="\n".join(body_lines))

        # User profile thumbnail
        container.add_thumbnail(ctx.author.display_avatar.url)

        # Divider & Requested by footer
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.name}")

        await send_container_response(ctx, container)

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
        afk_icon = _afk_emoji(self.bot, "afk", "loading", "kyoka")
        success_icon = _afk_emoji(self.bot, "success", "icon_success")
        embed = discord.Embed(
            title=f"{afk_icon} {success_icon} Global AFK Activated",
            description=f"**{ctx.author.mention}** is now globally AFK.\n\n**Reason:** {final_reason}\n**Scope:** All shared servers",
            color=0x22C55E,
            timestamp=now,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Global AFK • Mentions will be notified in shared servers")
        await ctx.send(embed=embed)

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

            # Send welcome back card immediately
            heart_dot = _afk_emoji(self.bot, "heart_dot", "success", "kyoka")
            status_emoji = _afk_emoji(self.bot, "success", "icon_success", "kyoka")
            dot_str = f"{heart_dot} " if heart_dot else ""
            elapsed_seconds = max((now - afk_data.created_at).total_seconds(), 0.0)
            duration_str = format_duration(elapsed_seconds)

            raw_reason = afk_data.reason.strip() if afk_data.reason else ""
            reason_val = raw_reason if (raw_reason and raw_reason.lower() != "afk") else "None"

            container = KyokaContainer(accent_color=None)
            container.add_text(f"### {status_emoji} Welcome Back, {message.author.name}!")
            container.add_separator(divider=True)

            reason_emoji = _afk_emoji(self.bot, "command", "icon_info")
            duration_emoji = _afk_emoji(self.bot, "ping", "icon_ping")
            body_lines = [
                f"{reason_emoji} **Reason:** {reason_val}",
                f"{duration_emoji} **AFK Removed:** `{duration_str}`",
            ]

            if pending_notes:
                note_emoji = _afk_emoji(self.bot, "ticket", "icon_ticket")
                body_lines.append(f"{note_emoji} **Notes:** {len(pending_notes)} Note{'s' if len(pending_notes) > 1 else ''}")
                for n in pending_notes:
                    s_name = n.get("sender_name", "Someone")
                    note_msg = n.get("note", "")
                    body_lines.append(f"> **{s_name}:** {note_msg}")
            else:
                note_emoji = _afk_emoji(self.bot, "ticket", "icon_ticket")
                body_lines.append(f"{note_emoji} **Notes:** None")

            container.add_section(content="\n".join(body_lines))
            container.add_thumbnail(message.author.display_avatar.url)
            container.add_separator(divider=True)
            container.add_text(f"-# Welcome back {message.author.name}")

            try:
                await send_container_response(message.channel, container)
            except Exception as e:
                logger.debug(f"Failed to send AFK welcome back notice: {e}")

        # Notify mentions of globally AFK users in any server.
        if message.mentions:
            for target in message.mentions:
                if target.bot or target.id == author_id:
                    continue
                target_afk = self._global_afk_cache.get(target.id)
                if target_afk:
                    embed = discord.Embed(
                        title=f"{_afk_emoji(self.bot, 'afk', 'loading', 'kyoka')} {target.display_name} is Globally AFK",
                        description=f"**Reason:** {target_afk.reason}\n**Away since:** <t:{int(target_afk.created_at.timestamp())}:R>",
                        color=0x7C3AED,
                    )
                    embed.set_thumbnail(url=target.display_avatar.url)
                    try:
                        await message.channel.send(embed=embed)
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
                    heart_dot = _afk_emoji(self.bot, "heart_dot", "success", "kyoka")
                    dot_str = f"{heart_dot} " if heart_dot else ""

                    raw_reason = target_afk.reason.strip() if target_afk.reason else ""
                    reason_val = raw_reason if (raw_reason and raw_reason.lower() != "afk") else "None"

                    container = KyokaContainer(accent_color=None)
                    afk_icon = _afk_emoji(self.bot, "afk", "loading", "kyoka")
                    container.add_text(f"### {afk_icon} {mentioned_user.name}'s AFK".strip())
                    container.add_separator(divider=True)

                    reason_emoji = _afk_emoji(self.bot, "command", "icon_info")
                    time_emoji = _afk_emoji(self.bot, "ping", "icon_ping")
                    user_emoji = _afk_emoji(self.bot, "members", "icon_users")
                    body_lines = [
                        f"{reason_emoji} **Reason:** {reason_val}",
                        f"{time_emoji} **Went AFK:** <t:{int(target_afk.created_at.timestamp())}:R>",
                        f"{user_emoji} **Tag:** {mentioned_user.mention}",
                    ]
                    container.add_section(content="\n".join(body_lines))

                    container.add_thumbnail(mentioned_user.display_avatar.url)

                    container.add_separator(divider=True)
                    container.add_text(f"-# Mentioned by {message.author.name}")
                    container.add_separator(divider=True)

                    view = AFKLeaveNoteView(self.bot, mentioned_user.id, mentioned_user.display_name, guild_id)
                    try:
                        await send_container_response(message.channel, container, view=view)
                    except Exception as e:
                        logger.debug(f"Failed to send AFK mention notification: {e}")


async def setup(bot: KyokaBot) -> None:
    """Load the AFKCog into KyokaBot."""
    await bot.add_cog(AFKCog(bot))
