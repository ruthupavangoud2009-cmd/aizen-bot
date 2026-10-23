from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Optional

import discord

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.Leveling")


def xp_for_level(level: int) -> int:
    """XP needed to advance from level to level + 1."""
    lvl = max(1, level)
    return int(5 * (lvl ** 2) + (50 * lvl) + 100)


def total_xp_for_level(level: int) -> int:
    """Total cumulative XP required to reach level starting from level 1."""
    if level <= 1:
        return 0
    return sum(xp_for_level(lvl) for lvl in range(1, level))


def level_from_total_xp(total_xp: int) -> tuple[int, int, int]:
    """
    Calculate level, current progress in level, and XP needed for next level.
    Returns: (level, current_level_xp, needed_for_next)
    """
    xp = max(0, total_xp)
    lvl = 1
    while True:
        needed = xp_for_level(lvl)
        if xp < needed:
            return lvl, xp, needed
        xp -= needed
        lvl += 1


class LevelingManager:
    """
    Production-grade progression & leveling engine for KYOKA 3.0.
    Handles per-guild XP tracking, mathematically balanced progression curves,
    cooldown management, and leaderboard analytics.
    """

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # (guild_id, user_id) -> monotonic timestamp of last awarded XP
        self._cooldowns: dict[tuple[int, int], float] = {}
        # guild_id -> settings dict
        self._guild_settings: dict[int, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load guild leveling configurations into memory cache."""
        try:
            # Ensure leveling_settings table exists
            await self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS leveling_settings (
                    guild_id BIGINT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT TRUE,
                    announce_level_up BOOLEAN DEFAULT TRUE,
                    channel_id BIGINT,
                    cooldown_seconds INT DEFAULT 60,
                    min_xp INT DEFAULT 15,
                    max_xp INT DEFAULT 25,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            rows = await self.db.fetch_all("SELECT * FROM leveling_settings;")
            async with self._lock:
                self._guild_settings.clear()
                for r in rows:
                    self._guild_settings[int(r["guild_id"])] = {
                        "enabled": bool(r.get("enabled", True)),
                        "announce": bool(r.get("announce_level_up", True)),
                        "channel_id": int(r["channel_id"]) if r.get("channel_id") else None,
                        "cooldown": int(r.get("cooldown_seconds", 60)),
                        "min_xp": int(r.get("min_xp", 15)),
                        "max_xp": int(r.get("max_xp", 25)),
                    }
            logger.info(f"Loaded {len(self._guild_settings)} guild leveling setting(s).")
        except Exception as e:
            logger.debug(f"Notice loading leveling settings: {e}")

    def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        """Fetch cached settings with default values."""
        return self._guild_settings.get(
            guild_id,
            {
                "enabled": True,
                "announce": True,
                "channel_id": None,
                "cooldown": 60,
                "min_xp": 15,
                "max_xp": 25,
            },
        )

    async def award_message_xp(
        self,
        guild_id: int,
        user_id: int,
        is_opted_out: bool = False,
    ) -> tuple[bool, int, int, bool]:
        """
        Evaluate and award XP for a qualifying guild message.
        Returns: (awarded: bool, new_total_xp: int, new_level: int, leveled_up: bool)
        """
        if is_opted_out:
            return False, 0, 1, False

        settings = self.get_guild_settings(guild_id)
        if not settings["enabled"]:
            return False, 0, 1, False

        now = time.monotonic()
        key = (guild_id, user_id)
        last_time = self._cooldowns.get(key, 0.0)
        cooldown = settings.get("cooldown", 60)

        if now - last_time < cooldown:
            return False, 0, 1, False

        self._cooldowns[key] = now
        gain = random.randint(settings.get("min_xp", 15), settings.get("max_xp", 25))

        try:
            # Fetch existing profile
            row = await self.db.fetch_one(
                "SELECT xp, level FROM user_profiles WHERE guild_id = $1 AND user_id = $2;",
                guild_id,
                user_id,
            )
            old_xp = int(row["xp"]) if row and row.get("xp") is not None else 0
            old_lvl = int(row["level"]) if row and row.get("level") is not None else 1

            new_total_xp = old_xp + gain
            calc_lvl, _, _ = level_from_total_xp(new_total_xp)
            leveled_up = calc_lvl > old_lvl

            await self.db.execute(
                """
                INSERT INTO user_profiles (user_id, guild_id, xp, level)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET
                    xp = EXCLUDED.xp,
                    level = EXCLUDED.level;
                """,
                user_id,
                guild_id,
                new_total_xp,
                calc_lvl,
            )

            return True, new_total_xp, calc_lvl, leveled_up
        except Exception as e:
            logger.debug(f"Error awarding message XP: {e}")
            return False, 0, 1, False

    async def get_user_rank(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Fetch member level, current XP in level, needed XP for next level, and server rank."""
        try:
            row = await self.db.fetch_one(
                "SELECT xp, level FROM user_profiles WHERE guild_id = $1 AND user_id = $2;",
                guild_id,
                user_id,
            )
            total_xp = int(row["xp"]) if row and row.get("xp") is not None else 0
            calc_lvl, cur_xp, needed_xp = level_from_total_xp(total_xp)

            rank_row = await self.db.fetch_one(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM user_profiles
                WHERE guild_id = $1 AND xp > $2;
                """,
                guild_id,
                total_xp,
            )
            server_rank = int(rank_row["rank"]) if rank_row else 1

            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "total_xp": total_xp,
                "level": calc_lvl,
                "current_xp": cur_xp,
                "needed_xp": needed_xp,
                "rank": server_rank,
            }
        except Exception as e:
            logger.debug(f"Error fetching user rank: {e}")
            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "total_xp": 0,
                "level": 1,
                "current_xp": 0,
                "needed_xp": xp_for_level(1),
                "rank": 1,
            }

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch top members in the guild by total XP."""
        limit = max(1, min(limit, 25))
        try:
            rows = await self.db.fetch_all(
                """
                SELECT user_id, xp, level
                FROM user_profiles
                WHERE guild_id = $1 AND xp > 0
                ORDER BY xp DESC
                LIMIT $2;
                """,
                guild_id,
                limit,
            )
            results = []
            for r in rows:
                t_xp = int(r["xp"])
                lvl, cur_xp, need_xp = level_from_total_xp(t_xp)
                results.append({
                    "user_id": int(r["user_id"]),
                    "total_xp": t_xp,
                    "level": lvl,
                    "current_xp": cur_xp,
                    "needed_xp": need_xp,
                })
            return results
        except Exception as e:
            logger.debug(f"Error fetching guild leveling leaderboard: {e}")
            return []
