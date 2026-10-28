"""Central fail-closed owner authorization, bot staff permissions, and security audit helpers."""
from __future__ import annotations
import datetime as dt
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

OWNER_ID = 1505515188991033409
log = logging.getLogger("Kyoka.Security")
_denial_audit_at: dict[int, float] = {}

# ── Persistent Bot Staff Registry ──
_STAFF_FILE = Path("data/bot_staff.json")
_bot_staff_ids: set[int] = set()


def _load_bot_staff_disk() -> None:
    global _bot_staff_ids
    try:
        if _STAFF_FILE.exists():
            with open(_STAFF_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    _bot_staff_ids = {int(x) for x in data if str(x).isdigit()}
    except Exception as e:
        log.warning("Could not read %s: %s", _STAFF_FILE, e)


def _save_bot_staff_disk() -> None:
    try:
        _STAFF_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STAFF_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(_bot_staff_ids)), f, indent=2)
    except Exception as e:
        log.warning("Could not persist %s: %s", _STAFF_FILE, e)


# Load initial bot staff cache on import
_load_bot_staff_disk()


def is_primary_owner(user_id: int | None) -> bool:
    try:
        return user_id is not None and int(user_id) == OWNER_ID
    except (TypeError, ValueError):
        return False


def is_bot_staff(user_id: int | None) -> bool:
    """Return True if the user is a registered Bot Staff member."""
    if is_primary_owner(user_id):
        return True
    try:
        return user_id is not None and int(user_id) in _bot_staff_ids
    except (TypeError, ValueError):
        return False


def is_owner_or_staff(user_id: int | None) -> bool:
    """Check if the user has owner or bot staff privileges."""
    return is_primary_owner(user_id) or is_bot_staff(user_id)


def add_bot_staff(user_id: int) -> bool:
    """Add a user ID to the Bot Staff registry."""
    uid = int(user_id)
    if uid in _bot_staff_ids:
        return False
    _bot_staff_ids.add(uid)
    _save_bot_staff_disk()
    return True


def remove_bot_staff(user_id: int) -> bool:
    """Remove a user ID from the Bot Staff registry."""
    uid = int(user_id)
    if uid not in _bot_staff_ids:
        return False
    _bot_staff_ids.discard(uid)
    _save_bot_staff_disk()
    return True


def get_all_bot_staff() -> list[int]:
    """Return list of all registered Bot Staff user IDs."""
    return sorted(list(_bot_staff_ids))


async def audit(bot: Any, actor_id: int, action: str, target_id: int | None, outcome: str, details: str = "") -> None:
    """Best-effort audit; never include secrets or raw exception text."""
    try:
        await bot.db.execute(
            "INSERT INTO kyoka_audit_log (actor_id, action, target_id, occurred_at, outcome, details) VALUES (?, ?, ?, ?, ?, ?);",
            int(actor_id), action[:80], int(target_id) if target_id is not None else None,
            dt.datetime.now(dt.timezone.utc), outcome[:24], details[:500],
        )
    except Exception:
        log.warning("Audit write failed for action=%s outcome=%s", action[:80], outcome[:24])


async def authorize_owner(ctx: Any, action: str = "owner-command") -> bool:
    actor_id = getattr(getattr(ctx, "author", None), "id", None)
    if actor_id is None:
        actor_id = getattr(getattr(ctx, "user", None), "id", None)

    # SPAM COMMAND is strictly reserved for the primary owner! Staff CANNOT spam.
    if action == "spam":
        if is_primary_owner(actor_id):
            return True
        return False

    # All other bot commands: bot staff have every permission of the bot!
    if is_primary_owner(actor_id) or is_bot_staff(actor_id):
        return True

    now_mono = time.monotonic()
    key = int(actor_id or 0)
    if now_mono - _denial_audit_at.get(key, 0.0) >= 60:
        _denial_audit_at[key] = now_mono
        await audit(ctx.bot, key, action, None, "denied")
    try:
        if getattr(ctx, "interaction", None):
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
            else:
                await ctx.interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
        else:
            try:
                await ctx.author.send("You are not authorized to use this command.")
            except Exception:
                await ctx.send("You are not authorized to use this command.", delete_after=8)
    except Exception:
        pass
    return False
