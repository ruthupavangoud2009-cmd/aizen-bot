"""
Kyoka 3.0 - Guild-Scoped Branding Manager
Strict per-server bot identity management (Avatar, Bio, Banner, Name).
Guarantees absolute server isolation with in-memory caching and safe fallbacks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from src.core.config import Config

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.Branding")


class BrandingManager:
    """Manages guild-specific bot branding (name, bio, avatar, banner) with caching and strict server isolation."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._cache: dict[int, dict[str, Any]] = {}

    def get_default_branding(self) -> dict[str, Any]:
        """Return the global default KYOKA branding."""
        assets = getattr(Config, "ASSETS", None)
        default_avatar = getattr(assets, "AIZEN_AVATAR_URL", "") if assets else ""
        default_banner = getattr(assets, "BANNER_URL", "") if assets else ""
        return {
            "guild_id": None,
            "display_name": "KYOKA 3.0",
            "bio": "Power isn't given. It's taken. — Sosuke Aizen",
            "avatar_url": default_avatar or "https://cdn.discordapp.com/embed/avatars/0.png",
            "banner_url": default_banner or "",
            "is_custom": False,
            "applied_nickname": False,
            "applied_discord_avatar": False,
            "set_by": None,
            "updated_at": None,
        }

    def invalidate_cache(self, guild_id: int) -> None:
        """Invalidate the cached branding for a specific guild."""
        self._cache.pop(guild_id, None)

    async def get_branding(self, guild_id: int | None) -> dict[str, Any]:
        """
        Fetch branding for a guild.
        Strict isolation:
        - If guild_id is None (e.g. DM): return global default branding.
        - If guild_id has custom settings: return custom settings with fallback for any unset field.
        - If guild_id has no custom settings: return global default branding.
        """
        if not guild_id:
            return self.get_default_branding()

        if guild_id in self._cache:
            return dict(self._cache[guild_id])

        defaults = self.get_default_branding()
        defaults["guild_id"] = guild_id

        if not self.db:
            return defaults

        query = """
        SELECT guild_id, display_name, bio, avatar_url, banner_url, set_by, applied_nickname, applied_discord_avatar, updated_at
        FROM guild_branding
        WHERE guild_id = ?;
        """
        try:
            row = await self.db.fetch_one(query, guild_id)
            if row:
                is_custom = bool(
                    row.get("display_name") or row.get("bio") or row.get("avatar_url") or row.get("banner_url")
                )
                branding = {
                    "guild_id": guild_id,
                    "display_name": row.get("display_name") or defaults["display_name"],
                    "bio": row.get("bio") or defaults["bio"],
                    "avatar_url": row.get("avatar_url") or defaults["avatar_url"],
                    "banner_url": row.get("banner_url") or defaults["banner_url"],
                    "is_custom": is_custom,
                    "applied_nickname": bool(row.get("applied_nickname")),
                    "applied_discord_avatar": bool(row.get("applied_discord_avatar")),
                    "set_by": row.get("set_by"),
                    "updated_at": row.get("updated_at"),
                }
                self._cache[guild_id] = branding
                return dict(branding)
        except Exception as e:
            logger.debug(f"Notice fetching branding for guild {guild_id}: {e}")

        # Fallback to defaults
        self._cache[guild_id] = defaults
        return dict(defaults)

    async def set_field(
        self,
        guild_id: int,
        field: str,
        value: Any,
        set_by: int,
        extra_flags: dict[str, bool] | None = None,
    ) -> None:
        """Safely upsert a specific branding field for a guild."""
        if field not in {"display_name", "bio", "avatar_url", "banner_url"}:
            raise ValueError(f"Invalid branding field: {field}")

        extra = extra_flags or {}
        nick_flag = extra.get("applied_nickname")
        avatar_flag = extra.get("applied_discord_avatar")

        nick_clause = f", applied_nickname = {str(nick_flag).upper()}" if nick_flag is not None else ""
        avatar_clause = f", applied_discord_avatar = {str(avatar_flag).upper()}" if avatar_flag is not None else ""

        nick_insert_col = ", applied_nickname" if nick_flag is not None else ""
        nick_insert_val = f", {str(nick_flag).upper()}" if nick_flag is not None else ""
        avatar_insert_col = ", applied_discord_avatar" if avatar_flag is not None else ""
        avatar_insert_val = f", {str(avatar_flag).upper()}" if avatar_flag is not None else ""

        query = f"""
        INSERT INTO guild_branding (guild_id, {field}, set_by, updated_at{nick_insert_col}{avatar_insert_col})
        VALUES (?, ?, ?, CURRENT_TIMESTAMP{nick_insert_val}{avatar_insert_val})
        ON CONFLICT (guild_id) DO UPDATE SET
            {field} = excluded.{field},
            set_by = excluded.set_by,
            updated_at = CURRENT_TIMESTAMP{nick_clause}{avatar_clause};
        """

        try:
            await self.db.execute(query, guild_id, value, set_by)
            if guild_id in self._cache:
                self._cache[guild_id][field] = value
                self._cache[guild_id]["is_custom"] = True
                if extra_flags:
                    self._cache[guild_id].update(extra_flags)
            else:
                defaults = self.get_default_branding()
                defaults["guild_id"] = guild_id
                defaults[field] = value
                defaults["is_custom"] = True
                if extra_flags:
                    defaults.update(extra_flags)
                self._cache[guild_id] = defaults
        except Exception as e:
            logger.error(f"Failed to update branding {field} for guild {guild_id}: {e}")
            raise

    async def load_cache(self) -> None:
        """Preload all server branding configurations into memory."""
        if not self.db or not hasattr(self.db, "fetch_all"):
            return
        query = """
        SELECT guild_id, display_name, bio, avatar_url, banner_url, set_by, applied_nickname, applied_discord_avatar, updated_at
        FROM guild_branding;
        """
        try:
            rows = await self.db.fetch_all(query)
            defaults = self.get_default_branding()
            for row in rows:
                gid = row.get("guild_id")
                if not gid:
                    continue
                is_custom = bool(
                    row.get("display_name") or row.get("bio") or row.get("avatar_url") or row.get("banner_url")
                )
                self._cache[int(gid)] = {
                    "guild_id": int(gid),
                    "display_name": row.get("display_name") or defaults["display_name"],
                    "bio": row.get("bio") or defaults["bio"],
                    "avatar_url": row.get("avatar_url") or defaults["avatar_url"],
                    "banner_url": row.get("banner_url") or defaults["banner_url"],
                    "is_custom": is_custom,
                    "applied_nickname": bool(row.get("applied_nickname")),
                    "applied_discord_avatar": bool(row.get("applied_discord_avatar")),
                    "set_by": row.get("set_by"),
                    "updated_at": row.get("updated_at"),
                }
            logger.info("Loaded %d guild branding configurations into cache.", len(self._cache))
        except Exception as e:
            logger.warning("Could not pre-load guild branding cache: %s", e)

    async def reset_field(self, guild_id: int, field: str) -> None:
        """Reset a single branding field back to default for a guild."""
        if field not in {"display_name", "bio", "avatar_url", "banner_url"}:
            raise ValueError(f"Invalid branding field: {field}")
        if not self.db:
            return
        query = f"UPDATE guild_branding SET {field} = NULL, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?;"
        try:
            await self.db.execute(query, guild_id)
            if guild_id in self._cache:
                defaults = self.get_default_branding()
                self._cache[guild_id][field] = defaults[field]
                is_custom = any(
                    self._cache[guild_id].get(f) != defaults[f]
                    for f in ("display_name", "bio", "avatar_url", "banner_url")
                )
                self._cache[guild_id]["is_custom"] = is_custom
            else:
                self.invalidate_cache(guild_id)
        except Exception as e:
            logger.error(f"Failed to reset branding field {field} for guild {guild_id}: {e}")
            raise

    async def reset_branding(self, guild_id: int) -> None:
        """Reset all branding for a guild back to global default."""
        try:
            if self.db:
                await self.db.execute("DELETE FROM guild_branding WHERE guild_id = ?;", guild_id)
            defaults = self.get_default_branding()
            defaults["guild_id"] = guild_id
            self._cache[guild_id] = defaults
        except Exception as e:
            logger.error(f"Failed to reset branding for guild {guild_id}: {e}")
            raise

