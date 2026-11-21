from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from src.core.config import Config
from src.core.cache import MicrosecondCache

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyoka.GuildManager")


class GuildManager:
    """Manages guild-specific configurations with zero-latency in-memory cache."""

    COLOR_PRESETS: dict[str, int] = {
        "grey": 0x2B2D31,
        "gray": 0x2B2D31,
        "dark_grey": 0x1E1F22,
        "dark_gray": 0x1E1F22,
        "light_grey": 0x808080,
        "light_gray": 0x808080,
        "silver": 0xCCCCCC,
        "white": 0xF8FAFC,
        "black": 0x0A0A0F,
        "dark": 0x120C1F,
        "purple": 0x7C3AED,
        "violet": 0x2B0938,
        "aizen": 0x2B0938,
        "blue": 0x38BDF8,
        "cyan": 0x06B6D4,
        "green": 0x10B981,
        "emerald": 0x10B981,
        "red": 0xEF4444,
        "crimson": 0xFF3366,
        "pink": 0xF472B6,
        "sakura": 0xFFB7C5,
        "gold": 0xF59E0B,
        "amber": 0xF59E0B,
        "orange": 0xF97316,
    }

    def __init__(self, db: BaseDatabase, cache: MicrosecondCache | None = None) -> None:
        self.db = db
        self.cache = cache or MicrosecondCache()

    async def load_cache(self) -> None:
        """Load all guild settings into memory on bot startup."""
        try:
            records = await self.db.fetch_all("SELECT guild_id, prefix, disabled_commands, ui_color FROM guild_settings;")
            for row in records:
                g_id = row["guild_id"]
                if row.get("prefix"):
                    self.cache.set_prefix(g_id, row["prefix"])

                disabled = row.get("disabled_commands") or ""
                if disabled:
                    self.cache.set_disabled_commands(g_id, set(disabled.split(",")))

                raw_color = row.get("ui_color")
                if raw_color:
                    c_val, _ = self.parse_color(str(raw_color))
                    if c_val is not None:
                        self.cache.set_ui_color(g_id, c_val)
        except Exception:
            records = await self.db.fetch_all("SELECT guild_id, prefix, disabled_commands FROM guild_settings;")
            for row in records:
                g_id = row["guild_id"]
                if row.get("prefix"):
                    self.cache.set_prefix(g_id, row["prefix"])
                disabled = row.get("disabled_commands") or ""
                if disabled:
                    self.cache.set_disabled_commands(g_id, set(disabled.split(",")))

        logger.info(f"Loaded {len(self.cache.prefixes)} guild prefix(es) and {len(self.cache.ui_colors)} UI color(s) into L1 microsecond cache.")

    def parse_color(self, color_input: str) -> tuple[int | None, str]:
        """Parse color name or hex code into integer color value and display name."""
        clean = color_input.strip().lower().replace("#", "").replace("0x", "")
        if clean in self.COLOR_PRESETS:
            return self.COLOR_PRESETS[clean], clean.replace("_", " ").title()
        if len(clean) == 6:
            try:
                val = int(clean, 16)
                return val, f"#{clean.upper()}"
            except ValueError:
                pass
        return None, ""

    def get_ui_color(self, guild_id: int | None, default: int = 0x2B0938) -> int:
        """Retrieve the configured UI color for a guild."""
        return self.cache.get_ui_color(guild_id, default=default)

    async def set_ui_color(self, guild_id: int, color_val: int) -> None:
        """Store guild UI color in memory and database."""
        self.cache.set_ui_color(guild_id, color_val)
        hex_str = f"#{color_val:06X}"
        try:
            await self.db.execute(
                """
                ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS ui_color VARCHAR(16);
                """
            )
            await self.db.execute(
                """
                INSERT INTO guild_settings (guild_id, ui_color)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET ui_color = excluded.ui_color;
                """,
                guild_id,
                hex_str,
            )
        except Exception as e:
            logger.debug(f"Notice saving ui_color: {e}")

    async def reset_ui_color(self, guild_id: int) -> None:
        """Reset guild UI color to default."""
        self.cache.reset_ui_color(guild_id)
        try:
            await self.db.execute(
                """
                UPDATE guild_settings SET ui_color = NULL WHERE guild_id = ?;
                """,
                guild_id,
            )
        except Exception as e:
            logger.debug(f"Notice resetting ui_color: {e}")

    def get_prefix(self, guild_id: int | None) -> str:
        """Retrieve prefix from L1 memory cache (<0.01ms)."""
        return self.cache.get_prefix(guild_id, Config.DEFAULT_PREFIX)

    async def set_prefix(self, guild_id: int, new_prefix: str) -> None:
        """Update guild prefix in database and L1 memory cache immediately."""
        self.cache.set_prefix(guild_id, new_prefix)
        await self.db.execute(
            """
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix;
            """,
            guild_id,
            new_prefix,
        )
        logger.info(f"Guild {guild_id} prefix updated to '{new_prefix}'")

    async def reset_prefix(self, guild_id: int) -> None:
        """Reset guild prefix to bot default."""
        self.cache.reset_prefix(guild_id)
        await self.db.execute(
            """
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix;
            """,
            guild_id,
            Config.DEFAULT_PREFIX,
        )
        logger.info(f"Guild {guild_id} prefix reset to default '{Config.DEFAULT_PREFIX}'")

    def is_command_disabled(self, guild_id: int | None, command_name: str) -> bool:
        """Check if a command is disabled in a guild (<0.01ms)."""
        return self.cache.is_command_disabled(guild_id, command_name)
