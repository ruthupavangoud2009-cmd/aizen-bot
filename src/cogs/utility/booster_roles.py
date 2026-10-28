"""
Kyoka 3.0 - Nitro Booster Custom Roles System
Inspired by Greed bot's booster role customization suite.
Allows server Nitro Boosters to create, customize, and share their own exclusive cosmetic roles.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import aiohttp
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class BoosterRoles(commands.Cog, name="Utility-BoosterRoles"):
    """
    Greed-style Nitro Booster Custom Roles.
    Server boosters can create their own custom personal role with hex colors, names, icons, and sharing.
    """
    category = "💎・SERVER PERKS & UTILITY"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Initialize database table for booster roles."""
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_booster_roles (
                        guild_id BIGINT,
                        user_id BIGINT,
                        role_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (guild_id, user_id)
                    );
                    """
                )
            except Exception:
                pass

    def _is_booster(self, member: discord.Member) -> bool:
        """Check if member is boosting the server or is server administrator."""
        if member.premium_since is not None:
            return True
        if member.guild_permissions.administrator:
            return True
        if member.id == member.guild.owner_id:
            return True
        return False

    async def _get_user_role(self, guild_id: int, user_id: int) -> Optional[int]:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_one"):
            try:
                row = await self.bot.db.fetch_one(
                    "SELECT role_id FROM guild_booster_roles WHERE guild_id = ? AND user_id = ?;",
                    guild_id,
                    user_id,
                )
                return row["role_id"] if row else None
            except Exception:
                pass
        return None

    # ─── COMMAND GROUP ────────────────────────────────────────────────────────

    @commands.group(
        name="boosterrole",
        aliases=["br", "customrole", "myrole"],
        invoke_without_command=True,
        description="Nitro Booster personal role customization suite.",
    )
    @commands.guild_only()
    async def boosterrole_group(self, ctx: CustomContext) -> None:
        """Display booster role dashboard or help."""
        p = ctx.clean_prefix
        container = KyokaContainer(accent_color=None)
        container.add_text("**💎 Nitro Booster Custom Role Suite**")
        container.add_separator(divider=True)
        container.add_text(
            f"• `{p}boosterrole create <name>` — Create your personal booster role\n"
            f"• `{p}boosterrole color <#hex>` — Change your role's color\n"
            f"• `{p}boosterrole name <new_name>` — Rename your personal role\n"
            f"• `{p}boosterrole icon <url>` — Set a custom role icon\n"
            f"• `{p}boosterrole share <@user>` — Share your role with a friend\n"
            f"• `{p}boosterrole unshare <@user>` — Remove your role from a friend\n"
            f"• `{p}boosterrole info` — View your custom role details\n"
            f"• `{p}boosterrole delete` — Delete your custom role\n\n"
            f"*Exclusive to server Nitro Boosters.*"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boosterrole_group.command(name="create", help="Create your personal booster role.")
    @commands.guild_only()
    async def cmd_create(self, ctx: CustomContext, *, name: str) -> None:
        """Create a new custom booster role."""
        if not self._is_booster(ctx.author):
            return await ctx.send_error("This feature is exclusively for server Nitro Boosters!")

        existing_role_id = await self._get_user_role(ctx.guild.id, ctx.author.id)
        if existing_role_id and ctx.guild.get_role(existing_role_id):
            role = ctx.guild.get_role(existing_role_id)
            return await ctx.send_warning(f"You already have a custom role: {role.mention}. Use `{ctx.clean_prefix}boosterrole name` or `color` to modify it.")

        clean_name = name.strip()[:100]
        try:
            role = await ctx.guild.create_role(
                name=clean_name,
                reason=f"Custom Booster Role for {ctx.author} ({ctx.author.id})",
            )
            # Position below bot's top role
            target_pos = max(1, ctx.guild.me.top_role.position - 1)
            try:
                await role.edit(position=target_pos)
            except Exception:
                pass
            await ctx.author.add_roles(role, reason="Booster role created")
        except Exception as e:
            return await ctx.send_error(f"Failed to create role: {e}")

        # Save to DB
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO guild_booster_roles (guild_id, user_id, role_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        role_id = EXCLUDED.role_id,
                        created_at = CURRENT_TIMESTAMP;
                    """,
                    ctx.guild.id,
                    ctx.author.id,
                    role.id,
                )
            except Exception:
                pass

        container = KyokaContainer(accent_color=None)
        container.add_text("**💎 Custom Booster Role Created!**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Role:** {role.mention} (`{clean_name}`)\n"
            f"• **Owner:** {ctx.author.mention}\n\n"
            f"> Customize color using `{ctx.clean_prefix}boosterrole color <#hex>`\n"
            f"> Share with friends using `{ctx.clean_prefix}boosterrole share <@friend>`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boosterrole_group.command(name="color", aliases=["colour"], help="Change your booster role's color.")
    @commands.guild_only()
    async def cmd_color(self, ctx: CustomContext, hex_code: str) -> None:
        """Change the hex color of your booster role."""
        if not self._is_booster(ctx.author):
            return await ctx.send_error("This feature is exclusively for server Nitro Boosters!")

        role_id = await self._get_user_role(ctx.guild.id, ctx.author.id)
        role = ctx.guild.get_role(role_id) if role_id else None
        if not role:
            return await ctx.send_error(f"You don't have a booster role yet. Create one with `{ctx.clean_prefix}boosterrole create <name>`!")

        clean_hex = hex_code.strip().lstrip("#")
        if not re.match(r"^[0-9a-fA-F]{6}$", clean_hex):
            return await ctx.send_error("Please provide a valid 6-character hex color code (e.g. `#FF5733` or `7C3AED`)!")

        int_color = int(clean_hex, 16)
        try:
            await role.edit(color=discord.Color(int_color), reason=f"Booster role color updated by {ctx.author}")
        except Exception as e:
            return await ctx.send_error(f"Failed to update role color: {e}")

        container = KyokaContainer(accent_color=int_color)
        container.add_text("**🎨 Booster Role Color Updated**")
        container.add_separator(divider=True)
        container.add_text(f"> Updated {role.mention} color to **`#{clean_hex.upper()}`**.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boosterrole_group.command(name="name", aliases=["rename"], help="Rename your booster role.")
    @commands.guild_only()
    async def cmd_name(self, ctx: CustomContext, *, new_name: str) -> None:
        """Rename your booster role."""
        if not self._is_booster(ctx.author):
            return await ctx.send_error("This feature is exclusively for server Nitro Boosters!")

        role_id = await self._get_user_role(ctx.guild.id, ctx.author.id)
        role = ctx.guild.get_role(role_id) if role_id else None
        if not role:
            return await ctx.send_error(f"You don't have a booster role yet. Create one with `{ctx.clean_prefix}boosterrole create <name>`!")

        clean_name = new_name.strip()[:100]
        try:
            await role.edit(name=clean_name, reason=f"Booster role renamed by {ctx.author}")
        except Exception as e:
            return await ctx.send_error(f"Failed to rename role: {e}")

        container = KyokaContainer(accent_color=None)
        container.add_text("**✏️ Booster Role Renamed**")
        container.add_separator(divider=True)
        container.add_text(f"> Updated your booster role name to **`{clean_name}`** ({role.mention}).")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boosterrole_group.command(name="share", help="Share your booster role with a friend.")
    @commands.guild_only()
    async def cmd_share(self, ctx: CustomContext, member: discord.Member) -> None:
        """Share your booster role with a server friend."""
        if not self._is_booster(ctx.author):
            return await ctx.send_error("This feature is exclusively for server Nitro Boosters!")

        role_id = await self._get_user_role(ctx.guild.id, ctx.author.id)
        role = ctx.guild.get_role(role_id) if role_id else None
        if not role:
            return await ctx.send_error(f"You don't have a booster role yet. Create one with `{ctx.clean_prefix}boosterrole create <name>`!")

        if role in member.roles:
            return await ctx.send_warning(f"{member.mention} already has your booster role!")

        try:
            await member.add_roles(role, reason=f"Booster role shared by {ctx.author}")
        except Exception as e:
            return await ctx.send_error(f"Could not assign role to {member.mention}: {e}")

        container = KyokaContainer(accent_color=None)
        container.add_text("**🤝 Booster Role Shared**")
        container.add_separator(divider=True)
        container.add_text(f"> Successfully granted your custom role {role.mention} to {member.mention}!")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boosterrole_group.command(name="unshare", help="Remove your booster role from a friend.")
    @commands.guild_only()
    async def cmd_unshare(self, ctx: CustomContext, member: discord.Member) -> None:
        """Remove your booster role from a friend."""
        role_id = await self._get_user_role(ctx.guild.id, ctx.author.id)
        role = ctx.guild.get_role(role_id) if role_id else None
        if not role:
            return await ctx.send_error("You don't have a booster role configured.")

        if role not in member.roles:
            return await ctx.send_warning(f"{member.mention} does not have your booster role.")

        try:
            await member.remove_roles(role, reason=f"Booster role unshared by {ctx.author}")
        except Exception as e:
            return await ctx.send_error(f"Could not remove role from {member.mention}: {e}")

        container = KyokaContainer(accent_color=None)
        container.add_text("**👋 Booster Role Removed**")
        container.add_separator(divider=True)
        container.add_text(f"> Removed your custom role {role.mention} from {member.mention}.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boosterrole_group.command(name="delete", help="Delete your personal booster role.")
    @commands.guild_only()
    async def cmd_delete(self, ctx: CustomContext) -> None:
        """Delete your booster role."""
        role_id = await self._get_user_role(ctx.guild.id, ctx.author.id)
        role = ctx.guild.get_role(role_id) if role_id else None

        if role:
            try:
                await role.delete(reason=f"Booster role deleted by owner {ctx.author}")
            except Exception as e:
                return await ctx.send_error(f"Failed to delete role: {e}")

        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    "DELETE FROM guild_booster_roles WHERE guild_id = ? AND user_id = ?;",
                    ctx.guild.id,
                    ctx.author.id,
                )
            except Exception:
                pass

        container = KyokaContainer(accent_color=None)
        container.add_text("**🗑️ Booster Role Deleted**")
        container.add_separator(divider=True)
        container.add_text("> Your custom booster role has been completely removed from this server.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(BoosterRoles(bot))
