"""Central fail-closed owner authorization and security audit helpers."""
from __future__ import annotations
import datetime as dt
import logging
import time
from typing import Any

OWNER_ID = 1505515188991033409
log = logging.getLogger("Kyoka.Security")
_denial_audit_at: dict[int, float] = {}


def is_primary_owner(user_id: int | None) -> bool:
    try:
        return user_id is not None and int(user_id) == OWNER_ID
    except (TypeError, ValueError):
        return False


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
    if is_primary_owner(actor_id):
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
