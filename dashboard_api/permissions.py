"""Discord permission bitwise calculations and cross-server authorization guards.

In Discord OAuth2:
- Permission bit 0x8  = ADMINISTRATOR
- Permission bit 0x20 = MANAGE_GUILD
Users possessing either bit or who own the guild are authorized to view and edit bot settings.
"""
from __future__ import annotations

from typing import Any, Mapping

# Discord Permission Bit Constants
ADMINISTRATOR: int = 0x00000008
MANAGE_GUILD: int = 0x00000020


def has_manage_permission(permissions: int | str | None, is_owner: bool = False) -> bool:
    """Check if the provided permission integer includes Administrator or Manage Guild, or if user is owner."""
    if is_owner:
        return True
    if permissions is None:
        return False
    try:
        perm_int = int(permissions)
    except (ValueError, TypeError):
        return False

    is_admin = bool(perm_int & ADMINISTRATOR)
    is_manager = bool(perm_int & MANAGE_GUILD)
    return is_admin or is_manager


def can_manage_guild(guild: Mapping[str, Any]) -> bool:
    """Inspect a Discord guild payload returned by `/users/@me/guilds` to check if user has management rights."""
    is_owner = bool(guild.get("owner", False))
    permissions = guild.get("permissions")
    return has_manage_permission(permissions, is_owner=is_owner)


def find_manageable_guild(guilds: list[dict[str, Any]], target_guild_id: str | int) -> dict[str, Any] | None:
    """Find a guild in the user's guild list by ID and verify the user has management permissions.

    Returns the guild dictionary if authorized, None otherwise.
    This guarantees cross-server isolation by strictly checking the user's live guild permissions.
    """
    target_id_str = str(target_guild_id)
    for guild in guilds:
        if str(guild.get("id")) == target_id_str:
            if can_manage_guild(guild):
                return guild
            return None
    return None
