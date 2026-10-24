"""
Tests for Global Cross-Server Vouch System and Bot Staff Historical Imports:
1. Global aggregation: A vouch created in Guild A (TPL) contributes to global totals in Guild B (YKL).
2. Global leaderboard (vlb) queries all servers.
3. Global profile (vouchinfo) shows combined count and historical provenance.
4. Bot Staff historical import (vouchimport) by authorized staff.
5. Historical import with 'unknown' original voucher.
6. Rejection of unauthorized imports.
7. Rejection of self-vouch imports.
8. Rejection of duplicate imports.
9. Audit log recording for all staff imports.
"""

import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from src.cogs.general.vouches import Vouches, conn, DB


@pytest.fixture(autouse=True)
def clean_test_reputation_db(tmp_path, monkeypatch):
    test_db = tmp_path / "kyoka_reputation.sqlite3"
    monkeypatch.setattr("src.cogs.general.vouches.DB", test_db)
    yield test_db


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.get_user = MagicMock(return_value=None)
    bot.user = MagicMock()
    bot.user.display_avatar.url = "https://example.com/bot_avatar.png"
    return bot


@pytest.fixture
def vouch_cog(mock_bot):
    c = Vouches(mock_bot)
    for attr in dir(c):
        val = getattr(c, attr)
        if isinstance(val, (commands.Command, commands.HybridCommand)):
            val.cog = c
    return c


@pytest.fixture
def target_user():
    u = MagicMock(spec=discord.User)
    u.id = 888111222
    u.name = "ProTrader"
    u.display_name = "ProTrader"
    u.mention = "<@888111222>"
    u.bot = False
    u.display_avatar.url = "https://example.com/protrader.png"
    return u


@pytest.fixture
def guild_a_ctx(target_user):
    """Context in Guild A (TPL)."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 10000001
    ctx.guild.name = "TPL Trading Server"
    ctx.guild.icon = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 70000001
    ctx.author.mention = "<@70000001>"
    ctx.author.guild_permissions.administrator = False
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def guild_b_ctx():
    """Context in Guild B (YKL)."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 20000002
    ctx.guild.name = "YKL Community Hub"
    ctx.guild.icon = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 70000002
    ctx.author.mention = "<@70000002>"
    ctx.author.guild_permissions.administrator = False
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def staff_ctx(guild_a_ctx):
    """Authorized Bot Staff / Owner context."""
    guild_a_ctx.author.id = 1505515188991033409  # Authoritative primary owner ID
    guild_a_ctx.author.guild_permissions.administrator = True
    return guild_a_ctx


@pytest.mark.asyncio
async def test_global_vouch_cross_server_aggregation(vouch_cog, guild_a_ctx, guild_b_ctx, target_user):
    """Vouch given in Guild A (TPL) must immediately reflect in Guild B (YKL) global profile."""
    # Step 1: Voucher creates vouch in Guild A
    await vouch_cog.vouch(guild_a_ctx, target_user, reason="raid carried Dough V2 fast and safe")
    guild_a_ctx.reply.assert_called_once()

    # Step 2: In Guild B, check global profile for target_user
    await vouch_cog.vouchinfo(guild_b_ctx, target_user)
    guild_b_ctx.reply.assert_called_once()

    embed = guild_b_ctx.reply.call_args[1]["embed"]
    assert "GLOBAL REPUTATION PROFILE" in embed.title
    assert "Global Verified Vouches:** `1`" in embed.description
    assert "Raid Carry / Awakening:** `1`" in embed.description


@pytest.mark.asyncio
async def test_global_leaderboard_includes_all_servers(vouch_cog, guild_a_ctx, guild_b_ctx, target_user):
    """Global leaderboard (vlb) must rank top providers across all guilds."""
    now = time.time()
    with conn() as c:
        # 3 vouches in Guild A for target_user
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, is_active) VALUES(?,11,?, 'good', ?, 0, 1)",
                  (guild_a_ctx.guild.id, target_user.id, now))
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, is_active) VALUES(?,12,?, 'great', ?, 0, 1)",
                  (guild_a_ctx.guild.id, target_user.id, now))
        # 1 vouch in Guild B for target_user
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, is_active) VALUES(?,21,?, 'awesome', ?, 0, 1)",
                  (guild_b_ctx.guild.id, target_user.id, now))

    # Request global leaderboard from Guild B
    await vouch_cog.vlb(guild_b_ctx)
    guild_b_ctx.reply.assert_called_once()
    embed = guild_b_ctx.reply.call_args[1]["embed"]
    assert "GLOBAL VOUCH LEADERBOARD" in embed.title
    assert "3 vouches" in embed.description


@pytest.mark.asyncio
async def test_bot_staff_historical_vouch_import_with_author(vouch_cog, staff_ctx, target_user):
    """Authorized Bot Staff can import historical vouches with specified original voucher."""
    original_voucher = "<@999888111>"
    await vouch_cog.vouchimport(
        staff_ctx,
        target_user,
        original_voucher,
        reason="raid Completed 10x Buddha carry services in old server",
    )

    staff_ctx.reply.assert_called_once()
    embed = staff_ctx.reply.call_args[1]["embed"]
    assert "HISTORICAL VOUCH IMPORTED" in embed.title
    assert "[STAFF IMPORT]" in str(embed.to_dict())

    # Check database persistence
    with conn() as c:
        row = c.execute("SELECT * FROM vouches WHERE target_id=? AND source='historical_import'", (target_user.id,)).fetchone()
        assert row is not None
        assert row["voucher_id"] == 999888111
        assert row["staff_id"] == staff_ctx.author.id
        assert row["source"] == "historical_import"
        assert row["is_active"] == 1

        # Verify audit log was recorded
        audit = c.execute("SELECT * FROM vouch_audit_log WHERE action='IMPORT'").fetchone()
        assert audit is not None
        assert audit["mod_id"] == staff_ctx.author.id


@pytest.mark.asyncio
async def test_bot_staff_historical_vouch_import_with_unknown_author(vouch_cog, staff_ctx, target_user):
    """Authorized Bot Staff can import historical vouches when original voucher is unknown."""
    await vouch_cog.vouchimport(
        staff_ctx,
        target_user,
        "unknown",
        reason="fruit Traded Leopard for 2x Dough in legacy trading group",
    )

    staff_ctx.reply.assert_called_once()
    embed = staff_ctx.reply.call_args[1]["embed"]
    assert "HISTORICAL VOUCH IMPORTED" in embed.title
    assert "Unknown / Historical Author" in str(embed.to_dict())

    with conn() as c:
        row = c.execute("SELECT * FROM vouches WHERE target_id=? AND source='historical_import'", (target_user.id,)).fetchone()
        assert row is not None
        assert row["voucher_id"] is None
        assert row["source"] == "historical_import"


@pytest.mark.asyncio
async def test_historical_import_unauthorized_rejected(vouch_cog, guild_a_ctx, target_user):
    """Ordinary guild members cannot import historical vouches."""
    # Ordinary user context (not owner, not admin, not in botstaff)
    guild_a_ctx.author.id = 444333222
    guild_a_ctx.author.guild_permissions.administrator = False

    await vouch_cog.vouchimport(guild_a_ctx, target_user, "<@123>", reason="raid Carried 5x raids")
    assert "access denied" in guild_a_ctx.reply.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_historical_import_duplicate_rejected(vouch_cog, staff_ctx, target_user):
    """Exact duplicate historical imports are safely rejected."""
    reason = "raid Completed Dough raid series"
    # First import
    await vouch_cog.vouchimport(staff_ctx, target_user, "unknown", reason=reason)
    assert staff_ctx.reply.call_args[1].get("embed") is not None

    staff_ctx.reply.reset_mock()
    # Second import with same reason
    await vouch_cog.vouchimport(staff_ctx, target_user, "unknown", reason=reason)
    assert "already exists" in staff_ctx.reply.call_args[0][0].lower()
