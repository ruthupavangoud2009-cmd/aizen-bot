"""
Kyoka Discord Bot - AntiPing Role Protection Cog
Enforces strict anti-ping rules so no one in the server can mention protected roles.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import TYPE_CHECKING, Optional, Set, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Moderation.AntiPing")


class AntiPingCog(commands.Cog, name="AntiPing"):
    """Server role protection system preventing unauthorized role mentions."""

    category: str = "🛡️・MODERATION"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        # Fast in-memory caches:
        # guild_id -> set of protected role_ids
        self._protected_roles: Dict[int, Set[int]] = {}
        # guild_id -> settings dict {enabled: bool, action: str, timeout_seconds: int}
        self._settings: Dict[int, Dict[str, Any]] = {}
        # guild_id -> set of whitelisted user/role IDs
        self._whitelist: Dict[int, Set[int]] = {}
        self._initialized = False

    async def cog_load(self) -> None:
        """Initialize database tables and populate in-memory lookup cache."""
        try:
            await self._init_database()
            await self._load_cache()
            self._initialized = True
            logger.info("AntiPing system successfully initialized and loaded into cache.")
        except Exception as e:
            logger.exception("Failed initializing AntiPing database/cache: %s", e)

    async def _init_database(self) -> None:
        """Ensure PostgreSQL tables exist for antiping roles and settings."""
        if not hasattr(self.bot, "db") or not self.bot.db:
            return

        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_antiping_roles (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                added_by BIGINT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, role_id)
            );
        """)

        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_antiping_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                action VARCHAR(32) DEFAULT 'delete',
                timeout_seconds INT DEFAULT 60
            );
        """)

        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_antiping_whitelist (
                guild_id BIGINT NOT NULL,
                target_id BIGINT NOT NULL,
                target_type VARCHAR(16) NOT NULL,
                PRIMARY KEY (guild_id, target_id)
            );
        """)

    async def _load_cache(self) -> None:
        """Load all guild antiping configurations into memory for zero-lag lookups."""
        if not hasattr(self.bot, "db") or not self.bot.db:
            return

        # 1. Load roles
        role_rows = await self.bot.db.fetch_all("SELECT guild_id, role_id FROM guild_antiping_roles;")
        roles_by_guild: Dict[int, Set[int]] = {}
        for r in role_rows:
            gid = int(r["guild_id"])
            rid = int(r["role_id"])
            roles_by_guild.setdefault(gid, set()).add(rid)
        self._protected_roles = roles_by_guild

        # 2. Load settings
        sett_rows = await self.bot.db.fetch_all("SELECT guild_id, enabled, action, timeout_seconds FROM guild_antiping_settings;")
        settings_by_guild: Dict[int, Dict[str, Any]] = {}
        for s in sett_rows:
            gid = int(s["guild_id"])
            settings_by_guild[gid] = {
                "enabled": bool(s["enabled"]),
                "action": str(s["action"]).lower(),
                "timeout_seconds": int(s.get("timeout_seconds") or 60),
            }
        self._settings = settings_by_guild

        # 3. Load whitelist
        wl_rows = await self.bot.db.fetch_all("SELECT guild_id, target_id FROM guild_antiping_whitelist;")
        wl_by_guild: Dict[int, Set[int]] = {}
        for w in wl_rows:
            gid = int(w["guild_id"])
            tid = int(w["target_id"])
            wl_by_guild.setdefault(gid, set()).add(tid)
        self._whitelist = wl_by_guild

    def _is_enabled(self, guild_id: int) -> bool:
        sett = self._settings.get(guild_id)
        if sett is None:
            return True
        return bool(sett.get("enabled", True))

    def _get_action(self, guild_id: int) -> tuple[str, int]:
        sett = self._settings.get(guild_id) or {}
        action = sett.get("action", "delete")
        timeout_sec = sett.get("timeout_seconds", 60)
        return action, timeout_sec

    def _is_immune(self, member: discord.Member) -> bool:
        """Check if a member is exempt from antiping enforcement (Server Owner or Whitelist)."""
        guild = member.guild
        # Server owner is immune
        if member.id == guild.owner_id:
            return True

        # Bot primary owner is immune
        from src.security.owner import is_primary_owner
        if is_primary_owner(member.id):
            return True

        wl = self._whitelist.get(guild.id, set())
        if member.id in wl:
            return True

        # Check member roles against whitelist
        if any(r.id in wl for r in member.roles):
            return True

        return False

    async def _handle_violation(self, message: discord.Message, pinged_role: discord.Role) -> None:
        """Execute enforcement when an unauthorized role ping occurs."""
        guild = message.guild
        member = message.author if isinstance(message.author, discord.Member) else (guild.get_member(message.author.id) if guild else None)
        if not guild or not member:
            return

        # 1. Immediately delete the offending message to extinguish the ping
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        action, timeout_sec = self._get_action(guild.id)
        punishment_text = "Message deleted"

        # 2. Execute configured punishment
        if action == "timeout":
            try:
                until = discord.utils.utcnow() + dt.timedelta(seconds=timeout_sec)
                await member.timeout(until, reason=f"Kyoka AntiPing: Pinged protected role @{pinged_role.name}")
                punishment_text = f"Message deleted & Timed out for {timeout_sec}s"
            except Exception as exc:
                logger.debug("Failed applying antiping timeout to %s: %s", member.id, exc)
        elif action == "kick":
            try:
                await member.kick(reason=f"Kyoka AntiPing: Pinged protected role @{pinged_role.name}")
                punishment_text = "Message deleted & Member kicked"
            except Exception as exc:
                logger.debug("Failed applying antiping kick to %s: %s", member.id, exc)

        # 3. Send temporary auto-deleting warning banner in channel
        try:
            container = KyokaContainer(accent_color=None)
            container.add_section(
                content=(
                    f"⚠️ **Protected Role Mention Blocked**\n"
                    f"> {member.mention}, you cannot ping the protected role **@{pinged_role.name}** in this server!\n"
                    f"> *Action taken: `{punishment_text}`*"
                )
            )
            sent = await send_container_response(message.channel, container)
            if sent and hasattr(sent, "delete"):
                import asyncio
                asyncio.create_task(self._auto_delete_msg(sent, delay=7.0))
        except Exception:
            pass

        logger.info(
            "AntiPing violation intercepted: guild=%s author=%s role=@%s action=%s",
            guild.id,
            member.id,
            pinged_role.name,
            action,
        )

    @staticmethod
    async def _auto_delete_msg(msg: discord.Message, delay: float) -> None:
        import asyncio
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except Exception:
            pass

    # ─── REAL-TIME MESSAGE LISTENERS ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Intercept any message that mentions an antiping protected role."""
        if not message.guild or message.author.bot:
            return

        guild_id = message.guild.id
        if not self._is_enabled(guild_id):
            return

        protected_ids = self._protected_roles.get(guild_id)
        if not protected_ids:
            return

        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if not member or self._is_immune(member):
            return

        # Check Discord role mentions objects
        for role in message.role_mentions:
            if role.id in protected_ids:
                await self._handle_violation(message, role)
                return

        # Check raw mention regex <@&ROLE_ID> in text to catch ghost-pings or unrendered raw pings
        if "<@&" in message.content:
            raw_ids = re.findall(r"<@&(\d+)>", message.content)
            for r_id_str in raw_ids:
                r_id = int(r_id_str)
                if r_id in protected_ids:
                    role_obj = message.guild.get_role(r_id)
                    if role_obj:
                        await self._handle_violation(message, role_obj)
                        return

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Intercept stealth message edits that try to sneak in a protected role ping."""
        if not after.guild or after.author.bot:
            return

        guild_id = after.guild.id
        if not self._is_enabled(guild_id):
            return

        protected_ids = self._protected_roles.get(guild_id)
        if not protected_ids:
            return

        member = after.author if isinstance(after.author, discord.Member) else after.guild.get_member(after.author.id)
        if not member or self._is_immune(member):
            return

        # Check Discord role mentions objects
        for role in after.role_mentions:
            if role.id in protected_ids:
                await self._handle_violation(after, role)
                return

        # Check raw mention regex
        if "<@&" in after.content:
            raw_ids = re.findall(r"<@&(\d+)>", after.content)
            for r_id_str in raw_ids:
                r_id = int(r_id_str)
                if r_id in protected_ids:
                    role_obj = after.guild.get_role(r_id)
                    if role_obj:
                        await self._handle_violation(after, role_obj)
                        return

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Ensure protected roles are never made mentionable by accident."""
        guild = after.guild
        protected_ids = self._protected_roles.get(guild.id, set())
        if after.id in protected_ids:
            # If someone tried to enable mentionable, automatically revert it
            if after.mentionable:
                try:
                    await after.edit(
                        mentionable=False,
                        reason="Kyoka AntiPing: Protected role must remain unmentionable",
                    )
                    logger.info("Automatically reverted mentionable=False on protected role %s in %s", after.id, guild.id)
                except Exception as e:
                    logger.debug("Could not auto-revert mentionable on role %s: %s", after.id, e)

    # ─── MANAGEMENT COMMANDS ──────────────────────────────────────────────────

    @commands.hybrid_group(
        name="antiping",
        aliases=["aprole", "antipingrole", "blockping"],
        invoke_without_command=True,
        description="Configure anti-ping role protection so nobody can ping protected roles.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def antiping_group(self, ctx: CustomContext) -> None:
        """Display current AntiPing status, protected roles, and enforcement settings."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        p = ctx.prefix
        protected = self._protected_roles.get(guild_id, set())
        enabled = self._is_enabled(guild_id)
        action, timeout_sec = self._get_action(guild_id)
        wl = self._whitelist.get(guild_id, set())

        status_badge = "🟢 **Active & Protecting**" if enabled else "🔴 **Disabled**"

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**🛡️ Anti-Ping Role Protection**")
        container.add_separator(divider=True)

        # Build list of protected roles
        roles_text = ""
        if protected:
            role_lines = []
            for rid in protected:
                r = ctx.guild.get_role(rid)
                if r:
                    role_lines.append(f"• {r.mention} `@{r.name}` `「{r.id}」`")
                else:
                    role_lines.append(f"• `[Deleted Role: {rid}]`")
            roles_text = "\n".join(role_lines)
        else:
            roles_text = "*No roles currently protected. Add one using `+antiping add @role`!*"

        container.add_text(
            f"**Status:** {status_badge}\n"
            f"**Enforcement Action:** `{action.upper()}`" + (f" (`{timeout_sec}s`)" if action == "timeout" else "") + "\n"
            f"**Protected Roles ({len(protected)}):**\n{roles_text}\n\n"
            f"**Whitelisted Entities ({len(wl)}):** `{len(wl)} exempt users/roles`\n\n"
            f"**Management Commands:**\n"
            f"• `{p}antiping add @role` — Protect a role so no one can ping it\n"
            f"• `{p}antiping remove @role` — Remove a role from protection\n"
            f"• `{p}antiping list` — View all protected roles\n"
            f"• `{p}antiping action <delete|timeout|kick>` — Set punishment\n"
            f"• `{p}antiping timeout <seconds>` — Configure timeout duration\n"
            f"• `{p}antiping whitelist add/remove <@user/@role>` — Manage immunity\n"
            f"• `{p}antiping enable / disable` — Toggle system"
        )
        await send_container_response(ctx, container)

    @antiping_group.command(name="add", description="Add a role to anti-ping protection so nobody can ping it.")
    @app_commands.describe(role="Role to protect from being pinged")
    @commands.has_permissions(manage_roles=True)
    async def antiping_add(self, ctx: CustomContext, role: discord.Role) -> None:
        """Protect a role so that anyone who mentions it has their message deleted and penalized."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        if role.is_default():
            await ctx.send_error("You cannot add `@everyone` as an antiping role. Use `+antinuke` for everyone protection.")
            return

        protected = self._protected_roles.setdefault(guild_id, set())
        if role.id in protected:
            await ctx.send_warning(f"{role.mention} is already protected by AntiPing!")
            return

        # 1. Save to Database
        await self.bot.db.execute(
            """INSERT INTO guild_antiping_roles (guild_id, role_id, added_by)
               VALUES (?, ?, ?) ON CONFLICT (guild_id, role_id) DO NOTHING""",
            guild_id, role.id, ctx.author.id,
        )

        # 2. Update cache
        protected.add(role.id)

        # 3. Best effort: disable mentionable on Discord role so it doesn't suggest in chat
        mentionable_note = ""
        if role.mentionable:
            try:
                if ctx.guild.me.guild_permissions.manage_roles and ctx.guild.me.top_role > role:
                    await role.edit(mentionable=False, reason=f"Kyoka AntiPing: Protected by {ctx.author}")
                    mentionable_note = "\n> *Role mentionable setting was automatically set to `False`.*"
            except Exception:
                pass

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Role Added to AntiPing Protection**")
        container.add_separator(divider=True)
        container.add_text(
            f"✅ **Protected Role:** {role.mention} `@{role.name}` `「{role.id}」`\n\n"
            f"> Anyone who mentions this role in chat will immediately have their message deleted and face the configured punishment.{mentionable_note}"
        )
        await send_container_response(ctx, container)

    @antiping_group.command(name="remove", description="Remove a role from anti-ping protection.")
    @app_commands.describe(role="Role to remove from anti-ping protection")
    @commands.has_permissions(manage_roles=True)
    async def antiping_remove(self, ctx: CustomContext, role: discord.Role) -> None:
        """Remove a role from anti-ping protection."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        protected = self._protected_roles.get(guild_id, set())
        if role.id not in protected:
            await ctx.send_warning(f"{role.mention} is not currently in the AntiPing protected list.")
            return

        # 1. Delete from database
        await self.bot.db.execute(
            "DELETE FROM guild_antiping_roles WHERE guild_id = ? AND role_id = ?",
            guild_id, role.id,
        )

        # 2. Update cache
        protected.discard(role.id)

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Role Removed from AntiPing Protection**")
        container.add_separator(divider=True)
        container.add_text(f"🗑️ {role.mention} `@{role.name}` has been removed from AntiPing protection.")
        await send_container_response(ctx, container)

    @antiping_group.command(name="list", description="List all roles protected by AntiPing in this server.")
    @commands.has_permissions(manage_roles=True)
    async def antiping_list(self, ctx: CustomContext) -> None:
        """Show all protected roles in this server."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        protected = self._protected_roles.get(guild_id, set())
        if not protected:
            await ctx.send_info("No roles are currently protected by AntiPing in this server. Use `+antiping add @role` to add one.")
            return

        lines = []
        for rid in sorted(list(protected)):
            r = ctx.guild.get_role(rid)
            if r:
                lines.append(f"• {r.mention} `@{r.name}` — `{len(r.members)} member(s)` `「{r.id}」`")
            else:
                lines.append(f"• `[Deleted Role: {rid}]`")

        container = KyokaContainer(accent_color=None)
        container.add_section(content=f"**Protected AntiPing Roles ({len(protected)})**")
        container.add_separator(divider=True)
        container.add_text("\n".join(lines))
        await send_container_response(ctx, container)

    @antiping_group.command(name="action", description="Set the punishment action when someone mentions a protected role.")
    @app_commands.describe(action="Punishment action: delete, timeout, or kick")
    @app_commands.choices(action=[
        app_commands.Choice(name="Delete Message Only", value="delete"),
        app_commands.Choice(name="Delete & Timeout Member", value="timeout"),
        app_commands.Choice(name="Delete & Kick Member", value="kick"),
    ])
    @commands.has_permissions(manage_guild=True)
    async def antiping_action(self, ctx: CustomContext, action: str) -> None:
        """Configure the penalty for unauthorized role pings."""
        if not ctx.guild:
            return

        act = action.lower().strip()
        if act not in ("delete", "timeout", "kick"):
            await ctx.send_error("Invalid action! Choose from `delete`, `timeout`, or `kick`.")
            return

        guild_id = ctx.guild.id
        sett = self._settings.setdefault(guild_id, {"enabled": True, "action": "delete", "timeout_seconds": 60})
        sett["action"] = act

        await self.bot.db.execute(
            """INSERT INTO guild_antiping_settings (guild_id, enabled, action, timeout_seconds)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (guild_id) DO UPDATE SET action = EXCLUDED.action""",
            guild_id, sett.get("enabled", True), act, sett.get("timeout_seconds", 60),
        )

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**AntiPing Action Updated**")
        container.add_separator(divider=True)
        container.add_text(f"Action when someone mentions a protected role is now set to **`{act.upper()}`**.")
        await send_container_response(ctx, container)

    @antiping_group.command(name="timeout", description="Set the timeout duration in seconds if action is timeout.")
    @app_commands.describe(seconds="Timeout duration in seconds (10 to 3600)")
    @commands.has_permissions(manage_guild=True)
    async def antiping_timeout(self, ctx: CustomContext, seconds: int) -> None:
        """Set timeout duration for role ping violations."""
        if not ctx.guild:
            return

        if seconds < 10 or seconds > 3600:
            await ctx.send_error("Timeout duration must be between 10 and 3600 seconds (1 hour).")
            return

        guild_id = ctx.guild.id
        sett = self._settings.setdefault(guild_id, {"enabled": True, "action": "delete", "timeout_seconds": 60})
        sett["timeout_seconds"] = seconds

        await self.bot.db.execute(
            """INSERT INTO guild_antiping_settings (guild_id, enabled, action, timeout_seconds)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (guild_id) DO UPDATE SET timeout_seconds = EXCLUDED.timeout_seconds""",
            guild_id, sett.get("enabled", True), sett.get("action", "delete"), seconds,
        )

        await ctx.send_success(f"AntiPing timeout penalty duration set to **`{seconds} seconds`**.")

    @antiping_group.command(name="enable", description="Enable AntiPing protection for this server.")
    @commands.has_permissions(manage_guild=True)
    async def antiping_enable(self, ctx: CustomContext) -> None:
        """Enable AntiPing protection."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        sett = self._settings.setdefault(guild_id, {"enabled": True, "action": "delete", "timeout_seconds": 60})
        sett["enabled"] = True

        await self.bot.db.execute(
            """INSERT INTO guild_antiping_settings (guild_id, enabled, action, timeout_seconds)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (guild_id) DO UPDATE SET enabled = TRUE""",
            guild_id, True, sett.get("action", "delete"), sett.get("timeout_seconds", 60),
        )
        await ctx.send_success("AntiPing role protection is now **enabled**.")

    @antiping_group.command(name="disable", description="Disable AntiPing protection for this server.")
    @commands.has_permissions(manage_guild=True)
    async def antiping_disable(self, ctx: CustomContext) -> None:
        """Disable AntiPing protection."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        sett = self._settings.setdefault(guild_id, {"enabled": False, "action": "delete", "timeout_seconds": 60})
        sett["enabled"] = False

        await self.bot.db.execute(
            """INSERT INTO guild_antiping_settings (guild_id, enabled, action, timeout_seconds)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (guild_id) DO UPDATE SET enabled = FALSE""",
            guild_id, False, sett.get("action", "delete"), sett.get("timeout_seconds", 60),
        )
        await ctx.send_success("AntiPing role protection is now **disabled**.")

    @antiping_group.command(name="whitelist", description="Exempt a user or role from AntiPing enforcement.")
    @app_commands.describe(
        action="add or remove",
        target="User or Role to exempt",
    )
    @commands.has_permissions(administrator=True)
    async def antiping_whitelist(
        self,
        ctx: CustomContext,
        action: str,
        target: discord.User | discord.Role,
    ) -> None:
        """Add or remove an exempt user or role from AntiPing."""
        if not ctx.guild:
            return

        act = action.lower().strip()
        guild_id = ctx.guild.id
        wl = self._whitelist.setdefault(guild_id, set())
        is_role = isinstance(target, discord.Role)
        target_type = "role" if is_role else "user"

        if act == "add":
            if target.id in wl:
                await ctx.send_warning(f"{target.mention} is already whitelisted from AntiPing.")
                return
            await self.bot.db.execute(
                """INSERT INTO guild_antiping_whitelist (guild_id, target_id, target_type)
                   VALUES (?, ?, ?) ON CONFLICT DO NOTHING""",
                guild_id, target.id, target_type,
            )
            wl.add(target.id)
            await ctx.send_success(f"{target.mention} is now **whitelisted** and allowed to ping protected roles.")
        elif act in ("remove", "delete"):
            if target.id not in wl:
                await ctx.send_warning(f"{target.mention} is not in the AntiPing whitelist.")
                return
            await self.bot.db.execute(
                "DELETE FROM guild_antiping_whitelist WHERE guild_id = ? AND target_id = ?",
                guild_id, target.id,
            )
            wl.discard(target.id)
            await ctx.send_success(f"{target.mention} has been **removed** from the AntiPing whitelist.")
        else:
            await ctx.send_error("Invalid action! Use `add` or `remove`.")

    @antiping_group.command(name="reset", description="Clear all AntiPing protected roles and reset server settings.")
    @commands.has_permissions(administrator=True)
    async def antiping_reset(self, ctx: CustomContext) -> None:
        """Reset all AntiPing roles and configuration for this server."""
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        await self.bot.db.execute("DELETE FROM guild_antiping_roles WHERE guild_id = ?", guild_id)
        await self.bot.db.execute("DELETE FROM guild_antiping_settings WHERE guild_id = ?", guild_id)
        await self.bot.db.execute("DELETE FROM guild_antiping_whitelist WHERE guild_id = ?", guild_id)

        self._protected_roles.pop(guild_id, None)
        self._settings.pop(guild_id, None)
        self._whitelist.pop(guild_id, None)

        await ctx.send_success("All AntiPing protected roles and server configurations have been reset.")


async def setup(bot: KyokaBot) -> None:
    """Load the AntiPingCog into KyokaBot."""
    await bot.add_cog(AntiPingCog(bot))
