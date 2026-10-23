from __future__ import annotations

import asyncio
import csv
import datetime
import io
import json
import logging
import math
import secrets
from typing import TYPE_CHECKING, Any, Optional

import discord

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase
    from src.managers.activity_manager import ActivityManager

logger = logging.getLogger("Kyoka.Managers.Giveaway")


def weighted_sample_without_replacement(
    items_with_weights: list[tuple[Any, float]], k: int
) -> list[Any]:
    """
    Mathematically proven Efraimidis-Spirakis algorithm for weighted random
    sampling without replacement. Uses cryptographically secure secrets.SystemRandom.
    Avoids huge array memory expansion.
    """
    if not items_with_weights or k <= 0:
        return []
    if len(items_with_weights) <= k:
        return [item for item, _ in items_with_weights]

    rng = secrets.SystemRandom()
    keys = []
    for item, weight in items_with_weights:
        w = max(0.0001, float(weight))
        u = rng.random()
        while u == 0.0:
            u = rng.random()
        # Key = u ** (1 / w)
        key = math.pow(u, 1.0 / w)
        keys.append((key, item))

    keys.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in keys[:k]]


class ToggleResult(tuple):
    """3-tuple for backward compatibility: (success, action, count), with failure_reason attribute."""
    def __new__(cls, success: bool, action: str, count: int, failure_reason: Optional[str] = None):
        return super().__new__(cls, (success, action, count))

    def __init__(self, success: bool, action: str, count: int, failure_reason: Optional[str] = None):
        self.success = success
        self.action = action
        self.count = count
        self.failure_reason = failure_reason


class GiveawayManager:
    """
    Enterprise Giveaway Engine for KYOKA 3.0.
    Handles persistent giveaway lifecycles, complex eligibility rules,
    activity verification, role bonus multipliers with configurable stacking,
    cryptographically sound weighted winner selection, templates, claims, and audit logs.
    """

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # message_id -> giveaway dict
        self._active_giveaways: dict[int, dict[str, Any]] = {}
        # giveaway_id -> message_id index
        self._id_to_message_id: dict[int, int] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load all active (unended, uncancelled) giveaways into memory cache."""
        try:
            rows = await self.db.fetch_all(
                "SELECT * FROM giveaways WHERE is_ended = FALSE AND is_cancelled = FALSE ORDER BY ends_at ASC;"
            )
            async with self._lock:
                self._active_giveaways.clear()
                self._id_to_message_id.clear()
                for r in rows:
                    mid = int(r["message_id"])
                    gid = int(r["id"])
                    data = self._row_to_giveaway_dict(r)
                    self._active_giveaways[mid] = data
                    self._id_to_message_id[gid] = mid

            logger.info(f"Loaded {len(self._active_giveaways)} active giveaway(s) into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load active giveaways cache: {e}", exc_info=e)

    def _row_to_giveaway_dict(self, r: Any) -> dict[str, Any]:
        """Convert a database row to a structured giveaway dict."""
        end_t = r["ends_at"]
        if end_t and end_t.tzinfo is None:
            end_t = end_t.replace(tzinfo=datetime.timezone.utc)
        start_t = r.get("starts_at")
        if start_t and getattr(start_t, "tzinfo", None) is None:
            start_t = start_t.replace(tzinfo=datetime.timezone.utc)

        return {
            "id": int(r["id"]) if "id" in r else 0,
            "guild_id": int(r["guild_id"]) if "guild_id" in r else 0,
            "channel_id": int(r.get("channel_id", 0) or 0),
            "message_id": int(r.get("message_id", 0) or 0),
            "host_id": int(r.get("host_id", 0) or 0),
            "prize": str(r.get("prize", "") or ""),
            "description": str(r.get("description", "") or ""),
            "winner_count": int(r.get("winner_count", 1) or 1),
            "ends_at": end_t,
            "starts_at": start_t,
            "required_role_id": int(r["required_role_id"]) if r.get("required_role_id") else None,
            "is_ended": bool(r.get("is_ended", False)),
            "is_paused": bool(r.get("is_paused", False)),
            "is_cancelled": bool(r.get("is_cancelled", False)),
            "paused_at": r.get("paused_at"),
            "remaining_seconds_when_paused": r.get("remaining_seconds_when_paused"),
            "claim_deadline_seconds": int(r.get("claim_deadline_seconds", 0) or 0),
            "auto_reroll_unclaimed": bool(r.get("auto_reroll_unclaimed", False)),
            "entry_limit": int(r.get("entry_limit", 0) or 0),
            "embed_color": str(r.get("embed_color", "") or ""),
            "thumbnail_url": str(r.get("thumbnail_url", "") or ""),
            "image_url": str(r.get("image_url", "") or ""),
            "bonus_stacking_policy": str(r.get("bonus_stacking_policy", "highest") or "highest"),
            "bonus_multiplier_cap": float(r.get("bonus_multiplier_cap", 10.0) or 10.0),
        }

    def get_giveaway_by_message_id(self, message_id: int) -> Optional[dict[str, Any]]:
        """Retrieve active giveaway data by Discord message ID."""
        return self._active_giveaways.get(message_id)

    def get_giveaway_by_id(self, giveaway_id: int) -> Optional[dict[str, Any]]:
        """Retrieve active giveaway data by database ID."""
        mid = self._id_to_message_id.get(giveaway_id)
        if mid:
            return self._active_giveaways.get(mid)
        return None

    def get_active_giveaways_for_guild(self, guild_id: int) -> list[dict[str, Any]]:
        """Return all ongoing giveaways within a specific server."""
        return [g for g in self._active_giveaways.values() if g["guild_id"] == guild_id]

    def get_due_giveaways(self) -> list[dict[str, Any]]:
        """Return all giveaways whose duration has expired and need winner determination."""
        now = datetime.datetime.now(datetime.timezone.utc)
        due = []
        for g in self._active_giveaways.values():
            if g.get("is_paused") or g.get("is_ended") or g.get("is_cancelled"):
                continue
            end_t = g["ends_at"]
            if end_t.tzinfo is None:
                end_t = end_t.replace(tzinfo=datetime.timezone.utc)
            if end_t <= now:
                due.append(g)
        return due

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        host_id: int,
        prize: str,
        winner_count: int,
        ends_at: datetime.datetime,
        description: str = "",
        required_role_id: Optional[int] = None,
        claim_deadline_seconds: int = 0,
        entry_limit: int = 0,
        embed_color: str = "",
        thumbnail_url: str = "",
        image_url: str = "",
        bonus_stacking_policy: str = "highest",
        bonus_multiplier_cap: float = 10.0,
    ) -> int:
        """Register a new giveaway in PostgreSQL and activate it in memory cache."""
        if ends_at.tzinfo is not None:
            db_ends_at = ends_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            mem_ends_at = ends_at.astimezone(datetime.timezone.utc)
        else:
            db_ends_at = ends_at
            mem_ends_at = ends_at.replace(tzinfo=datetime.timezone.utc)

        row = await self.db.fetch_one(
            """
            INSERT INTO giveaways (
                guild_id, channel_id, message_id, host_id, prize,
                winner_count, ends_at, description, required_role_id,
                claim_deadline_seconds, entry_limit, embed_color,
                thumbnail_url, image_url, bonus_stacking_policy, bonus_multiplier_cap
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
            )
            RETURNING id;
            """,
            guild_id,
            channel_id,
            message_id,
            host_id,
            prize,
            winner_count,
            db_ends_at,
            description,
            required_role_id,
            claim_deadline_seconds,
            entry_limit,
            embed_color,
            thumbnail_url,
            image_url,
            bonus_stacking_policy,
            bonus_multiplier_cap,
        )
        giveaway_id = int(row["id"])

        data = {
            "id": giveaway_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "host_id": host_id,
            "prize": prize,
            "description": description,
            "winner_count": winner_count,
            "ends_at": mem_ends_at,
            "starts_at": datetime.datetime.now(datetime.timezone.utc),
            "required_role_id": required_role_id,
            "is_ended": False,
            "is_paused": False,
            "is_cancelled": False,
            "claim_deadline_seconds": claim_deadline_seconds,
            "auto_reroll_unclaimed": False,
            "entry_limit": entry_limit,
            "embed_color": embed_color,
            "thumbnail_url": thumbnail_url,
            "image_url": image_url,
            "bonus_stacking_policy": bonus_stacking_policy,
            "bonus_multiplier_cap": bonus_multiplier_cap,
        }

        async with self._lock:
            self._active_giveaways[message_id] = data
            self._id_to_message_id[giveaway_id] = message_id

        # Log audit entry
        await self.log_audit(
            guild_id,
            giveaway_id,
            host_id,
            "create",
            f"Created giveaway '{prize}' with {winner_count} winner(s).",
        )
        return giveaway_id

    async def pause_giveaway(self, message_id: int, actor_id: int) -> Optional[dict[str, Any]]:
        """Pause entries and freeze countdown for an active giveaway."""
        gw = self.get_giveaway_by_message_id(message_id)
        if not gw:
            gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
            if not gw_row:
                return None
            gw = self._row_to_giveaway_dict(gw_row)

        if gw.get("is_ended") or gw.get("is_paused"):
            return None

        now = datetime.datetime.now(datetime.timezone.utc)
        ends_at = gw["ends_at"]
        remaining = max(0, int((ends_at - now).total_seconds()))

        await self.db.execute(
            """
            UPDATE giveaways
            SET is_paused = TRUE, paused_at = CURRENT_TIMESTAMP, remaining_seconds_when_paused = $2
            WHERE message_id = $1;
            """,
            message_id,
            remaining,
        )

        gw["is_paused"] = True
        gw["paused_at"] = now
        gw["remaining_seconds_when_paused"] = remaining

        await self.log_audit(
            gw["guild_id"],
            gw["id"],
            actor_id,
            "pause",
            f"Paused giveaway with {remaining}s remaining.",
        )
        return gw

    async def resume_giveaway(self, message_id: int, actor_id: int) -> Optional[dict[str, Any]]:
        """Resume a paused giveaway with preserved remaining duration."""
        gw = self.get_giveaway_by_message_id(message_id)
        if not gw:
            gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
            if not gw_row:
                return None
            gw = self._row_to_giveaway_dict(gw_row)

        if not gw.get("is_paused"):
            return None

        remaining = gw.get("remaining_seconds_when_paused") or 60
        now = datetime.datetime.now(datetime.timezone.utc)
        new_ends_at = now + datetime.timedelta(seconds=remaining)
        db_ends_at = new_ends_at.replace(tzinfo=None)

        await self.db.execute(
            """
            UPDATE giveaways
            SET is_paused = FALSE, paused_at = NULL, remaining_seconds_when_paused = NULL, ends_at = $2
            WHERE message_id = $1;
            """,
            message_id,
            db_ends_at,
        )

        gw["is_paused"] = False
        gw["paused_at"] = None
        gw["remaining_seconds_when_paused"] = None
        gw["ends_at"] = new_ends_at

        await self.log_audit(
            gw["guild_id"],
            gw["id"],
            actor_id,
            "resume",
            f"Resumed giveaway with new end time {new_ends_at.isoformat()}.",
        )
        return gw

    async def cancel_giveaway(self, message_id: int, actor_id: int, reason: str = "") -> Optional[dict[str, Any]]:
        """Cancel a giveaway without drawing any winners."""
        gw = self.get_giveaway_by_message_id(message_id)
        if not gw:
            gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
            if not gw_row:
                return None
            gw = self._row_to_giveaway_dict(gw_row)

        giveaway_id = gw["id"]

        await self.db.execute(
            """
            UPDATE giveaways
            SET is_cancelled = TRUE, is_ended = TRUE
            WHERE id = $1;
            """,
            giveaway_id,
        )

        async with self._lock:
            self._active_giveaways.pop(message_id, None)
            self._id_to_message_id.pop(giveaway_id, None)

        gw["is_cancelled"] = True
        gw["is_ended"] = True

        await self.log_audit(
            gw["guild_id"],
            giveaway_id,
            actor_id,
            "cancel",
            f"Cancelled giveaway '{gw['prize']}'. Reason: {reason or 'No reason provided'}",
        )
        return gw

    async def edit_giveaway(
        self,
        message_id: int,
        actor_id: int,
        prize: Optional[str] = None,
        winner_count: Optional[int] = None,
        duration_delta: Optional[datetime.timedelta] = None,
        required_role_id: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """Edit active giveaway parameters."""
        gw = self.get_giveaway_by_message_id(message_id)
        if not gw or gw.get("is_ended"):
            return None

        updates = []
        params = []
        idx = 1

        if prize is not None:
            updates.append(f"prize = ${idx}")
            params.append(prize)
            gw["prize"] = prize
            idx += 1

        if winner_count is not None and winner_count >= 1:
            updates.append(f"winner_count = ${idx}")
            params.append(winner_count)
            gw["winner_count"] = winner_count
            idx += 1

        if duration_delta is not None:
            new_end = gw["ends_at"] + duration_delta
            gw["ends_at"] = new_end
            updates.append(f"ends_at = ${idx}")
            params.append(new_end.replace(tzinfo=None))
            idx += 1

        if required_role_id is not None:
            updates.append(f"required_role_id = ${idx}")
            val = required_role_id if required_role_id > 0 else None
            params.append(val)
            gw["required_role_id"] = val
            idx += 1

        if updates:
            params.append(message_id)
            query = f"UPDATE giveaways SET {', '.join(updates)} WHERE message_id = ${idx};"
            await self.db.execute(query, *params)
            await self.log_audit(
                gw["guild_id"],
                gw["id"],
                actor_id,
                "edit",
                f"Edited giveaway settings (prize={prize}, winners={winner_count}).",
            )

        return gw

    # ─── REQUIREMENTS & ELIGIBILITY ──────────────────────────────────────────

    async def add_requirement(
        self,
        guild_id: int,
        giveaway_id: Optional[int],
        req_type: str,
        req_value: str,
        channel_id: Optional[int] = None,
    ) -> int:
        """Add an eligibility requirement to a giveaway or server defaults."""
        row = await self.db.fetch_one(
            """
            INSERT INTO giveaway_requirements (giveaway_id, guild_id, req_type, req_value, channel_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id;
            """,
            giveaway_id,
            guild_id,
            req_type,
            req_value,
            channel_id,
        )
        return int(row["id"])

    async def remove_requirement(self, requirement_id: int) -> bool:
        """Remove an eligibility requirement by ID."""
        await self.db.execute("DELETE FROM giveaway_requirements WHERE id = $1;", requirement_id)
        return True

    async def get_requirements(
        self,
        guild_id: int,
        giveaway_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Fetch all configured requirements for a giveaway or server defaults."""
        if giveaway_id:
            rows = await self.db.fetch_all(
                "SELECT * FROM giveaway_requirements WHERE giveaway_id = $1 OR (giveaway_id IS NULL AND guild_id = $2);",
                giveaway_id,
                guild_id,
            )
        else:
            rows = await self.db.fetch_all(
                "SELECT * FROM giveaway_requirements WHERE guild_id = $1;",
                guild_id,
            )
        return [dict(r) for r in rows]

    async def check_member_eligibility(
        self,
        giveaway: dict[str, Any],
        member: discord.Member,
        activity_mgr: Optional[ActivityManager] = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """
        Evaluate all configured entry requirements for a member.
        Returns: (passed_all: bool, breakdown: list of requirement status dicts)
        """
        breakdown: list[dict[str, Any]] = []
        passed_all = True
        guild_id = giveaway["guild_id"]
        giveaway_id = giveaway.get("id")

        # 1. Legacy / Simple required_role_id
        if giveaway.get("required_role_id"):
            req_role_id = int(giveaway["required_role_id"])
            has_role = any(r.id == req_role_id for r in member.roles)
            req_status = {
                "type": "required_role",
                "label": f"Required Role: <@&{req_role_id}>",
                "passed": has_role,
                "reason": "Passed" if has_role else "Missing required role",
            }
            breakdown.append(req_status)
            if not has_role:
                passed_all = False

        # 2. Advanced requirements from giveaway_requirements table
        requirements = await self.get_requirements(guild_id, giveaway_id)

        for req in requirements:
            rtype = req["req_type"]
            rval = req["req_value"]
            passed = True
            reason = "Passed"
            label = ""

            # Required specific role
            if rtype in ("role_required", "must_have_role"):
                target_role_id = int(rval)
                passed = any(r.id == target_role_id for r in member.roles)
                label = f"Must have role: <@&{target_role_id}>"
                reason = "Passed" if passed else "Missing required role"

            # Excluded role
            elif rtype in ("role_excluded", "must_not_have_role"):
                target_role_id = int(rval)
                passed = not any(r.id == target_role_id for r in member.roles)
                label = f"Must NOT have role: <@&{target_role_id}>"
                reason = "Passed" if passed else "Possesses excluded role"

            # Must have ANY of several roles
            elif rtype in ("role_any", "must_have_any"):
                role_ids = [int(x.strip()) for x in rval.split(",") if x.strip().isdigit()]
                passed = any(r.id in role_ids for r in member.roles)
                mentions = ", ".join(f"<@&{rid}>" for rid in role_ids)
                label = f"Must have any of: {mentions}"
                reason = "Passed" if passed else "Missing all permitted roles"

            # Must have ALL of specified roles
            elif rtype in ("role_all", "must_have_all"):
                role_ids = [int(x.strip()) for x in rval.split(",") if x.strip().isdigit()]
                user_role_ids = {r.id for r in member.roles}
                passed = all(rid in user_role_ids for rid in role_ids)
                mentions = ", ".join(f"<@&{rid}>" for rid in role_ids)
                label = f"Must have all of: {mentions}"
                reason = "Passed" if passed else "Missing one or more required roles"

            # Minimum message activity today
            elif rtype in ("messages_daily", "activity_daily"):
                count_needed = int(rval)
                label = f"Send at least {count_needed} messages today"
                if activity_mgr:
                    passed, actual = await activity_mgr.check_requirement(
                        guild_id, member.id, "daily", count_needed
                    )
                    reason = f"Passed ({actual}/{count_needed})" if passed else f"Only sent {actual}/{count_needed} messages today"
                else:
                    passed = False
                    reason = "Activity tracking module unavailable"

            # Minimum message activity in last 7 days
            elif rtype in ("messages_weekly", "activity_weekly"):
                count_needed = int(rval)
                label = f"Send at least {count_needed} messages in past 7 days"
                if activity_mgr:
                    passed, actual = await activity_mgr.check_requirement(
                        guild_id, member.id, "weekly", count_needed
                    )
                    reason = f"Passed ({actual}/{count_needed})" if passed else f"Only sent {actual}/{count_needed} messages this week"
                else:
                    passed = False
                    reason = "Activity tracking module unavailable"

            # Minimum message activity in a specific channel
            elif rtype in ("messages_channel", "activity_channel"):
                count_needed = int(rval)
                chan_id = req.get("channel_id")
                label = f"Send at least {count_needed} messages in <#{chan_id}>"
                if activity_mgr and chan_id:
                    passed, actual = await activity_mgr.check_requirement(
                        guild_id, member.id, "channel", count_needed, channel_id=chan_id
                    )
                    reason = f"Passed ({actual}/{count_needed})" if passed else f"Only sent {actual}/{count_needed} in target channel"
                else:
                    passed = False
                    reason = "Channel activity check unavailable"

            # Minimum Discord account age
            elif rtype in ("account_age_days", "account_age"):
                min_days = int(rval)
                now = datetime.datetime.now(datetime.timezone.utc)
                age_days = (now - member.created_at).days
                passed = age_days >= min_days
                label = f"Discord account age: at least {min_days} days"
                reason = f"Passed ({age_days} days old)" if passed else f"Account is only {age_days} days old (needs {min_days})"

            # Minimum Server membership age
            elif rtype in ("server_age_days", "join_age"):
                min_days = int(rval)
                now = datetime.datetime.now(datetime.timezone.utc)
                joined_at = member.joined_at or member.created_at
                join_days = (now - joined_at).days
                passed = join_days >= min_days
                label = f"Server membership age: at least {min_days} days"
                reason = f"Passed ({join_days} days in server)" if passed else f"Joined {join_days} days ago (needs {min_days})"

            # Official server tag verification (Discord Clan / Primary Guild)
            elif rtype in ("server_tag", "tag"):
                target_tag = rval.strip().upper()
                label = f"Equip server tag: [{target_tag}]"
                # Inspect official discord.py 2.7.1 member.primary_guild
                primary_guild = getattr(member, "primary_guild", None)
                if primary_guild is not None and getattr(primary_guild, "identity_enabled", False):
                    equipped_tag = getattr(primary_guild, "tag", None)
                    if equipped_tag and equipped_tag.upper() == target_tag:
                        passed = True
                        reason = f"Passed (equipped [{equipped_tag}])"
                    else:
                        passed = False
                        reason = f"Equipped tag '[{equipped_tag}]' does not match '[{target_tag}]'"
                else:
                    passed = False
                    reason = f"No primary server tag equipped. Equip the [{target_tag}] tag in Discord profile settings."

            breakdown.append({
                "type": rtype,
                "label": label or rtype,
                "passed": passed,
                "reason": reason,
            })
            if not passed:
                passed_all = False

        return passed_all, breakdown

    # ─── BONUS ENTRIES & WEIGHTS ─────────────────────────────────────────────

    async def add_bonus_role(
        self,
        guild_id: int,
        role_id: int,
        multiplier: float = 1.0,
        extra_entries: int = 0,
        giveaway_id: Optional[int] = None,
    ) -> int:
        """Configure a role-based bonus multiplier or extra entries."""
        row = await self.db.fetch_one(
            """
            INSERT INTO giveaway_bonus_roles (guild_id, giveaway_id, role_id, multiplier, extra_entries)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id;
            """,
            guild_id,
            giveaway_id,
            role_id,
            multiplier,
            extra_entries,
        )
        return int(row["id"])

    async def get_bonus_roles(
        self,
        guild_id: int,
        giveaway_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Fetch configured bonus roles for a giveaway or server defaults."""
        if giveaway_id:
            rows = await self.db.fetch_all(
                "SELECT * FROM giveaway_bonus_roles WHERE giveaway_id = $1 OR (giveaway_id IS NULL AND guild_id = $2);",
                giveaway_id,
                guild_id,
            )
        else:
            rows = await self.db.fetch_all(
                "SELECT * FROM giveaway_bonus_roles WHERE guild_id = $1;",
                guild_id,
            )
        return [dict(r) for r in rows]

    async def remove_bonus_role(self, bonus_id: int) -> bool:
        """Remove a bonus role configuration by ID."""
        await self.db.execute("DELETE FROM giveaway_bonus_roles WHERE id = $1;", bonus_id)
        return True

    async def calculate_member_bonus(
        self,
        giveaway: dict[str, Any],
        member: discord.Member,
    ) -> tuple[int, float, list[str], str]:
        """
        Calculate base entries, effective weight, qualifying roles, and audit breakdown.
        Supports stacking policies: 'highest', 'additive', 'multiplicative' (with cap).
        Returns: (base_entries, effective_weight, qualifying_roles, breakdown_str)
        """
        base_entries = 1
        guild_id = giveaway["guild_id"]
        giveaway_id = giveaway.get("id")
        policy = giveaway.get("bonus_stacking_policy", "highest").lower()
        cap = float(giveaway.get("bonus_multiplier_cap", 10.0))

        bonus_roles = await self.get_bonus_roles(guild_id, giveaway_id)
        if not bonus_roles:
            return base_entries, 1.0, [], "Base entry: 1 (no bonus roles)"

        qualifying_roles: list[str] = []
        multipliers: list[float] = []
        extra_entries_total = 0

        user_role_ids = {r.id for r in member.roles}

        for br in bonus_roles:
            rid = int(br["role_id"])
            if rid in user_role_ids:
                role_obj = member.guild.get_role(rid)
                role_name = role_obj.name if role_obj else str(rid)
                mult = float(br.get("multiplier", 1.0))
                extra = int(br.get("extra_entries", 0))

                qualifying_roles.append(f"{role_name} ({mult}x, +{extra})")
                multipliers.append(mult)
                extra_entries_total += extra

        if not multipliers:
            return base_entries, 1.0, [], "Base entry: 1"

        if policy == "additive":
            # 1.0 + sum(m - 1.0)
            effective_multiplier = 1.0 + sum(m - 1.0 for m in multipliers)
            effective_weight = min(cap, max(1.0, effective_multiplier))
            breakdown = f"Additive bonus: {effective_weight:.1f}x (+{extra_entries_total} extra)"
        elif policy == "multiplicative":
            # Product of multipliers
            prod = 1.0
            for m in multipliers:
                prod *= m
            effective_weight = min(cap, max(1.0, prod))
            breakdown = f"Multiplicative bonus (capped at {cap}x): {effective_weight:.1f}x"
        else:
            # 'highest' (default)
            effective_weight = min(cap, max(multipliers))
            breakdown = f"Highest multiplier: {effective_weight:.1f}x (+{extra_entries_total} extra)"

        return base_entries + extra_entries_total, effective_weight, qualifying_roles, breakdown

    # ─── PARTICIPANTS JOIN & LEAVE ───────────────────────────────────────────

    async def toggle_participant(
        self,
        giveaway_id: int,
        member: discord.Member,
        activity_mgr: Optional[ActivityManager] = None,
    ) -> tuple[bool, str, int, Optional[str]]:
        """
        Atomically add or remove a participant from a giveaway.
        Verifies all requirements on entry.
        Returns: (success: bool, action: 'entered' | 'left' | 'failed', count: int, failure_reason: Optional[str])
        """
        # 1. Check if giveaway is paused
        mid = self._id_to_message_id.get(giveaway_id)
        gw = self._active_giveaways.get(mid) if mid else None
        if not gw:
            gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE id = $1;", giveaway_id)
            if not gw_row:
                return ToggleResult(False, "failed", 0, "Giveaway not found.")
            gw = self._row_to_giveaway_dict(gw_row)

        if gw.get("is_paused"):
            return ToggleResult(False, "failed", 0, "This giveaway is temporarily paused. Entries are frozen.")

        if gw.get("is_ended") or gw.get("is_cancelled"):
            return ToggleResult(False, "failed", 0, "This giveaway has already ended.")

        # 2. Check if user already entered
        existing = await self.db.fetch_one(
            "SELECT is_excluded, exclusion_reason FROM giveaway_participants WHERE giveaway_id = $1 AND user_id = $2;",
            giveaway_id,
            member.id,
        )

        if existing:
            if existing.get("is_excluded"):
                reason = existing.get("exclusion_reason", "Administratively excluded")
                return ToggleResult(False, "failed", 0, f"You have been excluded from this giveaway: {reason}")

            # Leave giveaway
            await self.db.execute(
                "DELETE FROM giveaway_participants WHERE giveaway_id = $1 AND user_id = $2;",
                giveaway_id,
                member.id,
            )
            count = await self.get_participant_count(giveaway_id)
            return ToggleResult(True, "left", count, None)

        # 3. Check entry limit
        entry_limit = int(gw.get("entry_limit", 0) or 0)
        current_count = await self.get_participant_count(giveaway_id)
        if entry_limit > 0 and current_count >= entry_limit:
            return ToggleResult(False, "failed", current_count, f"Entry limit of {entry_limit} participants reached.")

        # 4. Check eligibility
        passed, breakdown = await self.check_member_eligibility(gw, member, activity_mgr)
        if not passed:
            failed_reasons = [b["reason"] for b in breakdown if not b["passed"]]
            reason_str = "; ".join(failed_reasons)
            return ToggleResult(False, "failed", current_count, f"Requirements not met: {reason_str}")

        # 5. Calculate bonus entries and weight
        base_entries, weight, qroles, breakdown_str = await self.calculate_member_bonus(gw, member)
        qroles_str = ", ".join(qroles)

        # 6. Insert participant
        await self.db.execute(
            """
            INSERT INTO giveaway_participants (
                giveaway_id, user_id, base_entries, effective_weight, qualifying_roles, bonus_breakdown
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (giveaway_id, user_id) DO NOTHING;
            """,
            giveaway_id,
            member.id,
            base_entries,
            weight,
            qroles_str,
            breakdown_str,
        )

        new_count = await self.get_participant_count(giveaway_id)
        return ToggleResult(True, "entered", new_count, None)

    async def get_participant_count(self, giveaway_id: int) -> int:
        """Fetch total non-excluded participants in this giveaway."""
        row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM giveaway_participants WHERE giveaway_id = $1 AND is_excluded = FALSE;",
            giveaway_id,
        )
        return int(row["cnt"]) if row else 0

    async def get_participants(self, giveaway_id: int) -> list[tuple[int, float]]:
        """Fetch all eligible participants with their effective weights: list of (user_id, weight)."""
        rows = await self.db.fetch_all(
            "SELECT user_id, effective_weight FROM giveaway_participants WHERE giveaway_id = $1 AND is_excluded = FALSE;",
            giveaway_id,
        )
        return [(int(r["user_id"]), float(r["effective_weight"])) for r in rows]

    async def exclude_participant(
        self,
        giveaway_id: int,
        user_id: int,
        actor_id: int,
        reason: str,
    ) -> bool:
        """Administratively exclude a participant from a giveaway with an audit reason."""
        await self.db.execute(
            """
            UPDATE giveaway_participants
            SET is_excluded = TRUE, exclusion_reason = $3, excluded_by = $4
            WHERE giveaway_id = $1 AND user_id = $2;
            """,
            giveaway_id,
            user_id,
            reason,
            actor_id,
        )
        gw = self.get_giveaway_by_id(giveaway_id)
        guild_id = gw["guild_id"] if gw else 0
        await self.log_audit(
            guild_id,
            giveaway_id,
            actor_id,
            "exclude",
            f"Excluded user <@{user_id}>. Reason: {reason}",
        )
        return True

    async def include_participant(
        self,
        giveaway_id: int,
        user_id: int,
        actor_id: int,
    ) -> bool:
        """Restore a previously excluded participant."""
        await self.db.execute(
            """
            UPDATE giveaway_participants
            SET is_excluded = FALSE, exclusion_reason = '', excluded_by = NULL
            WHERE giveaway_id = $1 AND user_id = $2;
            """,
            giveaway_id,
            user_id,
        )
        gw = self.get_giveaway_by_id(giveaway_id)
        guild_id = gw["guild_id"] if gw else 0
        await self.log_audit(
            guild_id,
            giveaway_id,
            actor_id,
            "include",
            f"Restored user <@{user_id}> to giveaway.",
        )
        return True

    # ─── WINNER SELECTION & CLAIMS ───────────────────────────────────────────

    async def end_giveaway(self, message_id: int) -> Optional[dict[str, Any]]:
        """
        Finalize giveaway: select unique winners using weighted sampling,
        record draw audit trail and claim deadlines, evict from in-memory active cache.
        """
        gw = self.get_giveaway_by_message_id(message_id)
        if not gw:
            gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
            if not gw_row:
                return None
            gw = self._row_to_giveaway_dict(gw_row)

        giveaway_id = gw["id"]

        # Mark ended in DB
        await self.db.execute(
            "UPDATE giveaways SET is_ended = TRUE WHERE id = $1;",
            giveaway_id,
        )

        async with self._lock:
            self._active_giveaways.pop(message_id, None)
            self._id_to_message_id.pop(giveaway_id, None)

        # Draw weighted winners
        participants = await self.get_participants(giveaway_id)
        winner_count = gw["winner_count"]

        if not participants:
            winners = []
        else:
            winners = weighted_sample_without_replacement(participants, winner_count)

        # Record winners in giveaway_winners table
        claim_deadline_seconds = gw.get("claim_deadline_seconds", 0)
        now = datetime.datetime.now(datetime.timezone.utc)
        claim_deadline = (
            now + datetime.timedelta(seconds=claim_deadline_seconds)
            if claim_deadline_seconds > 0
            else None
        )

        weights_map = dict(participants)
        for w_id in winners:
            w_weight = weights_map.get(w_id, 1.0)
            await self.db.execute(
                """
                INSERT INTO giveaway_winners (giveaway_id, user_id, weight, drawn_at, claim_deadline)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP, $4);
                """,
                giveaway_id,
                w_id,
                w_weight,
                claim_deadline.replace(tzinfo=None) if claim_deadline else None,
            )

        result = dict(gw)
        result["is_ended"] = True
        result["winners"] = winners
        result["total_entries"] = len(participants)
        result["claim_deadline"] = claim_deadline

        await self.log_audit(
            gw["guild_id"],
            giveaway_id,
            gw["host_id"],
            "end",
            f"Ended giveaway '{gw['prize']}'. Drawn {len(winners)} winner(s).",
        )
        return result

    async def reroll_giveaway(
        self,
        message_id: int,
        count: int = 1,
        actor_id: Optional[int] = None,
    ) -> Optional[tuple[dict[str, Any], list[int]]]:
        """Select new random winner(s) using weighted selection from participants."""
        gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
        if not gw_row:
            return None

        giveaway_id = int(gw_row["id"])
        participants = await self.get_participants(giveaway_id)

        if not participants:
            return dict(gw_row), []

        # Exclude previous active winners if desired
        prev_winners = await self.db.fetch_all(
            "SELECT user_id FROM giveaway_winners WHERE giveaway_id = $1 AND is_rerolled = FALSE;",
            giveaway_id,
        )
        prev_winner_ids = {int(r["user_id"]) for r in prev_winners}

        available = [p for p in participants if p[0] not in prev_winner_ids]
        if not available:
            available = participants

        pick_count = min(count, len(available))
        new_winners = weighted_sample_without_replacement(available, pick_count)

        # Record rerolls
        weights_map = dict(participants)
        for w_id in new_winners:
            await self.db.execute(
                """
                INSERT INTO giveaway_winners (giveaway_id, user_id, weight, drawn_at, is_rerolled)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP, FALSE);
                """,
                giveaway_id,
                w_id,
                weights_map.get(w_id, 1.0),
            )

        if actor_id:
            await self.log_audit(
                int(gw_row["guild_id"]),
                giveaway_id,
                actor_id,
                "reroll",
                f"Rerolled {len(new_winners)} winner(s) for giveaway '{gw_row['prize']}'.",
            )

        return dict(gw_row), new_winners

    # ─── TEMPLATES ───────────────────────────────────────────────────────────

    async def save_template(
        self,
        guild_id: int,
        name: str,
        prize: str,
        description: str,
        winner_count: int,
        duration_seconds: int,
        requirements: list[dict[str, Any]],
        bonus_roles: list[dict[str, Any]],
        user_id: int,
    ) -> int:
        """Save a reusable giveaway template for a server."""
        req_json = json.dumps(requirements)
        bonus_json = json.dumps(bonus_roles)

        row = await self.db.fetch_one(
            """
            INSERT INTO giveaway_templates (
                guild_id, name, prize, description, winner_count,
                duration_seconds, requirements_json, bonus_roles_json, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (guild_id, name) DO UPDATE SET
                prize = EXCLUDED.prize,
                description = EXCLUDED.description,
                winner_count = EXCLUDED.winner_count,
                duration_seconds = EXCLUDED.duration_seconds,
                requirements_json = EXCLUDED.requirements_json,
                bonus_roles_json = EXCLUDED.bonus_roles_json,
                created_by = EXCLUDED.created_by,
                created_at = CURRENT_TIMESTAMP
            RETURNING id;
            """,
            guild_id,
            name,
            prize,
            description,
            winner_count,
            duration_seconds,
            req_json,
            bonus_json,
            user_id,
        )
        return int(row["id"])

    async def get_templates(self, guild_id: int) -> list[dict[str, Any]]:
        """Fetch all saved giveaway templates for a guild."""
        rows = await self.db.fetch_all(
            "SELECT * FROM giveaway_templates WHERE guild_id = $1 ORDER BY name ASC;",
            guild_id,
        )
        return [dict(r) for r in rows]

    async def get_template(self, guild_id: int, name: str) -> Optional[dict[str, Any]]:
        """Fetch a specific template by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM giveaway_templates WHERE guild_id = $1 AND LOWER(name) = LOWER($2);",
            guild_id,
            name,
        )
        return dict(row) if row else None

    async def delete_template(self, guild_id: int, name: str) -> bool:
        """Delete a saved giveaway template."""
        await self.db.execute(
            "DELETE FROM giveaway_templates WHERE guild_id = $1 AND LOWER(name) = LOWER($2);",
            guild_id,
            name,
        )
        return True

    # ─── AUDIT LOGGING & CSV EXPORT ──────────────────────────────────────────

    async def log_audit(
        self,
        guild_id: int,
        giveaway_id: Optional[int],
        actor_id: int,
        action: str,
        details: str,
    ) -> None:
        """Record an administrative or lifecycle event in the audit trail."""
        try:
            await self.db.execute(
                """
                INSERT INTO giveaway_audit_log (guild_id, giveaway_id, actor_id, action, details)
                VALUES ($1, $2, $3, $4, $5);
                """,
                guild_id,
                giveaway_id,
                actor_id,
                action,
                details,
            )
        except Exception as e:
            logger.debug(f"Audit log write failed: {e}")

    async def get_audit_logs(self, guild_id: int, limit: int = 15) -> list[dict[str, Any]]:
        """Fetch recent audit log records for a server."""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM giveaway_audit_log
            WHERE guild_id = $1
            ORDER BY occurred_at DESC
            LIMIT $2;
            """,
            guild_id,
            limit,
        )
        return [dict(r) for r in rows]

    async def export_giveaway_csv(self, giveaway_id: int) -> str:
        """Generate a complete CSV audit export for a giveaway."""
        gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE id = $1;", giveaway_id)
        if not gw_row:
            return ""

        participants = await self.db.fetch_all(
            """
            SELECT user_id, base_entries, effective_weight, qualifying_roles,
                   is_excluded, exclusion_reason, joined_at
            FROM giveaway_participants
            WHERE giveaway_id = $1
            ORDER BY joined_at ASC;
            """,
            giveaway_id,
        )

        winners_rows = await self.db.fetch_all(
            "SELECT user_id, is_claimed, is_rerolled FROM giveaway_winners WHERE giveaway_id = $1;",
            giveaway_id,
        )
        winner_ids = {int(w["user_id"]) for w in winners_rows}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Giveaway ID",
            "Prize",
            "User ID",
            "Base Entries",
            "Effective Weight",
            "Qualifying Roles",
            "Is Excluded",
            "Exclusion Reason",
            "Is Winner",
            "Joined At",
        ])

        prize = str(gw_row["prize"])
        for p in participants:
            uid = int(p["user_id"])
            writer.writerow([
                giveaway_id,
                prize,
                uid,
                p["base_entries"],
                p["effective_weight"],
                p["qualifying_roles"],
                p["is_excluded"],
                p["exclusion_reason"],
                uid in winner_ids,
                p["joined_at"],
            ])

        return output.getvalue()
