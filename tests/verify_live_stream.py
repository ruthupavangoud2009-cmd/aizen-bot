import asyncio
import aiohttp
import json

async def full_integration_verification():
    base_url = "https://kyoka-lavalink.onrender.com"
    ws_url = "wss://kyoka-lavalink.onrender.com/v4/websocket"
    password = "onlyforkyoka"

    print("=" * 65)
    print("KYOKA MUSIC SYSTEM - FULL END-TO-END VERIFICATION")
    print("=" * 65)

    async with aiohttp.ClientSession() as session:
        # Step 1: Nginx & Java Health
        print("[1] Checking /healthz...")
        async with session.get(f"{base_url}/healthz") as r:
            assert r.status == 200, f"Healthz failed with {r.status}"
            body = await r.text()
            print("    PASS: /healthz returned 200 OK ->", body.strip())

        # Step 2: Lavalink REST /v4/info
        print("[2] Checking /v4/info...")
        async with session.get(f"{base_url}/v4/info", headers={"Authorization": password}) as r:
            assert r.status == 200, f"/v4/info failed with {r.status}"
            info = await r.json()
            plugins = [p.get("name") for p in info.get("plugins", [])]
            print(f"    PASS: Lavalink {info.get('version', {}).get('semver')} online, JVM {info.get('jvm')}")
            print(f"    Loaded Plugins: {plugins}")
            assert "youtube-plugin" in plugins, "youtube-plugin missing"
            assert "lavasrc-plugin" in plugins, "lavasrc-plugin missing"

        # Step 3: WebSocket Handshake & Session Creation
        print("[3] Establishing Wavelink WebSocket Session (/v4/websocket)...")
        headers = {
            "Authorization": password,
            "User-Id": "1562505487214321714",
            "Client-Name": "Wavelink/3.5.2"
        }
        async with session.ws_connect(ws_url, headers=headers) as ws:
            msg = await asyncio.wait_for(ws.receive(), timeout=10.0)
            payload = json.loads(msg.data)
            assert payload.get("op") == "ready", f"Expected ready op, got {payload}"
            session_id = payload.get("sessionId")
            print(f"    PASS: WebSocket connected! op=ready, sessionId={session_id}")

            # Step 4: Search & Load YouTube Track
            print("[4] Testing YouTube Search & Audio Track Resolution via Lavalink...")
            search_url = f"{base_url}/v4/loadtracks?identifier=ytsearch:Never+Gonna+Give+You+Up"
            async with session.get(search_url, headers={"Authorization": password}) as r_search:
                assert r_search.status == 200, f"Search failed with {r_search.status}"
                search_data = await r_search.json()
                tracks = search_data.get("data", [])
                assert len(tracks) > 0, "No tracks returned"
                top = tracks[0]
                info = top.get("info", {})
                print(f"    PASS: Resolved '{info.get('title')}' by {info.get('author')}")
                print(f"          Duration: {info.get('length')}ms | Stream Source: {info.get('sourceName')}")
                print(f"          Track Encoded Hash: {top.get('encoded')[:32]}...")

    print("=" * 65)
    print("ALL 4 END-TO-END PHASES VERIFIED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(full_integration_verification())
