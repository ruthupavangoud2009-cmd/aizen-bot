from __future__ import annotations

import asyncio
import logging
import os
import random
import signal
import sys
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
    Cloudflare / Discord 429 rate limits, and gateway disconnects."""
    global active_bot

    try:
        Config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        return

    # Backoff state — reset on successful connect+ready, increased on failure
    backoff_base = 15.0     # seconds base for transient-error backoff
    backoff_attempt = 0     # how many consecutive transient failures
    use_proxy = bool(Config.DISCORD_PROXY)

    while True:
        try:
            active_proxy = Config.DISCORD_PROXY if use_proxy else None
            bot = KyokaBot(proxy=active_proxy)
            active_bot = bot
            route_desc = "via proxy" if active_proxy else "direct connection"
            logger.info(f"Connecting {Config.BOT_NAME} in [{Config.ENVIRONMENT.upper()}] mode to Discord Gateway ({route_desc})...")
            async with bot:
                await bot.start(Config.TOKEN)
            # Clean exit: reset backoff
            backoff_attempt = 0
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

                # Detect Cloudflare IP ban (HTML page returned instead of JSON)
                is_cloudflare_block = (
                    "<!doctype" in response_text.lower()
                    or "cloudflare" in response_text.lower()
                    or "access denied" in response_text.lower()
                )

                if is_cloudflare_block:
                    wait_time = 120.0  # 2 minutes cooldown
                    logger.warning(
                        f"Cloudflare IP block detected on Render shared IP. "
                        f"Cooling down for {wait_time:.0f}s before reconnecting. "
                        f"(TIP: Change Render service Region to Singapore, Ohio, or Oregon in Settings to get an unblocked IP instantly!)"
                    )
                else:
                    wait_time = max(retry_after if retry_after else backoff_base, 45.0)
                    logger.warning(
                        f"Discord Gateway Rate Limit (429) active: {response_text}. "
                        f"Cooling down for {wait_time:.0f}s before reconnecting to allow Discord rate-limit window to reset..."
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
            # These are transient network failures (proxy timeout, DNS, TLS, etc.).
            # Apply bounded exponential backoff with full jitter and route failover.
            exc_type = type(e).__name__
            wait = _jittered_backoff(backoff_base, backoff_attempt)
            backoff_attempt = min(backoff_attempt + 1, 6)
            if Config.DISCORD_PROXY:
                use_proxy = not use_proxy
                next_route = "proxy" if use_proxy else "direct connection"
                logger.warning(
                    f"Transient network error ({exc_type}): {e}. "
                    f"Retrying in {wait:.1f}s (attempt {backoff_attempt}, switching next attempt to {next_route})..."
                )
            else:
                logger.warning(
                    f"Transient network error ({exc_type}): {e}. "
                    f"Retrying in {wait:.1f}s (attempt {backoff_attempt}, direct connection)..."
                )
            await asyncio.sleep(wait)

        except Exception as e:
            # Unknown / unexpected error — log type and message for diagnosis, retry with backoff.
            exc_type = type(e).__name__
            exc_str = str(e)
            if "Connection timeout to host" in exc_str or "Cannot connect to host" in exc_str or "TimeoutError" in exc_type:
                wait = _jittered_backoff(backoff_base, backoff_attempt)
                backoff_attempt = min(backoff_attempt + 1, 6)
                if Config.DISCORD_PROXY:
                    use_proxy = not use_proxy
                    next_route = "proxy" if use_proxy else "direct connection"
                    logger.warning(
                        f"Network connection timeout ({exc_type}): {exc_str[:200]}. "
                        f"Retrying in {wait:.1f}s (attempt {backoff_attempt}, switching next attempt to {next_route})..."
                    )
                else:
                    logger.warning(
                        f"Network connection timeout ({exc_type}): {exc_str[:200]}. "
                        f"Retrying in {wait:.1f}s (attempt {backoff_attempt}, direct connection)..."
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
