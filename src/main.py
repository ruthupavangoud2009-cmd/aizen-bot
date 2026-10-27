from __future__ import annotations

import asyncio
import logging
import os
import random
import signal
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure static FFmpeg binaries are registered on PATH
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

import discord
import discord.opus
from src.core.bot import KyokaBot
from src.core.config import Config
from src.core.server import HealthServer
from src.utils.logger import setup_logger

logger = setup_logger("Kyoka")

# Ensure Opus library is loaded across Windows, Linux, and Cloud Hosting
if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(str(BASE_DIR))
    except Exception:
        pass

if not discord.opus.is_loaded():
    possible_opus_paths = [
        str(Path(sys.prefix) / "Lib/site-packages/discord/bin/libopus-0.x64.dll"),
        str(Path(sys.prefix) / "Lib/site-packages/discord/bin/libopus-0.x86.dll"),
        str(BASE_DIR / "opus.dll"),
        str(BASE_DIR / "libopus.so.0"),
        str(BASE_DIR / "libopus.so"),
        "/usr/lib/x86_64-linux-gnu/libopus.so.0",
        "/usr/lib/x86_64-linux-gnu/libopus.so",
        "/usr/lib/libopus.so.0",
        "/usr/lib64/libopus.so.0",
        "/usr/local/lib/libopus.so.0",
        "opus.dll",
        "libopus.so.0",
        "libopus.so",
        "libopus-0.dll",
        "libopus-0.x64.dll",
    ]
    import ctypes.util
    opus_lib = ctypes.util.find_library("opus")
    if opus_lib:
        possible_opus_paths.insert(0, opus_lib)

    for target in possible_opus_paths:
        try:
            discord.opus.load_opus(target)
            if discord.opus.is_loaded():
                logger.info(f"Loaded Opus library from: {target}")
                break
        except Exception as e:
            logger.debug(f"Notice loading {target}: {e}")

    if discord.opus.is_loaded():
        logger.info("Discord Opus voice engine is fully loaded & active.")
    else:
        logger.warning("Discord Opus library could not be loaded automatically.")

active_bot: KyokaBot | None = None


def get_current_bot() -> KyokaBot | None:
    return active_bot


# Transient aiohttp network errors that are safe to retry with backoff.
# These cover: proxy timeouts, DNS failures, connection refused, TLS errors.
_TRANSIENT_AIOHTTP_ERRORS: tuple[type[Exception], ...] = ()
try:
    import aiohttp
    _TRANSIENT_AIOHTTP_ERRORS = (
        aiohttp.ServerTimeoutError,
        aiohttp.ClientConnectorError,
        aiohttp.ClientConnectionError,
        aiohttp.ClientOSError,
        aiohttp.ServerDisconnectedError,
        aiohttp.TooManyRedirects,
    )
except ImportError:
    pass


def _jittered_backoff(base: float, attempt: int, cap: float = 300.0) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2^attempt)).

    - Starts at base seconds, doubles each attempt, caps at `cap` seconds.
    - Full jitter spreads retry storms across multiple reconnect attempts.
    - Does NOT use random seeds tied to secrets or tokens.
    """
    ceiling = min(cap, base * (2.0 ** attempt))
    return random.uniform(0.0, ceiling)


async def run_bot_loop() -> None:
    """Run bot with bounded exponential backoff for transient network errors,
    instant route failover on Discord 429 rate limits, and zero-downtime gateway reconnection."""
    global active_bot

    try:
        Config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        return

    backoff_base = 15.0
    backoff_attempt = 0

    # Route cooldown tracking: route identifier -> monotonic timestamp when cooldown expires
    route_cooldowns: dict[str, float] = {}

    def get_route_label(proxy_url: str | None) -> str:
        if not proxy_url:
            return "direct connection"
        import urllib.parse
        parsed = urllib.parse.urlparse(proxy_url)
        host = parsed.hostname or "proxy"
        port = f":{parsed.port}" if parsed.port else ""
        return f"proxy ({host}{port})"

    while True:
        try:
            now = time.monotonic()
            proxy_pool = Config.get_proxy_pool()

            # Assemble candidate routes: all configured proxies first, then direct connection
            candidate_routes: list[str | None] = []
            for p in proxy_pool:
                if p not in candidate_routes:
                    candidate_routes.append(p)
            candidate_routes.append(None)  # Direct connection is always an available option

            # Find candidates that are NOT currently on cooldown
            available_routes = [
                r for r in candidate_routes
                if route_cooldowns.get(r or "direct", 0.0) <= now
            ]

            if available_routes:
                active_proxy = available_routes[0]
            else:
                # All routes currently cooling down: find earliest expiring route
                earliest_expire = min(
                    route_cooldowns.get(r or "direct", now) for r in candidate_routes
                )
                remaining_wait = max(0.0, earliest_expire - now)
                capped_wait = max(5.0, min(remaining_wait, 45.0))

                logger.warning(
                    f"⚠️ All gateway outbound routes are currently rate-limited by Discord "
                    f"(earliest route unlocks in {remaining_wait:.0f}s). Cooling down for {capped_wait:.0f}s before retrying...\n"
                    f"💡 INSTANT UNBLOCK TIPS:\n"
                    f"  1. If hosting on Render: In Render Dashboard -> Settings -> change Region (e.g. Frankfurt -> Oregon / Singapore) for a fresh clean IP immediately!\n"
                    f"  2. If running locally: Update or remove DISCORD_PROXY in your .env file to route via your clean home IP.\n"
                    f"  3. Configure multiple proxies in DISCORD_PROXY_POOL (comma-separated) for automated round-robin failover."
                )
                await asyncio.sleep(capped_wait)
                continue

            current_route_key = active_proxy or "direct"
            current_route_name = get_route_label(active_proxy)

            bot = KyokaBot(proxy=active_proxy)
            active_bot = bot
            logger.info(f"Connecting {Config.BOT_NAME} in [{Config.ENVIRONMENT.upper()}] mode to Discord Gateway ({current_route_name})...")

            async with bot:
                await bot.start(Config.TOKEN)

            # Clean exit / graceful disconnect
            backoff_attempt = 0
            route_cooldowns.pop(current_route_key, None)
            await asyncio.sleep(5)

        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", None)
                response_text = getattr(e, "text", str(e))
                if retry_after is None and hasattr(e, "response") and e.response is not None:
                    retry_header = getattr(e.response, "headers", {}).get("Retry-After")
                    if retry_header:
                        try:
                            retry_after = float(retry_header)
                        except ValueError:
                            pass

                block_penalty = float(retry_after) if retry_after else 1800.0

                # Mark the current route on cooldown for the rate limit duration
                route_cooldowns[current_route_key] = time.monotonic() + block_penalty

                # Check if an alternative route is available right now
                proxy_pool = Config.get_proxy_pool()
                candidate_routes = [p for p in proxy_pool] + [None]
                other_unblocked = [
                    r for r in candidate_routes
                    if (r or "direct") != current_route_key
                    and route_cooldowns.get(r or "direct", 0.0) <= time.monotonic()
                ]

                if other_unblocked:
                    next_route = other_unblocked[0]
                    next_name = get_route_label(next_route)
                    logger.warning(
                        f"🚨 Discord Gateway Rate Limit (429) hit on [{current_route_name}]: {response_text[:180]}. "
                        f"(Discord assigned block time: {block_penalty:.0f}s / {block_penalty/60:.1f}m).\n"
                        f"⚡ INSTANT FAILOVER: Bypassing {block_penalty:.0f}s wait! Switching immediately to alternative route [{next_name}] in 3.0s..."
                    )
                    await asyncio.sleep(3.0)
                    backoff_attempt = 0
                    continue
                else:
                    # All routes blocked
                    wait_time = max(15.0, min(block_penalty, 60.0))
                    logger.warning(
                        f"🚨 Discord Gateway Rate Limit (429) active on [{current_route_name}]: {response_text[:180]}.\n"
                        f"Cooldown remaining: {block_penalty:.0f}s. Pausing for {wait_time:.0f}s before re-evaluating route availability...\n"
                        f"💡 INSTANT UNBLOCK TIP: If hosting on Render, go to Render Settings -> Region -> change to Oregon or Singapore to get an unblocked IP in 10s!"
                    )
                    await asyncio.sleep(wait_time)
                    backoff_attempt = min(backoff_attempt + 1, 6)

            else:
                logger.error(f"Discord HTTP Exception ({e.status}): {e}. Retrying in 15s...")
                await asyncio.sleep(15)
                backoff_attempt = 0

        except discord.LoginFailure as e:
            logger.critical(f"FATAL: Discord Login Failure (Invalid Token): {e}")
            break

        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Bot execution cancelled.")
            break

        except _TRANSIENT_AIOHTTP_ERRORS as e:
            exc_type = type(e).__name__
            wait = _jittered_backoff(backoff_base, backoff_attempt)
            backoff_attempt = min(backoff_attempt + 1, 6)

            # Mark current route as transiently failing for 60s
            route_cooldowns[current_route_key] = time.monotonic() + 60.0

            logger.warning(
                f"Transient network error ({exc_type}) on [{current_route_name}]: {e}. "
                f"Cooling down route for 60s and retrying in {wait:.1f}s..."
            )
            await asyncio.sleep(wait)

        except Exception as e:
            exc_type = type(e).__name__
            exc_str = str(e)
            if "Connection timeout to host" in exc_str or "Cannot connect to host" in exc_str or "TimeoutError" in exc_type:
                wait = _jittered_backoff(backoff_base, backoff_attempt)
                backoff_attempt = min(backoff_attempt + 1, 6)
                route_cooldowns[current_route_key] = time.monotonic() + 60.0
                logger.warning(
                    f"Connection timeout ({exc_type}) on [{current_route_name}]: {exc_str[:180]}. "
                    f"Retrying in {wait:.1f}s..."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"Unexpected {exc_type}: {exc_str[:300]}. Retrying in 15s...",
                    exc_info=e
                )
                backoff_attempt = 0
                await asyncio.sleep(15)

        finally:
            active_bot = None


async def main() -> None:
    """Launch 24/7 Web Server and resilient bot loop."""
    # Register SIGTERM handler for graceful container replacement on Render
    main_task = asyncio.current_task()

    def _sigterm_handler(*_):
        logger.info("Received termination signal (SIGTERM). Initiating graceful shutdown...")
        if main_task and not main_task.done():
            main_task.cancel()

    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _sigterm_handler)
        except Exception:
            pass

    # start Web Server first so Render Port Scan passes immediately (<1s)
    server = HealthServer(bot_getter=get_current_bot)
    await server.start()

    # run bot loop
    try:
        await run_bot_loop()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Bot execution cancelled. Cleaning up services...")
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user.")
