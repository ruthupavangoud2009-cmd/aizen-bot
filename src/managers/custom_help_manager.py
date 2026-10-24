"""
Kyoka Discord Bot - Per-Server Custom Help Category Manager
Allows server administrators to create, edit, organize, and customize their own help categories
and assign registered bot commands to them dynamically without editing Python source code.
Includes in-memory caching with automatic invalidation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.CustomHelp")


class CustomHelpManager:
    """Manages custom guild-specific command categories stored in PostgreSQL with caching."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._cache: dict[int, list[dict[str, Any]]] = {}

    def invalidate_cache(self, guild_id: int) -> None:
        """Clear cache for a guild."""
        self._cache.pop(guild_id, None)

    async def get_guild_categories(self, guild_id: int) -> list[dict[str, Any]]:
        """Retrieve all custom help categories for a guild ordered by priority and name."""
        if guild_id in self._cache:
            return self._cache[guild_id]

        query = """
        SELECT guild_id, category_name, emoji, description, commands, priority, is_hidden
        FROM guild_custom_help_categories
        WHERE guild_id = $1
        ORDER BY priority ASC, category_name ASC;
        """
        try:
            rows = await self.db.fetch_all(query, guild_id)
            categories = [dict(r) for r in rows] if rows else []
            self._cache[guild_id] = categories
            return categories
        except Exception as e:
            logger.debug(f"Notice fetching custom categories for guild {guild_id}: {e}")
            return []

    async def create_category(
        self,
        guild_id: int,
        name: str,
        emoji: str = "📁",
        description: str = "Custom server commands",
    ) -> tuple[bool, str]:
        """Create a new custom help category for a guild."""
        clean_name = name.strip()[:64]
        if not clean_name:
            return False, "Category name cannot be empty."

        clean_emoji = (emoji or "📁").strip()[:32]
        clean_desc = (description or "Custom server commands").strip()[:128]

        query = """
        INSERT INTO guild_custom_help_categories (guild_id, category_name, emoji, description, commands, priority, is_hidden)
        VALUES ($1, $2, $3, $4, '{}', 0, FALSE)
        ON CONFLICT (guild_id, category_name) DO NOTHING
        RETURNING category_name;
        """
        try:
            row = await self.db.fetch_one(query, guild_id, clean_name, clean_emoji, clean_desc)
            self.invalidate_cache(guild_id)
            if row:
                return True, f"Category **{clean_name}** created successfully."
            return False, f"A category named **{clean_name}** already exists."
        except Exception as e:
            logger.error(f"Error creating custom category: {e}")
            return False, f"Database error creating category: {e}"

    async def rename_category(
        self,
        guild_id: int,
        old_name: str,
        new_name: str,
    ) -> tuple[bool, str]:
        """Rename an existing custom category."""
        clean_old = old_name.strip()
        clean_new = new_name.strip()[:64]
        if not clean_new:
            return False, "New category name cannot be empty."

        query = """
        UPDATE guild_custom_help_categories
        SET category_name = $1
        WHERE guild_id = $2 AND LOWER(category_name) = LOWER($3)
        RETURNING category_name;
        """
        try:
            row = await self.db.fetch_one(query, clean_new, guild_id, clean_old)
            self.invalidate_cache(guild_id)
            if row:
                return True, f"Renamed category to **{clean_new}**."
            return False, f"Category **{old_name}** was not found."
        except Exception as e:
            logger.error(f"Error renaming custom category: {e}")
            return False, f"Error renaming category: {e}"

    async def set_emoji(
        self,
        guild_id: int,
        name: str,
        emoji: str,
    ) -> tuple[bool, str]:
        """Update the icon/emoji for a custom category."""
        clean_name = name.strip()
        clean_emoji = (emoji or "📁").strip()[:32]

        query = """
        UPDATE guild_custom_help_categories
        SET emoji = $1
        WHERE guild_id = $2 AND LOWER(category_name) = LOWER($3)
        RETURNING category_name;
        """
        try:
            row = await self.db.fetch_one(query, clean_emoji, guild_id, clean_name)
            self.invalidate_cache(guild_id)
            if row:
                return True, f"Set emoji for **{row['category_name']}** to {clean_emoji}."
            return False, f"Category **{name}** was not found."
        except Exception as e:
            logger.error(f"Error updating emoji: {e}")
            return False, f"Error updating emoji: {e}"

    async def add_command(
        self,
        guild_id: int,
        category_name: str,
        command_name: str,
        all_registered_commands: set[str],
        owner_only_commands: set[str],
    ) -> tuple[bool, str]:
        """Add a registered command to a custom category with security validation."""
        cmd_lower = command_name.strip().lower()
        if cmd_lower in owner_only_commands:
            return False, f"Security violation: Owner-only command `{command_name}` cannot be added to custom categories."

        if cmd_lower not in all_registered_commands:
            return False, f"Command `{command_name}` is not a registered bot command."

        query = """
        UPDATE guild_custom_help_categories
        SET commands = array_append(commands, $1)
        WHERE guild_id = $2 AND LOWER(category_name) = LOWER($3) AND NOT ($1 = ANY(commands))
        RETURNING category_name, commands;
        """
        try:
            row = await self.db.fetch_one(query, cmd_lower, guild_id, category_name.strip())
            self.invalidate_cache(guild_id)
            if row:
                return True, f"Added `{cmd_lower}` to **{row['category_name']}**."
            # Check if it didn't update because category didn't exist or command was already present
            existing = await self.get_guild_categories(guild_id)
            matched = next((c for c in existing if c["category_name"].lower() == category_name.strip().lower()), None)
            if not matched:
                return False, f"Category **{category_name}** was not found."
            if cmd_lower in (matched.get("commands") or []):
                return False, f"Command `{cmd_lower}` is already in **{matched['category_name']}**."
            return False, "Failed to add command."
        except Exception as e:
            logger.error(f"Error adding command to custom category: {e}")
            return False, f"Error: {e}"

    async def remove_command(
        self,
        guild_id: int,
        category_name: str,
        command_name: str,
    ) -> tuple[bool, str]:
        """Remove a command from a custom category."""
        cmd_lower = command_name.strip().lower()

        query = """
        UPDATE guild_custom_help_categories
        SET commands = array_remove(commands, $1)
        WHERE guild_id = $2 AND LOWER(category_name) = LOWER($3)
        RETURNING category_name, commands;
        """
        try:
            row = await self.db.fetch_one(query, cmd_lower, guild_id, category_name.strip())
            self.invalidate_cache(guild_id)
            if row:
                return True, f"Removed `{cmd_lower}` from **{row['category_name']}**."
            return False, f"Category **{category_name}** was not found."
        except Exception as e:
            logger.error(f"Error removing command from custom category: {e}")
            return False, f"Error: {e}"

    async def delete_category(
        self,
        guild_id: int,
        name: str,
    ) -> tuple[bool, str]:
        """Permanently delete a custom category."""
        query = """
        DELETE FROM guild_custom_help_categories
        WHERE guild_id = $1 AND LOWER(category_name) = LOWER($2)
        RETURNING category_name;
        """
        try:
            row = await self.db.fetch_one(query, guild_id, name.strip())
            self.invalidate_cache(guild_id)
            if row:
                return True, f"Deleted category **{row['category_name']}**."
            return False, f"Category **{name}** was not found."
        except Exception as e:
            logger.error(f"Error deleting custom category: {e}")
            return False, f"Error: {e}"

    async def set_visibility(
        self,
        guild_id: int,
        name: str,
        is_hidden: bool,
    ) -> tuple[bool, str]:
        """Show or hide a custom category from the public help menu."""
        query = """
        UPDATE guild_custom_help_categories
        SET is_hidden = $1
        WHERE guild_id = $2 AND LOWER(category_name) = LOWER($3)
        RETURNING category_name;
        """
        try:
            row = await self.db.fetch_one(query, is_hidden, guild_id, name.strip())
            self.invalidate_cache(guild_id)
            if row:
                status = "hidden" if is_hidden else "visible"
                return True, f"Category **{row['category_name']}** is now **{status}**."
            return False, f"Category **{name}** was not found."
        except Exception as e:
            logger.error(f"Error setting visibility: {e}")
            return False, f"Error: {e}"

    async def reset_categories(self, guild_id: int) -> tuple[bool, str]:
        """Delete all custom help categories for a guild, restoring bot defaults."""
        query = "DELETE FROM guild_custom_help_categories WHERE guild_id = $1;"
        try:
            await self.db.execute(query, guild_id)
            self.invalidate_cache(guild_id)
            return True, "All custom categories have been cleared. Default help layout restored."
        except Exception as e:
            logger.error(f"Error resetting custom categories: {e}")
            return False, f"Error resetting categories: {e}"
