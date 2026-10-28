"""
Kyoka 3.0 - Fake Permissions System
Inspired by Greed bot's Fake Permissions (fakeperms) architecture.
Allows server administrators to delegate moderation command execution to staff roles
without assigning dangerous native Discord guild permissions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

VALID_PERMISSIONS = {
    "ban_members",
    "kick_members",
    "moderate_members",
    "manage_messages",
    "manage_channels",
    "manage_roles",
    "manage_nicknames",
    "manage_guild",
    "view_audit_log",
    "mention_everyone",
    "deafen_members",
    "mute_members",
    "move_members",
}


class FakePerms(commands.Cog, name="Admin-FakePerms"):
    """
    Greed-style Fake Permissions (fakeperms) suite.
    Enables granular bot command authorization for staff roles without dangerous native Discord permissions.
    """
    category = "⚙️・ADMINISTRATION & CONFIG"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        # guild_id -> role_id -> set(perm_names)
        self._cache: Dict[int, Dict[int, Set[str]]] = {}

    async def cog_load(self) -> None:
        """Initialize database table for fake permissions and load memory cache."""
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_fake_permissions (
                        guild_id BIGINT,
                        role_id BIGINT,
                        permission TEXT,
                        granted_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (guild_id, role_id, permission)
                    );
                    """
                )
            except Exception:
                pass
        await self._load_cache()

    async def _load_cache(self) -> None:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_all"):
            try:
                rows = await self.bot.db.fetch_all("SELECT guild_id, role_id, permission FROM guild_fake_permissions;")
                self._cache.clear()
                for r in rows:
                    gid = r["guild_id"]
                    rid = r["role_id"]
                    perm = r["permission"]
                    if gid not in self._cache:
                        self._cache[gid] = {}
                    if rid not in self._cache[gid]:
                        self._cache[gid][rid] = set()
                    self._cache[gid][rid].add(perm)
            except Exception:
                pass

    def has_fake_perm(self, member: discord.Member, perm_name: str) -> bool:
        """Check if any of member's roles have the specified fake permission."""
        if not member.guild:
            return False
        guild_perms = self._cache.get(member.guild.id, {})
        for role in member.roles:
            if role.id in guild_perms and perm_name in guild_perms[role.id]:
                return True
        return False

    def get_member_fake_perms(self, member: discord.Member) -> Set[str]:
        """Get the full set of fake permissions granted to member through their roles."""
        res: Set[str] = set()
        if not member.guild:
            return res
        guild_perms = self._cache.get(member.guild.id, {})
        for role in member.roles:
            if role.id in guild_perms:
                res.update(guild_perms[role.id])
        return res

    # ─── COMMAND GROUP ────────────────────────────────────────────────────────

    @commands.group(
        name="fakeperms",
        aliases=["fakeperm", "fp"],
        invoke_without_command=True,
        description="Greed-style fake permission delegation for staff.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def fakeperms_group(self, ctx: CustomContext) -> None:
        """Display fake permissions help and available permissions."""
        p = ctx.clean_prefix
        valid_list = ", ".join(f"`{p}`" for p in sorted(VALID_PERMISSIONS))

        container = KyokaContainer(accent_color=None)
        container.add_text("**🛡️ KYOKA Fake Permissions (fakeperms) Suite**")
        container.add_separator(divider=True)
        container.add_text(
            f"• `{p}fakeperms grant <@role> <permission>` — Grant bot permission to role\n"
            f"• `{p}fakeperms revoke <@role> <permission>` — Revoke bot permission from role\n"
            f"• `{p}fakeperms list` — View all fake permissions in this server\n"
            f"• `{p}fakeperms check [@user]` — Check effective permissions for a user\n"
            f"• `{p}fakeperms clear` — Wipe all fake permissions in this server\n\n"
            f"**Supported Permissions:**\n{valid_list}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @fakeperms_group.command(name="grant", help="Grant a fake permission to a role.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def cmd_grant(self, ctx: CustomContext, role: discord.Role, permission: str) -> None:
        """Grant a fake permission to a role."""
        perm_clean = permission.lower().strip()
        if perm_clean not in VALID_PERMISSIONS:
            return await ctx.send_error(
                f"Unknown permission `{perm_clean}`. Choose from: {', '.join(f'`{p}`' for p in sorted(VALID_PERMISSIONS))}"
            )

        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO guild_fake_permissions (guild_id, role_id, permission, granted_by)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (guild_id, role_id, permission) DO NOTHING;
                    """,
                    ctx.guild.id,
                    role.id,
                    perm_clean,
                    ctx.author.id,
                )
            except Exception:
                pass

        if ctx.guild.id not in self._cache:
            self._cache[ctx.guild.id] = {}
        if role.id not in self._cache[ctx.guild.id]:
            self._cache[ctx.guild.id][role.id] = set()
        self._cache[ctx.guild.id][role.id].add(perm_clean)

        container = KyokaContainer(accent_color=None)
        container.add_text("**✅ Fake Permission Granted**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Role:** {role.mention}\n"
            f"• **Permission:** `{perm_clean}`\n\n"
            f"> Members with {role.mention} can now execute commands requiring `{perm_clean}` without native Discord permission."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @fakeperms_group.command(name="revoke", help="Revoke a fake permission from a role.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def cmd_revoke(self, ctx: CustomContext, role: discord.Role, permission: str) -> None:
        """Revoke a fake permission from a role."""
        perm_clean = permission.lower().strip()

        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    "DELETE FROM guild_fake_permissions WHERE guild_id = ? AND role_id = ? AND permission = ?;",
                    ctx.guild.id,
                    role.id,
                    perm_clean,
                )
            except Exception:
                pass

        if ctx.guild.id in self._cache and role.id in self._cache[ctx.guild.id]:
            self._cache[ctx.guild.id][role.id].discard(perm_clean)

        container = KyokaContainer(accent_color=None)
        container.add_text("**🗑️ Fake Permission Revoked**")
        container.add_separator(divider=True)
        container.add_text(f"> Revoked `{perm_clean}` from {role.mention}.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @fakeperms_group.command(name="list", help="View all fake permissions in this server.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def cmd_list(self, ctx: CustomContext) -> None:
        """View all active fake permissions."""
        guild_perms = self._cache.get(ctx.guild.id, {})
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**🛡️ Server Fake Permissions • {ctx.guild.name}**")
        container.add_separator(divider=True)

        if not guild_perms:
            container.add_text("> No fake permissions granted yet on this server.")
        else:
            lines = []
            for rid, perms in guild_perms.items():
                role = ctx.guild.get_role(rid)
                role_str = role.mention if role else f"`Deleted Role ({rid})`"
                perms_str = ", ".join(f"`{p}`" for p in sorted(perms))
                lines.append(f"• {role_str}:\n  > {perms_str}")
            container.add_text("\n\n".join(lines))

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @fakeperms_group.command(name="check", help="Check effective permissions for a user.")
    @commands.guild_only()
    async def cmd_check(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        """Audit native and fake permissions for a user."""
        target = member or ctx.author
        fake_set = self.get_member_fake_perms(target)
        fake_str = ", ".join(f"`{p}`" for p in sorted(fake_set)) if fake_set else "*None*"

        native_perms = [name for name, val in target.guild_permissions if val and name in VALID_PERMISSIONS]
        native_str = ", ".join(f"`{p}`" for p in sorted(native_perms)) if native_perms else "*None*"

        container = KyokaContainer(accent_color=None)
        container.add_text(f"**🔍 Permissions Audit • {target.display_name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Member:** {target.mention} (`{target.id}`)\n"
            f"• **Native Discord Permissions:**\n  > {native_str}\n\n"
            f"• **Fake Permissions (KYOKA Staff):**\n  > {fake_str}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(FakePerms(bot))
