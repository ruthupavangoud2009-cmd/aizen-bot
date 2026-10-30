from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from urllib.parse import urlencode, urlsplit, urlunsplit

from aiohttp import web

SUPPORTED_MEDIA_EXTENSIONS = {".mp4", ".m4v", ".webm", ".ogv", ".ogg"}
ROOM_SOCKETS: dict[str, set[web.WebSocketResponse]] = {}


def new_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_media_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not any(parsed.path.lower().endswith(ext) for ext in SUPPORTED_MEDIA_EXTENSIONS)
            or host in {"localhost", "localhost.localdomain"}
            or host.endswith((".localhost", ".local", ".internal", ".test"))
        ):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def player_url(room_id: str, token: str, invite_token: str | None = None) -> str:
    base = os.getenv("WATCH_PARTY_FRONTEND_URL", "https://aizen-bot.pages.dev").strip().rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise ValueError("WATCH_PARTY_FRONTEND_URL must be an absolute HTTP(S) URL.")
    fragment = {"key": token}
    if invite_token:
        fragment["invite"] = invite_token
    return urlunsplit((parts.scheme, parts.netloc, "/watch.html", urlencode({"room": room_id}), urlencode(fragment)))


async def broadcast_room(room_id: str, payload: dict) -> None:
    sockets = ROOM_SOCKETS.get(room_id, set())
    stale = []
    message = json.dumps(payload)
    for socket in tuple(sockets):
        if socket.closed:
            stale.append(socket)
            continue
        try:
            await socket.send_str(message)
        except (ConnectionError, RuntimeError):
            stale.append(socket)
    for socket in stale:
        sockets.discard(socket)
    if not sockets:
        ROOM_SOCKETS.pop(room_id, None)
