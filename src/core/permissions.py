"""
Kyoka 3.0 - Permission Services & Hierarchy Guards
Authoritative permission checks, role hierarchy validation, and fail-closed guards.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple, TypeVar
import discord
from discord import app_commands
from discord.ext import commands

from src.security.owner import OWNER_ID, is_primary_owner, is_bot_staff, is_owner_or_staff

logger = logging.getLogger("Kyoka.Core.Permissions")

T = TypeVar("T")
_staff_permission_overrides_installed = False


def install_bot_staff_permission_overrides() -> None:
    """Let registered bot staff pass ordinary server permission decorators."""
    global _staff_permission_overrides_installed
    if _staff_permission_overrides_installed:
        return

    native_has_permissions = commands.has_permissions
    native_has_guild_permissions = commands.has_guild_permissions
    native_app_has_permissions = app_commands.checks.has_permissions

    def has_permissions(**perms: bool):
        native_check = native_has_permissions(**perms)
        native_predicate = native_check.predicate

        async def predicate(ctx: commands.Context) -> bool:
            if ctx.guild and is_bot_staff(getattr(ctx.author, "id", None)):
                return True
            return await discord.utils.maybe_coroutine(native_predicate, ctx)

        return commands.check(predicate)

    def has_guild_permissions(**perms: bool):
        native_check = native_has_guild_permissions(**perms)
        native_predicate = native_check.predicate

        async def predicate(ctx: commands.Context) -> bool:
            if ctx.guild and is_bot_staff(getattr(ctx.author, "id", None)):
                return True
            return await discord.utils.maybe_coroutine(native_predicate, ctx)

        return commands.check(predicate)

    def app_has_permissions(**perms: bool):
        native_app_has_permissions(**perms)

        async def predicate(interaction: discord.Interaction) -> bool:
            if interaction.guild_id and is_bot_staff(getattr(interaction.user, "id", None)):
                return True
            missing = [
                permission
                for permission, value in perms.items()
                if getattr(interaction.permissions, permission) != value
            ]
            if missing:
                raise app_commands.MissingPermissions(missing)
            return True

        return app_commands.check(predicate)

    commands.has_permissions = has_permissions
    commands.has_guild_permissions = has_guild_permissions
    app_commands.checks.has_permissions = app_has_permissions
    _staff_permission_overrides_installed = True


def is_bot_owner(user_id: int | None) -> bool:
    """Authoritative check against immutable primary owner ID."""
    return is_primary_owner(user_id)


def is_bot_staff_member(user_id: int | None) -> bool:
    """Check if user has bot staff privileges."""
    return is_bot_staff(user_id)


def is_server_admin(member: discord.Member) -> bool:
    """Check if member has Administrator permission or is guild owner."""
    if not isinstance(member, discord.Member):
        return False
    if member.guild.owner_id == member.id:
        return True
    return member.guild_permissions.administrator


def check_hierarchy(
    executor: discord.Member,
    target: discord.Member,
    bot_member: Optional[discord.Member] = None,
) -> Tuple[bool, str]:
    """
    Validate Discord role hierarchy for moderation actions:
    1. Executor cannot target the guild owner.
    2. Executor cannot target themselves.
    3. Executor cannot target someone with a higher or equal top role (unless guild owner, primary bot owner, or bot staff).
    4. Bot must have a higher top role than target.
    """
    if target.id == executor.guild.owner_id:
        return False, "You cannot moderate the server owner."

    if target.id == executor.id:
        return False, "You cannot execute this moderation action on yourself."

    # Primary owner or bot staff overrides executor hierarchy checks if needed, but not guild owner
    if not (is_primary_owner(executor.id) or is_bot_staff(executor.id) or executor.id == executor.guild.owner_id):
        if executor.top_role.position <= target.top_role.position:
            return False, f"Your role ({executor.top_role.name}) must be strictly higher than {target.display_name}'s role ({target.top_role.name})."

    if bot_member:
        if bot_member.top_role.position <= target.top_role.position:
            return False, f"My role ({bot_member.top_role.name}) is lower than or equal to {target.display_name}'s role ({target.top_role.name})."

    return True, ""


def can_moderate(ctx: commands.Context, target: discord.Member) -> Tuple[bool, str]:
    """Convenience helper checking both executor and bot role hierarchy against target."""
    if not ctx.guild or not isinstance(ctx.author, discord.Member):
        return False, "Moderation actions can only be used inside a server."
    bot_member = ctx.guild.me
    return check_hierarchy(ctx.author, target, bot_member)


def require_owner(allow_staff: bool = False):
    """Command check requiring primary bot owner or bot staff authorization."""
    async def predicate(ctx: commands.Context) -> bool:
        if allow_staff:
            if not is_owner_or_staff(ctx.author.id):
                raise commands.CheckFailure("⛔ Only the bot owner or bot staff can execute this command.")
            return True
        if not is_primary_owner(ctx.author.id):
            raise commands.CheckFailure("⛔ Only the primary bot owner can execute this command.")
        return True
    return commands.check(predicate)


def require_guild_permissions(**perms: bool) -> Callable[[T], T]:
    """Command check requiring specific Discord guild permissions or administrator."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage("This command cannot be used in private messages.")

        # Primary bot owner, bot staff, or guild owner always bypasses
        if is_primary_owner(ctx.author.id) or is_bot_staff(ctx.author.id) or ctx.author.id == ctx.guild.owner_id:
            return True

        user_perms = ctx.channel.permissions_for(ctx.author)
        if user_perms.administrator:
            return True

        missing = [perm for perm, value in perms.items() if getattr(user_perms, perm) != value]
        if missing:
            formatted = ", ".join(missing).replace("_", " ").title()
            raise commands.MissingPermissions([formatted])
        return True

    return commands.check(predicate)
