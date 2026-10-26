"""Live safety check script for the currently running KYOKA 3.0 server at 127.0.0.1:8080."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aiohttp
from dashboard_api.auth import create_session_token
from src.security.owner import OWNER_ID

BASE_URL = "http://127.0.0.1:8080"
NON_OWNER_ID = "999888777666555444"
from dashboard_api.config import DashboardConfig
SECRET_KEY = DashboardConfig.from_env().secret_key

async def main():
    passed = 0
    failed = 0

    async with aiohttp.ClientSession() as session:
        print("\n--- 1. Testing Public HTML Pages ---")
        pages = [
            "/index.html",
            "/features.html",
            "/commands.html",
            "/premium.html",
            "/changelog.html",
            "/support.html",
            "/privacy.html",
            "/terms.html",
            "/dashboard.html",
            "/owner.html",
        ]
        for p in pages:
            async with session.get(f"{BASE_URL}{p}") as resp:
                text = await resp.text()
                if resp.status == 200 and len(text) > 500:
                    print(f"  [PASS] GET {p} -> {resp.status} ({len(text)} bytes)")
                    passed += 1
                else:
                    print(f"  [FAIL] GET {p} -> {resp.status}")
                    failed += 1

        print("\n--- 2. Testing Static CSS/JS & Assets ---")
        assets = [
            "/css/style.css",
            "/css/dashboard.css",
            "/css/owner.css",
            "/js/api.js",
            "/js/app.js",
            "/js/commands.js",
            "/js/dashboard.js",
            "/js/owner.js",
            "/assets/logo.svg",
        ]
        for a in assets:
            async with session.get(f"{BASE_URL}{a}") as resp:
                data = await resp.read()
                if resp.status == 200 and len(data) > 50:
                    print(f"  [PASS] GET {a} -> {resp.status} ({len(data)} bytes)")
                    passed += 1
                else:
                    print(f"  [FAIL] GET {a} -> {resp.status}")
                    failed += 1

        print("\n--- 3. Testing Public API Endpoints ---")
        apis = [
            ("/api/health", 200),
            ("/api/stats", 200),
            ("/api/commands", 200),
        ]
        for ep, expected in apis:
            async with session.get(f"{BASE_URL}{ep}") as resp:
                if resp.status == expected:
                    body = await resp.json()
                    print(f"  [PASS] GET {ep} -> {resp.status}")
                    passed += 1
                else:
                    print(f"  [FAIL] GET {ep} -> {resp.status} (expected {expected})")
                    failed += 1

        print("\n--- 4. Testing Unauthenticated Access Restrictions (Expect 401) ---")
        guarded = [
            "/api/auth/me",
            "/api/guilds",
            "/api/owner/overview",
            "/api/owner/bot-status",
            "/api/owner/guilds",
            "/api/owner/premium",
            "/api/owner/integrations",
            "/api/owner/audit-log",
            "/api/owner/config",
            "/api/owner/diagnostics",
        ]
        for ep in guarded:
            async with session.get(f"{BASE_URL}{ep}") as resp:
                if resp.status == 401:
                    print(f"  [PASS] Unauthenticated GET {ep} -> {resp.status} (Unauthorized)")
                    passed += 1
                else:
                    print(f"  [FAIL] Unauthenticated GET {ep} -> {resp.status} (expected 401)")
                    failed += 1

        print("\n--- 5. Testing Non-Owner Access Restrictions (Expect 403 Forbidden) ---")
        # Build non-owner session
        non_owner_payload = {"user_id": NON_OWNER_ID, "username": "OrdinaryAdmin"}
        non_owner_token = create_session_token(non_owner_payload, SECRET_KEY)
        cookies = {"kyoka_session": non_owner_token}

        owner_endpoints = [
            "/api/owner/overview",
            "/api/owner/bot-status",
            "/api/owner/guilds",
            "/api/owner/premium",
            "/api/owner/integrations",
            "/api/owner/audit-log",
            "/api/owner/config",
            "/api/owner/diagnostics",
        ]
        for ep in owner_endpoints:
            async with session.get(f"{BASE_URL}{ep}", cookies=cookies) as resp:
                if resp.status == 403:
                    print(f"  [PASS] Non-Owner GET {ep} -> {resp.status} (Forbidden as expected)")
                    passed += 1
                else:
                    print(f"  [FAIL] Non-Owner GET {ep} -> {resp.status} (expected 403)")
                    failed += 1

        # Test non-owner POST to grant premium
        async with session.post(
            f"{BASE_URL}/api/owner/premium/grant",
            json={"guild_id": "111222333444", "tier": "pro", "duration_days": 30},
            cookies=cookies
        ) as resp:
            if resp.status == 403:
                print(f"  [PASS] Non-Owner POST /api/owner/premium/grant -> {resp.status} (Forbidden as expected)")
                passed += 1
            else:
                print(f"  [FAIL] Non-Owner POST /api/owner/premium/grant -> {resp.status} (expected 403)")
                failed += 1

        print("\n--- 6. Testing Authoritative Owner Access (Expect 200 OK) ---")
        owner_payload = {"user_id": str(OWNER_ID), "username": "KyokaAuthoritativeOwner"}
        owner_token = create_session_token(owner_payload, SECRET_KEY)
        owner_cookies = {"kyoka_session": owner_token}

        for ep in ["/api/owner/overview", "/api/owner/integrations", "/api/owner/diagnostics", "/api/owner/config"]:
            async with session.get(f"{BASE_URL}{ep}", cookies=owner_cookies) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  [PASS] Authoritative Owner GET {ep} -> {resp.status} OK")
                    passed += 1
                else:
                    print(f"  [FAIL] Authoritative Owner GET {ep} -> {resp.status} (expected 200)")
                    failed += 1

        print("\n--- 7. Testing Cross-Server Permission Checks ---")
        # Ordinary user with access to guild 1001, attempting to access guild 9999
        guild_payload = {
            "user_id": "5555555555",
            "username": "ServerAAdmin",
            "access_token": "mock_test_token",
            "mock_guilds": [{"id": "1001", "name": "Server A", "permissions": "32"}]  # MANAGE_GUILD
        }
        guild_token = create_session_token(guild_payload, SECRET_KEY)
        guild_cookies = {"kyoka_session": guild_token}

        # Try accessing unauthorized Server B (9999)
        async with session.get(f"{BASE_URL}/api/guilds/9999/settings", cookies=guild_cookies) as resp:
            if resp.status == 403:
                print(f"  [PASS] Cross-server access GET /api/guilds/9999/settings -> {resp.status} (Forbidden as expected)")
                passed += 1
            else:
                print(f"  [FAIL] Cross-server access GET /api/guilds/9999/settings -> {resp.status} (expected 403)")
                failed += 1

        # Try accessing authorized Server A (1001)
        async with session.get(f"{BASE_URL}/api/guilds/1001/settings", cookies=guild_cookies) as resp:
            if resp.status == 200:
                print(f"  [PASS] Authorized guild access GET /api/guilds/1001/settings -> {resp.status} OK")
                passed += 1
            else:
                print(f"  [FAIL] Authorized guild access GET /api/guilds/1001/settings -> {resp.status} (expected 200)")
                failed += 1

    print(f"\n==========================================")
    print(f"TOTAL TESTS: {passed + failed} | PASSED: {passed} | FAILED: {failed}")
    print(f"==========================================")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
