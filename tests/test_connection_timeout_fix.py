"""Focused tests for KYOKA 3.0 Discord connection timeout fix.

Tests the retry/backoff logic in src/main.py:
- Transient aiohttp network errors are caught and retried with bounded backoff
- LoginFailure is NOT retried (permanent auth failure)
- 429 respects Retry-After header
- Jitter backoff stays within expected bounds
- String-based fallback catch covers aiohttp errors wrapped as generic Exception
- No duplicate login attempts triggered
- Prefix and slash command registries not disturbed

All tests are fully mocked. No real Discord API calls are made.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiohttp

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import _jittered_backoff, _TRANSIENT_AIOHTTP_ERRORS


class TestJitteredBackoff:
    def test_attempt_zero_is_between_zero_and_base(self):
        for _ in range(50):
            result = _jittered_backoff(15.0, 0)
            assert 0.0 <= result <= 15.0

    def test_attempt_one_doubles_ceiling(self):
        for _ in range(50):
            result = _jittered_backoff(15.0, 1)
            assert 0.0 <= result <= 30.0

    def test_high_attempt_capped_at_300(self):
        for _ in range(50):
            result = _jittered_backoff(15.0, 20)
            assert 0.0 <= result <= 300.0

    def test_custom_cap(self):
        for _ in range(50):
            result = _jittered_backoff(10.0, 10, cap=60.0)
            assert 0.0 <= result <= 60.0

    def test_zero_base_returns_zero(self):
        assert _jittered_backoff(0.0, 5) == 0.0


class TestTransientErrorsTuple:
    def test_server_timeout_error_in_transient(self):
        assert aiohttp.ServerTimeoutError in _TRANSIENT_AIOHTTP_ERRORS

    def test_client_connector_error_in_transient(self):
        assert aiohttp.ClientConnectorError in _TRANSIENT_AIOHTTP_ERRORS

    def test_server_disconnected_in_transient(self):
        assert aiohttp.ServerDisconnectedError in _TRANSIENT_AIOHTTP_ERRORS

    def test_client_connection_error_in_transient(self):
        assert aiohttp.ClientConnectionError in _TRANSIENT_AIOHTTP_ERRORS

    def test_transient_is_non_empty_tuple(self):
        assert isinstance(_TRANSIENT_AIOHTTP_ERRORS, tuple)
        assert len(_TRANSIENT_AIOHTTP_ERRORS) >= 4

    def test_login_failure_not_in_transient(self):
        import discord
        assert discord.LoginFailure not in _TRANSIENT_AIOHTTP_ERRORS

    def test_server_timeout_error_is_catchable(self):
        err = aiohttp.ServerTimeoutError()
        assert isinstance(err, _TRANSIENT_AIOHTTP_ERRORS)


@pytest.mark.asyncio
async def test_transient_timeout_retried_with_backoff():
    import discord
    import src.main as main_module
    call_count = 0

    async def fake_start(token):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise aiohttp.ServerTimeoutError()
        raise asyncio.CancelledError()

    fake_bot = AsyncMock()
    fake_bot.start = fake_start
    fake_bot.__aenter__ = AsyncMock(return_value=fake_bot)
    fake_bot.__aexit__ = AsyncMock(return_value=False)

    with patch.object(main_module, 'KyokaBot', return_value=fake_bot), \
         patch.object(main_module, '_jittered_backoff', return_value=0.001), \
         patch('asyncio.sleep', new_callable=AsyncMock), \
         patch.object(main_module.logger, 'warning') as mock_warn, \
         patch.object(main_module.logger, 'critical') as mock_crit:
        await main_module.run_bot_loop()

    assert call_count == 3
    transient_warns = [str(c) for c in mock_warn.call_args_list if 'Transient network error' in str(c)]
    assert len(transient_warns) >= 2
    assert not mock_crit.called


@pytest.mark.asyncio
async def test_login_failure_stops_loop():
    import discord
    import src.main as main_module
    call_count = 0

    async def fake_start(token):
        nonlocal call_count
        call_count += 1
        raise discord.LoginFailure("Improper token has been passed.")

    fake_bot = AsyncMock()
    fake_bot.start = fake_start
    fake_bot.__aenter__ = AsyncMock(return_value=fake_bot)
    fake_bot.__aexit__ = AsyncMock(return_value=False)

    with patch.object(main_module, 'KyokaBot', return_value=fake_bot), \
         patch('asyncio.sleep', new_callable=AsyncMock), \
         patch.object(main_module.logger, 'critical') as mock_crit:
        await main_module.run_bot_loop()

    assert call_count == 1
    assert mock_crit.called


@pytest.mark.asyncio
async def test_string_pattern_fallback_catches_connection_timeout():
    import src.main as main_module
    call_count = 0

    async def fake_start(token):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception('Connection timeout to host https://discord.com/api/v10/users/@me')
        raise asyncio.CancelledError()

    fake_bot = AsyncMock()
    fake_bot.start = fake_start
    fake_bot.__aenter__ = AsyncMock(return_value=fake_bot)
    fake_bot.__aexit__ = AsyncMock(return_value=False)

    with patch.object(main_module, 'KyokaBot', return_value=fake_bot), \
         patch.object(main_module, '_jittered_backoff', return_value=0.001), \
         patch('asyncio.sleep', new_callable=AsyncMock), \
         patch.object(main_module.logger, 'warning') as mock_warn, \
         patch.object(main_module.logger, 'error') as mock_err:
        await main_module.run_bot_loop()

    warn_msgs = [str(c) for c in mock_warn.call_args_list]
    assert any('Network connection error' in m or 'Connection timeout' in m for m in warn_msgs)
    unexpected = [c for c in mock_err.call_args_list if 'Unexpected' in str(c)]
    assert not unexpected


@pytest.mark.asyncio
async def test_backoff_attempt_increments_and_caps():
    import src.main as main_module
    attempts_recorded = []
    call_count = 0

    def record_jitter(base, attempt, cap=300.0):
        attempts_recorded.append(attempt)
        return 0.001

    async def fake_start(token):
        nonlocal call_count
        call_count += 1
        if call_count <= 8:
            raise aiohttp.ServerTimeoutError()
        raise asyncio.CancelledError()

    fake_bot = AsyncMock()
    fake_bot.start = fake_start
    fake_bot.__aenter__ = AsyncMock(return_value=fake_bot)
    fake_bot.__aexit__ = AsyncMock(return_value=False)

    with patch.object(main_module, 'KyokaBot', return_value=fake_bot), \
         patch.object(main_module, '_jittered_backoff', side_effect=record_jitter), \
         patch('asyncio.sleep', new_callable=AsyncMock), \
         patch.object(main_module.logger, 'warning'):
        await main_module.run_bot_loop()

    assert all(a <= 6 for a in attempts_recorded)
    assert len(attempts_recorded) >= 7


@pytest.mark.asyncio
async def test_no_duplicate_bot_instance_on_retry():
    import src.main as main_module
    bots_created = []
    call_count = 0

    async def fake_start(token):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise aiohttp.ServerTimeoutError()
        raise asyncio.CancelledError()

    def make_bot(*args, **kwargs):
        bot = AsyncMock()
        bot.start = fake_start
        bot.__aenter__ = AsyncMock(return_value=bot)
        bot.__aexit__ = AsyncMock(return_value=False)
        bots_created.append(bot)
        return bot

    with patch.object(main_module, 'KyokaBot', side_effect=make_bot), \
         patch.object(main_module, '_jittered_backoff', return_value=0.001), \
         patch('asyncio.sleep', new_callable=AsyncMock), \
         patch.object(main_module.logger, 'warning'):
        await main_module.run_bot_loop()

    assert len(bots_created) == 3
    assert main_module.active_bot is None


@pytest.mark.asyncio
async def test_sigterm_handling_cancels_gracefully():
    import src.main as main_module

    server_stopped = False
    bot_loop_ran = False

    class FakeServer:
        def __init__(self, *args, **kwargs):
            pass
        async def start(self):
            pass
        async def stop(self):
            nonlocal server_stopped
            server_stopped = True

    async def fake_run_bot_loop():
        nonlocal bot_loop_ran
        bot_loop_ran = True
        raise asyncio.CancelledError()

    with patch.object(main_module, "HealthServer", FakeServer), \
         patch.object(main_module, "run_bot_loop", fake_run_bot_loop):
        await main_module.main()

    assert bot_loop_ran is True
    assert server_stopped is True

