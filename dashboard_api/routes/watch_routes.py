"""Watch Party room APIs and authenticated playback WebSockets."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import re
from urllib.parse import urlencode, urlsplit, urlunsplit
from datetime import datetime, timezone
from typing import Any

import discord
from aiohttp import WSMsgType, web

from dashboard_api.routes.guild_routes import get_authenticated_session, verify_guild_access
from src.watch_party import ROOM_SOCKETS, broadcast_room, new_token, token_hash, validate_media_url

logger = logging.getLogger("Kyoka.Dashboard.WatchParty")
ROOM_TTL_HOURS = 24
CLIENT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{12,64}$")


def _bot_db(request: web.Request) -> Any:
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    return getattr(bot, "db", None) if bot else None


async def _fetch_one(request: web.Request, query: str, *args: Any) -> dict[str, Any] | None:
    bot_db = _bot_db(request)
    if bot_db and hasattr(bot_db, "fetch_one"):
        return await bot_db.fetch_one(re.sub(r"\$\d+", "?", query), *args)
    db = request.app["db"]
    if not getattr(db, "pool", None):
        raise web.HTTPServiceUnavailable(reason="Watch Party requires the configured PostgreSQL database.")
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def _fetch_all(request: web.Request, query: str, *args: Any) -> list[dict[str, Any]]:
    bot_db = _bot_db(request)
    if bot_db and hasattr(bot_db, "fetch_all"):
        return await bot_db.fetch_all(re.sub(r"\$\d+", "?", query), *args)
    db = request.app["db"]
    if not getattr(db, "pool", None):
        raise web.HTTPServiceUnavailable(reason="Watch Party requires the configured PostgreSQL database.")
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def _execute(request: web.Request, query: str, *args: Any) -> None:
    bot_db = _bot_db(request)
    if bot_db and hasattr(bot_db, "execute"):
        await bot_db.execute(re.sub(r"\$\d+", "?", query), *args)
        return
    db = request.app["db"]
    if not getattr(db, "pool", None):
        raise web.HTTPServiceUnavailable(reason="Watch Party requires the configured PostgreSQL database.")
    async with db.pool.acquire() as conn:
        await conn.execute(query, *args)


async def _ensure_tables(app: web.Application) -> None:
    db = app.get("db")
    if not getattr(db, "pool", None):
        return
    async with db.pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS watch_party_rooms (
                room_id TEXT PRIMARY KEY, guild_id BIGINT NOT NULL, host_id BIGINT NOT NULL,
                source_url TEXT, current_time DOUBLE PRECISION NOT NULL DEFAULT 0,
                status VARCHAR(16) NOT NULL DEFAULT 'idle',
                playback_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                invite_hash CHAR(64) NOT NULL, host_hash CHAR(64) NOT NULL,
                max_members INTEGER NOT NULL DEFAULT 25,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(), closed_at TIMESTAMPTZ
            );
            CREATE UNIQUE INDEX IF NOT EXISTS watch_party_one_open_room_per_guild
            ON watch_party_rooms (guild_id) WHERE status <> 'closed';
            CREATE TABLE IF NOT EXISTS watch_party_members (
                room_id TEXT NOT NULL REFERENCES watch_party_rooms(room_id) ON DELETE CASCADE,
                member_key TEXT NOT NULL, display_name VARCHAR(80) NOT NULL,
                joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (room_id, member_key)
            );
            CREATE TABLE IF NOT EXISTS watch_party_settings (
                guild_id BIGINT PRIMARY KEY, max_members INTEGER NOT NULL DEFAULT 25,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)


async def _active_room(request: web.Request, room_id: str) -> dict[str, Any]:
    room = await _fetch_one(request, "SELECT * FROM watch_party_rooms WHERE room_id = $1", room_id)
    if not room or room["status"] == "closed":
        raise web.HTTPNotFound(reason="Watch Party room not found or closed.")
    last_activity = room.get("last_activity")
    if last_activity and (datetime.now(timezone.utc) - last_activity).total_seconds() > ROOM_TTL_HOURS * 3600:
        await _execute(request, "UPDATE watch_party_rooms SET status = 'closed', closed_at = NOW() WHERE room_id = $1", room_id)
        await broadcast_room(room_id, {"type": "closed"})
        raise web.HTTPGone(reason="This Watch Party expired after 24 hours of inactivity.")
    return room


async def _check_key(request: web.Request, room: dict[str, Any], key: str) -> bool:
    if not key or len(key) > 128:
        return False
    candidate = token_hash(key)
    guest = hmac.compare_digest(candidate, room["invite_hash"].strip())
    host = hmac.compare_digest(candidate, room["host_hash"].strip())
    return guest or host


async def _public_room(request: web.Request, room: dict[str, Any]) -> dict[str, Any]:
    members = await _fetch_all(
        request,
        "SELECT member_key, display_name FROM watch_party_members WHERE room_id = $1 ORDER BY joined_at",
        room["room_id"],
    )
    position = float(room.get("current_time") or 0)
    updated = room.get("playback_updated_at")
    if room["status"] == "playing" and updated:
        position += max(0, (datetime.now(timezone.utc) - updated).total_seconds())
    return {
        "roomId": room["room_id"],
        "status": room["status"],
        "source": room.get("source_url"),
        "currentTime": position,
        "hostId": str(room["host_id"]),
        "maxMembers": room["max_members"],
        "members": members,
    }


async def _create_dashboard_room(request: web.Request) -> web.Response:
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    session = await get_authenticated_session(request)
    user_id = int(session.get("user_id") or session.get("id") or 0)
    body = await request.json()
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(reason="Expected a JSON object.")

    configured = await _fetch_one(request, "SELECT max_members FROM watch_party_settings WHERE guild_id = $1", guild_id)
    max_members = int(configured["max_members"]) if configured else 25
    existing = await _fetch_one(request, "SELECT room_id FROM watch_party_rooms WHERE guild_id = $1 AND status <> 'closed' LIMIT 1", guild_id)
    if existing:
        raise web.HTTPConflict(reason="This server already has an active Watch Party.")

    invite, host_key = new_token(), new_token()
    room_id = new_token()[:12]
    row = await _fetch_one(
        request,
        """INSERT INTO watch_party_rooms
           (room_id, guild_id, host_id, invite_hash, host_hash, max_members, status)
           VALUES ($1, $2, $3, $4, $5, $6, 'idle')
           ON CONFLICT DO NOTHING RETURNING room_id""",
        room_id, guild_id, user_id, token_hash(invite), token_hash(host_key), max_members,
    )
    if not row:
        raise web.HTTPConflict(reason="This server already has an active Watch Party.")
    cfg = request.app["config"]
    frontend = cfg.primary_frontend_url.rstrip("/")
    invite_url = _player_link(frontend, room_id, invite)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    discord_posted = False
    guild = bot.get_guild(guild_id) if bot else None
    if guild:
        channels = ([guild.system_channel] if guild.system_channel else []) + list(guild.text_channels)
        seen: set[int] = set()
        for channel in channels:
            if channel is None or channel.id in seen:
                continue
            seen.add(channel.id)
            permissions = channel.permissions_for(guild.me) if guild.me else None
            if not permissions or not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                continue
            embed = discord.Embed(
                title="⛩️ KYOKA WATCH PARTY",
                description=f"**Host:** <@{user_id}>\n**Status:** Waiting for a video\n**Room:** `{room_id}`\n\nJoin the web player to watch. Playback is synchronized between connected browsers.",
                color=0x7C3AED,
            )
            embed.add_field(name="Invitation", value=f"[Join Watch Party]({invite_url})", inline=False)
            embed.set_footer(text="Browser playback only · Direct video URLs · No Discord Go Live")
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Join Watch Party", url=invite_url, style=discord.ButtonStyle.link, emoji="🎬"))
            try:
                await channel.send(embed=embed, view=view)
                discord_posted = True
            except discord.HTTPException:
                logger.exception("Could not post dashboard-created Watch Party invite to guild %s", guild_id)
                continue
            break
    return web.json_response({
        "roomId": room_id,
        "inviteUrl": invite_url,
        "hostUrl": _player_link(frontend, room_id, host_key, invite),
        "status": "idle",
        "maxMembers": max_members,
        "discordPosted": discord_posted,
    }, status=201)


def _player_link(base: str, room_id: str, key: str, invite_token: str | None = None) -> str:
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise web.HTTPInternalServerError(reason="The frontend URL is not configured correctly.")
    fragment = {"key": key}
    if invite_token:
        fragment["invite"] = invite_token
    return urlunsplit((parsed.scheme, parsed.netloc, "/watch.html", urlencode({"room": room_id}), urlencode(fragment)))


async def _list_dashboard_rooms(request: web.Request) -> web.Response:
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    expired = await _fetch_all(
        request,
        """UPDATE watch_party_rooms SET status = 'closed', closed_at = NOW()
           WHERE guild_id = $1 AND status <> 'closed'
           AND last_activity < NOW() - INTERVAL '24 hours' RETURNING room_id""",
        guild_id,
    )
    for row in expired:
        await broadcast_room(row["room_id"], {"type": "closed"})
    rows = await _fetch_all(
        request,
        """SELECT room_id, host_id, source_url, status, current_time, max_members, created_at, last_activity
           FROM watch_party_rooms WHERE guild_id = $1
           ORDER BY created_at DESC LIMIT 50""",
        guild_id,
    )
    rooms = []
    for row in rows:
        members = await _fetch_one(request, "SELECT COUNT(*) AS count FROM watch_party_members WHERE room_id = $1", row["room_id"])
        rooms.append({
            "roomId": row["room_id"], "hostId": str(row["host_id"]), "source": row.get("source_url"),
            "status": row["status"], "currentTime": row["current_time"], "maxMembers": row["max_members"],
            "memberCount": int(members["count"]) if members else 0,
            "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
            "lastActivity": row["last_activity"].isoformat() if row.get("last_activity") else None,
        })
    setting = await _fetch_one(request, "SELECT max_members FROM watch_party_settings WHERE guild_id = $1", guild_id)
    return web.json_response({"rooms": rooms, "maxMembers": int(setting["max_members"]) if setting else 25})


async def _save_settings(request: web.Request) -> web.Response:
    guild_id = int(request.match_info["guild_id"])
    await verify_guild_access(request, guild_id)
    body = await request.json()
    try:
        max_members = int(body.get("maxMembers"))
    except (AttributeError, TypeError, ValueError):
        raise web.HTTPBadRequest(reason="maxMembers must be an integer.")
    if not 2 <= max_members <= 100:
        raise web.HTTPBadRequest(reason="maxMembers must be between 2 and 100.")
    await _execute(
        request,
        """INSERT INTO watch_party_settings (guild_id, max_members) VALUES ($1, $2)
           ON CONFLICT (guild_id) DO UPDATE SET max_members = EXCLUDED.max_members, updated_at = NOW()""",
        guild_id, max_members,
    )
    return web.json_response({"maxMembers": max_members, "hostControlsOnly": True})


async def _close_dashboard_room(request: web.Request) -> web.Response:
    guild_id = int(request.match_info["guild_id"])
    room_id = request.match_info["room_id"]
    await verify_guild_access(request, guild_id)
    room = await _fetch_one(request, "SELECT room_id FROM watch_party_rooms WHERE room_id = $1 AND guild_id = $2 AND status <> 'closed'", room_id, guild_id)
    if not room:
        raise web.HTTPNotFound(reason="Active Watch Party not found.")
    await _execute(request, "UPDATE watch_party_rooms SET status = 'closed', closed_at = NOW(), last_activity = NOW() WHERE room_id = $1", room_id)
    await broadcast_room(room_id, {"type": "closed"})
    return web.json_response({"closed": True})


async def _room_state(request: web.Request) -> web.Response:
    room = await _active_room(request, request.match_info["room_id"])
    key = request.query.get("key", "")
    if not await _check_key(request, room, key):
        raise web.HTTPUnauthorized(reason="Invitation is invalid or expired.")
    await _execute(request, "UPDATE watch_party_rooms SET last_activity = NOW() WHERE room_id = $1", room["room_id"])
    state = await _public_room(request, room)
    state["isHost"] = hmac.compare_digest(token_hash(key), room["host_hash"].strip())
    return web.json_response(state)


async def _create_guest_invite(request: web.Request) -> web.Response:
    room = await _active_room(request, request.match_info["room_id"])
    body = await request.json()
    key = body.get("key", "") if isinstance(body, dict) else ""
    if not key or not hmac.compare_digest(token_hash(key), room["host_hash"].strip()):
        raise web.HTTPForbidden(reason="Only the room host can create an invitation.")
    invite = new_token()
    await _execute(request, "UPDATE watch_party_rooms SET invite_hash = $1, last_activity = NOW() WHERE room_id = $2", token_hash(invite), room["room_id"])
    return web.json_response({"inviteUrl": _player_link(request.app["config"].primary_frontend_url, room["room_id"], invite)})


async def _dashboard_invite(request: web.Request) -> web.Response:
    guild_id = int(request.match_info["guild_id"])
    room_id = request.match_info["room_id"]
    await verify_guild_access(request, guild_id)
    room = await _fetch_one(
        request,
        "SELECT room_id FROM watch_party_rooms WHERE room_id = $1 AND guild_id = $2 AND status <> 'closed'",
        room_id,
        guild_id,
    )
    if not room:
        raise web.HTTPNotFound(reason="Active Watch Party not found.")
    invite = new_token()
    await _execute(
        request,
        "UPDATE watch_party_rooms SET invite_hash = $1, last_activity = NOW() WHERE room_id = $2",
        token_hash(invite),
        room_id,
    )
    return web.json_response({"inviteUrl": _player_link(request.app["config"].primary_frontend_url, room_id, invite)})


async def _dashboard_host_link(request: web.Request) -> web.Response:
    guild_id = int(request.match_info["guild_id"])
    room_id = request.match_info["room_id"]
    await verify_guild_access(request, guild_id)
    session = await get_authenticated_session(request)
    user_id = int(session.get("user_id") or session.get("id") or 0)
    room = await _fetch_one(
        request,
        "SELECT room_id FROM watch_party_rooms WHERE room_id = $1 AND guild_id = $2 AND status <> 'closed'",
        room_id,
        guild_id,
    )
    if not room:
        raise web.HTTPNotFound(reason="Active Watch Party not found.")
    host_key = new_token()
    await _execute(
        request,
        "UPDATE watch_party_rooms SET host_id = $1, host_hash = $2, last_activity = NOW() WHERE room_id = $3",
        user_id,
        token_hash(host_key),
        room_id,
    )
    await broadcast_room(room_id, {"type": "host_changed"})
    return web.json_response({"hostUrl": _player_link(request.app["config"].primary_frontend_url, room_id, host_key)})


async def _room_websocket(request: web.Request) -> web.StreamResponse:
    room_id = request.match_info["room_id"]
    room = await _active_room(request, room_id)
    key = request.query.get("key", "")
    if not await _check_key(request, room, key):
        raise web.HTTPUnauthorized(reason="Invitation is invalid or expired.")
    origin = request.headers.get("Origin")
    config = request.app["config"]
    if origin and hasattr(config, "is_origin_allowed") and not config.is_origin_allowed(origin):
        raise web.HTTPForbidden(reason="WebSocket origin is not allowed.")

    client_key = request.query.get("client", "")
    if not CLIENT_KEY_RE.fullmatch(client_key):
        raise web.HTTPBadRequest(reason="A valid player client identifier is required.")
    host = hmac.compare_digest(token_hash(key), room["host_hash"].strip())
    count = await _fetch_one(request, "SELECT COUNT(*) AS count FROM watch_party_members WHERE room_id = $1", room_id)
    exists = await _fetch_one(request, "SELECT 1 AS present FROM watch_party_members WHERE room_id = $1 AND member_key = $2", room_id, client_key)
    if not exists and count and int(count["count"]) >= room["max_members"]:
        raise web.HTTPConflict(reason="This Watch Party has reached its member limit.")
    await _execute(
        request,
        """INSERT INTO watch_party_members (room_id, member_key, display_name)
           VALUES ($1, $2, $3)
           ON CONFLICT (room_id, member_key) DO UPDATE SET last_seen = NOW()""",
        room_id, client_key, ("Host " if host else "Guest ") + client_key[-4:],
    )
    await _execute(request, "UPDATE watch_party_rooms SET last_activity = NOW() WHERE room_id = $1", room_id)

    ws = web.WebSocketResponse(heartbeat=25, max_msg_size=8192)
    await ws.prepare(request)
    ROOM_SOCKETS.setdefault(room_id, set()).add(ws)
    try:
        room = await _active_room(request, room_id)
        initial_state = await _public_room(request, room)
        initial_state["isHost"] = host
        await ws.send_json({"type": "state", **initial_state})
        await broadcast_room(room_id, {"type": "members", "members": (await _public_room(request, room))["members"]})
        last_control = 0.0
        async for message in ws:
            if message.type == WSMsgType.TEXT:
                try:
                    event = json.loads(message.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid event payload."})
                    continue
                if event.get("type") == "leave":
                    break
                if event.get("type") != "control":
                    continue
                current_host = await _fetch_one(request, "SELECT host_hash FROM watch_party_rooms WHERE room_id = $1 AND status <> 'closed'", room_id)
                if not current_host or not hmac.compare_digest(token_hash(key), current_host["host_hash"].strip()):
                    await ws.send_json({"type": "host_changed"})
                    continue
                if not host:
                    await ws.send_json({"type": "error", "message": "Only the room host can control playback."})
                    continue
                now = asyncio.get_running_loop().time()
                if now - last_control < 0.35:
                    await ws.send_json({"type": "error", "message": "Playback controls are rate limited."})
                    continue
                last_control = now
                action = event.get("action")
                if action not in {"play", "pause", "seek", "stop", "tick"}:
                    continue
                source = event.get("source") if action == "play" else None
                if source is not None and not validate_media_url(source):
                    await ws.send_json({"type": "error", "message": "Unsupported direct media URL."})
                    continue
                try:
                    current_time = float(event.get("currentTime", 0))
                except (TypeError, ValueError):
                    current_time = 0
                if not math.isfinite(current_time) or not 0 <= current_time <= 86_400:
                    continue
                if action == "play" and source:
                    await _execute(request, "UPDATE watch_party_rooms SET source_url = $1, current_time = $2, status = 'playing', playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = $3", source, current_time, room_id)
                elif action == "stop":
                    current_time = 0
                    await _execute(request, "UPDATE watch_party_rooms SET current_time = 0, status = 'stopped', playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = $1", room_id)
                elif action == "tick":
                    await _execute(request, "UPDATE watch_party_rooms SET current_time = $1, playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = $2", current_time, room_id)
                else:
                    status = "paused" if action == "pause" else ("playing" if action == "play" else room["status"])
                    await _execute(request, "UPDATE watch_party_rooms SET current_time = $1, status = $2, playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = $3", current_time, status, room_id)
                state = await _fetch_one(request, "SELECT * FROM watch_party_rooms WHERE room_id = $1", room_id)
                await broadcast_room(room_id, {"type": "state", **(await _public_room(request, state))})
            elif message.type in {WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED}:
                break
    finally:
        ROOM_SOCKETS.get(room_id, set()).discard(ws)
        await _execute(request, "DELETE FROM watch_party_members WHERE room_id = $1 AND member_key = $2", room_id, client_key)
        if not ROOM_SOCKETS.get(room_id):
            ROOM_SOCKETS.pop(room_id, None)
        else:
            current_room = await _fetch_one(request, "SELECT * FROM watch_party_rooms WHERE room_id = $1", room_id)
            if current_room and current_room["status"] != "closed":
                await broadcast_room(room_id, {"type": "members", "members": (await _public_room(request, current_room))["members"]})
    return ws


def register_watch_routes(app: web.Application) -> None:
    app.router.add_post("/api/guilds/{guild_id}/watch/rooms", _create_dashboard_room)
    app.router.add_get("/api/guilds/{guild_id}/watch/rooms", _list_dashboard_rooms)
    app.router.add_patch("/api/guilds/{guild_id}/watch/settings", _save_settings)
    app.router.add_post("/api/guilds/{guild_id}/watch/rooms/{room_id}/invite", _dashboard_invite)
    app.router.add_post("/api/guilds/{guild_id}/watch/rooms/{room_id}/host", _dashboard_host_link)
    app.router.add_delete("/api/guilds/{guild_id}/watch/rooms/{room_id}", _close_dashboard_room)
    app.router.add_get("/api/watch/{room_id}/state", _room_state)
    app.router.add_post("/api/watch/{room_id}/invite", _create_guest_invite)
    app.router.add_get("/api/watch/{room_id}/ws", _room_websocket)
    app.on_startup.append(_ensure_tables)
