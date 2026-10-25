"""
Central fail-closed authorization guard for restricted Adult Humor commands.
Validates against persistent SQLite database (data/kyoka_adult.sqlite3),
ADULT_COMMAND_ALLOWLIST environment variable, and Primary Owner (1505515188991033409).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional
import discord

from src.security.owner import OWNER_ID, is_primary_owner

logger = logging.getLogger("Kyoka.Security.AdultGuard")

ADULT_DB_PATH = Path("data/kyoka_adult.sqlite3")
_cached_allowlist: Optional[set[int]] = None


def _get_adult_db() -> sqlite3.Connection:
    """Connect to adult allowlist SQLite database and ensure tables exist."""
    ADULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ADULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS adult_allowlist (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER NOT NULL,
            added_at REAL NOT NULL,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS adult_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_user_id INTEGER NOT NULL,
            performed_by INTEGER NOT NULL,
            action TEXT NOT NULL,
            timestamp REAL NOT NULL,
            notes TEXT DEFAULT ''
        );
    """)
    return conn


def get_adult_allowlist() -> set[int]:
    """
    Parse and validate authorized Discord user IDs from database and ADULT_COMMAND_ALLOWLIST.
    Primary bot owner is always authorized.
    """
    global _cached_allowlist
    if _cached_allowlist is None:
        _cached_allowlist = {OWNER_ID}
        # Load from persistent SQLite database
        try:
            with _get_adult_db() as conn:
                rows = conn.execute("SELECT user_id FROM adult_allowlist").fetchall()
                for r in rows:
                    _cached_allowlist.add(int(r["user_id"]))
        except Exception as ex:
            logger.warning(f"Failed to read adult_allowlist database: {ex}")

    allowlist = set(_cached_allowlist)

    # Merge with current environment variable if configured
    raw = os.getenv("ADULT_COMMAND_ALLOWLIST", "").strip()
    if raw:
        for token in raw.split(","):
            cleaned = token.strip()
            if cleaned.isdigit():
                allowlist.add(int(cleaned))

    return allowlist


def add_adult_user(user_id: int, added_by: int, notes: str = "") -> bool:
    """
    Add a user to the persistent adult command allowlist.
    Only primary owner can perform this. Revocation/addition takes effect immediately.
    """
    global _cached_allowlist
    now = time.time()
    try:
        with _get_adult_db() as conn:
            conn.execute(
                "INSERT INTO adult_allowlist (user_id, added_by, added_at, notes) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET added_by=excluded.added_by, added_at=excluded.added_at, notes=excluded.notes",
                (int(user_id), int(added_by), now, notes[:200]),
            )
            conn.execute(
                "INSERT INTO adult_audit_log (target_user_id, performed_by, action, timestamp, notes) VALUES (?, ?, 'ADDED', ?, ?)",
                (int(user_id), int(added_by), now, notes[:200]),
            )
            conn.commit()

        # Update cache immediately
        if _cached_allowlist is not None:
            _cached_allowlist.add(int(user_id))
        else:
            get_adult_allowlist()
        logger.info(f"User {user_id} added to adult allowlist by {added_by}")
        return True
    except Exception as ex:
        logger.error(f"Failed to add user {user_id} to adult allowlist: {ex}")
        return False


def remove_adult_user(user_id: int, removed_by: int, notes: str = "") -> bool:
    """
    Remove a user from the persistent adult command allowlist.
    Takes effect immediately in memory and in the persistent database.
    """
    global _cached_allowlist
    if int(user_id) == OWNER_ID:
        return False  # Cannot remove primary owner

    now = time.time()
    try:
        with _get_adult_db() as conn:
            conn.execute("DELETE FROM adult_allowlist WHERE user_id = ?", (int(user_id),))
            conn.execute(
                "INSERT INTO adult_audit_log (target_user_id, performed_by, action, timestamp, notes) VALUES (?, ?, 'REVOKED', ?, ?)",
                (int(user_id), int(removed_by), now, notes[:200]),
            )
            conn.commit()

        # Update cache immediately for zero-delay revocation
        if _cached_allowlist is not None:
            _cached_allowlist.discard(int(user_id))
        else:
            get_adult_allowlist()
        logger.info(f"User {user_id} revoked from adult allowlist by {removed_by}")
        return True
    except Exception as ex:
        logger.error(f"Failed to remove user {user_id} from adult allowlist: {ex}")
        return False


def list_adult_users() -> list[dict[str, Any]]:
    """Return list of authorized users from database."""
    try:
        with _get_adult_db() as conn:
            rows = conn.execute("SELECT * FROM adult_allowlist ORDER BY added_at DESC").fetchall()
            return [dict(r) for r in rows]
    except Exception as ex:
        logger.error(f"Failed to list adult allowlist users: {ex}")
        return []


def is_adult_authorized(user_id: int | None) -> bool:
    """Check if the given Discord user ID is on the adult command allowlist."""
    if user_id is None:
        return False
    try:
        uid = int(user_id)
        if is_primary_owner(uid):
            return True
        return uid in get_adult_allowlist()
    except (TypeError, ValueError):
        return False


async def authorize_adult(ctx_or_interaction: Any, action_name: str = "adult-action") -> bool:
    """
    Verify authorization before executing any adult-category command or fetching adult GIFs.
    If unauthorized, immediately sends a polite, private rejection notice without leaking keys or allowlists.
    """
    user_id = None
    if hasattr(ctx_or_interaction, "author") and ctx_or_interaction.author:
        user_id = ctx_or_interaction.author.id
    elif hasattr(ctx_or_interaction, "user") and ctx_or_interaction.user:
        user_id = ctx_or_interaction.user.id

    if is_adult_authorized(user_id):
        return True

    msg = (
        "⛔ **Access Denied: Restricted Category**\n"
        "> This command is part of the restricted **Adult Humor** suite.\n"
        "> Access is strictly owner-controlled and restricted to approved accounts."
    )

    try:
        interaction = getattr(ctx_or_interaction, "interaction", None)
        if interaction is not None:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return False

        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(msg, ephemeral=True)
            return False

        # Regular prefix context
        await ctx_or_interaction.send(msg)
    except Exception as e:
        logger.debug(f"Could not send adult authorization rejection notice: {e}")

    return False

