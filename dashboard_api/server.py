"""Main web application factory, middleware, rate limiting, and security headers."""
from __future__ import annotations

import asyncio
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
from dashboard_api.routes.ticket_routes import register_ticket_routes

logger = logging.getLogger("Kyoka.Dashboard.Server")


@web.middleware
async def error_handling_middleware(request: web.Request, handler) -> web.Response:
    """Catch unhandled exceptions, client cancellations, and disconnections gracefully to prevent server-level error logs."""
    try:
        return await handler(request)
    except web.HTTPRedirection:
        raise
    except web.HTTPException as http_exc:
        # Re-raise standard HTML/page errors (e.g. 404 for missing static files)
        if not request.path.startswith("/api/"):
            raise

        origin = request.headers.get("Origin", "")
        headers = {
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept",
            "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
        }
        if origin:
            headers["Access-Control-Allow-Credentials"] = "true"

        return web.json_response(
            {
                "error": http_exc.reason or type(http_exc).__name__,
                "status": http_exc.status,
                "message": getattr(http_exc, "text", str(http_exc.reason or "")),
            },
            status=http_exc.status,
            headers=headers,
        )
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as conn_err:
        logger.debug(f"Client disconnected during {request.method} {request.path} from {request.remote}: {conn_err}")
        return web.Response(status=499, text="Client Closed Request")
    except Exception as exc:
        logger.warning(f"Handled error during {request.method} {request.path} from {request.remote}: {exc}")
        if request.path.startswith("/api/"):
            origin = request.headers.get("Origin", "")
            headers = {
                "Access-Control-Allow-Origin": origin if origin else "*",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept",
                "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
            }
            if origin:
                headers["Access-Control-Allow-Credentials"] = "true"
            return web.json_response(
                {
                    "error": "Internal Server Error",
                    "status": 500,
                    "message": "An error occurred while processing the request.",
                },
                status=500,
                headers=headers,
            )
        return web.Response(status=500, text="Internal Server Error")


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

    is_allowed = False
    echo_origin = ""

    if origin:
        if config.is_origin_allowed(origin):
            is_allowed = True
            echo_origin = origin
    elif not config.is_production:
        is_allowed = True
        echo_origin = "*"

    # Handle Preflight OPTIONS
    if request.method == "OPTIONS":
        res = web.Response(status=204)
        if is_allowed and echo_origin:
            res.headers["Access-Control-Allow-Origin"] = echo_origin
            if echo_origin != "*":
                res.headers["Access-Control-Allow-Credentials"] = "true"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
        res.headers["Access-Control-Max-Age"] = "86400"
        return res

    response = await handler(request)

    # Attach CORS to normal responses
    if is_allowed and echo_origin:
        response.headers["Access-Control-Allow-Origin"] = echo_origin
        if echo_origin != "*":
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

    try:
        db: BaseDatabaseAdapter = app["db"]
        await db.connect()
        logger.info("KYOKA 3.0 Dashboard API startup sequence completed.")
    except Exception as exc:
        logger.critical(f"KYOKA 3.0 Dashboard API startup failed: {exc}")
        # Reliably close client session immediately on startup failure to eliminate unclosed session warnings
        if "http_session" in app and not app["http_session"].closed:
            await app["http_session"].close()
        db_adapter = app.get("db")
        if db_adapter:
            try:
                await db_adapter.close()
            except Exception:
                pass
        raise


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
    serve_website: bool = True,
    bot: Any = None,
    bot_getter: Any = None,
) -> web.Application:
    """Application factory for KYOKA Dashboard API."""
    cfg = config or DashboardConfig.from_env()

    if db is None:
        if cfg.database_url:
            db_adapter = PostgresDatabaseAdapter(cfg.database_url)
        else:
            if cfg.is_production:
                raise RuntimeError(
                    "DATABASE_URL environment variable is required in production mode. "
                    "Cannot start the KYOKA Dashboard in production with in-memory storage."
                )
            logger.warning("No DATABASE_URL configured. Initializing in-memory mock database for tests/offline dev.")
            db_adapter = MockDatabaseAdapter()
    else:
        db_adapter = db

    app = web.Application(
        middlewares=[
            error_handling_middleware,
            rate_limit_middleware,
            cors_middleware,
            security_headers_middleware,
        ]
    )

    app["config"] = cfg
    app["db"] = db_adapter
    app["rate_limiter"] = SlidingWindowRateLimiter(default_limit=cfg.rate_limit_per_minute)
    if bot is not None:
        app["bot"] = bot
    if bot_getter is not None:
        app["bot_getter"] = bot_getter

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Register API blueprints
    register_auth_routes(app)
    register_guild_routes(app)
    register_music_routes(app)
    register_owner_routes(app)
    register_system_routes(app)
    register_ticket_routes(app)

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
                ("tickets", "tickets.html"),
                ("staff", "staff.html"),
            ]
            for clean_route, filename in named_pages:
                page_path = os.path.join(website_dir, filename)
                handler = make_page_handler(page_path)
                app.router.add_get(f"/{clean_route}", handler)
                app.router.add_get(f"/{filename}", handler)

            # 3. Static assets (css, js, assets, etc.) with directory listing strictly disabled
            app.router.add_static("/", website_dir, show_index=False)

    return app
