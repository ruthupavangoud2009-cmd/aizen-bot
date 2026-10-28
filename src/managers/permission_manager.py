from __future__ import annotations

import logging
from typing import Callable, TYPE_CHECKING, Any
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyoka.PermissionManager")


class PermissionManager:
    """Manages bot developers and owner authorization checks."""

    def __init__(self, bot: commands.Bot, db: BaseDatabase) -> None:
        self.bot = bot
        self.db = db
        self._developer_ids: set[int] = set()

    async def load_cache(self) -> None:
        """Load registered developer IDs and owner ID into memory."""
        # KYOKA has exactly one privileged identity. Discord application/team
        # ownership and legacy database rows must never expand this allowlist.
        from src.security.owner import OWNER_ID
        self.bot.owner_id = OWNER_ID
        self.bot.owner_ids = {OWNER_ID}
        self._developer_ids = set()
        logger.info("Loaded single primary owner authorization policy.")

    def is_developer_sync(self, user_id: int) -> bool:
        """Fast, synchronous in-memory developer/staff check (0ns latency, zero API calls)."""
        from src.security.owner import is_owner_or_staff
        return is_owner_or_staff(user_id)

    async def is_owner(self, user_id: int) -> bool:
        """Only the configured primary owner ID is an owner."""
        from src.security.owner import is_primary_owner
        return is_primary_owner(user_id)

    async def is_developer(self, user_id: int) -> bool:
        """Primary owner and authorized bot staff have developer bot privileges."""
        return self.is_developer_sync(user_id)

    async def add_developer(self, user_id: int, added_by: int) -> None:
        """Reject legacy multi-developer grants; only the primary owner is privileged."""
        from src.security.owner import is_primary_owner
        if not is_primary_owner(added_by) or not is_primary_owner(user_id):
            raise PermissionError("KYOKA supports exactly one owner/developer ID.")
        self._developer_ids.clear()
        await self.db.execute(
            "INSERT OR IGNORE INTO system_developers (user_id, added_by) VALUES (?, ?);",
            user_id,
            added_by,
        )
        logger.info(f"Added developer ID: {user_id}")

    async def remove_developer(self, user_id: int) -> None:
        """Clear a legacy developer record; it never grants privileges."""
        self._developer_ids.discard(user_id)
        await self.db.execute(
            "DELETE FROM system_developers WHERE user_id = ?;",
            user_id,
        )
        logger.info(f"Removed developer ID: {user_id}")

    def has_permission(self, member: discord.Member, perm_name: str) -> bool:
        """Check if member has native Discord permission, administrator, or Greed-style fake permission."""
        if not member:
            return False
        perms = getattr(member, "guild_permissions", None)
        if perms:
            if getattr(perms, "administrator", False) is True:
                return True
            if getattr(perms, perm_name, False) is True:
                return True
        fakeperms_cog = self.bot.get_cog("Admin-FakePerms")
        if fakeperms_cog and hasattr(fakeperms_cog, "has_fake_perm"):
            return fakeperms_cog.has_fake_perm(member, perm_name)
        return False


# ==========================================
# Custom Command Check Decorators
# ==========================================

def is_owner() -> Callable:
    """Command check: only the configured numeric primary owner ID."""
    async def predicate(ctx: commands.Context) -> bool:
        from src.security.owner import is_primary_owner
        if not is_primary_owner(getattr(ctx.author, "id", None)):
            raise commands.NotOwner("This command is restricted to the primary bot owner.")
        return True
    return commands.check(predicate)


def is_developer() -> Callable:
    """Command check: Accessible by Bot Owners and registered Developers."""
    async def predicate(ctx: commands.Context) -> bool:
        bot: Any = ctx.bot
        perm_mgr: PermissionManager = bot.perm_mgr
        if not await perm_mgr.is_developer(ctx.author.id):
            raise commands.CheckFailure("This command is restricted to Bot Developers.")
        return True
    return commands.check(predicate)
