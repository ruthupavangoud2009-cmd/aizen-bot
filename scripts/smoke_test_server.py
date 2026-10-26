"""Smoke test script for KYOKA 3.0 Web Dashboard API and Static Frontend.

Starts the server asynchronously, executes HTTP requests against all static pages,
CSS/JS assets, and API routes, verifies responses and security headers, then shuts down cleanly.
"""
import asyncio
import os
import sys

# Ensure root dir is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aiohttp
from aiohttp import web
from dashboard_api.config import DashboardConfig
from dashboard_api.server import create_app
from dashboard_api.database import MockDatabaseAdapter


async def run_smoke_test():
    port = 8099
    host = "127.0.0.1"

    config = DashboardConfig(
        client_id="123456789012345678",
        client_secret="mock_client_secret_xyz",
        bot_token="mock_bot_token_abc",
        redirect_uri=f"http://{host}:{port}/api/auth/callback",
        bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
        support_server_url="https://discord.gg/7q4tn6dA6V",
        secret_key="smoke_test_secret_key_32_characters_long",
        is_production=False,
        database_url="",
        host=host,
        port=port
    )

    db = MockDatabaseAdapter()
    app = create_app(config=config, db=db, serve_website=True)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[SMOKE] Server listening on http://{host}:{port}")

    passed = 0
    failed = 0
    base_url = f"http://{host}:{port}"

    async with aiohttp.ClientSession() as session:
        # 1. Test Static Pages
        pages = [
            "/index.html",
            "/features.html",
            "/commands.html",
            "/support.html",
            "/dashboard.html",
        ]
        for page in pages:
            url = f"{base_url}{page}"
            try:
                async with session.get(url) as resp:
                    if resp.status == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                        text = await resp.text()
                        print(f"  [PASS] GET {page} -> Status: {resp.status}, Size: {len(text)} bytes")
                        passed += 1
                    else:
                        print(f"  [FAIL] GET {page} -> Unexpected Status: {resp.status}")
                        failed += 1
            except Exception as e:
                print(f"  [FAIL] GET {page} -> Error: {e}")
                failed += 1

        # 2. Test CSS and JS Assets
        assets = [
            "/css/style.css",
            "/css/dashboard.css",
            "/js/api.js",
            "/js/app.js",
            "/js/commands.js",
            "/js/dashboard.js",
            "/assets/logo.svg",
        ]
        for asset in assets:
            url = f"{base_url}{asset}"
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        print(f"  [PASS] GET {asset} -> Status: {resp.status}, Size: {len(content)} bytes")
                        passed += 1
                    else:
                        print(f"  [FAIL] GET {asset} -> Unexpected Status: {resp.status}")
                        failed += 1
            except Exception as e:
                print(f"  [FAIL] GET {asset} -> Error: {e}")
                failed += 1

        # 3. Test API Health Endpoint
        try:
            async with session.get(f"{base_url}/api/health") as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("status") == "healthy":
                    print(f"  [PASS] GET /api/health -> Status: {resp.status}, Data: {data}")
                    passed += 1
                else:
                    print(f"  [FAIL] GET /api/health -> Unexpected Status: {resp.status}, Data: {data}")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] GET /api/health -> Error: {e}")
            failed += 1

        # 4. Test API Stats Endpoint
        try:
            async with session.get(f"{base_url}/api/stats") as resp:
                data = await resp.json()
                if resp.status == 200 and "commands_available" in data:
                    print(f"  [PASS] GET /api/stats -> Status: {resp.status}, Data: {data}")
                    passed += 1
                else:
                    print(f"  [FAIL] GET /api/stats -> Unexpected Status: {resp.status}")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] GET /api/stats -> Error: {e}")
            failed += 1

        # 5. Test API Commands Endpoint
        try:
            async with session.get(f"{base_url}/api/commands") as resp:
                data = await resp.json()
                cmds = data.get("commands", [])
                if resp.status == 200 and len(cmds) >= 50:
                    print(f"  [PASS] GET /api/commands -> Status: {resp.status}, Count: {len(cmds)} commands")
                    passed += 1
                else:
                    print(f"  [FAIL] GET /api/commands -> Unexpected Count: {len(cmds)}")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] GET /api/commands -> Error: {e}")
            failed += 1

        # 6. Test Unauthenticated Protected Endpoints (Expect 401)
        for ep in ["/api/auth/me", "/api/guilds", "/api/guilds/1001/settings"]:
            try:
                async with session.get(f"{base_url}{ep}") as resp:
                    if resp.status == 401:
                        print(f"  [PASS] GET {ep} without auth -> Status: {resp.status} (Unauthorized as expected)")
                        passed += 1
                    else:
                        print(f"  [FAIL] GET {ep} without auth -> Unexpected Status: {resp.status}")
                        failed += 1
            except Exception as e:
                print(f"  [FAIL] GET {ep} -> Error: {e}")
                failed += 1

        # 7. Test OAuth Login URL Generation (JSON format)
        try:
            async with session.get(f"{base_url}/api/auth/login?format=json") as resp:
                data = await resp.json()
                if resp.status == 200 and "auth_url" in data and "state" in data:
                    print(f"  [PASS] GET /api/auth/login?format=json -> Status: {resp.status}, State generated")
                    passed += 1
                else:
                    print(f"  [FAIL] GET /api/auth/login?format=json -> Unexpected: {data}")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] GET /api/auth/login -> Error: {e}")
            failed += 1

        # 8. Test Security Headers
        try:
            async with session.get(f"{base_url}/api/health") as resp:
                headers = resp.headers
                nosniff = headers.get("X-Content-Type-Options") == "nosniff"
                deny = headers.get("X-Frame-Options") == "DENY"
                csp = "default-src" in headers.get("Content-Security-Policy", "")
                if nosniff and deny and csp:
                    print(f"  [PASS] Security Headers Check -> nosniff={nosniff}, DENY={deny}, CSP present")
                    passed += 1
                else:
                    print(f"  [FAIL] Security Headers Check missing expected headers: {headers}")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] Security Headers Check -> Error: {e}")
            failed += 1

    await runner.cleanup()
    print(f"\n[SMOKE RESULTS] Total tests: {passed + failed} | Passed: {passed} | Failed: {failed}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
