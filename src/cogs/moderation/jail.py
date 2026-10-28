"""
Kyoka 3.0 - Server Jail & Isolation System
Inspired by Greed bot's jail and detention suite.
Isolates delinquent members by stripping their roles, assigning a Jailed role,
and restricting them to a designated #jail channel, with automatic role restoration on unjail.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


def parse_time_duration(time_str: str) -> Optional[datetime.timedelta]:
    """Parse time string like 10m, 2h, 1d into timedelta."""
    match = re.match(r"^(\d+)\s*(s|m|h|d|w)$", time_str.lower().strip())
    if not match:
        return None
    val = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return datetime.timedelta(seconds=val)
    elif unit == "m":
        return datetime.timedelta(minutes=val)
    elif unit == "h":
        return datetime.timedelta(hours=val)
    elif unit == "d":
        return datetime.timedelta(days=val)
    elif unit == "w":
        return datetime.timedelta(weeks=val)
    return None


class Jail(commands.Cog, name="Moderation-Jail"):
    """
    Greed-style Jail & Isolation detention system.
    Strips offending members of roles, locks them into #jail channel, and auto-restores roles on release.
    """
    category = "🛡️・MODERATION & SECURITY"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._unjailed_tasks: Dict[tuple[int, int], asyncio.Task] = {}

    async def cog_load(self) -> None:
        """Initialize database tables for jail configurations and detained users."""
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_jail_settings (
                        guild_id BIGINT PRIMARY KEY,
                        role_id BIGINT,
                        channel_id BIGINT,
                        log_channel_id BIGINT,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_jailed_users (
                        guild_id BIGINT,
                        user_id BIGINT,
                        moderator_id BIGINT,
                        reason TEXT,
                        stripped_roles JSONB,
                        jailed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        PRIMARY KEY (guild_id, user_id)
                    );
                    """
                )
            except Exception:
                pass

    # ─── JAIL COMMAND GROUP ──────────────────────────────────────────────────

    @commands.group(
        name="jail",
        invoke_without_command=True,
        description="Greed-style member isolation detention system.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def jail_group(self, ctx: CustomContext, member: Optional[discord.Member] = None, *, rest: str = "") -> None:
        """Jail a member or view jail panel."""
        if not member:
            return await self.cmd_help(ctx)

        # Parse duration and reason
        # rest can be: "10m spamming" or "spamming and toxic"
        parts = rest.strip().split(maxsplit=1)
        duration_delta = None
        reason = "No reason provided."

        if parts:
            possible_duration = parse_time_duration(parts[0])
            if possible_duration:
                duration_delta = possible_duration
                reason = parts[1] if len(parts) > 1 else reason
            else:
                reason = rest

        await self._jail_member(ctx, member, reason=reason, duration=duration_delta)

    @jail_group.command(name="help", help="View jail system commands.")
    @commands.guild_only()
    async def cmd_help(self, ctx: CustomContext) -> None:
        """Display jail system manual."""
        p = ctx.clean_prefix
        container = KyokaContainer(accent_color=None)
        container.add_text("**⛓️ KYOKA Jail & Detention System**")
        container.add_separator(divider=True)
        container.add_text(
            f"• `{p}jail <@user> [duration] [reason]` — Strip roles and isolate user in jail\n"
            f"• `{p}unjail <@user> [reason]` — Release user and restore all original roles\n"
            f"• `{p}jail setup` — Automatically provision Jailed role and #jail channel\n"
            f"• `{p}jail setrole <@role>` — Configure existing role as Jailed role\n"
            f"• `{p}jail setchannel <#channel>` — Configure existing channel as jail\n"
            f"• `{p}jail list` — View all currently jailed users in this server\n\n"
            f"*Example: `{p}jail @Troll 30m Raiding and spamming`*"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @jail_group.command(name="setup", help="Automatically create Jailed role and #jail channel.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def cmd_setup(self, ctx: CustomContext) -> None:
        """Automatically create Jailed role and #jail channel with proper permissions."""
        guild = ctx.guild
        if not guild:
            return

        async with ctx.typing():
            # 1. Create or find Jailed role
            jail_role = discord.utils.get(guild.roles, name="Jailed")
            if not jail_role:
                try:
                    jail_role = await guild.create_role(
                        name="Jailed",
                        color=discord.Color.dark_gray(),
                        reason="KYOKA Jail System Setup",
                    )
                except Exception as e:
                    return await ctx.send_error(f"Failed to create 'Jailed' role: {e}")

            # 2. Create or find #jail channel
            jail_ch = discord.utils.get(guild.text_channels, name="jail")
            if not jail_ch:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    jail_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
                }
                try:
                    jail_ch = await guild.create_text_channel(
                        name="jail",
                        overwrites=overwrites,
                        topic="⛓️ Detention facility. You have been isolated by server staff.",
                        reason="KYOKA Jail System Setup",
                    )
                except Exception as e:
                    return await ctx.send_error(f"Failed to create '#jail' channel: {e}")

            # Save in database
            if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
                try:
                    await self.bot.db.execute(
                        """
                        INSERT INTO guild_jail_settings (guild_id, role_id, channel_id)
                        VALUES (?, ?, ?)
                        ON CONFLICT (guild_id) DO UPDATE SET
                            role_id = EXCLUDED.role_id,
                            channel_id = EXCLUDED.channel_id,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        guild.id,
                        jail_role.id,
                        jail_ch.id,
                    )
                except Exception:
                    pass

        container = KyokaContainer(accent_color=None)
        container.add_text("**✅ Jail System Setup Complete**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Jailed Role:** {jail_role.mention}\n"
            f"• **Jail Channel:** {jail_ch.mention}\n\n"
            f"> Offending members will be stripped of their normal roles and restricted to {jail_ch.mention}."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @jail_group.command(name="list", help="View all currently jailed users.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def cmd_list(self, ctx: CustomContext) -> None:
        """View all currently detained members."""
        guild = ctx.guild
        if not guild:
            return

        rows = []
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_all"):
            try:
                rows = await self.bot.db.fetch_all(
                    "SELECT user_id, moderator_id, reason, jailed_at, expires_at FROM guild_jailed_users WHERE guild_id = ?;",
                    guild.id,
                )
            except Exception:
                pass

        container = KyokaContainer(accent_color=None)
        container.add_text(f"**⛓️ Currently Jailed Inmates • {guild.name}**")
        container.add_separator(divider=True)

        if not rows:
            container.add_text("> The jail is currently empty. No members are detained.")
        else:
            lines = []
            for r in rows:
                uid = r["user_id"]
                mod_id = r["moderator_id"]
                reason = r["reason"] or "No reason specified"
                exp = r["expires_at"]
                exp_str = f"<t:{int(exp.timestamp())}:R>" if exp else "Indefinite"
                lines.append(f"• <@{uid}> (`{uid}`) — Exp: {exp_str}\n  > *Reason:* {reason} *(by <@{mod_id}>)*")
            container.add_text("\n\n".join(lines))

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.command(
        name="unjail",
        aliases=["release"],
        description="Release a member from jail and restore their original roles.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def unjail_cmd(self, ctx: CustomContext, member: discord.Member, *, reason: str = "Released by staff.") -> None:
        """Release a detained member and restore their roles."""
        await self._unjail_member(ctx, member, reason=reason)

    # ─── CORE JAIL ENGINE ─────────────────────────────────────────────────────

    async def _get_jail_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_one"):
            try:
                return await self.bot.db.fetch_one(
                    "SELECT role_id, channel_id FROM guild_jail_settings WHERE guild_id = ?;",
                    guild_id,
                )
            except Exception:
                pass
        return None

    async def _jail_member(
        self,
        ctx: CustomContext,
        member: discord.Member,
        reason: str,
        duration: Optional[datetime.timedelta] = None,
    ) -> None:
        """Execute role stripping, assign Jailed role, and record in DB."""
        guild = ctx.guild
        if not guild:
            return

        if member.id == ctx.author.id:
            return await ctx.send_error("You cannot jail yourself!")
        if member.id == guild.me.id:
            return await ctx.send_error("I cannot jail myself!")
        def _get_pos(obj: Any) -> int:
            pos = getattr(obj, "position", 0)
            return pos if isinstance(pos, int) else 0

        author_pos = _get_pos(ctx.author.top_role)
        member_pos = _get_pos(member.top_role)
        bot_pos = _get_pos(guild.me.top_role)

        if member_pos >= author_pos and ctx.author.id != guild.owner_id:
            return await ctx.send_error("You cannot jail someone with an equal or higher role than you!")
        if member_pos >= bot_pos:
            return await ctx.send_error("I cannot jail this user because their role is higher than my highest role!")

        settings = await self._get_jail_settings(guild.id)
        role_id = settings["role_id"] if settings else None
        jail_role = guild.get_role(role_id) if role_id else discord.utils.get(guild.roles, name="Jailed")

        if not jail_role:
            return await ctx.send_error(f"Jail role not found. Please run `{ctx.clean_prefix}jail setup` first!")

        # 1. Collect roles to strip
        roles_to_strip = [
            r for r in member.roles
            if not r.is_default() and not getattr(r, "managed", False) and _get_pos(r) < bot_pos
        ]
        stripped_ids = [r.id for r in roles_to_strip]

        expires_at = None
        if duration:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + duration

        # 2. Remove roles & add Jailed role
        try:
            if roles_to_strip:
                await member.remove_roles(*roles_to_strip, reason=f"Jailed: {reason}")
            await member.add_roles(jail_role, reason=f"Jailed: {reason}")
        except Exception as e:
            return await ctx.send_error(f"Failed to update roles for {member.mention}: {e}")

        # 3. Save to database
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO guild_jailed_users (guild_id, user_id, moderator_id, reason, stripped_roles, expires_at)
                    VALUES (?, ?, ?, ?, ?::jsonb, ?)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        moderator_id = EXCLUDED.moderator_id,
                        reason = EXCLUDED.reason,
                        stripped_roles = EXCLUDED.stripped_roles,
                        expires_at = EXCLUDED.expires_at,
                        jailed_at = CURRENT_TIMESTAMP;
                    """,
                    guild.id,
                    member.id,
                    ctx.author.id,
                    reason,
                    json.dumps(stripped_ids),
                    expires_at,
                )
            except Exception:
                pass

        # 4. Schedule automatic unjail timer if duration was given
        if duration:
            task_key = (guild.id, member.id)
            if task_key in self._unjailed_tasks:
                self._unjailed_tasks[task_key].cancel()

            async def _auto_unjail():
                await asyncio.sleep(duration.total_seconds())
                try:
                    await self._unjail_member(ctx, member, reason="Jail sentence completed.")
                except Exception:
                    pass

            self._unjailed_tasks[task_key] = asyncio.create_task(_auto_unjail())

        dur_text = f"**Duration:** `{str(duration)}`\n" if duration else ""
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**⛓️ Member Detained • {member.display_name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Inmate:** {member.mention} (`{member.id}`)\n"
            f"• **Moderator:** {ctx.author.mention}\n"
            f"{dur_text}"
            f"• **Reason:** {reason}\n"
            f"• **Roles Stripped:** `{len(stripped_ids)} role(s) archived`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Action executed by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    async def _unjail_member(self, ctx: CustomContext, member: discord.Member, reason: str) -> None:
        """Release detained member, restore original roles, and clean up database record."""
        guild = ctx.guild
        if not guild:
            return

        row = None
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_one"):
            try:
                row = await self.bot.db.fetch_one(
                    "SELECT stripped_roles FROM guild_jailed_users WHERE guild_id = ? AND user_id = ?;",
                    guild.id,
                    member.id,
                )
            except Exception:
                pass

        settings = await self._get_jail_settings(guild.id)
        role_id = settings["role_id"] if settings else None
        jail_role = guild.get_role(role_id) if role_id else discord.utils.get(guild.roles, name="Jailed")

        # 1. Remove jail role
        if jail_role and jail_role in member.roles:
            try:
                await member.remove_roles(jail_role, reason=f"Unjailed: {reason}")
            except Exception:
                pass

        # 2. Restore stripped roles
        restored_count = 0
        if row and row.get("stripped_roles"):
            raw_ids = row["stripped_roles"]
            if isinstance(raw_ids, str):
                try:
                    raw_ids = json.loads(raw_ids)
                except Exception:
                    raw_ids = []
            if isinstance(raw_ids, list):
                bot_pos = getattr(guild.me.top_role, "position", 0)
                bot_pos = bot_pos if isinstance(bot_pos, int) else 0
                roles_to_restore = [guild.get_role(rid) for rid in raw_ids if guild.get_role(rid)]
                roles_to_restore = [
                    r for r in roles_to_restore
                    if r and (getattr(r, "position", 0) if isinstance(getattr(r, "position", 0), int) else 0) < bot_pos
                ]
                if roles_to_restore:
                    try:
                        await member.add_roles(*roles_to_restore, reason=f"Unjailed: {reason}")
                        restored_count = len(roles_to_restore)
                    except Exception:
                        pass

        # 3. Clean up DB record
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    "DELETE FROM guild_jailed_users WHERE guild_id = ? AND user_id = ?;",
                    guild.id,
                    member.id,
                )
            except Exception:
                pass

        task_key = (guild.id, member.id)
        if task_key in self._unjailed_tasks:
            self._unjailed_tasks.pop(task_key).cancel()

        container = KyokaContainer(accent_color=None)
        container.add_text(f"**🕊️ Member Released • {member.display_name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Member:** {member.mention} (`{member.id}`)\n"
            f"• **Moderator:** {ctx.author.mention}\n"
            f"• **Reason:** {reason}\n"
            f"• **Roles Restored:** `{restored_count} role(s) restored`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Action executed by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Jail(bot))
