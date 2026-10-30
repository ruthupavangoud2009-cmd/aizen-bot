from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.Activity")


class ActivityManager:
    """
    High-performance, privacy-respecting message activity tracker for KYOKA 3.0.
    Stores only message counts and timestamps (NEVER message contents).
    Includes cooldowns, spam filtering, channel exclusions, and user privacy opt-outs.
    """

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # (guild_id, user_id) -> last message monotonic timestamp for spam prevention
        self._cooldowns: dict[tuple[int, int], float] = {}
        # user_id -> opt-out boolean cached
        self._opt_outs: set[int] = set()
        # guild_id -> config cache dict
        self._guild_configs: dict[int, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load privacy opt-out set and server configs into memory cache."""
        try:
            # Opt-out users
            opt_rows = await self.db.fetch_all(
                "SELECT user_id FROM user_privacy_preferences WHERE opt_out_activity = TRUE;"
            )
            self._opt_outs = {int(r["user_id"]) for r in opt_rows}

            # Server activity configs
            cfg_rows = await self.db.fetch_all(
                "SELECT guild_id, activity_tracking_enabled, activity_cooldown_seconds, "
                "activity_excluded_channels, activity_min_length FROM server_giveaway_config;"
            )
            async with self._lock:
                self._guild_configs.clear()
                for r in cfg_rows:
                    self._guild_configs[int(r["guild_id"])] = {
                        "enabled": bool(r.get("activity_tracking_enabled", True)),
                        "cooldown": int(r.get("activity_cooldown_seconds", 5)),
                        "excluded_channels": [
                            int(c.strip())
                            for c in str(r.get("activity_excluded_channels", "")).split(",")
                            if c.strip().isdigit()
                        ],
                        "min_length": int(r.get("activity_min_length", 3)),
                    }
            logger.info(
                f"Loaded {len(self._opt_outs)} privacy opt-outs and {len(self._guild_configs)} activity configs."
            )
        except Exception as e:
            logger.debug(f"Notice loading activity cache: {e}")

    def is_opted_out(self, user_id: int) -> bool:
        """Check if a user has opted out of activity tracking."""
        return user_id in self._opt_outs

    async def set_opt_out(self, user_id: int, opt_out: bool) -> None:
        """Update a user's privacy opt-out status."""
        if opt_out:
            self._opt_outs.add(user_id)
            await self.db.execute(
                """
                INSERT INTO user_privacy_preferences (user_id, opt_out_activity, updated_at)
                VALUES ($1, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET opt_out_activity = TRUE, updated_at = CURRENT_TIMESTAMP;
                """,
                user_id,
            )
        else:
            self._opt_outs.discard(user_id)
            await self.db.execute(
                """
                INSERT INTO user_privacy_preferences (user_id, opt_out_activity, updated_at)
                VALUES ($1, FALSE, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET opt_out_activity = FALSE, updated_at = CURRENT_TIMESTAMP;
                """,
                user_id,
            )

    async def erase_user_data(self, user_id: int) -> int:
        """Permanently delete all tracked activity counts for a user across all servers."""
        res1 = await self.db.execute("DELETE FROM member_activity WHERE user_id = $1;", user_id)
        await self.db.execute("DELETE FROM member_activity_channel WHERE user_id = $1;", user_id)
        return 1

    def get_guild_config(self, guild_id: int) -> dict[str, Any]:
        """Fetch cached activity config for a guild with defaults."""
        return self._guild_configs.get(
            guild_id,
            {
                "enabled": True,
                "cooldown": 5,
                "excluded_channels": [],
                "min_length": 3,
            },
        )

    def update_guild_config_cache(
        self,
        guild_id: int,
        enabled: bool = True,
        cooldown: int = 5,
        excluded_channels: Optional[list[int]] = None,
        min_length: int = 3,
    ) -> None:
        """Update local cache for server activity settings."""
        self._guild_configs[guild_id] = {
            "enabled": enabled,
            "cooldown": cooldown,
            "excluded_channels": excluded_channels or [],
            "min_length": min_length,
        }

    def should_record_message(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        content_length: int,
    ) -> bool:
        """Check cached activity filters before scheduling background work."""
        if self.is_opted_out(user_id):
            return False

        config = self.get_guild_config(guild_id)
        if (
            not config["enabled"]
            or channel_id in config["excluded_channels"]
            or content_length < config["min_length"]
        ):
            return False

        last_t = self._cooldowns.get((guild_id, user_id), 0.0)
        return time.monotonic() - last_t >= config["cooldown"]

    async def record_message(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        content_length: int,
    ) -> bool:
        """
        Record a qualifying message.
        Enforces privacy opt-out, server enable toggle, channel exclusions,
        minimum message length, and per-user message cooldown.
        Returns True if counted, False if filtered out.
        """
        if not self.should_record_message(guild_id, user_id, channel_id, content_length):
            return False

        key = (guild_id, user_id)
        self._cooldowns[key] = time.monotonic()

        try:
            # Upsert into member_activity (calendar day based)
            await self.db.execute(
                """
                INSERT INTO member_activity (guild_id, user_id, message_date, message_count, last_message_at)
                VALUES ($1, $2, CURRENT_DATE, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id, user_id, message_date)
                DO UPDATE SET
                    message_count = member_activity.message_count + 1,
                    last_message_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                user_id,
            )

            # Upsert into member_activity_channel
            await self.db.execute(
                """
                INSERT INTO member_activity_channel (guild_id, user_id, channel_id, message_date, message_count)
                VALUES ($1, $2, $3, CURRENT_DATE, 1)
                ON CONFLICT (guild_id, user_id, channel_id, message_date)
                DO UPDATE SET message_count = member_activity_channel.message_count + 1;
                """,
                guild_id,
                user_id,
                channel_id,
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to record message activity: {e}")
            return False

    async def get_user_activity(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Fetch daily, weekly (7d), and monthly (30d) activity counts for a user in a guild."""
        try:
            today_row = await self.db.fetch_one(
                """
                SELECT message_count, last_message_at
                FROM member_activity
                WHERE guild_id = $1 AND user_id = $2 AND message_date = CURRENT_DATE;
                """,
                guild_id,
                user_id,
            )
            today_count = int(today_row["message_count"]) if today_row else 0
            last_msg_at = today_row["last_message_at"] if today_row else None

            week_row = await self.db.fetch_one(
                """
                SELECT COALESCE(SUM(message_count), 0) AS total
                FROM member_activity
                WHERE guild_id = $1 AND user_id = $2 AND message_date >= CURRENT_DATE - INTERVAL '6 days';
                """,
                guild_id,
                user_id,
            )
            week_count = int(week_row["total"]) if week_row else 0

            month_row = await self.db.fetch_one(
                """
                SELECT COALESCE(SUM(message_count), 0) AS total
                FROM member_activity
                WHERE guild_id = $1 AND user_id = $2 AND message_date >= CURRENT_DATE - INTERVAL '29 days';
                """,
                guild_id,
                user_id,
            )
            month_count = int(month_row["total"]) if month_row else 0

            # Rank in server based on weekly count
            rank_row = await self.db.fetch_one(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM (
                    SELECT user_id, SUM(message_count) as total
                    FROM member_activity
                    WHERE guild_id = $1 AND message_date >= CURRENT_DATE - INTERVAL '6 days'
                    GROUP BY user_id
                    HAVING SUM(message_count) > $2
                ) sub;
                """,
                guild_id,
                week_count,
            )
            rank = int(rank_row["rank"]) if rank_row else 1

            return {
                "today": today_count,
                "weekly": week_count,
                "monthly": month_count,
                "last_message_at": last_msg_at,
                "rank": rank,
                "opted_out": self.is_opted_out(user_id),
            }
        except Exception as e:
            logger.debug(f"Error fetching user activity: {e}")
            return {
                "today": 0,
                "weekly": 0,
                "monthly": 0,
                "last_message_at": None,
                "rank": 0,
                "opted_out": self.is_opted_out(user_id),
            }

    async def get_leaderboard(
        self,
        guild_id: int,
        period: str = "today",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Fetch leaderboard for server activity.
        period: 'today' | 'weekly' | 'all'
        """
        limit = max(1, min(limit, 25))
        try:
            if period.lower() in ("today", "daily", "24h"):
                rows = await self.db.fetch_all(
                    """
                    SELECT user_id, message_count AS total
                    FROM member_activity
                    WHERE guild_id = $1 AND message_date = CURRENT_DATE
                    ORDER BY message_count DESC
                    LIMIT $2;
                    """,
                    guild_id,
                    limit,
                )
            elif period.lower() in ("weekly", "7d", "week"):
                rows = await self.db.fetch_all(
                    """
                    SELECT user_id, SUM(message_count) AS total
                    FROM member_activity
                    WHERE guild_id = $1 AND message_date >= CURRENT_DATE - INTERVAL '6 days'
                    GROUP BY user_id
                    ORDER BY total DESC
                    LIMIT $2;
                    """,
                    guild_id,
                    limit,
                )
            else:
                rows = await self.db.fetch_all(
                    """
                    SELECT user_id, SUM(message_count) AS total
                    FROM member_activity
                    WHERE guild_id = $1
                    GROUP BY user_id
                    ORDER BY total DESC
                    LIMIT $2;
                    """,
                    guild_id,
                    limit,
                )
            return [{"user_id": int(r["user_id"]), "total": int(r["total"])} for r in rows]
        except Exception as e:
            logger.debug(f"Error fetching leaderboard: {e}")
            return []

    async def check_requirement(
        self,
        guild_id: int,
        user_id: int,
        req_type: str,
        threshold: int,
        channel_id: Optional[int] = None,
    ) -> tuple[bool, int]:
        """
        Check if user satisfies an activity requirement.
        Returns: (passed: bool, actual_count: int)
        """
        try:
            if req_type in ("messages_daily", "daily"):
                row = await self.db.fetch_one(
                    """
                    SELECT COALESCE(message_count, 0) AS cnt
                    FROM member_activity
                    WHERE guild_id = $1 AND user_id = $2 AND message_date = CURRENT_DATE;
                    """,
                    guild_id,
                    user_id,
                )
                actual = int(row["cnt"]) if row else 0
                return actual >= threshold, actual

            elif req_type in ("messages_weekly", "weekly"):
                row = await self.db.fetch_one(
                    """
                    SELECT COALESCE(SUM(message_count), 0) AS cnt
                    FROM member_activity
                    WHERE guild_id = $1 AND user_id = $2 AND message_date >= CURRENT_DATE - INTERVAL '6 days';
                    """,
                    guild_id,
                    user_id,
                )
                actual = int(row["cnt"]) if row else 0
                return actual >= threshold, actual

            elif req_type in ("messages_channel", "channel") and channel_id:
                row = await self.db.fetch_one(
                    """
                    SELECT COALESCE(SUM(message_count), 0) AS cnt
                    FROM member_activity_channel
                    WHERE guild_id = $1 AND user_id = $2 AND channel_id = $3
                      AND message_date >= CURRENT_DATE - INTERVAL '6 days';
                    """,
                    guild_id,
                    user_id,
                    channel_id,
                )
                actual = int(row["cnt"]) if row else 0
                return actual >= threshold, actual

            return True, 0
        except Exception as e:
            logger.debug(f"Error checking activity requirement: {e}")
            return False, 0
