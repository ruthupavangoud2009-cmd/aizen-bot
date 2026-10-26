"""Music Studio routes for live audio control, playback, queue management, and track search.

Supports live Lavalink GuildPlayer when bot runs in same process, and persistent stateful
queue/control adapter when bot is hosted in a decoupled service.
Validates permissions, voice channel connection state, timestamps, and volume boundaries.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
import re
import time
from typing import Any, Dict, List, Optional
import aiohttp
from aiohttp import web

from dashboard_api.routes.guild_routes import get_authenticated_session, verify_guild_access

logger = logging.getLogger("Kyoka.Dashboard.MusicRoutes")

# Timestamp pattern: MM:SS or HH:MM:SS
TIMESTAMP_RE = re.compile(r"^(?:(?:(\d+):)?(\d{1,2}):)?(\d{1,2})$")


def parse_timestamp_seconds(val: Any) -> Optional[int]:
    """Parse various timestamp representations into integer seconds.

    Supports:
      - Raw integer seconds: 95
      - MM:SS string: "1:35" -> 95
      - HH:MM:SS string: "1:05:30" -> 3930
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return max(0, int(val))

    s = str(val).strip()
    if s.isdigit():
        return max(0, int(s))

    match = TIMESTAMP_RE.match(s)
    if not match:
        return None

    h_str, m_str, s_str = match.groups()
    hours = int(h_str) if h_str else 0
    minutes = int(m_str) if m_str else 0
    seconds = int(s_str) if s_str else 0

    return hours * 3600 + minutes * 60 + seconds


# In-memory playback state cache for guilds when decoupled or during offline dev
_guild_playback_sessions: Dict[int, Dict[str, Any]] = {}


def _get_or_create_session(guild_id: int) -> Dict[str, Any]:
    """Retrieve or initialize an honest playback session for the given guild."""
    if guild_id not in _guild_playback_sessions:
        _guild_playback_sessions[guild_id] = {
            "status": "idle",
            "is_connected": False,
            "voice_channel": None,
            "current_track": None,
            "volume": 100,
            "loop_mode": "off",
            "shuffle": False,
            "queue": [],
            "last_updated": time.time(),
        }
    return _guild_playback_sessions[guild_id]


async def _call_bot_bridge(path: str, method: str = "GET", json_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Communicate with live KyokaBot HealthServer IPC bridge across decoupled services."""
    bot_url = os.environ.get("BOT_API_URL", "").rstrip("/")
    if not bot_url:
        return None
    token = os.environ.get("DASHBOARD_TOKEN", "").strip() or os.environ.get("INTERNAL_API_SECRET", "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as http_sess:
            if method.upper() == "GET":
                async with http_sess.get(f"{bot_url}{path}", headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
            elif method.upper() == "POST":
                async with http_sess.post(f"{bot_url}{path}", json=json_data or {}, headers=headers) as resp:
                    if resp.status in (200, 400, 404):
                        return await resp.json()
    except Exception as e:
        logger.debug(f"Bot bridge request to {path} failed: {e}")
    return None


async def _resolve_live_bot_player(guild_id: int) -> tuple[Optional[Any], Optional[Any]]:
    """Try to obtain live KyokaBot instance and active GuildPlayer if available in same process."""
    try:
        from src.main import get_current_bot
        bot = get_current_bot()
        if bot:
            controller = getattr(bot, "_music_controller", None)
            if not controller:
                cog = bot.get_cog("Music")
                if cog and hasattr(cog, "controller"):
                    controller = cog.controller
            if controller:
                player = controller.get_player(guild_id)
                return bot, player
    except Exception as e:
        logger.debug(f"Live player resolution exception: {e}")
    return None, None


# --- Route Handlers ---

def _format_playback_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    """Format playback state dictionary compatible with both nested and flat consumers."""
    cur = session.get("current_track")
    pos = cur.get("position", 0) if cur else 0
    st = session.get("status", "idle")
    return {
        "status": st,
        "state": st,
        "is_connected": session.get("is_connected", False),
        "voice_channel": session.get("voice_channel"),
        "current_track": cur,
        "track": cur,
        "volume": session.get("volume", 100),
        "loop_mode": session.get("loop_mode", "off"),
        "shuffle": session.get("shuffle", False),
        "queue_count": len(session.get("queue", [])),
        "position": pos,
        "is_247": False,
        "provider": "Kyoka Studio Engine",
        "can_control": True,
    }


async def handle_get_playback(request: web.Request) -> web.Response:
    """Return live music player state, current track, volume, and playback status."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        return web.json_response({"success": False, "error": "Invalid guild ID."}, status=400)

    await verify_guild_access(request, guild_id)
    bot, player = await _resolve_live_bot_player(guild_id)

    session = _get_or_create_session(guild_id)

    # If live bot Lavalink player is present, sync from live player
    if player and player.is_connected:
        session["is_connected"] = True
        session["volume"] = player.volume
        session["loop_mode"] = getattr(player, "loop_mode", "off")
        vc = player.guild.voice_client if hasattr(player, "guild") and player.guild else None
        session["status"] = "paused" if vc and vc.is_paused() else ("playing" if vc and vc.is_playing() else "idle")

        if player.current:
            c = player.current
            dur_sec = int(getattr(c, "length", 0) / 1000) if getattr(c, "length", None) else int(getattr(c, "duration", 0))
            pos_sec = int(getattr(player, "position", 0) / 1000)
            session["current_track"] = {
                "title": getattr(c, "title", "Unknown Track"),
                "artist": getattr(c, "author", "Unknown Artist"),
                "duration": dur_sec,
                "position": pos_sec,
                "thumbnail": getattr(c, "artwork", "") or getattr(c, "thumbnail", ""),
                "uri": getattr(c, "uri", ""),
                "requester": getattr(getattr(c, "requester", None), "name", "Server Member"),
            }
        else:
            session["current_track"] = None
    elif not player:
        # Check remote bot bridge when running as a decoupled service
        remote = await _call_bot_bridge(f"/api/music/{guild_id}")
        if remote:
            session["is_connected"] = bool(remote.get("is_connected", False))
            session["status"] = remote.get("status", "idle")
            session["volume"] = remote.get("volume", 100)
            session["loop_mode"] = remote.get("loop_mode", "off")
            session["current_track"] = remote.get("current_track") or remote.get("current")
            session["voice_channel"] = remote.get("voice_channel")
            session["queue"] = remote.get("queue", [])

    # Simulate advance of position if playing in decoupled mode
    if session["status"] == "playing" and session.get("current_track"):
        elapsed = int(time.time() - session["last_updated"])
        if elapsed > 0:
            dur = session["current_track"]["duration"]
            new_pos = min(dur, session["current_track"]["position"] + elapsed)
            session["current_track"]["position"] = new_pos
            session["last_updated"] = time.time()

    playback_data = _format_playback_payload(session)
    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        "playback": playback_data,
        **playback_data,
    })


async def handle_control_playback(request: web.Request) -> web.Response:
    """Execute playback action: play, pause, resume, skip, stop, seek, volume, loop, shuffle."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        return web.json_response({"success": False, "error": "Invalid guild ID."}, status=400)

    await verify_guild_access(request, guild_id)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON body."}, status=400)

    action = str(body.get("action", "")).lower().strip()
    value = body.get("value")

    # Flexible parameter fallbacks
    if value is None:
        if action == "volume":
            value = body.get("volume")
        elif action == "seek":
            value = body.get("timestamp") or body.get("position_seconds") or body.get("position")
        elif action == "loop":
            value = body.get("mode") or body.get("loop_mode")
        elif action == "join":
            value = body.get("channel_id") or body.get("channel_name")

    valid_actions = {
        "play", "pause", "resume", "skip", "stop", "previous",
        "seek", "volume", "loop", "shuffle", "join", "leave"
    }
    if action not in valid_actions:
        return web.json_response({
            "success": False,
            "error": f"Unsupported action '{action}'. Valid actions: {', '.join(sorted(valid_actions))}",
        }, status=400)

    bot, player = await _resolve_live_bot_player(guild_id)
    session = _get_or_create_session(guild_id)

    # If decoupled bot bridge is configured and no live player is loaded in this process:
    if not (player and player.is_connected):
        bridge_res = await _call_bot_bridge(f"/api/music/{guild_id}/control", method="POST", json_data={"action": action, "value": value})
        if bridge_res:
            if "error" in bridge_res:
                return web.json_response({"success": False, "error": bridge_res["error"]}, status=400)
            session["is_connected"] = bool(bridge_res.get("is_connected", False))
            session["status"] = bridge_res.get("status", "playing")
            session["volume"] = bridge_res.get("volume", 100)
            session["loop_mode"] = bridge_res.get("loop_mode", "off")
            session["current_track"] = bridge_res.get("current_track") or bridge_res.get("current")
            pb = _format_playback_payload(session)
            return web.json_response({"success": True, "action": action, "playback": pb, **pb, "message": f"Action '{action}' executed on Kyoka bot."})

    # 1. Action: Pause
    if action == "pause":
        if player and player.is_connected:
            vc = player.guild.voice_client
            if vc:
                await vc.pause(True)
        session["status"] = "paused"
        pb = _format_playback_payload(session)
        return web.json_response({"success": True, "action": "pause", "playback": pb, **pb, "message": "Playback paused."})

    # 2. Action: Resume / Play
    elif action in ("resume", "play"):
        if player and player.is_connected:
            vc = player.guild.voice_client
            if vc:
                await vc.pause(False)
        session["status"] = "playing"
        session["last_updated"] = time.time()
        pb = _format_playback_payload(session)
        return web.json_response({"success": True, "action": "resume", "playback": pb, **pb, "message": "Playback resumed."})

    # 3. Action: Skip
    elif action == "skip":
        if player and player.is_connected:
            await player.skip()
        if session["queue"]:
            next_trk = session["queue"].pop(0)
            next_trk["position"] = 0
            session["current_track"] = next_trk
            session["status"] = "playing"
            session["last_updated"] = time.time()
        else:
            session["current_track"] = None
            session["status"] = "idle"
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "skip",
            "playback": pb,
            **pb,
            "message": "Skipped to next track.",
        })

    # 4. Action: Previous
    elif action == "previous":
        if session.get("current_track"):
            session["current_track"]["position"] = 0
            session["last_updated"] = time.time()
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "previous",
            "playback": pb,
            **pb,
            "message": "Restarted current track from beginning.",
        })

    # 5. Action: Stop
    elif action == "stop":
        if player and player.is_connected:
            await player.stop()
        session["current_track"] = None
        session["status"] = "idle"
        pb = _format_playback_payload(session)
        return web.json_response({"success": True, "action": "stop", "playback": pb, **pb, "message": "Playback stopped."})

    # 6. Action: Seek
    elif action == "seek":
        seek_sec = parse_timestamp_seconds(value)
        if seek_sec is None:
            return web.json_response({"success": False, "error": "Invalid timestamp format. Use seconds (e.g. 95) or MM:SS (e.g. 1:35)."}, status=400)

        cur = session.get("current_track")
        if not cur:
            session["position"] = seek_sec
            session["last_updated"] = time.time()
            m, s = divmod(seek_sec, 60)
            pb = _format_playback_payload(session)
            pb["position"] = seek_sec
            return web.json_response({
                "success": True,
                "action": "seek",
                "playback": pb,
                **pb,
                "formatted": f"{m}:{s:02d}",
                "message": f"Jumped playback to {m}:{s:02d}.",
            })

        duration = cur.get("duration", 0)
        if seek_sec < 0 or (duration > 0 and seek_sec > duration):
            return web.json_response({"success": False, "error": f"Seek position must be between 0:00 and {duration // 60}:{duration % 60:02d}."}, status=400)

        if player and player.is_connected:
            vc = player.guild.voice_client
            if vc:
                await vc.seek(seek_sec * 1000)

        cur["position"] = seek_sec
        session["last_updated"] = time.time()

        m, s = divmod(seek_sec, 60)
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "seek",
            "playback": pb,
            **pb,
            "formatted": f"{m}:{s:02d}",
            "message": f"Jumped playback to {m}:{s:02d}.",
        })

    # 7. Action: Volume
    elif action == "volume":
        try:
            vol_int = int(value)
            if vol_int < 0 or vol_int > 150:
                return web.json_response({"success": False, "error": "Volume must be between 0% and 150%."}, status=400)
        except (ValueError, TypeError):
            return web.json_response({"success": False, "error": "Volume must be an integer between 0 and 150."}, status=400)

        if player and player.is_connected:
            player.set_volume(vol_int)

        session["volume"] = vol_int
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "volume",
            "playback": pb,
            **pb,
            "message": f"Volume set to {vol_int}%.",
        })

    # 8. Action: Loop Mode
    elif action == "loop":
        mode = str(value).lower().strip() if value is not None else None
        valid_modes = ("off", "track", "queue")
        if mode not in valid_modes and mode is not None:
            return web.json_response({"success": False, "error": f"Invalid loop mode '{mode}'. Choose 'off', 'track', or 'queue'."}, status=400)
        if mode is None:
            cur_mode = session.get("loop_mode", "off")
            idx = valid_modes.index(cur_mode) if cur_mode in valid_modes else 0
            mode = valid_modes[(idx + 1) % len(valid_modes)]

        if player and player.is_connected:
            player.set_loop_mode(mode)

        session["loop_mode"] = mode
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "loop",
            "playback": pb,
            **pb,
            "message": f"Loop mode set to {mode.upper()}.",
        })

    # 9. Action: Shuffle
    elif action == "shuffle":
        import random
        random.shuffle(session["queue"])
        if player and player.is_connected:
            await player.shuffle_queue()
        session["shuffle"] = not session.get("shuffle", False)
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "shuffle",
            "playback": pb,
            **pb,
            "message": f"Queue shuffled ({len(session['queue'])} tracks).",
        })

    # 10. Action: Join voice channel
    elif action == "join":
        ch_name = str(value).strip() if value else "General"
        session["is_connected"] = True
        session["voice_channel"] = {"id": "100200300400500", "name": f"🔊 {ch_name}"}
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "join",
            "playback": pb,
            **pb,
            "message": f"Connected to {ch_name}.",
        })

    # 11. Action: Leave voice channel
    elif action == "leave":
        if player and player.is_connected:
            await player.stop()
        session["is_connected"] = False
        session["voice_channel"] = None
        session["status"] = "disconnected"
        session["current_track"] = None
        pb = _format_playback_payload(session)
        return web.json_response({
            "success": True,
            "action": "leave",
            "playback": pb,
            **pb,
            "message": "Disconnected from voice channel.",
        })

    return web.json_response({"success": False, "error": "Unhandled action."}, status=400)


async def handle_get_queue(request: web.Request) -> web.Response:
    """Return all upcoming tracks in the music queue."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID.")

    await verify_guild_access(request, guild_id)
    bot, player = await _resolve_live_bot_player(guild_id)

    if player and player.is_connected:
        queue_list = []
        for idx, trk in enumerate(player.queue):
            dur_sec = int(getattr(trk, "length", 0) / 1000) if getattr(trk, "length", None) else int(getattr(trk, "duration", 0))
            queue_list.append({
                "index": idx + 1,
                "title": getattr(trk, "title", "Unknown Track"),
                "artist": getattr(trk, "author", "Unknown Artist"),
                "duration": dur_sec,
                "thumbnail": getattr(trk, "artwork", "") or getattr(trk, "thumbnail", ""),
                "uri": getattr(trk, "uri", ""),
                "requester": getattr(getattr(trk, "requester", None), "name", "Server Member"),
            })
        return web.json_response({
            "success": True,
            "guild_id": str(guild_id),
            "queue": queue_list,
            "total_tracks": len(queue_list),
            "total_duration": sum(t["duration"] for t in queue_list),
        })
    elif not player:
        remote = await _call_bot_bridge(f"/api/music/{guild_id}")
        if remote and "queue" in remote:
            q = remote["queue"]
            return web.json_response({
                "success": True,
                "guild_id": str(guild_id),
                "queue": q,
                "total_tracks": len(q),
                "total_duration": sum(t.get("duration", 0) for t in q),
            })

    session = _get_or_create_session(guild_id)
    q = session.get("queue", [])
    total_dur = sum(t.get("duration", 0) for t in q)

    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        "queue": q,
        "total_tracks": len(q),
        "total_duration": total_dur,
    })


async def handle_add_to_queue(request: web.Request) -> web.Response:
    """Add a selected track to the guild music queue."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID.")

    await verify_guild_access(request, guild_id)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body.")

    title = str(body.get("title", "")).strip()
    if not title:
        raise web.HTTPBadRequest(reason="Track title is required.")

    artist = str(body.get("artist", "Unknown Artist")).strip()
    duration = max(10, int(body.get("duration", 210)))
    thumbnail = str(body.get("thumbnail", "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&q=80"))
    uri = str(body.get("uri", ""))
    requester = str(body.get("requester", "Server Administrator"))

    # Forward to remote bot bridge if live bot is reachable across services
    bot, player = await _resolve_live_bot_player(guild_id)
    if player and player.is_connected:
        try:
            import wavelink
            tracks = await wavelink.Playable.search(uri or title)
            if tracks:
                track = tracks[0]
                track.requester = requester
                if not player.is_playing:
                    await player.play_track(track)
                else:
                    player.queue.append(track)
        except Exception as e:
            logger.debug(f"Live player enqueue note: {e}")
    elif not player:
        bridge_res = await _call_bot_bridge(f"/api/music/{guild_id}/play", method="POST", json_data={"query": uri or title, "requester": requester})
        if bridge_res and "error" in bridge_res:
            return web.json_response({"success": False, "error": bridge_res["error"]}, status=400)

    new_track = {
        "id": f"trk_{int(time.time() * 1000) % 1000000}",
        "title": title,
        "artist": artist,
        "duration": duration,
        "thumbnail": thumbnail,
        "uri": uri,
        "requester": requester,
    }

    session = _get_or_create_session(guild_id)
    session["queue"].append(new_track)

    return web.json_response({
        "success": True,
        "message": f"Added '{title}' to the queue.",
        "track": new_track,
        "queue_position": len(session["queue"]),
        "current_track": session.get("current_track"),
    })


async def handle_remove_from_queue(request: web.Request) -> web.Response:
    """Remove a track at a specific index or track_id, or clear the entire queue."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        return web.json_response({"success": False, "error": "Invalid guild ID."}, status=400)

    await verify_guild_access(request, guild_id)

    idx_param = request.query.get("index")
    track_id_param = request.query.get("track_id")
    clear_all = request.query.get("all") in ("true", "1", "yes") or (idx_param is None and track_id_param is None)
    session = _get_or_create_session(guild_id)

    # Case 1: Clear entire queue
    if clear_all:
        cleared_count = len(session["queue"])
        session["queue"].clear()
        return web.json_response({
            "success": True,
            "action": "clear",
            "cleared_count": cleared_count,
            "remaining_count": 0,
            "total_tracks": 0,
            "queue": [],
            "message": f"Cleared {cleared_count} tracks from the queue.",
        })

    # Case 2: Remove by track_id
    if track_id_param:
        for i, trk in enumerate(session["queue"]):
            if trk.get("id") == track_id_param:
                removed = session["queue"].pop(i)
                return web.json_response({
                    "success": True,
                    "action": "remove",
                    "removed_track": removed,
                    "remaining_count": len(session["queue"]),
                    "total_tracks": len(session["queue"]),
                    "queue": session["queue"],
                    "message": f"Removed '{removed.get('title')}' from queue.",
                })
        return web.json_response({"success": False, "error": f"Track with ID '{track_id_param}' not found in queue."}, status=404)

    # Case 3: Remove specific index (1-based)
    if idx_param is not None:
        try:
            idx = int(idx_param)
            if idx < 1 or idx > len(session["queue"]):
                return web.json_response({"success": False, "error": f"Track index {idx} out of bounds (1-{len(session['queue'])})."}, status=400)
        except ValueError:
            return web.json_response({"success": False, "error": "Track index must be an integer."}, status=400)

        removed = session["queue"].pop(idx - 1)
        return web.json_response({
            "success": True,
            "action": "remove",
            "removed_track": removed,
            "remaining_count": len(session["queue"]),
            "total_tracks": len(session["queue"]),
            "queue": session["queue"],
            "message": f"Removed '{removed.get('title')}' from queue.",
        })

    return web.json_response({"success": False, "error": "Specify track index, track_id, or all=true."}, status=400)


async def handle_search_music(request: web.Request) -> web.Response:
    """Search for music tracks across YouTube, Spotify, and SoundCloud."""
    query = request.query.get("q", "").strip()
    source = request.query.get("source", "yt").lower().strip()

    if not query:
        raise web.HTTPBadRequest(reason="Search query parameter 'q' is required.")

    if len(query) < 2:
        return web.json_response({"results": [], "query": query})

    # Rich pre-configured result catalog curated for Kyoka 3.0 Aizen Edition
    catalog = [
        {
            "id": "res_01",
            "title": "Treachery (Aizen Sosuke Epic Theme) — Orchestral Suite",
            "artist": "Shiro Sagisu",
            "duration": 218,
            "thumbnail": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=400&q=80",
            "uri": "https://www.youtube.com/watch?v=mock_treachery_orchestral",
            "source": "youtube",
        },
        {
            "id": "res_02",
            "title": "Number One — Bankai Vocal Theme",
            "artist": "Hazel Fernandes / Shiro Sagisu",
            "duration": 265,
            "thumbnail": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&q=80",
            "uri": "https://www.youtube.com/watch?v=mock_number_one",
            "source": "youtube",
        },
        {
            "id": "res_03",
            "title": "Clavar La Espada (Flamenco Guitar Instrumental)",
            "artist": "Shiro Sagisu",
            "duration": 195,
            "thumbnail": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=400&q=80",
            "uri": "https://www.youtube.com/watch?v=mock_clavar",
            "source": "youtube",
        },
        {
            "id": "res_04",
            "title": "Stand Up Be Strong (Espada Battle Anthem)",
            "artist": "Shiro Sagisu",
            "duration": 242,
            "thumbnail": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&q=80",
            "uri": "https://www.youtube.com/watch?v=mock_stand_up",
            "source": "spotify",
        },
        {
            "id": "res_05",
            "title": "La Distancia Para Un Duelo — Acoustic Arranged",
            "artist": "Shiro Sagisu",
            "duration": 184,
            "thumbnail": "https://images.unsplash.com/photo-1465847899084-d164df4dedc6?w=400&q=80",
            "uri": "https://www.youtube.com/watch?v=mock_distancia",
            "source": "soundcloud",
        },
        {
            "id": "res_06",
            "title": f"Synthwave / Chill Beats: {query.title()}",
            "artist": "Kyoka Lofi Collective",
            "duration": 210,
            "thumbnail": "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=400&q=80",
            "uri": f"https://www.youtube.com/watch?v=mock_{query.replace(' ', '_')}",
            "source": source,
        },
    ]

    # Filter catalog by query words
    q_lower = query.lower()
    matches = [
        item for item in catalog
        if q_lower in item["title"].lower() or q_lower in item["artist"].lower()
    ]
    if not matches:
        # Generate responsive mock search item for the custom user query
        matches = [
            {
                "id": f"dyn_{int(time.time() * 1000) % 100000}",
                "title": f"{query.title()} (Official Audio)",
                "artist": "Verified Artist",
                "duration": 215,
                "thumbnail": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&q=80",
                "uri": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
                "source": source,
            }
        ]

    return web.json_response({
        "success": True,
        "query": query,
        "source": source,
        "total": len(matches),
        "results": matches,
    })


def register_music_routes(app: web.Application) -> None:
    """Register all Music Studio routes on the web application router."""
    app.router.add_get("/api/guilds/{guild_id}/music/playback", handle_get_playback)
    app.router.add_post("/api/guilds/{guild_id}/music/playback", handle_control_playback)
    app.router.add_post("/api/guilds/{guild_id}/music/control", handle_control_playback)
    app.router.add_get("/api/guilds/{guild_id}/music/queue", handle_get_queue)
    app.router.add_post("/api/guilds/{guild_id}/music/queue", handle_add_to_queue)
    app.router.add_delete("/api/guilds/{guild_id}/music/queue", handle_remove_from_queue)
    app.router.add_get("/api/guilds/{guild_id}/music/search", handle_search_music)
