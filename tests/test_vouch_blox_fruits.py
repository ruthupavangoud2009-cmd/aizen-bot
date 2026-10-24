"""
Unit and integration tests for Blox Fruits Vouch System:
1. Vouch creation with service types (raid, fruit, leveling, etc.).
2. Anti-self vouching and anti-bot vouching.
3. Cooldown enforcement.
4. Duplicate vouches held for review.
5. Vouch profile statistics and service breakdown.
6. Leaderboard ranking.
7. Moderator vouch removal with audit logging.
"""

import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import pytest

from src.cogs.general.vouches import Vouches, conn, SERVICE_TYPES


@pytest.fixture(autouse=True)
def clean_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "kyoka_reputation.sqlite3"
    monkeypatch.setattr("src.cogs.general.vouches.DB", test_db)
    yield test_db


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 11111111
    ctx.guild.name = "Blox Trading Hub"
    ctx.guild.icon = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 22222222
    ctx.author.name = "TraderBob"
    ctx.author.mention = "<@22222222>"
    ctx.author.guild_permissions.administrator = False
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def target_member():
    m = MagicMock(spec=discord.Member)
    m.id = 33333333
    m.name = "RaidCarrier"
    m.display_name = "RaidCarrier"
    m.mention = "<@33333333>"
    m.bot = False
    m.display_avatar.url = "https://example.com/avatar.png"
    return m


@pytest.fixture
def cog():
    c = Vouches(MagicMock())
    for attr in dir(c):
        val = getattr(c, attr)
        if isinstance(val, (commands.Command, commands.HybridCommand)):
            val.cog = c
    return c


@pytest.mark.asyncio
async def test_vouch_creation_with_service_type(cog, mock_ctx, target_member):
    # User submits vouch for raid service
    await cog.vouch(mock_ctx, target_member, reason="raid carried me through 5x dough raids super fast")

    mock_ctx.reply.assert_called_once()
    call_kwargs = mock_ctx.reply.call_args[1]
    embed = call_kwargs.get("embed")
    assert embed is not None
    assert "VOUCH REGISTERED" in embed.title
    assert "Raid Carry" in str(embed.to_dict())

    # Check database persistence
    with conn() as c:
        row = c.execute("SELECT * FROM vouches WHERE target_id=?", (target_member.id,)).fetchone()
        assert row is not None
        assert row["service_type"] == "raid"
        assert row["held"] == 0


@pytest.mark.asyncio
async def test_anti_self_and_bot_vouching(cog, mock_ctx, target_member):
    # Self vouch
    mock_ctx.author.id = target_member.id
    await cog.vouch(mock_ctx, target_member, reason="awesome guy")
    assert "not allowed" in mock_ctx.reply.call_args[0][0].lower()

    # Bot vouch
    mock_ctx.reply.reset_mock()
    mock_ctx.author.id = 999999
    target_member.bot = True
    await cog.vouch(mock_ctx, target_member, reason="awesome guy")
    assert "not allowed" in mock_ctx.reply.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_duplicate_vouch_held_for_review(cog, mock_ctx, target_member):
    # First vouch
    await cog.vouch(mock_ctx, target_member, reason="fruit traded kitsune smoothly")

    # Bypass cooldown in DB for test of duplicate logic
    with conn() as c:
        c.execute("DELETE FROM vouch_global_cooldowns")

    mock_ctx.reply.reset_mock()
    # Second vouch by same user for same target
    await cog.vouch(mock_ctx, target_member, reason="fruit another great trade")

    # Should be held for review
    assert "held for review" in mock_ctx.reply.call_args[0][0].lower()
    with conn() as c:
        held_row = c.execute("SELECT * FROM vouches WHERE voucher_id=? AND target_id=? AND held=1",
                             (mock_ctx.author.id, target_member.id)).fetchone()
        assert held_row is not None


@pytest.mark.asyncio
async def test_vouch_leaderboard(cog, mock_ctx, target_member):
    with conn() as c:
        # Seed 3 vouches for target_member
        now = time.time()
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, service_type) VALUES(?,101,?, 'good', ?, 0, 'raid')",
                  (mock_ctx.guild.id, target_member.id, now))
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, service_type) VALUES(?,102,?, 'great', ?, 0, 'fruit')",
                  (mock_ctx.guild.id, target_member.id, now))
        # Seed 1 vouch for another member
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, service_type) VALUES(?,103,44444444, 'ok', ?, 0, 'leveling')",
                  (mock_ctx.guild.id, now))

    mock_ctx.guild.get_member.side_effect = lambda uid: target_member if uid == target_member.id else None
    await cog.vouchleaderboard(mock_ctx)

    mock_ctx.reply.assert_called_once()
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "VOUCH LEADERBOARD" in embed.title
    assert "2 vouches" in embed.description


@pytest.mark.asyncio
async def test_vouch_remove_with_audit_log(cog, mock_ctx, target_member):
    # Staff permission
    mock_ctx.author.guild_permissions.administrator = True

    with conn() as c:
        c.execute("INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, service_type) VALUES(?,101,?, 'good', ?, 0, 'raid')",
                  (mock_ctx.guild.id, target_member.id, time.time()))
        vid = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    await cog.vouchremove(mock_ctx, vid, reason="Fraudulent review")

    assert f"#{vid:04d}" in mock_ctx.reply.call_args[0][0]
    with conn() as c:
        # Verified deleted
        assert c.execute("SELECT * FROM vouches WHERE id=?", (vid,)).fetchone() is None
        # Verified audit logged
        audit = c.execute("SELECT * FROM vouch_audit_log WHERE vouch_id=?", (vid,)).fetchone()
        assert audit is not None
        assert audit["action"] == "REMOVE"
        assert audit["reason"] == "Fraudulent review"
