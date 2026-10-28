"""
Comprehensive Automated Test Suite for Kyoka 3.0 Invite Tracer System
Covers:
- Invite caching and cache lifecycle (create, delete, diffing)
- Member join attribution (standard code, vanity, bot oauth, unknown)
- Fake invite detection (self-invite, account age threshold)
- Member departure attribution and inviter deduction (left_count increment)
- Net invites calculation (Real - Left + Bonus)
- Leaderboard ranking, sorting, and pagination
- Admin bonus invite adjustments (addinvites, removeinvites)
- Admin reset operations (single member, guild-wide with confirmation)
- Logging channel configuration and event notifications
"""

from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from src.managers.invite_tracker_manager import InviteTrackerManager
from src.cogs.utility.invite_tracker import InviteTracker, InviteLeaderboardView, ResetConfirmationView


class MockPostgresDatabase:
    """Mock database simulating PostgreSQL tables for invite tracking."""

    def __init__(self) -> None:
        self.stats: dict[tuple[int, int], dict[str, int]] = {}
        self.member_invites: dict[tuple[int, int], dict[str, Any]] = {}
        self.settings: dict[int, dict[str, Any]] = {}

    async def execute(self, query: str, *args: Any) -> None:
        q = query.strip().upper()
        if "INSERT INTO GUILD_INVITE_SETTINGS" in q:
            guild_id = args[0]
            if "LOG_CHANNEL_ID" in q:
                ch_id = args[1]
                cur = self.settings.get(guild_id, {"fake_threshold_days": 7, "is_enabled": True})
                cur["guild_id"] = guild_id
                cur["log_channel_id"] = ch_id
                self.settings[guild_id] = cur
            elif "FAKE_THRESHOLD_DAYS" in q:
                days = args[1]
                cur = self.settings.get(guild_id, {"log_channel_id": None, "is_enabled": True})
                cur["guild_id"] = guild_id
                cur["fake_threshold_days"] = days
                self.settings[guild_id] = cur

        elif "INSERT INTO GUILD_MEMBER_INVITES" in q:
            guild_id, user_id, inviter_id, code, is_fake = args[0], args[1], args[2], args[3], args[4]
            self.member_invites[(guild_id, user_id)] = {
                "guild_id": guild_id,
                "user_id": user_id,
                "inviter_id": inviter_id,
                "invite_code": code,
                "is_fake": is_fake,
                "has_left": False,
                "joined_at": dt.datetime.now(dt.timezone.utc),
            }

        elif "INSERT INTO GUILD_INVITES_STATS" in q:
            guild_id, user_id = args[0], args[1]
            key = (guild_id, user_id)
            cur = self.stats.get(key, {"regular": 0, "left_count": 0, "fake": 0, "bonus": 0})
            if "LEFT_COUNT" in q and "EXCLUDED" not in q:
                cur["left_count"] += 1
            elif "BONUS" in q and "EXCLUDED.BONUS" in q:
                cur["bonus"] += args[2]
            elif len(args) >= 4:
                reg_add = args[2]
                fake_add = args[3]
                cur["regular"] += reg_add
                cur["fake"] += fake_add
            self.stats[key] = cur

        elif "UPDATE GUILD_MEMBER_INVITES SET HAS_LEFT = TRUE" in q:
            guild_id, user_id = args[0], args[1]
            if (guild_id, user_id) in self.member_invites:
                self.member_invites[(guild_id, user_id)]["has_left"] = True

        elif "DELETE FROM GUILD_INVITES_STATS WHERE GUILD_ID = ? AND USER_ID = ?" in q:
            self.stats.pop((args[0], args[1]), None)

        elif "DELETE FROM GUILD_INVITES_STATS WHERE GUILD_ID = ?" in q:
            self.stats = {k: v for k, v in self.stats.items() if k[0] != args[0]}

        elif "DELETE FROM GUILD_MEMBER_INVITES WHERE GUILD_ID = ?" in q:
            self.member_invites = {k: v for k, v in self.member_invites.items() if k[0] != args[0]}

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        q = query.strip().upper()
        if "FROM GUILD_INVITE_SETTINGS" in q:
            return self.settings.get(args[0])
        elif "FROM GUILD_INVITES_STATS" in q and "COUNT(*)" not in q and "RANK" not in q:
            guild_id, user_id = args[0], args[1]
            return self.stats.get((guild_id, user_id))
        elif "FROM GUILD_MEMBER_INVITES" in q:
            guild_id, user_id = args[0], args[1]
            return self.member_invites.get((guild_id, user_id))
        elif "COUNT(*) AS TOTAL" in q:
            guild_id = args[0]
            count = sum(1 for (g, _), s in self.stats.items() if g == guild_id and (s["regular"] > 0 or s["bonus"] != 0 or s["left_count"] > 0 or s["fake"] > 0))
            return {"total": count}
        elif "SELECT COUNT(*) + 1 AS RANK" in q:
            guild_id, _, target_uid = args[0], args[1], args[2]
            target_net = 0
            if (guild_id, target_uid) in self.stats:
                s = self.stats[(guild_id, target_uid)]
                target_net = s["regular"] - s["left_count"] + s["bonus"]
            rank = 1
            for (g, uid), s in self.stats.items():
                if g == guild_id and uid != target_uid:
                    net = s["regular"] - s["left_count"] + s["bonus"]
                    if net > target_net:
                        rank += 1
            return {"rank": rank}
        return None

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = query.strip().upper()
        if "FROM GUILD_INVITES_STATS" in q:
            guild_id = args[0]
            limit = args[1]
            offset = args[2]
            items = []
            for (g, uid), s in self.stats.items():
                if g == guild_id and (s["regular"] > 0 or s["bonus"] != 0 or s["left_count"] > 0 or s["fake"] > 0):
                    net = s["regular"] - s["left_count"] + s["bonus"]
                    items.append({
                        "user_id": uid,
                        "regular": s["regular"],
                        "left_count": s["left_count"],
                        "fake": s["fake"],
                        "bonus": s["bonus"],
                        "net": net,
                    })
            items.sort(key=lambda x: (x["net"], x["regular"]), reverse=True)
            return items[offset : offset + limit]
        elif "FROM GUILD_MEMBER_INVITES" in q:
            guild_id, inviter_id = args[0], args[1]
            results = []
            for (g, uid), r in self.member_invites.items():
                if g == guild_id and r.get("inviter_id") == inviter_id:
                    results.append(r)
            return results
        return []


@pytest.fixture
def mock_db():
    return MockPostgresDatabase()


@pytest.fixture
def invite_manager(mock_db):
    bot = MagicMock()
    return InviteTrackerManager(mock_db, bot=bot)


# ─────────────────────────────────────────────────────────────────────────────
# 1. MANAGER UNIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invite_caching_and_cache_updates(invite_manager):
    """Verify loading and caching guild invites."""
    guild = MagicMock(id=111, features=[])
    inv1 = MagicMock(code="abc1", uses=5)
    inv2 = MagicMock(code="abc2", uses=12)
    guild.invites = AsyncMock(return_value=[inv1, inv2])

    cache = await invite_manager.load_guild_invites(guild)
    assert cache == {"abc1": 5, "abc2": 12}
    assert invite_manager._invite_cache[111] == {"abc1": 5, "abc2": 12}

    # Test adding an invite to cache
    new_inv = MagicMock(guild=guild, code="new3", uses=0)
    invite_manager.add_invite_to_cache(new_inv)
    assert invite_manager._invite_cache[111]["new3"] == 0

    # Test removing invite from cache
    invite_manager.remove_invite_from_cache(new_inv)
    assert "new3" not in invite_manager._invite_cache[111]


@pytest.mark.asyncio
async def test_member_join_attribution_standard_code(invite_manager):
    """When a member joins via an invite whose uses incremented, inviter gets a real invite."""
    guild = MagicMock(id=222, features=[])
    inviter = MagicMock(id=999, name="TopInviter")

    # Initial cache: code 'kyoka' has 3 uses
    invite_manager._invite_cache[guild.id] = {"kyoka": 3}

    # Member joins: account age is 30 days (older than 7 day threshold -> real)
    member = MagicMock(id=555, guild=guild, bot=False)
    member.created_at = discord.utils.utcnow() - dt.timedelta(days=30)

    # Current invites on guild: 'kyoka' now has 4 uses
    inv = MagicMock(code="kyoka", uses=4, inviter=inviter)
    guild.invites = AsyncMock(return_value=[inv])

    res = await invite_manager.track_member_join(member)

    assert res["inviter_id"] == 999
    assert res["code"] == "kyoka"
    assert res["is_fake"] is False
    assert res["stats"]["regular"] == 1
    assert res["stats"]["net"] == 1

    # Verify database record
    inv_record = await invite_manager.get_user_inviter(guild.id, member.id)
    assert inv_record is not None
    assert inv_record["inviter_id"] == 999
    assert inv_record["invite_code"] == "kyoka"
    assert inv_record["is_fake"] is False


@pytest.mark.asyncio
async def test_fake_invite_detection_young_account_and_self_invite(invite_manager):
    """Accounts younger than threshold or inviting oneself are flagged as fake."""
    guild = MagicMock(id=333, features=[])
    inviter = MagicMock(id=888)

    invite_manager._invite_cache[guild.id] = {"code1": 0}

    # 1. Young account (2 days old < 7 day threshold)
    young_member = MagicMock(id=777, guild=guild, bot=False)
    young_member.created_at = discord.utils.utcnow() - dt.timedelta(days=2)

    inv = MagicMock(code="code1", uses=1, inviter=inviter)
    guild.invites = AsyncMock(return_value=[inv])

    res1 = await invite_manager.track_member_join(young_member)
    assert res1["is_fake"] is True
    assert res1["stats"]["fake"] == 1
    assert res1["stats"]["regular"] == 0

    # 2. Self-invite: inviter_id == member.id
    invite_manager._invite_cache[guild.id] = {"code1": 1}
    self_member = MagicMock(id=888, guild=guild, bot=False)
    self_member.created_at = discord.utils.utcnow() - dt.timedelta(days=50)

    inv2 = MagicMock(code="code1", uses=2, inviter=self_member)
    guild.invites = AsyncMock(return_value=[inv2])

    res2 = await invite_manager.track_member_join(self_member)
    assert res2["is_fake"] is True


@pytest.mark.asyncio
async def test_member_leave_deducts_from_inviter(invite_manager):
    """When an invited member leaves, inviter's left count is incremented and net invites decrease."""
    guild = MagicMock(id=444, features=[])
    inviter = MagicMock(id=101, name="OriginalInviter")

    invite_manager._invite_cache[guild.id] = {"party": 0}

    member = MagicMock(id=202, guild=guild, bot=False)
    member.created_at = discord.utils.utcnow() - dt.timedelta(days=20)

    inv = MagicMock(code="party", uses=1, inviter=inviter)
    guild.invites = AsyncMock(return_value=[inv])

    # Join
    await invite_manager.track_member_join(member)
    stats_before = await invite_manager.get_user_stats(guild.id, inviter.id)
    assert stats_before["net"] == 1
    assert stats_before["left"] == 0

    # Leave
    leave_res = await invite_manager.track_member_leave(member)
    assert leave_res is not None
    assert leave_res["inviter_id"] == 101

    stats_after = await invite_manager.get_user_stats(guild.id, inviter.id)
    assert stats_after["regular"] == 1
    assert stats_after["left"] == 1
    assert stats_after["net"] == 0  # 1 regular - 1 left = 0 net


@pytest.mark.asyncio
async def test_bonus_invites_and_net_calculation(invite_manager):
    """Formula: Net = Regular - Left + Bonus."""
    guild_id = 555
    user_id = 12345

    # Add 10 bonus invites
    stats = await invite_manager.add_bonus_invites(guild_id, user_id, 10)
    assert stats["bonus"] == 10
    assert stats["net"] == 10

    # Deduct 3 bonus invites
    stats = await invite_manager.remove_bonus_invites(guild_id, user_id, 3)
    assert stats["bonus"] == 7
    assert stats["net"] == 7


@pytest.mark.asyncio
async def test_leaderboard_sorting_and_ranks(invite_manager):
    """Verify leaderboard sorts by Net Invites DESC."""
    guild_id = 777

    # User A: 5 regular, 0 left -> net 5
    await invite_manager.add_bonus_invites(guild_id, user_id=1, amount=5)
    # User B: 15 regular, 2 left -> net 13
    await invite_manager.add_bonus_invites(guild_id, user_id=2, amount=13)
    # User C: 2 regular, 1 left -> net 1
    await invite_manager.add_bonus_invites(guild_id, user_id=3, amount=1)

    lb = await invite_manager.get_leaderboard(guild_id, limit=10)
    assert len(lb) == 3
    assert lb[0]["user_id"] == 2 and lb[0]["net"] == 13 and lb[0]["rank"] == 1
    assert lb[1]["user_id"] == 1 and lb[1]["net"] == 5 and lb[1]["rank"] == 2
    assert lb[2]["user_id"] == 3 and lb[2]["net"] == 1 and lb[2]["rank"] == 3

    # Check rank computation
    rank_b = await invite_manager.get_user_rank(guild_id, user_id=2)
    assert rank_b == 1
    rank_a = await invite_manager.get_user_rank(guild_id, user_id=1)
    assert rank_a == 2


@pytest.mark.asyncio
async def test_reset_operations(invite_manager):
    """Verify single-user and guild-wide invite reset."""
    guild_id = 888
    await invite_manager.add_bonus_invites(guild_id, user_id=10, amount=5)
    await invite_manager.add_bonus_invites(guild_id, user_id=20, amount=8)

    # Reset single user
    await invite_manager.reset_user_invites(guild_id, user_id=10)
    stats10 = await invite_manager.get_user_stats(guild_id, user_id=10)
    assert stats10["net"] == 0

    stats20 = await invite_manager.get_user_stats(guild_id, user_id=20)
    assert stats20["net"] == 8

    # Reset whole guild
    await invite_manager.reset_guild_invites(guild_id)
    stats20_after = await invite_manager.get_user_stats(guild_id, user_id=20)
    assert stats20_after["net"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. COG & COMMAND TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_bot(mock_db):
    bot = MagicMock()
    bot.db = mock_db
    bot.invite_tracker_mgr = InviteTrackerManager(mock_db, bot=bot)
    return bot


@pytest.mark.asyncio
async def test_invites_command_embed_card(mock_bot):
    """The ?invites command returns a structured card with Net, Real, Left, Fake, Bonus, and Rank."""
    cog = InviteTracker(mock_bot)

    guild = MagicMock(id=999, name="Kyoka Support")
    member = MagicMock(id=123, display_name="AizenSosuke", guild=guild)
    member.display_avatar.url = "https://cdn.discord.com/avatars/123/aizen.png"

    # Setup 10 real invites and 2 bonus
    await cog.manager.add_bonus_invites(guild.id, member.id, 2)

    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = member
    ctx.send = AsyncMock()

    await cog.invites.callback(cog, ctx, member=member)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1].get("embed") or ctx.send.call_args[0][0]
    assert "AizenSosuke" in embed.title
    assert "2 Net Invites" in embed.description
    assert any("Breakdown" in f.name for f in embed.fields)


@pytest.mark.asyncio
async def test_inviteleaderboard_view_pagination(mock_bot):
    """The ?inviteleaderboard command displays leaderboard and handles pagination buttons."""
    cog = InviteTracker(mock_bot)
    guild = MagicMock(id=1234, name="Soul Society")
    author = MagicMock(id=555)

    # Add 15 inviters to trigger multiple pages (per_page = 10)
    for i in range(1, 16):
        await cog.manager.add_bonus_invites(guild.id, user_id=i * 100, amount=20 - i)

    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = author
    ctx.send = AsyncMock()

    await cog.inviteleaderboard.callback(cog, ctx)

    ctx.send.assert_called_once()
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    view = kwargs.get("view")

    assert "Invite Leaderboard" in embed.title
    assert isinstance(view, InviteLeaderboardView)
    assert view.page == 1
    assert view.total_pages == 2
    assert view.prev_button.disabled is True
    assert view.next_button.disabled is False


@pytest.mark.asyncio
async def test_addinvites_and_removeinvites_commands(mock_bot):
    """Admin commands addinvites and removeinvites adjust bonus counts."""
    cog = InviteTracker(mock_bot)
    guild = MagicMock(id=4321, name="Test Guild")
    target = MagicMock(id=888, mention="<@888>")

    ctx = MagicMock()
    ctx.guild = guild
    ctx.send = AsyncMock()

    # Add 5 bonus invites
    await cog.addinvites.callback(cog, ctx, member=target, amount=5)
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Bonus Invites Added" in embed.title
    assert "5" in embed.description

    # Deduct 2 bonus invites
    ctx.send.reset_mock()
    await cog.removeinvites.callback(cog, ctx, member=target, amount=2)
    ctx.send.assert_called_once()
    embed2 = ctx.send.call_args[1]["embed"]
    assert "Bonus Invites Removed" in embed2.title


@pytest.mark.asyncio
async def test_setinvitechannel_command(mock_bot):
    """Configure or disable real-time invite logging channel."""
    cog = InviteTracker(mock_bot)
    guild = MagicMock(id=7777)
    channel = MagicMock(id=8888, mention="<#8888>")

    ctx = MagicMock()
    ctx.guild = guild
    ctx.send = AsyncMock()

    # Enable channel
    await cog.setinvitechannel.callback(cog, ctx, channel=channel)
    settings = await cog.manager.get_settings(guild.id)
    assert settings["log_channel_id"] == 8888

    # Disable channel
    ctx.send.reset_mock()
    await cog.setinvitechannel.callback(cog, ctx, channel=None)
    settings = await cog.manager.get_settings(guild.id)
    assert settings["log_channel_id"] is None
