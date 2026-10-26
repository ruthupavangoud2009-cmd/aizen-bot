"""Unit tests for Discord OAuth2 state validation, HMAC sessions, and CSRF protection."""
import time
import pytest
from dashboard_api.auth import (
    create_oauth_state,
    verify_oauth_state,
    create_session_token,
    verify_session_token,
)

SECRET_KEY = "test_super_secret_dashboard_key_32_chars_long"


def test_oauth_state_generation_and_validation():
    state = create_oauth_state(SECRET_KEY)
    assert state is not None
    assert len(state.split(".")) == 3

    # Valid verification
    assert verify_oauth_state(state, SECRET_KEY, max_age_seconds=600) is True


def test_oauth_state_tampered_fails():
    state = create_oauth_state(SECRET_KEY)
    parts = state.split(".")
    # Tamper with nonce
    tampered_state = f"tampered_nonce.{parts[1]}.{parts[2]}"
    assert verify_oauth_state(tampered_state, SECRET_KEY) is False

    # Tamper with signature
    tampered_sig = f"{parts[0]}.{parts[1]}.bad_signature_value"
    assert verify_oauth_state(tampered_sig, SECRET_KEY) is False


def test_oauth_state_expired_fails():
    state = create_oauth_state(SECRET_KEY)
    # Check with 0-second max_age after sleeping 0.05s
    time.sleep(0.05)
    assert verify_oauth_state(state, SECRET_KEY, max_age_seconds=0) is False


def test_session_token_creation_and_verification():
    user_data = {
        "user_id": "123456789012345678",
        "username": "TestUser",
        "discriminator": "0001",
        "avatar": "abcdef123456",
        "access_token": "valid_discord_token"
    }

    token = create_session_token(user_data, SECRET_KEY)
    assert token is not None

    decoded = verify_session_token(token, SECRET_KEY, max_age_seconds=3600)
    assert decoded is not None
    assert decoded["user_id"] == "123456789012345678"
    assert decoded["username"] == "TestUser"
    assert decoded["access_token"] == "valid_discord_token"


def test_session_token_tampered_fails():
    user_data = {"user_id": "111", "username": "Admin"}
    token = create_session_token(user_data, SECRET_KEY)
    b64_part, sig = token.split(".")

    # Tamper with signature
    tampered_sig_token = f"{b64_part}.invalid_sig"
    assert verify_session_token(tampered_sig_token, SECRET_KEY) is None

    # Wrong secret key
    assert verify_session_token(token, "different_secret_key") is None


def test_session_token_expired_fails():
    user_data = {"user_id": "111", "username": "Admin"}
    token = create_session_token(user_data, SECRET_KEY)
    time.sleep(0.05)
    assert verify_session_token(token, SECRET_KEY, max_age_seconds=0) is None


def test_missing_oauth_configuration_detection():
    """Verify that get_missing_oauth_vars accurately flags missing settings without leaking values."""
    from dashboard_api.config import DashboardConfig

    # Completely unconfigured
    cfg_empty = DashboardConfig(
        client_id="",
        client_secret="",
        redirect_uri="",
        bot_token="",
        secret_key="secret",
    )
    missing = cfg_empty.get_missing_oauth_vars()
    assert "DISCORD_CLIENT_ID" in missing
    assert "DISCORD_CLIENT_SECRET" in missing
    assert cfg_empty.is_oauth_configured is False

    # Fully configured
    cfg_full = DashboardConfig(
        client_id="1474805799988756673",
        client_secret="mock_secret_value",
        redirect_uri="http://localhost:8080/api/auth/callback",
        bot_token="mock_token",
        secret_key="secret",
    )
    assert cfg_full.get_missing_oauth_vars() == []
    assert cfg_full.is_oauth_configured is True


def test_canonical_variable_resolution_order(monkeypatch):
    """Verify canonical DISCORD_* env vars take precedence over legacy fallback names."""
    import os
    from dashboard_api.config import DashboardConfig

    monkeypatch.setenv("DISCORD_CLIENT_ID", "canonical_client_id_999")
    monkeypatch.setenv("CLIENT_ID", "legacy_client_id_111")
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "canonical_secret_888")
    monkeypatch.setenv("CLIENT_SECRET", "legacy_secret_222")

    cfg = DashboardConfig.from_env()
    assert cfg.client_id == "canonical_client_id_999"
    assert cfg.client_secret == "canonical_secret_888"


@pytest.mark.asyncio
async def test_oauth_login_missing_config_returns_safe_error():
    """When OAuth credentials are missing, /api/auth/login must return safe error identifying missing variable."""
    from aiohttp import web
    from dashboard_api.config import DashboardConfig
    from dashboard_api.database import MockDatabaseAdapter
    from dashboard_api.server import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = DashboardConfig(
        client_id="",  # Missing client_id
        client_secret="",
        redirect_uri="http://localhost:8080/api/auth/callback",
        bot_token="token",
        secret_key=SECRET_KEY,
    )
    app = create_app(config=cfg, db=MockDatabaseAdapter(), serve_website=False)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        resp = await client.get("/api/auth/login", headers={"Accept": "application/json"})
        assert resp.status == 500
        data = await resp.json()
        assert "Discord OAuth2 is not configured" in data["error"]
        assert "DISCORD_CLIENT_ID" in data["missing_variables"]
        # Ensure secret value is not in response
        assert "mock_secret" not in str(data)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_oauth_login_configured_redirects_to_discord():
    """When configured, /api/auth/login must redirect to discord.com/oauth2/authorize with state."""
    from aiohttp import web
    from dashboard_api.config import DashboardConfig
    from dashboard_api.database import MockDatabaseAdapter
    from dashboard_api.server import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = DashboardConfig(
        client_id="1474805799988756673",
        client_secret="test_secret_123",
        redirect_uri="http://localhost:8080/api/auth/callback",
        bot_token="token",
        secret_key=SECRET_KEY,
    )
    app = create_app(config=cfg, db=MockDatabaseAdapter(), serve_website=False)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        resp = await client.get("/api/auth/login", allow_redirects=False)
        assert resp.status == 302
        location = resp.headers.get("Location")
        assert location is not None
        assert "oauth2/authorize" in location
        assert "client_id=1474805799988756673" in location
        assert "state=" in location
        assert "response_type=code" in location
        assert "kyoka_oauth_state=" in resp.headers.get("Set-Cookie", "")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_oauth_callback_mismatched_state_redirects_to_pages_dashboard():
    """Mismatched state must redirect to https://aizen-bot.pages.dev/dashboard.html?error=invalid_state, NEVER onrender."""
    from dashboard_api.config import DashboardConfig
    from dashboard_api.database import MockDatabaseAdapter
    from dashboard_api.server import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = DashboardConfig(
        client_id="1562505487214321714",
        client_secret="test_secret_123",
        redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
        bot_token="token",
        secret_key=SECRET_KEY,
        is_production=True,
    )
    app = create_app(config=cfg, db=MockDatabaseAdapter(), serve_website=False)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # Pass a bogus state and mismatched cookie
        client.session.cookie_jar.update_cookies({"kyoka_oauth_state": "legitimate_cookie_state_value"})
        resp = await client.get("/api/auth/callback?code=fake_code&state=forged_state_parameter", allow_redirects=False)
        assert resp.status == 302
        location = resp.headers.get("Location")
        assert location is not None
        assert location.startswith("https://aizen-bot.pages.dev/dashboard.html?error=invalid_state")
        assert "onrender.com" not in location
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_oauth_callback_missing_state_cookie_and_bad_state():
    """Missing state cookie and invalid state HMAC must safely fail with invalid_state on aizen-bot.pages.dev."""
    from dashboard_api.config import DashboardConfig
    from dashboard_api.database import MockDatabaseAdapter
    from dashboard_api.server import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = DashboardConfig(
        client_id="1562505487214321714",
        client_secret="test_secret_123",
        redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
        bot_token="token",
        secret_key=SECRET_KEY,
        is_production=True,
    )
    app = create_app(config=cfg, db=MockDatabaseAdapter(), serve_website=False)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        resp = await client.get("/api/auth/callback?code=fake_code&state=non_existent_state", allow_redirects=False)
        assert resp.status == 302
        location = resp.headers.get("Location")
        assert location is not None
        assert "https://aizen-bot.pages.dev/dashboard.html?error=invalid_state" in location
        assert "onrender.com" not in location
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_oauth_successful_flow_redirects_to_pages_dashboard(monkeypatch):
    """Successful OAuth authorization must redirect to https://aizen-bot.pages.dev/dashboard.html#token=..."""
    from unittest.mock import AsyncMock
    from dashboard_api.config import DashboardConfig
    from dashboard_api.database import MockDatabaseAdapter
    from dashboard_api.server import create_app
    from aiohttp.test_utils import TestClient, TestServer
    import dashboard_api.routes.auth_routes as auth_mod

    cfg = DashboardConfig(
        client_id="1562505487214321714",
        client_secret="test_secret_123",
        redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
        bot_token="token",
        secret_key=SECRET_KEY,
        is_production=True,
    )

    # Mock exchange_discord_code and fetch_discord_user
    mock_exchange = AsyncMock(return_value={"access_token": "mock_access_token_abc"})
    mock_fetch_user = AsyncMock(return_value={
        "id": "1505515188991033409",
        "username": "AizenLord",
        "discriminator": "0001",
        "avatar": "mock_avatar_hash"
    })
    monkeypatch.setattr(auth_mod, "exchange_discord_code", mock_exchange)
    monkeypatch.setattr(auth_mod, "fetch_discord_user", mock_fetch_user)

    app = create_app(config=cfg, db=MockDatabaseAdapter(), serve_website=False)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        valid_state = "valid_secure_state_token_12345"
        client.session.cookie_jar.update_cookies({"kyoka_oauth_state": valid_state})
        resp = await client.get(f"/api/auth/callback?code=good_code&state={valid_state}", allow_redirects=False)
        assert resp.status == 302
        location = resp.headers.get("Location")
        assert location is not None
        assert location.startswith("https://aizen-bot.pages.dev/dashboard.html#token=")
        assert "onrender.com" not in location
        assert cfg.session_cookie_name in resp.headers.get("Set-Cookie", "")
    finally:
        await client.close()


def test_production_primary_frontend_url_never_returns_render():
    """Verify primary_frontend_url always returns https://aizen-bot.pages.dev in production."""
    from dashboard_api.config import DashboardConfig

    cfg = DashboardConfig(
        client_id="1562505487214321714",
        client_secret="test_secret",
        redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
        bot_token="token",
        secret_key="secret",
        is_production=True,
        frontend_origin="https://kyokasugisetsu.onrender.com,https://aizen-bot.pages.dev",
    )
    assert cfg.primary_frontend_url == "https://aizen-bot.pages.dev"
    assert "onrender.com" not in cfg.primary_frontend_url


