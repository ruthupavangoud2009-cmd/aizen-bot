"""Main web application factory, middleware, rate limiting, and security headers."""
from __future__ import annotations

import logging
import os
from typing import Optional
import aiohttp
from aiohttp import web

from dashboard_api.config import DashboardConfig
from dashboard_api.database import BaseDatabaseAdapter, PostgresDatabaseAdapter, MockDatabaseAdapter
from dashboard_api.rate_limiter import SlidingWindowRateLimiter
from dashboard_api.routes.auth_routes import register_auth_routes
from dashboard_api.routes.guild_routes import register_guild_routes
from dashboard_api.routes.owner_routes import register_owner_routes
from dashboard_api.routes.music_routes import register_music_routes
from dashboard_api.routes.system_routes import register_system_routes

logger = logging.getLogger("Kyoka.Dashboard.Server")


@web.middleware
async def security_headers_middleware(request: web.Request, handler) -> web.Response:
    """Inject strict security headers onto every HTTP response."""
    response = await handler(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # CSP for browser protection
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://cdn.discordapp.com https://images.unsplash.com; "
        "connect-src 'self' https://discord.com;"
    )
    response.headers["Content-Security-Policy"] = csp

    return response


@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    """Handle Cross-Origin Resource Sharing (CORS) for decoupled Cloudflare Pages frontend."""
    config: DashboardConfig = request.app["config"]
    origin = request.headers.get("Origin", "")

    # Handle Preflight OPTIONS
    if request.method == "OPTIONS":
        res = web.Response(status=204)
        if config.frontend_origin == "*" or (origin and origin == config.frontend_origin):
            res.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
            res.headers["Access-Control-Allow-Credentials"] = "true"
        elif config.frontend_origin:
            res.headers["Access-Control-Allow-Origin"] = config.frontend_origin
            res.headers["Access-Control-Allow-Credentials"] = "true"

        res.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        res.headers["Access-Control-Max-Age"] = "86400"
        return res

    response = await handler(request)

    # Attach CORS to normal responses
    if config.frontend_origin == "*" or (origin and origin == config.frontend_origin):
        response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    elif config.frontend_origin:
        response.headers["Access-Control-Allow-Origin"] = config.frontend_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


@web.middleware
async def rate_limit_middleware(request: web.Request, handler) -> web.Response:
    """Enforce rate limits on API routes to protect Discord tokens and DB resources."""
    # Exclude static assets from rate limiting
    if not request.path.startswith("/api/"):
        return await handler(request)

    limiter: SlidingWindowRateLimiter = request.app["rate_limiter"]

    # Extract client IP
    client_ip = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote
        or "unknown"
    )

    allowed, remaining, reset_in = limiter.is_allowed(client_ip)
    if not allowed:
        return web.json_response(
            {"error": "Too Many Requests", "message": "Rate limit exceeded. Please wait."},
            status=429,
            headers={"Retry-After": str(int(reset_in) + 1)}
        )

    response = await handler(request)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


async def on_startup(app: web.Application) -> None:
    """Initialize HTTP client session and database connector on startup."""
    app["http_session"] = aiohttp.ClientSession()

    db: BaseDatabaseAdapter = app["db"]
    await db.connect()
    logger.info("KYOKA 3.0 Dashboard API startup sequence completed.")


async def on_cleanup(app: web.Application) -> None:
    """Clean up resources on server shutdown."""
    if "http_session" in app and not app["http_session"].closed:
        await app["http_session"].close()

    db: BaseDatabaseAdapter = app.get("db")
    if db:
        await db.close()
    logger.info("KYOKA 3.0 Dashboard API shutdown completed.")


def create_app(
    config: Optional[DashboardConfig] = None,
    db: Optional[BaseDatabaseAdapter] = None,
    serve_website: bool = True
) -> web.Application:
    """Application factory for KYOKA Dashboard API."""
    cfg = config or DashboardConfig.from_env()

    if db is None:
        if cfg.database_url:
            db_adapter = PostgresDatabaseAdapter(cfg.database_url)
        else:
            logger.warning("No DATABASE_URL configured. Initializing in-memory mock database for tests/offline dev.")
            db_adapter = MockDatabaseAdapter()
    else:
        db_adapter = db

    app = web.Application(
        middlewares=[
            rate_limit_middleware,
            cors_middleware,
            security_headers_middleware,
        ]
    )

    app["config"] = cfg
    app["db"] = db_adapter
    app["rate_limiter"] = SlidingWindowRateLimiter(default_limit=cfg.rate_limit_per_minute)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Register API blueprints
    register_auth_routes(app)
    register_guild_routes(app)
    register_music_routes(app)
    register_owner_routes(app)
    register_system_routes(app)

    # Mount frontend static files and pages for unified hosting and standalone deployment
    if serve_website:
        website_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "website"))
        if os.path.isdir(website_dir):
            def make_page_handler(filepath: str):
                async def page_handler(request: web.Request) -> web.Response:
                    if os.path.isfile(filepath):
                        return web.FileResponse(filepath)
                    raise web.HTTPNotFound()
                return page_handler

            # 1. Homepage explicit routes
            index_path = os.path.join(website_dir, "index.html")
            app.router.add_get("/", make_page_handler(index_path))
            app.router.add_get("/index.html", make_page_handler(index_path))

            # 2. Clean URLs & .html named routes
            named_pages = [
                ("features", "features.html"),
                ("commands", "commands.html"),
                ("premium", "premium.html"),
                ("changelog", "changelog.html"),
                ("support", "support.html"),
                ("privacy", "privacy.html"),
                ("terms", "terms.html"),
                ("dashboard", "dashboard.html"),
                ("owner", "owner.html"),
            ]
            for clean_route, filename in named_pages:
                page_path = os.path.join(website_dir, filename)
                handler = make_page_handler(page_path)
                app.router.add_get(f"/{clean_route}", handler)
                app.router.add_get(f"/{filename}", handler)

            # 3. Static assets (css, js, assets, etc.) with directory listing strictly disabled
            app.router.add_static("/", website_dir, show_index=False)

    return app
