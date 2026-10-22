"""Persistent subscription lifecycle and fail-closed entitlement checks."""
from __future__ import annotations
import datetime as dt
import re
from typing import Any

TIERS = {"free": 0, "premium": 1, "pro": 2}
DURATION_RE = re.compile(r"^(\d+)([smhdw])$", re.I)


def parse_duration(value: str) -> dt.timedelta | None:
    if value.strip().lower() in {"lifetime", "forever"}:
        return None
    match = DURATION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("Use a duration such as `30d`, `12h`, `2w`, or `lifetime`.")
    amount = int(match.group(1))
    if amount < 1 or amount > 36500:
        raise ValueError("Duration must be between 1 and 36500 units.")
    unit = match.group(2).lower()
    return amount * {"s": dt.timedelta(seconds=1), "m": dt.timedelta(minutes=1), "h": dt.timedelta(hours=1), "d": dt.timedelta(days=1), "w": dt.timedelta(weeks=1)}[unit]


class PremiumService:
    def __init__(self, db: Any): self.db = db

    async def has_premium(self, *, scope: str, target_id: int, minimum_tier: str = "premium") -> bool:
        """Fail closed on errors; scope must be exactly user or server."""
        if scope not in {"user", "server"} or minimum_tier not in TIERS or TIERS[minimum_tier] == 0:
            return False
        table, column = ("user_premium", "user_id") if scope == "user" else ("guild_premium", "guild_id")
        try:
            row = await self.db.fetch_one(f"SELECT tier, expires_at, status FROM {table} WHERE {column} = ?;", int(target_id))
            if not row or str(row.get("status", "active")).lower() != "active": return False
            tier = str(row.get("tier", "free")).lower()
            if TIERS.get(tier, 0) < TIERS[minimum_tier]: return False
            expiry = row.get("expires_at")
            if expiry is None: return True
            if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=dt.timezone.utc)
            return expiry > dt.datetime.now(dt.timezone.utc)
        except Exception:
            return False

    async def grant(self, *, scope: str, target_id: int, tier: str, duration: str, actor_id: int, note: str = "", extend_existing: bool = False) -> dict[str, Any]:
        if scope not in {"user", "server"}: raise ValueError("Scope must be user or server.")
        tier = tier.lower()
        if tier not in {"premium", "pro"}: raise ValueError("Tier must be premium or pro.")
        delta = parse_duration(duration)
        now = dt.datetime.now(dt.timezone.utc)
        table, column = ("user_premium", "user_id") if scope == "user" else ("guild_premium", "guild_id")
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                old = await conn.fetchrow(f"SELECT expires_at, tier, status FROM {table} WHERE {column}=$1 FOR UPDATE", int(target_id))
                expiry = None if delta is None else now + delta
                if old and delta is not None and old["status"] == "active":
                    old_exp = old["expires_at"]
                    if old_exp is None:
                        expiry = None
                    else:
                        if old_exp.tzinfo is None: old_exp = old_exp.replace(tzinfo=dt.timezone.utc)
                        if old_exp > now and not extend_existing:
                            # Repeating a grant does not stack time; use explicit extend for renewal.
                            expiry = old_exp
                        else:
                            expiry = max(now, old_exp) + delta if extend_existing else now + delta
                if scope == "user":
                    await conn.execute("INSERT INTO user_premium (user_id,tier,expires_at,status,activated_by,updated_at) VALUES ($1,$2,$3,'active',$4,$5) ON CONFLICT (user_id) DO UPDATE SET tier=EXCLUDED.tier,expires_at=EXCLUDED.expires_at,status='active',activated_by=EXCLUDED.activated_by,updated_at=EXCLUDED.updated_at", int(target_id), tier, expiry, int(actor_id), now)
                else:
                    await conn.execute("INSERT INTO guild_premium (guild_id,tier,expires_at,status,activated_by,updated_at) VALUES ($1,$2,$3,'active',$4,$5) ON CONFLICT (guild_id) DO UPDATE SET tier=EXCLUDED.tier,expires_at=EXCLUDED.expires_at,status='active',activated_by=EXCLUDED.activated_by,updated_at=EXCLUDED.updated_at", int(target_id), tier, expiry, int(actor_id), now)
                await conn.execute("INSERT INTO kyoka_premium_history (scope,target_id,tier,action,actor_id,expires_at,note,occurred_at) VALUES ($1,$2,$3,'grant',$4,$5,$6,$7)", scope, int(target_id), tier, int(actor_id), expiry, note[:500], now)
        return {"scope": scope, "target_id": int(target_id), "tier": tier, "expires_at": expiry}

    async def revoke(self, *, scope: str, target_id: int, actor_id: int, note: str = "") -> bool:
        if scope not in {"user", "server"}: raise ValueError("Scope must be user or server.")
        table, column = ("user_premium", "user_id") if scope == "user" else ("guild_premium", "guild_id")
        now = dt.datetime.now(dt.timezone.utc)
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(f"SELECT tier FROM {table} WHERE {column}=$1 FOR UPDATE", int(target_id))
                if not row: return False
                await conn.execute(f"UPDATE {table} SET status='revoked', updated_at=$2 WHERE {column}=$1", int(target_id), now)
                await conn.execute("INSERT INTO kyoka_premium_history (scope,target_id,tier,action,actor_id,note,occurred_at) VALUES ($1,$2,$3,'revoke',$4,$5,$6)", scope, int(target_id), row["tier"], int(actor_id), note[:500], now)
        return True

    async def get(self, scope: str, target_id: int) -> dict[str, Any] | None:
        if scope not in {"user", "server"}: raise ValueError("Scope must be user or server.")
        table, column = ("user_premium", "user_id") if scope == "user" else ("guild_premium", "guild_id")
        row = await self.db.fetch_one(f"SELECT {column} AS target_id,tier,expires_at,status,activated_by,created_at,updated_at FROM {table} WHERE {column}=?", int(target_id))
        if row and row.get("expires_at") and row["expires_at"].tzinfo is None: row["expires_at"] = row["expires_at"].replace(tzinfo=dt.timezone.utc)
        return row
