"""
KYOKA — Moderation Case Ledger Manager
Manages sequential per-guild moderation case IDs (#1, #2, ...), case history,
moderator statistics, reason editing, and persistent PostgreSQL storage.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("Kyoka.Managers.Case")


class CaseManager:
    """Service layer for persistent moderation cases in PostgreSQL."""

    def __init__(self, db: Any) -> None:
        self.db = db

    async def create_case(
        self,
        guild_id: int,
        action: str,
        user_id: int,
        moderator_id: int,
        reason: str = "No reason provided",
        duration: Optional[str] = None,
        evidence: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[int]:
        """Create a new moderation case and return the sequential per-guild case_id."""
        if not self.db or not getattr(self.db, "_connected_once", False):
            return None

        clean_reason = (reason or "No reason provided").strip()[:1000]
        clean_action = (action or "action").strip().lower()[:32]

        try:
            row = await self.db.fetch_one(
                "SELECT COALESCE(MAX(case_id), 0) + 1 AS next_id FROM mod_cases WHERE guild_id = ?;",
                guild_id,
            )
            next_id = int(row["next_id"]) if row and row.get("next_id") else 1

            await self.db.execute(
                """
                INSERT INTO mod_cases
                    (guild_id, case_id, action, user_id, moderator_id, reason, duration, evidence, notes, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE);
                """,
                guild_id,
                next_id,
                clean_action,
                user_id,
                moderator_id,
                clean_reason,
                duration[:64] if duration else None,
                evidence[:1000] if evidence else None,
                notes[:1000] if notes else None,
            )
            return next_id
        except Exception as exc:
            logger.warning("Failed to record moderation case in guild %s: %s", guild_id, exc)
            return None

    async def get_case(self, guild_id: int, case_id: int) -> Optional[dict[str, Any]]:
        """Retrieve a single moderation case by guild_id and case_id."""
        if not self.db:
            return None
        return await self.db.fetch_one(
            "SELECT * FROM mod_cases WHERE guild_id = ? AND case_id = ?;",
            guild_id,
            case_id,
        )

    async def list_cases(
        self,
        guild_id: int,
        user_id: Optional[int] = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Retrieve recent moderation cases for a guild or specific target user."""
        if not self.db:
            return []
        safe_limit = max(1, min(100, int(limit)))
        if user_id is not None:
            return await self.db.fetch_all(
                """
                SELECT * FROM mod_cases
                WHERE guild_id = ? AND user_id = ?
                ORDER BY case_id DESC
                LIMIT ?;
                """,
                guild_id,
                user_id,
                safe_limit,
            )
        return await self.db.fetch_all(
            """
            SELECT * FROM mod_cases
            WHERE guild_id = ?
            ORDER BY case_id DESC
            LIMIT ?;
            """,
            guild_id,
            safe_limit,
        )

    async def update_reason(
        self,
        guild_id: int,
        case_id: int,
        new_reason: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Update the reason (and optional notes) on an existing moderation case."""
        if not self.db:
            return False
        existing = await self.get_case(guild_id, case_id)
        if not existing:
            return False

        clean_reason = (new_reason or "No reason provided").strip()[:1000]
        if notes is not None:
            await self.db.execute(
                """
                UPDATE mod_cases
                SET reason = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND case_id = ?;
                """,
                clean_reason,
                notes.strip()[:1000],
                guild_id,
                case_id,
            )
        else:
            await self.db.execute(
                """
                UPDATE mod_cases
                SET reason = ?, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND case_id = ?;
                """,
                clean_reason,
                guild_id,
                case_id,
            )
        return True

    async def get_moderator_stats(self, guild_id: int, moderator_id: int) -> dict[str, int]:
        """Aggregate moderation action counts by a specific moderator."""
        if not self.db:
            return {}
        rows = await self.db.fetch_all(
            """
            SELECT action, COUNT(*) AS cnt
            FROM mod_cases
            WHERE guild_id = ? AND moderator_id = ?
            GROUP BY action;
            """,
            guild_id,
            moderator_id,
        )
        stats: dict[str, int] = {}
        total = 0
        for r in rows:
            act = str(r.get("action", "other")).lower()
            cnt = int(r.get("cnt", 0))
            stats[act] = cnt
            total += cnt
        stats["total"] = total
        return stats
