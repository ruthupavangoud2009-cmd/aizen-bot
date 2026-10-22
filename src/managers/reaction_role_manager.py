from __future__ import annotations

import logging
from typing import Any
from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.ReactionRoles")


class ReactionRoleManager:
    """Production-grade Reaction Roles manager with ultra-fast memory caching."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # message_id -> emoji -> binding dict
        self._bindings: dict[int, dict[str, dict[str, Any]]] = {}
        # guild_id -> set of message_ids
        self._guild_messages: dict[int, set[int]] = {}

    async def load_cache(self) -> None:
        """Preload all active reaction role bindings into memory for 0ms lookup latency."""
        try:
            rows = await self.db.fetch_all("SELECT * FROM reaction_roles ORDER BY id ASC;")
            self._bindings.clear()
            self._guild_messages.clear()

            count = 0
            for r in rows:
                mid = int(r["message_id"])
                gid = int(r["guild_id"])
                emoji = str(r["emoji"])

                if mid not in self._bindings:
                    self._bindings[mid] = {}
                self._bindings[mid][emoji] = dict(r)

                if gid not in self._guild_messages:
                    self._guild_messages[gid] = set()
                self._guild_messages[gid].add(mid)
                count += 1

            logger.info(f"Loaded {count} reaction role bindings across {len(self._guild_messages)} servers into memory.")
        except Exception as e:
            logger.error(f"Failed to load reaction roles cache: {e}", exc_info=e)

    async def add_binding(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        emoji: str,
        role_id: int,
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Save a reaction role binding to DB and update memory cache."""
        clean_mode = str(mode).lower() if mode in ("normal", "unique", "verify") else "normal"
        emoji_str = str(emoji).strip()

        await self.db.execute(
            """
            INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id, mode)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (message_id, emoji)
            DO UPDATE SET role_id = EXCLUDED.role_id, mode = EXCLUDED.mode;
            """,
            guild_id,
            channel_id,
            message_id,
            emoji_str,
            role_id,
            clean_mode,
        )

        binding = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "emoji": emoji_str,
            "role_id": role_id,
            "mode": clean_mode,
        }

        if message_id not in self._bindings:
            self._bindings[message_id] = {}
        self._bindings[message_id][emoji_str] = binding

        if guild_id not in self._guild_messages:
            self._guild_messages[guild_id] = set()
        self._guild_messages[guild_id].add(message_id)

        return binding

    async def remove_binding(self, message_id: int, emoji: str) -> bool:
        """Remove a reaction role binding by message ID and emoji."""
        emoji_str = str(emoji).strip()
        await self.db.execute(
            "DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?;",
            message_id,
            emoji_str,
        )

        if message_id in self._bindings:
            self._bindings[message_id].pop(emoji_str, None)
            if not self._bindings[message_id]:
                del self._bindings[message_id]
                for g_set in self._guild_messages.values():
                    g_set.discard(message_id)
            return True
        return False

    async def clear_bindings(self, message_id: int) -> int:
        """Delete all reaction roles attached to a message."""
        count = len(self._bindings.get(message_id, {}))
        await self.db.execute("DELETE FROM reaction_roles WHERE message_id = ?;", message_id)

        if message_id in self._bindings:
            del self._bindings[message_id]
            for g_set in self._guild_messages.values():
                g_set.discard(message_id)

        return count

    def get_binding(self, message_id: int, emoji: str) -> dict[str, Any] | None:
        """Fast O(1) in-memory lookup for a reaction role binding."""
        emoji_str = str(emoji).strip()
        msg_bindings = self._bindings.get(message_id)
        if not msg_bindings:
            return None
        return msg_bindings.get(emoji_str)

    def get_message_bindings(self, message_id: int) -> list[dict[str, Any]]:
        """Return all bindings registered on a message."""
        return list(self._bindings.get(message_id, {}).values())

    def get_guild_bindings(self, guild_id: int) -> list[dict[str, Any]]:
        """Return all bindings for an entire guild."""
        res: list[dict[str, Any]] = []
        msg_ids = self._guild_messages.get(guild_id, set())
        for mid in msg_ids:
            res.extend(self._bindings.get(mid, {}).values())
        return res
