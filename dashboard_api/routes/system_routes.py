"""Public system status, health checks, and command inventory metadata."""
from __future__ import annotations

from aiohttp import web

OFFICIAL_COMMANDS = [
    # Giveaway Group
    {"group": "Giveaway", "name": "/giveaway create", "description": "Create and publish an interactive giveaway with rich options.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway quick", "description": "Launch a giveaway with sensible default parameters.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway end", "description": "Conclude an active giveaway early and pick winners now.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway cancel", "description": "Cancel an active giveaway without drawing winners.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway pause", "description": "Pause entries and freeze countdown for an active giveaway.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway resume", "description": "Resume a paused giveaway with preserved duration.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway reroll", "description": "Select replacement winners for unclaimed/ineligible prizes.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway edit", "description": "Edit live giveaway settings (prize, winner count, description).", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway list", "description": "List active, scheduled, paused, and recent giveaways.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway info", "description": "View detailed giveaway information and status.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway entries", "description": "View participant count and authorized entry details.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway check", "description": "Check a specific member's eligibility.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway exclude", "description": "Administratively exclude a user with an audit reason.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway include", "description": "Restore an excluded user to eligible status.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway remind", "description": "Broadcast a reminder announcement for an ending giveaway.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway clone", "description": "Clone an existing giveaway's configuration.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway export", "description": "Export participant weights and entry breakdown to CSV.", "category": "Giveaways"},
    {"group": "Giveaway", "name": "/giveaway templates", "description": "Save, load, list, or delete reusable giveaway templates.", "category": "Giveaways"},

    # Requirements Group
    {"group": "Requirements", "name": "/requirements add", "description": "Attach eligibility requirements to a giveaway or server defaults.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements remove", "description": "Remove a configured eligibility requirement by ID.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements list", "description": "List all configured requirements for a giveaway or server.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements test", "description": "Test a member's eligibility against configured rules.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements activity", "description": "Configure daily or 7-day message volume requirements.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements roles", "description": "Configure required, permitted (any-of), or excluded roles.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements tag", "description": "Configure server clan tag verification.", "category": "Giveaways"},
    {"group": "Requirements", "name": "/requirements bonus", "description": "Configure role-based bonus entries and multiplier stacking.", "category": "Giveaways"},

    # Config Group
    {"group": "Config", "name": "/config view", "description": "Inspect complete server giveaway and activity configurations.", "category": "Administration"},
    {"group": "Config", "name": "/config channel", "description": "Designate default giveaway and announcement channels.", "category": "Administration"},
    {"group": "Config", "name": "/config roles", "description": "Set custom giveaway manager role and staff exceptions.", "category": "Administration"},
    {"group": "Config", "name": "/config permissions", "description": "Configure management permissions and host access.", "category": "Administration"},
    {"group": "Config", "name": "/config appearance", "description": "Configure embed accent color, banner, and thumbnail.", "category": "Administration"},
    {"group": "Config", "name": "/config notifications", "description": "Configure winner DMs, claim deadlines, and reminder intervals.", "category": "Administration"},
    {"group": "Config", "name": "/config activity", "description": "Configure message tracking cooldowns and channel exclusions.", "category": "Administration"},
    {"group": "Config", "name": "/config reset", "description": "Reset selected server settings to defaults after confirmation.", "category": "Administration"},

    # AI Group
    {"group": "AI", "name": "/ai setup", "description": "Configure AI personality, channel, tone, and rules for this server.", "category": "Artificial Intelligence"},
    {"group": "AI", "name": "/ai personality", "description": "Choose from 10 presets or configure a custom persona.", "category": "Artificial Intelligence"},
    {"group": "AI", "name": "/ai test", "description": "Preview AI conversational responses under current settings.", "category": "Artificial Intelligence"},
    {"group": "AI", "name": "/ai reset", "description": "Reset AI configuration to default after confirmation.", "category": "Artificial Intelligence"},
    {"group": "AI", "name": "/ai enable", "description": "Enable AI conversational responses in configured channels.", "category": "Artificial Intelligence"},
    {"group": "AI", "name": "/ai disable", "description": "Disable AI in specific channels or server-wide.", "category": "Artificial Intelligence"},

    # Utility & Admin Top Level Commands
    {"group": "General", "name": "/help", "description": "Interactive command guide and category help with dropdowns.", "category": "General"},
    {"group": "General", "name": "/ping", "description": "WebSocket latency, API heartbeat, and database query latency.", "category": "General"},
    {"group": "General", "name": "/botinfo", "description": "Bot version, uptime, server count, and environment status.", "category": "General"},
    {"group": "General", "name": "/serverinfo", "description": "Server statistics, owner, creation date, and feature toggles.", "category": "General"},
    {"group": "General", "name": "/userinfo", "description": "Member details, join dates, roles, and avatar display.", "category": "General"},
    {"group": "General", "name": "/activity", "description": "View requesting member's message statistics (today & 7 days).", "category": "Analytics"},
    {"group": "General", "name": "/leaderboard", "description": "Show server message activity leaderboard.", "category": "Analytics"},
    {"group": "General", "name": "/auditlog", "description": "View administrative giveaway and configuration audit trail.", "category": "Administration"},
    {"group": "General", "name": "/diagnostics", "description": "System health: database pool, background workers, and gateway.", "category": "Administration"},
    {"group": "General", "name": "/privacy", "description": "Privacy information, tracking opt-out, and right-to-be-forgotten erasure.", "category": "General"},

    # Key Administrative & Security Cogs
    {"group": "Antinuke", "name": "+antinuke", "description": "Anti-nuke security suite with vanity, role, channel, and bot protection.", "category": "Security"},
    {"group": "Antinuke", "name": "+whitelist", "description": "Manage users or roles immune to antinuke triggers.", "category": "Security"},
    {"group": "Antinuke", "name": "+extraowner", "description": "Designate trusted extra owners for server protection bypass.", "category": "Security"},
    {"group": "Verification", "name": "+verification setup", "description": "Enhanced member verification system with button or captcha modes.", "category": "Security"},
    {"group": "Music", "name": "+play <song>", "description": "High-fidelity audio playback with smart autoplay queue.", "category": "Music"},
    {"group": "Music", "name": "+247", "description": "Toggle 24/7 voice channel stay mode.", "category": "Music"},
]


async def handle_health(request: web.Request) -> web.Response:
    """System health check endpoint for monitoring uptime and database connectivity."""
    db = request.app.get("db")
    db_connected = False
    if db:
        try:
            if hasattr(db, "pool") and db.pool:
                if not getattr(db.pool, "_closed", False):
                    async with db.pool.acquire(timeout=4.0) as conn:
                        await conn.execute("SELECT 1;")
                    db_connected = True
                else:
                    db_connected = False
            elif hasattr(db, "is_connected"):
                db_connected = bool(db.is_connected)
            elif hasattr(db, "settings_store"):
                db_connected = getattr(db, "_is_connected", True)
        except Exception:
            db_connected = False

    config = request.app.get("config")
    is_prod = getattr(config, "is_production", False)

    status = "healthy" if db_connected else ("unhealthy" if is_prod else "degraded")
    http_code = 200 if (db_connected or not is_prod) else 503

    return web.json_response({
        "status": status,
        "service": "kyoka-dashboard-api",
        "version": "3.0.0",
        "database_connected": db_connected
    }, status=http_code)


async def handle_stats(request: web.Request) -> web.Response:
    """Public statistics for homepage showcase."""
    db = request.app["db"]
    stats = await db.get_public_stats()
    return web.json_response(stats)


async def handle_commands(request: web.Request) -> web.Response:
    """Return categorized list of real official bot commands."""
    return web.json_response({"commands": OFFICIAL_COMMANDS})


def register_system_routes(app: web.Application) -> None:
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/commands", handle_commands)
