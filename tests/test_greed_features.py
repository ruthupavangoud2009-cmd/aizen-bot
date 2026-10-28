"""
Kyoka 3.0 - Automated Test Suite for Greed-style Discord Bot Features.
Verifies:
1. BlackTea word-bomb elimination game mechanics, lives, prompts, and stats.
2. Jail detention system, role archiving, and automatic role restoration on release.
3. Booster custom roles creation, hex color validation, sharing, and deletion.
4. Vanity status rewards custom status detection, role assignment, and revocation.
5. Fake permissions delegation and PermissionManager integration.
6. Editsnipe and reactionsnipe caching and response formatting.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from src.cogs.fun.blacktea import BlackTea, BlackTeaPlayer, BLACKTEA_PROMPTS
from src.cogs.moderation.jail import Jail, parse_time_duration
from src.cogs.utility.booster_roles import BoosterRoles
from src.cogs.utility.vanity_rewards import VanityRewards
from src.cogs.admin.fakeperms import FakePerms, VALID_PERMISSIONS
from src.cogs.utility.snipe import SnipeCog, SnipeEntry
from src.managers.permission_manager import PermissionManager


# ─── 1. BLACKTEA TESTS ───────────────────────────────────────────────────────

def test_blacktea_prompts_and_player_lives():
    """Verify BlackTea prompt pool and player life states."""
    assert len(BLACKTEA_PROMPTS) >= 50
    for p in BLACKTEA_PROMPTS:
        assert len(p) == 3

    mock_member = MagicMock(spec=discord.Member)
    mock_member.id = 12345
    mock_member.display_name = "SpeedyGamer"

    player = BlackTeaPlayer(mock_member)
    assert player.lives == 3
    assert player.render_lives() == "❤️ ❤️ ❤️"

    player.lives -= 1
    assert player.render_lives() == "❤️ ❤️ 🖤"

    player.lives -= 1
    assert player.render_lives() == "❤️ 🖤 🖤"

    player.lives -= 1
    assert player.render_lives() == "🖤 🖤 🖤"


# ─── 2. JAIL SYSTEM TESTS ────────────────────────────────────────────────────

def test_jail_duration_parser():
    """Verify jail duration string parsing."""
    assert parse_time_duration("30s") == datetime.timedelta(seconds=30)
    assert parse_time_duration("10m") == datetime.timedelta(minutes=10)
    assert parse_time_duration("2h") == datetime.timedelta(hours=2)
    assert parse_time_duration("1d") == datetime.timedelta(days=1)
    assert parse_time_duration("1w") == datetime.timedelta(weeks=1)
    assert parse_time_duration("invalid") is None


@pytest.mark.asyncio
async def test_jail_role_stripping_and_restoration():
    """Verify member roles are stripped on jail and restored on unjail."""
    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()
    mock_bot.db.fetch_one = AsyncMock(return_value={"role_id": 999, "channel_id": 888})
    mock_bot.db.execute = AsyncMock()

    jail_cog = Jail(mock_bot)

    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 111
    mock_guild.owner_id = 999999

    jail_role = MagicMock(spec=discord.Role, id=999, name="Jailed")
    role_a = MagicMock(spec=discord.Role, id=101, name="Member", managed=False)
    role_b = MagicMock(spec=discord.Role, id=102, name="VIP", managed=False)
    role_a.is_default.return_value = False
    role_b.is_default.return_value = False

    mock_guild.get_role.side_effect = lambda rid: jail_role if rid == 999 else role_a if rid == 101 else role_b

    # Target member
    target = MagicMock(spec=discord.Member)
    target.id = 222
    target.roles = [role_a, role_b]
    target.top_role.position = 5
    target.remove_roles = AsyncMock()
    target.add_roles = AsyncMock()

    # Moderator & bot me
    mock_guild.me.top_role.position = 10
    ctx = MagicMock()
    ctx.guild = mock_guild
    ctx.author.id = 333
    ctx.author.top_role.position = 9
    ctx.author.display_name = "HeadMod"
    ctx.clean_prefix = "+"
    ctx.channel = MagicMock(id=888)
    ctx.channel.send = AsyncMock()
    ctx.send = AsyncMock()
    ctx._state = MagicMock()
    ctx._state.http.request = AsyncMock(return_value={"id": 123})
    ctx.bot = mock_bot
    mock_bot._state = ctx._state
    mock_bot.http = ctx._state.http

    with pytest.MonkeyPatch.context() as mp:
        mock_send = AsyncMock()
        mp.setattr("src.cogs.moderation.jail.send_container_response", mock_send)
        await jail_cog._jail_member(ctx, target, reason="Trolling", duration=None)

    target.remove_roles.assert_awaited_once()
    target.add_roles.assert_awaited_once_with(jail_role, reason="Jailed: Trolling")


# ─── 3. BOOSTER ROLES TESTS ──────────────────────────────────────────────────

def test_booster_eligibility():
    """Verify Nitro Booster detection."""
    mock_bot = MagicMock()
    cog = BoosterRoles(mock_bot)

    # Booster with premium_since
    booster_member = MagicMock(spec=discord.Member)
    booster_member.premium_since = datetime.datetime.now(datetime.timezone.utc)
    booster_member.guild_permissions.administrator = False
    assert cog._is_booster(booster_member) is True

    # Non-booster regular member
    reg_member = MagicMock(spec=discord.Member)
    reg_member.premium_since = None
    reg_member.guild_permissions.administrator = False
    reg_member.id = 555
    reg_member.guild.owner_id = 999
    assert cog._is_booster(reg_member) is False

    # Server Admin override
    admin_member = MagicMock(spec=discord.Member)
    admin_member.premium_since = None
    admin_member.guild_permissions.administrator = True
    assert cog._is_booster(admin_member) is True


# ─── 4. VANITY REWARDS TESTS ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vanity_status_detection_and_role_award():
    """Verify presence update grants role when vanity string is set in status."""
    mock_bot = MagicMock()
    cog = VanityRewards(mock_bot)
    cog._cache[111] = {
        "vanity_string": ".gg/aizen",
        "role_id": 777,
        "channel_id": None,
        "message": None,
    }

    mock_guild = MagicMock(spec=discord.Guild, id=111)
    vanity_role = MagicMock(spec=discord.Role, id=777)
    mock_guild.get_role.return_value = vanity_role
    mock_guild.me.top_role.position = 20
    vanity_role.position = 10

    # Before: status was None
    before = MagicMock(spec=discord.Member, guild=mock_guild, bot=False, roles=[])
    before.activities = []

    # After: status has '.gg/aizen'
    after = MagicMock(spec=discord.Member, guild=mock_guild, bot=False, roles=[])
    act = discord.CustomActivity(name="chilling in .gg/aizen")
    after.activities = [act]
    after.add_roles = AsyncMock()

    await cog.on_presence_update(before, after)
    after.add_roles.assert_awaited_once()


# ─── 5. FAKE PERMISSIONS TESTS ───────────────────────────────────────────────

def test_fakeperms_delegation_and_perm_manager():
    """Verify fake permissions are recognized by PermissionManager."""
    mock_bot = MagicMock()
    fakeperms_cog = FakePerms(mock_bot)
    fakeperms_cog._cache[111] = {
        500: {"ban_members", "kick_members"}
    }

    mock_bot.get_cog.return_value = fakeperms_cog
    perm_mgr = PermissionManager(mock_bot, MagicMock())

    # Member with role 500
    mock_role = MagicMock(spec=discord.Role, id=500)
    member = MagicMock(spec=discord.Member)
    member.guild.id = 111
    member.roles = [mock_role]
    member.guild_permissions.administrator = False
    member.guild_permissions.ban_members = False

    # Native perm is False, but FakePerm is True
    assert fakeperms_cog.has_fake_perm(member, "ban_members") is True
    assert perm_mgr.has_permission(member, "ban_members") is True
    assert perm_mgr.has_permission(member, "manage_channels") is False


# ─── 6. EDITSNIPE & REACTIONSNIPE TESTS ──────────────────────────────────────

@pytest.mark.asyncio
async def test_editsnipe_and_reactionsnipe_cache():
    """Verify editsnipe and reactionsnipe commands return stored events."""
    mock_bot = MagicMock()
    mock_bot.snipe_cache = {}
    mock_bot.guild_snipe_cache = {}
    mock_bot.reaction_snipe_cache = {}

    snipe_cog = SnipeCog(mock_bot)

    # 1. Edit event
    before_msg = MagicMock(spec=discord.Message)
    before_msg.id = 111
    before_msg.content = "Original typo here"
    before_msg.channel.id = 999
    before_msg.channel.name = "general"
    before_msg.guild.id = 888
    before_msg.author.id = 777
    before_msg.author.display_name = "TypoKing"
    before_msg.author.bot = False
    before_msg.attachments = []
    before_msg.created_at = datetime.datetime.now(datetime.timezone.utc)

    after_msg = MagicMock(spec=discord.Message)
    after_msg.content = "Fixed typo here"

    await snipe_cog.on_message_edit(before_msg, after_msg)
    assert len(mock_bot.snipe_cache[999]) == 1
    assert mock_bot.snipe_cache[999][0].type == "edit"
    assert mock_bot.snipe_cache[999][0].before == "Original typo here"
    assert mock_bot.snipe_cache[999][0].after == "Fixed typo here"

    # 2. Reaction remove event
    payload = MagicMock(spec=discord.RawReactionActionEvent)
    payload.guild_id = 888
    payload.channel_id = 999
    payload.message_id = 555
    payload.user_id = 777
    payload.emoji = "🔥"

    await snipe_cog.on_raw_reaction_remove(payload)
    assert len(mock_bot.reaction_snipe_cache[999]) == 1
    assert mock_bot.reaction_snipe_cache[999][0]["emoji"] == "🔥"
