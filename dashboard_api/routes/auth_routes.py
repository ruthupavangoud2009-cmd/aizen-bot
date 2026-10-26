"""Authentication endpoints for Discord OAuth2 login, callback, session validation and logout."""
from __future__ import annotations

import logging
from urllib.parse import urlencode
from aiohttp import web

from dashboard_api.auth import (
    create_oauth_state,
    verify_oauth_state,
    extract_oauth_state_extra,
    create_session_token,
    verify_session_token,
    exchange_discord_code,
    fetch_discord_user,
)

logger = logging.getLogger("Kyoka.Dashboard.AuthRoutes")


async def handle_login(request: web.Request) -> web.Response:
    """Redirect user to Discord OAuth2 authorization page with CSRF protection."""
    config = request.app["config"]
    missing = config.get_missing_oauth_vars()
    if missing:
        missing_str = ", ".join(missing)
        err_msg = f"Discord OAuth2 is not configured: missing {missing_str} in environment."
        logger.warning(err_msg)

        # JSON response for API / AJAX callers
        if request.query.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
            return web.json_response(
                {
                    "error": err_msg,
                    "missing_variables": missing,
                    "hint": "Set DISCORD_CLIENT_ID (or CLIENT_ID) and DISCORD_CLIENT_SECRET in your .env file or Render dashboard."
                },
                status=500
            )

        # Polished Aizen HTML explanation page for direct browser navigation
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>KYOKA 3.0 — Discord OAuth Configuration Required</title>
  <link rel="stylesheet" href="/css/style.css">
  <style>
    .oauth-box {{
      max-width: 600px; margin: 5rem auto; padding: 2.5rem;
      background: var(--bg-card); border: 1px solid var(--purple-border);
      border-radius: var(--radius-lg); box-shadow: 0 10px 40px rgba(0,0,0,0.6);
      text-align: center;
    }}
    .missing-list {{
      text-align: left; background: rgba(0,0,0,0.4); padding: 1rem 1.5rem;
      border-radius: var(--radius-sm); margin: 1.5rem 0; font-family: monospace;
      color: #f87171; border-left: 3px solid #ef4444;
    }}
  </style>
</head>
<body style="background: var(--bg-primary); color: var(--text-primary); font-family: sans-serif;">
  <div class="oauth-box">
    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">⚙️</div>
    <h2 style="color: #fff; margin-bottom: 0.5rem;">Discord OAuth2 Setup Required</h2>
    <p style="color: var(--text-muted); font-size: 0.95rem; line-height: 1.5;">
      The KYOKA Web Dashboard requires Discord Developer credentials to authenticate server managers safely.
    </p>
    <div class="missing-list">
      <strong>Missing required setting(s):</strong><br>
      {"<br>".join(f"• <code>{var}</code>" for var in missing)}
    </div>
    <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.5rem;">
      Configure these in your <code>.env</code> file (see <code>.env.example</code>) or your Render environment variables dashboard, then restart the server.
    </p>
    <div style="display: flex; gap: 1rem; justify-content: center;">
      <a href="/dashboard.html" class="btn btn-outline">Back to Dashboard</a>
      <a href="/support.html" class="btn btn-primary">Setup Guide</a>
    </div>
  </div>
</body>
</html>"""
        return web.Response(text=html_content, content_type="text/html", status=500)

    req_origin = request.query.get("origin", "").strip() or request.headers.get("Origin", "").strip()
    if not req_origin:
        referer = request.headers.get("Referer", "")
        if referer:
            from urllib.parse import urlparse
            p = urlparse(referer)
            if p.scheme and p.netloc:
                req_origin = f"{p.scheme}://{p.netloc}"

    extra = req_origin if (req_origin and config.is_origin_allowed(req_origin)) else ""
    state = create_oauth_state(config.secret_key, extra=extra)

    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "scope": "identify guilds",
        "redirect_uri": config.redirect_uri,
        "state": state,
        "prompt": "consent",
    }
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

    # If requested by frontend fetch directly
    if request.query.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
        return web.json_response({"auth_url": discord_auth_url, "state": state})

    raise web.HTTPFound(location=discord_auth_url)


async def handle_callback(request: web.Request) -> web.Response:
    """Handle Discord OAuth2 redirect callback, exchange code, and set secure session cookie."""
    config = request.app["config"]
    missing = config.get_missing_oauth_vars()
    if missing:
        raise web.HTTPInternalServerError(reason=f"Discord OAuth2 credentials incomplete: missing {', '.join(missing)}.")

    query = request.query
    state = query.get("state")

    # Determine frontend redirect target from state if available
    target_origin = config.primary_frontend_url.rstrip("/")
    if state:
        try:
            extra_origin = extract_oauth_state_extra(state, config.secret_key, max_age_seconds=config.state_max_age_seconds)
            if extra_origin and config.is_origin_allowed(extra_origin):
                target_origin = extra_origin.rstrip("/")
        except Exception:
            pass

    error = query.get("error")
    if error:
        logger.warning(f"OAuth error returned by Discord: {error}")
        target = f"{target_origin}/dashboard.html?error={error}"
        raise web.HTTPFound(location=target)

    code = query.get("code")

    if not code or not state:
        target = f"{target_origin}/dashboard.html?error=missing_code"
        raise web.HTTPFound(location=target)

    # 1. Validate CSRF state signature and expiration
    if not verify_oauth_state(state, config.secret_key, max_age_seconds=config.state_max_age_seconds):
        target = f"{target_origin}/dashboard.html?error=invalid_state"
        raise web.HTTPFound(location=target)

    http_session = request.app["http_session"]

    # 2. Exchange authorization code for token
    try:
        token_data = await exchange_discord_code(
            client_id=config.client_id,
            client_secret=config.client_secret,
            redirect_uri=config.redirect_uri,
            code=code,
            session=http_session
        )
    except Exception as e:
        logger.error(f"OAuth code exchange failed: {e}")
        raise web.HTTPBadRequest(reason=f"Discord authentication failed: {str(e)}")

    access_token = token_data.get("access_token")
    if not access_token:
        raise web.HTTPBadRequest(reason="Did not receive valid access token from Discord.")

    # 3. Fetch Discord user profile
    try:
        user_info = await fetch_discord_user(access_token, http_session)
    except Exception as e:
        logger.error(f"Failed to fetch user from Discord: {e}")
        raise web.HTTPBadGateway(reason="Failed to fetch Discord user profile.")

    # 4. Construct user session object
    user_id = str(user_info.get("id"))
    username = user_info.get("username", "User")
    discriminator = user_info.get("discriminator", "0")
    avatar = user_info.get("avatar")

    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=128"
        if avatar
        else f"https://cdn.discordapp.com/embed/avatars/{int(user_id) % 5}.png"
    )

    session_payload = {
        "user_id": user_id,
        "username": username,
        "discriminator": discriminator,
        "avatar": avatar,
        "avatar_url": avatar_url,
        "access_token": access_token,
    }

    session_token = create_session_token(session_payload, config.secret_key)

    # 5. Extract origin from state if client encoded it, or fall back to primary frontend url
    extra_origin = extract_oauth_state_extra(state, config.secret_key, max_age_seconds=config.state_max_age_seconds)
    if extra_origin and config.is_origin_allowed(extra_origin):
        target_origin = extra_origin.rstrip("/")
    else:
        target_origin = config.primary_frontend_url.rstrip("/")

    # Redirect to frontend dashboard with both secure cookie and #token in URL fragment for decoupling
    _redirect_target = f"{target_origin}/dashboard.html#token={session_token}"
    response = web.HTTPFound(location=_redirect_target)
    response.set_cookie(
        name=config.session_cookie_name,
        value=session_token,
        max_age=config.session_max_age_seconds,
        httponly=True,
        secure=config.is_production,
        # SameSite=None required for cross-origin deployments (Cloudflare Pages + Render).
        # SameSite=Lax is sufficient for same-origin (Render serves everything).
        samesite="None" if config.is_production else "Lax",
        path="/"
    )
    return response


async def handle_me(request: web.Request) -> web.Response:
    """Return profile for the currently authenticated user session."""
    config = request.app["config"]
    cookie_token = request.cookies.get(config.session_cookie_name)

    if not cookie_token:
        # Also check Authorization header Bearer token if used by frontend
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            cookie_token = auth_header[7:].strip()

    if not cookie_token:
        return web.json_response({"authenticated": False, "user": None}, status=401)

    session_data = verify_session_token(
        cookie_token,
        config.secret_key,
        max_age_seconds=config.session_max_age_seconds
    )
    if not session_data:
        return web.json_response({"authenticated": False, "user": None}, status=401)

    from src.security.owner import is_primary_owner

    # Return safe user profile (never expose access_token to client JS)
    safe_user = {
        "id": session_data.get("user_id"),
        "username": session_data.get("username"),
        "discriminator": session_data.get("discriminator"),
        "avatar": session_data.get("avatar"),
        "avatar_url": session_data.get("avatar_url"),
        "is_owner": is_primary_owner(session_data.get("user_id")),
    }
    return web.json_response({"authenticated": True, "user": safe_user})


async def handle_logout(request: web.Request) -> web.Response:
    """Invalidate session and clear session cookie."""
    config = request.app["config"]
    response = web.json_response({"success": True, "message": "Logged out successfully."})
    response.del_cookie(config.session_cookie_name, path="/")
    return response


def register_auth_routes(app: web.Application) -> None:
    # Canonical /api/auth routes
    app.router.add_get("/api/auth/login", handle_login)
    app.router.add_get("/api/auth/callback", handle_callback)
    app.router.add_get("/api/auth/me", handle_me)
    app.router.add_post("/api/auth/logout", handle_logout)

    # Route aliases without /api prefix
    app.router.add_get("/auth/login", handle_login)
    app.router.add_get("/auth/callback", handle_callback)
    app.router.add_get("/auth/me", handle_me)
    app.router.add_post("/auth/logout", handle_logout)
