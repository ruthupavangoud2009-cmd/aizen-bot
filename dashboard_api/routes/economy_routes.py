"""
Economy & Games Dashboard API Routes.
Provides authenticated configuration endpoints for:
- Currency name & emoji
- Starting balance
- Daily & weekly rewards
- Work & crime reward limits
- Gambling limits
- Robbing toggle
- Event multipliers
- Leaderboard & shop viewing
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from aiohttp import web

from dashboard_api.routes.guild_routes import verify_guild_access
from src.security.owner import OWNER_ID

logger = logging.getLogger("Kyoka.Dashboard.EconomyRoutes")


async def get_economy_settings(request: web.Request) -> web.Response:
    """Retrieve server economy configuration."""
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    db = request.app["db"]

    row = await db.fetch_one("SELECT * FROM economy_guild_settings WHERE guild_id = ?;", guild_id)
    if not row:
        defaults = {
            "guild_id": guild_id,
            "currency_name": "KYOKA Coins",
            "currency_emoji": "🪙",
            "starting_balance": 1000,
            "daily_reward": 500,
            "weekly_reward": 2500,
            "work_min": 100,
            "work_max": 400,
            "crime_min": 200,
            "crime_max": 800,
            "robbing_enabled": True,
            "gamble_limit": 50000,
            "event_multiplier": 1.0,
        }
        return web.json_response({"settings": defaults})

    return web.json_response({"settings": dict(row)})


async def update_economy_settings(request: web.Request) -> web.Response:
    """Update server economy configuration with strict validation."""
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    db = request.app["db"]

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body payload.")

    # Validate inputs
    currency_name = str(body.get("currency_name", "KYOKA Coins")).strip()[:50]
    currency_emoji = str(body.get("currency_emoji", "🪙")).strip()[:32]

    try:
        starting_balance = max(0, min(1000000, int(body.get("starting_balance", 1000))))
        daily_reward = max(0, min(500000, int(body.get("daily_reward", 500))))
        weekly_reward = max(0, min(2000000, int(body.get("weekly_reward", 2500))))
        work_min = max(0, min(50000, int(body.get("work_min", 100))))
        work_max = max(work_min, min(100000, int(body.get("work_max", 400))))
        crime_min = max(0, min(50000, int(body.get("crime_min", 200))))
        crime_max = max(crime_min, min(200000, int(body.get("crime_max", 800))))
        gamble_limit = max(100, min(10000000, int(body.get("gamble_limit", 50000))))
        robbing_enabled = bool(body.get("robbing_enabled", True))
        event_multiplier = max(0.1, min(10.0, float(body.get("event_multiplier", 1.0))))
    except (ValueError, TypeError) as err:
        raise web.HTTPBadRequest(reason=f"Validation error in numeric fields: {err}")

    await db.execute(
        """
        INSERT INTO economy_guild_settings (guild_id, currency_name, currency_emoji, starting_balance, daily_reward, weekly_reward, work_min, work_max, crime_min, crime_max, robbing_enabled, gamble_limit, event_multiplier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            currency_name = EXCLUDED.currency_name,
            currency_emoji = EXCLUDED.currency_emoji,
            starting_balance = EXCLUDED.starting_balance,
            daily_reward = EXCLUDED.daily_reward,
            weekly_reward = EXCLUDED.weekly_reward,
            work_min = EXCLUDED.work_min,
            work_max = EXCLUDED.work_max,
            crime_min = EXCLUDED.crime_min,
            crime_max = EXCLUDED.crime_max,
            robbing_enabled = EXCLUDED.robbing_enabled,
            gamble_limit = EXCLUDED.gamble_limit,
            event_multiplier = EXCLUDED.event_multiplier;
        """,
        guild_id, currency_name, currency_emoji, starting_balance, daily_reward,
        weekly_reward, work_min, work_max, crime_min, crime_max, robbing_enabled,
        gamble_limit, event_multiplier
    )

    updated_row = await db.fetch_one("SELECT * FROM economy_guild_settings WHERE guild_id = ?;", guild_id)
    return web.json_response({
        "success": True,
        "message": "Economy settings updated successfully.",
        "settings": dict(updated_row) if updated_row else {}
    })


async def get_economy_leaderboard(request: web.Request) -> web.Response:
    """View top server economy leaderboard for dashboard."""
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    db = request.app["db"]

    rows = await db.fetch_all(
        """
        SELECT user_id, balance, bank, (balance + bank) as net_worth, level, daily_streak
        FROM user_profiles
        WHERE guild_id = ? AND (balance + bank) > 0
        ORDER BY (balance + bank) DESC
        LIMIT 25;
        """,
        guild_id
    )
    return web.json_response({"leaderboard": [dict(r) for r in rows]})


async def get_economy_shop(request: web.Request) -> web.Response:
    """View shop items catalog for dashboard."""
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    db = request.app["db"]

    rows = await db.fetch_all("SELECT * FROM economy_items ORDER BY price ASC;")
    return web.json_response({"shop": [dict(r) for r in rows]})


def register_economy_routes(app: web.Application) -> None:
    """Register economy configuration routes onto the web application."""
    app.router.add_get("/api/guilds/{guild_id}/economy/settings", get_economy_settings)
    app.router.add_patch("/api/guilds/{guild_id}/economy/settings", update_economy_settings)
    app.router.add_post("/api/guilds/{guild_id}/economy/settings", update_economy_settings)
    app.router.add_get("/api/guilds/{guild_id}/economy/leaderboard", get_economy_leaderboard)
    app.router.add_get("/api/guilds/{guild_id}/economy/shop", get_economy_shop)
