"""
Kyoka 3.0 - Centralized Invite Tracker & Attribution Manager
Tracks member joins, departures, real/fake/left/bonus invites, and guild leaderboards.
Guarantees per-server isolation with database persistence and memory caching.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any, Optional
import discord

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Managers.InviteTracker")


class InviteTrackerManager:
    """Manages guild invite tracking, member join/leave attribution, stats, and leaderboards."""

    def __init__(self, db: PostgresDatabase, bot: KyokaBot | None = None) -> None:
        self.db = db
        self.bot = bot
        # guild_id -> {code: uses}
        self._invite_cache: dict[int, dict[str, int]] = {}
        # guild_id -> vanity_uses
        self._vanity_cache: dict[int, int] = {}
        # (guild_id, user_id) -> stats dict
        self._stats_cache: dict[tuple[int, int], dict[str, int]] = {}
        # guild_id -> settings dict
        self._settings_cache: dict[int, dict[str, Any]] = {}

    def get_default_settings(self, guild_id: int) -> dict[str, Any]:
        """Default invite tracker configuration for a guild."""
        return {
            "guild_id": guild_id,
            "log_channel_id": None,
            "fake_threshold_days": 7,
            "is_enabled": True,
        }

    async def get_settings(self, guild_id: int) -> dict[str, Any]:
        """Fetch guild invite tracking settings with in-memory cache."""
        if guild_id in self._settings_cache:
            return self._settings_cache[guild_id]

        defaults = self.get_default_settings(guild_id)
        if not self.db:
            return defaults

        try:
            row = await self.db.fetch_one(
                "SELECT guild_id, log_channel_id, fake_threshold_days, is_enabled FROM guild_invite_settings WHERE guild_id = ?;",
                guild_id,
            )
            if row:
                settings = {
                    "guild_id": guild_id,
                    "log_channel_id": int(row["log_channel_id"]) if row.get("log_channel_id") else None,
                    "fake_threshold_days": int(row.get("fake_threshold_days") or 7),
                    "is_enabled": bool(row.get("is_enabled", True)),
                }
            else:
                settings = defaults
        except Exception as e:
            logger.debug(f"Error fetching invite settings for guild {guild_id}: {e}")
            settings = defaults

        self._settings_cache[guild_id] = settings
        return settings

    async def set_log_channel(self, guild_id: int, channel_id: int | None) -> None:
        """Set or clear the invite join/leave logging channel."""
        ch_val = int(channel_id) if channel_id else None
        if self.db:
            await self.db.execute(
                """
                INSERT INTO guild_invite_settings (guild_id, log_channel_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    log_channel_id = EXCLUDED.log_channel_id,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                ch_val,
            )
        cfg = await self.get_settings(guild_id)
        cfg["log_channel_id"] = ch_val
        self._settings_cache[guild_id] = cfg

    async def set_fake_threshold(self, guild_id: int, days: int) -> None:
        """Set the account age threshold (in days) below which joins are flagged as fake."""
        safe_days = max(0, min(days, 365))
        if self.db:
            await self.db.execute(
                """
                INSERT INTO guild_invite_settings (guild_id, fake_threshold_days, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    fake_threshold_days = EXCLUDED.fake_threshold_days,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                safe_days,
            )
        cfg = await self.get_settings(guild_id)
        cfg["fake_threshold_days"] = safe_days
        self._settings_cache[guild_id] = cfg

    async def load_guild_invites(self, guild: discord.Guild) -> dict[str, int]:
        """Fetch and cache all active invites for a guild."""
        if not guild:
            return {}

        invite_map: dict[str, int] = {}
        try:
            me = guild.me
            can_fetch = (
                hasattr(me, "guild_permissions")
                and (me.guild_permissions.manage_guild or me.guild_permissions.administrator)
            ) or not hasattr(me, "guild_permissions")

            if can_fetch:
                invites = await guild.invites()
                for inv in invites:
                    invite_map[inv.code] = inv.uses or 0
        except Exception as e:
            logger.debug(f"Notice caching invites for guild {guild.id}: {e}")

        self._invite_cache[guild.id] = invite_map

        # Cache vanity URL uses if supported
        if "VANITY_URL" in getattr(guild, "features", []):
            try:
                vanity = await guild.vanity_invite()
                if vanity:
                    self._vanity_cache[guild.id] = vanity.uses or 0
            except Exception:
                pass

        return invite_map

    def add_invite_to_cache(self, invite: discord.Invite) -> None:
        """Add a newly created invite to cache."""
        if not invite.guild:
            return
        g_id = invite.guild.id
        if g_id not in self._invite_cache:
            self._invite_cache[g_id] = {}
        self._invite_cache[g_id][invite.code] = invite.uses or 0

    def remove_invite_from_cache(self, invite: discord.Invite) -> None:
        """Remove a deleted invite from cache."""
        if not invite.guild:
            return
        g_id = invite.guild.id
        if g_id in self._invite_cache:
            self._invite_cache[g_id].pop(invite.code, None)

    async def get_user_stats(self, guild_id: int, user_id: int) -> dict[str, int]:
        """Retrieve total, real, left, fake, bonus, and net invites for a user."""
        key = (guild_id, user_id)
        if key in self._stats_cache:
            return self._stats_cache[key]

        stats = {"regular": 0, "left": 0, "fake": 0, "bonus": 0, "net": 0}
        if self.db:
            try:
                row = await self.db.fetch_one(
                    "SELECT regular, left_count, fake, bonus FROM guild_invites_stats WHERE guild_id = ? AND user_id = ?;",
                    guild_id,
                    user_id,
                )
                if row:
                    reg = int(row.get("regular") or 0)
                    left = int(row.get("left_count") or 0)
                    fake = int(row.get("fake") or 0)
                    bonus = int(row.get("bonus") or 0)
                    net = reg - left + bonus
                    stats = {
                        "regular": reg,
                        "left": left,
                        "fake": fake,
                        "bonus": bonus,
                        "net": net,
                    }
            except Exception as e:
                logger.debug(f"Error fetching stats for user {user_id} in {guild_id}: {e}")

        self._stats_cache[key] = stats
        return stats

    async def get_user_inviter(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Retrieve the inviter record for a member."""
        if not self.db:
            return None
        try:
            row = await self.db.fetch_one(
                "SELECT inviter_id, invite_code, is_fake, has_left, joined_at FROM guild_member_invites WHERE guild_id = ? AND user_id = ?;",
                guild_id,
                user_id,
            )
            if row:
                return {
                    "inviter_id": int(row["inviter_id"]) if row.get("inviter_id") else None,
                    "invite_code": row.get("invite_code"),
                    "is_fake": bool(row.get("is_fake", False)),
                    "has_left": bool(row.get("has_left", False)),
                    "joined_at": row.get("joined_at"),
                }
        except Exception as e:
            logger.debug(f"Error getting inviter for {user_id} in {guild_id}: {e}")
        return None

    async def get_user_rank(self, guild_id: int, user_id: int) -> int | None:
        """Calculate the rank of a user in the server's invite leaderboard."""
        if not self.db:
            return None
        try:
            row = await self.db.fetch_one(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM guild_invites_stats
                WHERE guild_id = ?
                  AND (regular - left_count + bonus) > (
                      SELECT COALESCE(regular - left_count + bonus, 0)
                      FROM guild_invites_stats
                      WHERE guild_id = ? AND user_id = ?
                  );
                """,
                guild_id,
                guild_id,
                user_id,
            )
            if row and row.get("rank") is not None:
                return int(row["rank"])
        except Exception as e:
            logger.debug(f"Error getting rank for {user_id} in {guild_id}: {e}")
        return None

    async def get_leaderboard(self, guild_id: int, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """Fetch sorted leaderboard entries (Net invites DESC)."""
        if not self.db:
            return []
        try:
            rows = await self.db.fetch_all(
                """
                SELECT user_id, regular, left_count, fake, bonus,
                       (regular - left_count + bonus) AS net
                FROM guild_invites_stats
                WHERE guild_id = ?
                  AND (regular > 0 OR left_count > 0 OR fake > 0 OR bonus <> 0)
                ORDER BY net DESC, regular DESC, user_id ASC
                LIMIT ? OFFSET ?;
                """,
                guild_id,
                max(1, min(limit, 50)),
                max(0, offset),
            )
            results = []
            for idx, r in enumerate(rows, start=offset + 1):
                results.append({
                    "rank": idx,
                    "user_id": int(r["user_id"]),
                    "regular": int(r.get("regular") or 0),
                    "left": int(r.get("left_count") or 0),
                    "fake": int(r.get("fake") or 0),
                    "bonus": int(r.get("bonus") or 0),
                    "net": int(r.get("net") or 0),
                })
            return results
        except Exception as e:
            logger.debug(f"Error fetching leaderboard for guild {guild_id}: {e}")
            return []

    async def get_leaderboard_count(self, guild_id: int) -> int:
        """Count total members on the leaderboard for pagination."""
        if not self.db:
            return 0
        try:
            row = await self.db.fetch_one(
                """
                SELECT COUNT(*) as total
                FROM guild_invites_stats
                WHERE guild_id = ?
                  AND (regular > 0 OR left_count > 0 OR fake > 0 OR bonus <> 0);
                """,
                guild_id,
            )
            return int(row["total"]) if row and row.get("total") is not None else 0
        except Exception:
            return 0

    async def track_member_join(self, member: discord.Member) -> dict[str, Any]:
        """
        Detect which invite was used when a member joins.
        Updates cache, records attribution in database, and returns join metadata.
        """
        guild = member.guild
        old_invites = self._invite_cache.get(guild.id, {})
        new_invites_map: dict[str, int] = {}
        used_invite: discord.Invite | None = None
        inviter_id: int | None = None
        invite_code: str = "UNKNOWN"

        try:
            me = guild.me
            can_fetch = (
                hasattr(me, "guild_permissions")
                and (me.guild_permissions.manage_guild or me.guild_permissions.administrator)
            ) or not hasattr(me, "guild_permissions")

            if can_fetch:
                current_invites = await guild.invites()
                for inv in current_invites:
                    new_invites_map[inv.code] = inv.uses or 0
                    old_uses = old_invites.get(inv.code, 0)
                    if (inv.uses or 0) > old_uses:
                        used_invite = inv
                        invite_code = inv.code
                        if inv.inviter:
                            inviter_id = inv.inviter.id
        except Exception as e:
            logger.debug(f"Could not fetch current invites during join: {e}")

        # Update cache
        if new_invites_map:
            self._invite_cache[guild.id] = new_invites_map

        # Check vanity URL if no standard invite found
        is_vanity = False
        if not used_invite and "VANITY_URL" in getattr(guild, "features", []):
            try:
                vanity = await guild.vanity_invite()
                if vanity:
                    old_vanity = self._vanity_cache.get(guild.id, 0)
                    if (vanity.uses or 0) > old_vanity:
                        is_vanity = True
                        invite_code = "VANITY"
                        self._vanity_cache[guild.id] = vanity.uses or 0
            except Exception:
                pass

        # Check OAuth/bot addition
        is_oauth = False
        if not used_invite and not is_vanity and member.bot:
            is_oauth = True
            invite_code = "OAUTH_BOT"

        # Check fake / suspicious join
        is_fake = False
        settings = await self.get_settings(guild.id)
        threshold_days = settings.get("fake_threshold_days", 7)

        if inviter_id == member.id:
            # Self-invite is always flagged as fake
            is_fake = True
        elif member.created_at:
            account_age = (discord.utils.utcnow() - member.created_at).total_seconds()
            if account_age < (threshold_days * 86400):
                is_fake = True

        # Persist member join record
        if self.db:
            try:
                await self.db.execute(
                    """
                    INSERT INTO guild_member_invites (guild_id, user_id, inviter_id, invite_code, is_fake, has_left, joined_at)
                    VALUES (?, ?, ?, ?, ?, FALSE, CURRENT_TIMESTAMP)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        inviter_id = EXCLUDED.inviter_id,
                        invite_code = EXCLUDED.invite_code,
                        is_fake = EXCLUDED.is_fake,
                        has_left = FALSE,
                        joined_at = CURRENT_TIMESTAMP;
                    """,
                    guild.id,
                    member.id,
                    inviter_id,
                    invite_code,
                    is_fake,
                )
            except Exception as e:
                logger.error(f"Error persisting member invite join: {e}")

        # Update inviter stats
        stats: dict[str, int] = {"regular": 0, "left": 0, "fake": 0, "bonus": 0, "net": 0}
        if inviter_id:
            reg_add = 0 if is_fake else 1
            fake_add = 1 if is_fake else 0
            if self.db:
                try:
                    await self.db.execute(
                        """
                        INSERT INTO guild_invites_stats (guild_id, user_id, regular, left_count, fake, bonus, updated_at)
                        VALUES (?, ?, ?, 0, ?, 0, CURRENT_TIMESTAMP)
                        ON CONFLICT (guild_id, user_id) DO UPDATE SET
                            regular = guild_invites_stats.regular + EXCLUDED.regular,
                            fake = guild_invites_stats.fake + EXCLUDED.fake,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        guild.id,
                        inviter_id,
                        reg_add,
                        fake_add,
                    )
                except Exception as e:
                    logger.error(f"Error updating inviter stats on join: {e}")

            self._stats_cache.pop((guild.id, inviter_id), None)
            stats = await self.get_user_stats(guild.id, inviter_id)

        inviter_user = None
        if inviter_id and self.bot:
            inviter_user = guild.get_member(inviter_id) or self.bot.get_user(inviter_id)

        return {
            "guild_id": guild.id,
            "member": member,
            "inviter": inviter_user,
            "inviter_id": inviter_id,
            "code": invite_code,
            "is_fake": is_fake,
            "is_vanity": is_vanity,
            "is_oauth": is_oauth,
            "stats": stats,
        }

    async def track_member_leave(self, member: discord.Member) -> dict[str, Any] | None:
        """
        Record when an invited member leaves.
        Increments left count for original inviter and returns departure metadata.
        """
        guild = member.guild
        inv_record = await self.get_user_inviter(guild.id, member.id)
        if not inv_record:
            return None

        inviter_id = inv_record.get("inviter_id")
        if not inviter_id:
            return None

        if self.db:
            try:
                # Mark as has_left
                await self.db.execute(
                    "UPDATE guild_member_invites SET has_left = TRUE WHERE guild_id = ? AND user_id = ?;",
                    guild.id,
                    member.id,
                )
                # Increment left_count for inviter
                await self.db.execute(
                    """
                    INSERT INTO guild_invites_stats (guild_id, user_id, regular, left_count, fake, bonus, updated_at)
                    VALUES (?, ?, 0, 1, 0, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        left_count = guild_invites_stats.left_count + 1,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    guild.id,
                    inviter_id,
                )
            except Exception as e:
                logger.error(f"Error updating inviter left_count: {e}")

        self._stats_cache.pop((guild.id, inviter_id), None)
        stats = await self.get_user_stats(guild.id, inviter_id)

        inviter_user = None
        if self.bot:
            inviter_user = guild.get_member(inviter_id) or self.bot.get_user(inviter_id)

        return {
            "guild_id": guild.id,
            "member": member,
            "inviter": inviter_user,
            "inviter_id": inviter_id,
            "code": inv_record.get("invite_code"),
            "stats": stats,
        }

    async def add_bonus_invites(self, guild_id: int, user_id: int, amount: int) -> dict[str, int]:
        """Add bonus invites to a member."""
        if self.db:
            await self.db.execute(
                """
                INSERT INTO guild_invites_stats (guild_id, user_id, regular, left_count, fake, bonus, updated_at)
                VALUES (?, ?, 0, 0, 0, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    bonus = guild_invites_stats.bonus + EXCLUDED.bonus,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                user_id,
                int(amount),
            )
        self._stats_cache.pop((guild_id, user_id), None)
        return await self.get_user_stats(guild_id, user_id)

    async def remove_bonus_invites(self, guild_id: int, user_id: int, amount: int) -> dict[str, int]:
        """Remove bonus invites from a member."""
        return await self.add_bonus_invites(guild_id, user_id, -abs(int(amount)))

    async def reset_user_invites(self, guild_id: int, user_id: int) -> None:
        """Reset invite stats for a specific user in a guild."""
        if self.db:
            await self.db.execute(
                "DELETE FROM guild_invites_stats WHERE guild_id = ? AND user_id = ?;",
                guild_id,
                user_id,
            )
        self._stats_cache.pop((guild_id, user_id), None)

    async def reset_guild_invites(self, guild_id: int) -> None:
        """Reset all invite statistics for an entire guild."""
        if self.db:
            await self.db.execute("DELETE FROM guild_invites_stats WHERE guild_id = ?;", guild_id)
            await self.db.execute("DELETE FROM guild_member_invites WHERE guild_id = ?;", guild_id)
        # Clear stats cache for this guild
        keys_to_clear = [k for k in self._stats_cache.keys() if k[0] == guild_id]
        for k in keys_to_clear:
            self._stats_cache.pop(k, None)

    async def get_invited_members(self, guild_id: int, inviter_id: int, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch list of members invited by a specific user."""
        if not self.db:
            return []
        try:
            rows = await self.db.fetch_all(
                """
                SELECT user_id, invite_code, is_fake, has_left, joined_at
                FROM guild_member_invites
                WHERE guild_id = ? AND inviter_id = ?
                ORDER BY joined_at DESC
                LIMIT ?;
                """,
                guild_id,
                inviter_id,
                max(1, min(limit, 100)),
            )
            return [
                {
                    "user_id": int(r["user_id"]),
                    "invite_code": r.get("invite_code"),
                    "is_fake": bool(r.get("is_fake", False)),
                    "has_left": bool(r.get("has_left", False)),
                    "joined_at": r.get("joined_at"),
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"Error fetching invited members for {inviter_id} in {guild_id}: {e}")
            return []
