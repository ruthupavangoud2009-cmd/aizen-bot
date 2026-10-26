"""Owner-only administrative endpoints for KYOKA 3.0.

STRICT SECURITY REQUIREMENTS:
- Authoritative access restricted exclusively to OWNER_ID (1505515188991033409).
- Hard fail-closed server-side verification on EVERY request.
- Returns HTTP 403 Forbidden to any unauthorized user.
- Comprehensive audit logging for all administrative operations.
- Zero exposure of bot tokens, DB credentials, or secrets.
- Arbitrary shell / eval execution strictly prohibited.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional
from aiohttp import web

from dashboard_api.auth import verify_session_token
from src.security.owner import OWNER_ID, is_primary_owner

logger = logging.getLogger("Kyoka.Dashboard.OwnerRoutes")


async def get_authenticated_owner_session(request: web.Request) -> Dict[str, Any]:
    """Verify session exists and that the authenticated user is the authoritative bot owner.

    Raises:
        web.HTTPUnauthorized: If session is missing or expired.
        web.HTTPForbidden: If the authenticated user is NOT the bot owner.
    """
    config = request.app["config"]
    token = request.cookies.get(config.session_cookie_name)

    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise web.HTTPUnauthorized(reason="Authentication required. Please log in with Discord.")

    session_data = verify_session_token(
        token,
        config.secret_key,
        max_age_seconds=config.session_max_age_seconds
    )
    if not session_data:
        raise web.HTTPUnauthorized(reason="Session expired or invalid. Please log in again.")

    user_id = session_data.get("user_id")
    if not is_primary_owner(user_id):
        logger.warning(
            f"Unauthorized owner dashboard access attempt by user_id={user_id} "
            f"from IP={request.remote}"
        )
        # Record security denial event in audit log if DB is available
        db = request.app.get("db")
        if db and hasattr(db, "log_owner_audit"):
            try:
                await db.log_owner_audit(
                    actor_id=int(user_id or 0),
                    action="owner_access_denied",
                    target_id=None,
                    outcome="denied",
                    details=f"Unauthorized access attempt to {request.path}",
                )
            except Exception:
                pass

        raise web.HTTPForbidden(
            reason="Forbidden: Sovereign access restricted to authorized bot owner."
        )

    return session_data


# --- Section A: Global Overview ---

async def handle_owner_overview(request: web.Request) -> web.Response:
    """Return aggregated global metrics and service health for owner control center."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    overview_data = await db.get_owner_overview()
    return web.json_response(overview_data)


# --- Section B: Bot Operations & Gateway Status ---

async def handle_bot_operations(request: web.Request) -> web.Response:
    """Return live bot operations metrics, gateway connection state, and diagnostics."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    bot_ops = await db.get_bot_operations_status()
    return web.json_response(bot_ops)


# --- Section C: Guild Management ---

async def handle_owner_list_guilds(request: web.Request) -> web.Response:
    """Return all guilds registered in the bot database with configuration summaries."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    guilds = await db.get_all_registered_guilds()
    return web.json_response({"guilds": guilds, "total": len(guilds)})


# --- Section D: Premium Management ---

async def handle_owner_get_premium(request: web.Request) -> web.Response:
    """Return verified premium subscriptions and available license keys."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    premium_data = await db.get_owner_premium_data()
    return web.json_response(premium_data)


async def handle_owner_grant_premium(request: web.Request) -> web.Response:
    """Grant or extend guild/user premium with strict audit trail."""
    session = await get_authenticated_owner_session(request)
    db = request.app["db"]

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON request body.")

    target_type = str(body.get("target_type", "")).lower().strip()
    target_id_str = str(body.get("target_id", "")).strip()
    tier = str(body.get("tier", "pro")).lower().strip()
    days = body.get("days", 30)

    if target_type not in ("guild", "user"):
        raise web.HTTPBadRequest(reason="target_type must be 'guild' or 'user'.")
    if not target_id_str.isdigit() or len(target_id_str) < 15:
        raise web.HTTPBadRequest(reason="target_id must be a valid Discord snowflake.")
    if tier not in ("pro", "enterprise", "aizen"):
        tier = "pro"
    try:
        days_int = max(1, min(3650, int(days)))
    except (ValueError, TypeError):
        days_int = 30

    actor_id = int(session.get("user_id", OWNER_ID))
    target_id = int(target_id_str)

    res = await db.grant_premium(
        target_type=target_type,
        target_id=target_id,
        tier=tier,
        days=days_int,
        actor_id=actor_id,
    )

    return web.json_response({
        "success": True,
        "message": f"Successfully granted {tier.upper()} premium to {target_type} {target_id} for {days_int} days.",
        "details": res,
    })


async def handle_owner_revoke_premium(request: web.Request) -> web.Response:
    """Revoke guild/user premium with strict audit trail."""
    session = await get_authenticated_owner_session(request)
    db = request.app["db"]

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON request body.")

    target_type = str(body.get("target_type", "")).lower().strip()
    target_id_str = str(body.get("target_id", "")).strip()

    if target_type not in ("guild", "user"):
        raise web.HTTPBadRequest(reason="target_type must be 'guild' or 'user'.")
    if not target_id_str.isdigit():
        raise web.HTTPBadRequest(reason="target_id must be a valid Discord snowflake.")

    actor_id = int(session.get("user_id", OWNER_ID))
    target_id = int(target_id_str)

    await db.revoke_premium(target_type=target_type, target_id=target_id, actor_id=actor_id)

    return web.json_response({
        "success": True,
        "message": f"Revoked premium access for {target_type} {target_id}.",
    })


# --- Section E: Feature & Integration Health ---

async def handle_owner_integrations(request: web.Request) -> web.Response:
    """Return health status of all subsystems (Database, Discord API, Lavalink, AI)."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    integrations = await db.get_owner_integrations_health()
    return web.json_response(integrations)


# --- Section F: Audit Log ---

async def handle_owner_audit_log(request: web.Request) -> web.Response:
    """Fetch recent tamper-proof security audit log entries."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    limit = 50
    try:
        limit_param = request.query.get("limit")
        if limit_param:
            limit = max(5, min(200, int(limit_param)))
    except (ValueError, TypeError):
        pass

    logs = await db.get_owner_audit_logs(limit=limit)
    return web.json_response({"audit_logs": logs, "count": len(logs)})


# --- Section G: Safe Website Configuration ---

async def handle_owner_get_web_config(request: web.Request) -> web.Response:
    """Fetch safe public presentation settings and announcement banner configuration."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    config = await db.get_website_config()
    return web.json_response(config)


async def handle_owner_update_web_config(request: web.Request) -> web.Response:
    """Update safe public presentation settings (NO SECRETS)."""
    session = await get_authenticated_owner_session(request)
    db = request.app["db"]

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON request body.")

    # Strictly filter allowed fields to prevent any secret injection
    allowed_fields = {
        "announcement_enabled": bool(body.get("announcement_enabled", False)),
        "announcement_text": str(body.get("announcement_text", ""))[:250],
        "announcement_level": str(body.get("announcement_level", "info"))[:16],
        "support_discord_url": str(body.get("support_discord_url", "https://discord.gg/7q4tn6dA6V"))[:120],
        "docs_url": str(body.get("docs_url", "https://docs.kyokabot.com"))[:120],
    }

    actor_id = int(session.get("user_id", OWNER_ID))
    updated = await db.update_website_config(allowed_fields, actor_id=actor_id)

    return web.json_response({
        "success": True,
        "message": "Website configuration updated successfully.",
        "config": updated,
    })


# --- Section H: Maintenance & Diagnostics ---

async def handle_owner_diagnostics(request: web.Request) -> web.Response:
    """Return server system diagnostics and latency benchmarks without exposing secrets."""
    await get_authenticated_owner_session(request)
    db = request.app["db"]

    diag = await db.get_system_diagnostics()
    return web.json_response(diag)


def register_owner_routes(app: web.Application) -> None:
    """Register all owner endpoints to application router."""
    app.router.add_get("/api/owner/overview", handle_owner_overview)
    app.router.add_get("/api/owner/bot-status", handle_bot_operations)
    app.router.add_get("/api/owner/guilds", handle_owner_list_guilds)
    app.router.add_get("/api/owner/premium", handle_owner_get_premium)
    app.router.add_post("/api/owner/premium/grant", handle_owner_grant_premium)
    app.router.add_post("/api/owner/premium/revoke", handle_owner_revoke_premium)
    app.router.add_get("/api/owner/integrations", handle_owner_integrations)
    app.router.add_get("/api/owner/audit-log", handle_owner_audit_log)
    app.router.add_get("/api/owner/config", handle_owner_get_web_config)
    app.router.add_post("/api/owner/config", handle_owner_update_web_config)
    app.router.add_get("/api/owner/diagnostics", handle_owner_diagnostics)
