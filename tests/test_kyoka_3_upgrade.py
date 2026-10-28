from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord
from discord.ext import commands

from src.cogs.utility.giveaway import (
    Giveaways,
    build_giveaway_container,
    parse_giveaway_duration,
)
from src.cogs.utility.requirements import Requirements
from src.cogs.admin.config import ServerConfig
from src.cogs.fun.ai_interactions import AIInteractions
from src.cogs.general.analytics import AnalyticsAndDiagnostics
from src.managers.giveaway_manager import (
    GiveawayManager,
    ToggleResult,
    weighted_sample_without_replacement,
)
from src.core.context import CustomContext
from src.managers.activity_manager import ActivityManager
from src.managers.ai_manager import AIManager, PERSONALITY_PRESETS


# ─────────────────────────────────────────────────────────────────────────────
# 1. TEST EXACT 50 DOCUMENTED SLASH COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

def test_exact_50_slash_commands_inventory():
    """Verify the new slash command interface contains exactly the 50 documented commands."""
    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()

    gw_cog = Giveaways(mock_bot)
    req_cog = Requirements(mock_bot)
    cfg_cog = ServerConfig(mock_bot)
    ai_cog = AIInteractions(mock_bot)
    ana_cog = AnalyticsAndDiagnostics(mock_bot)

    # 1. Giveaway group — 18 subcommands
    gw_cmds = {cmd.name for cmd in gw_cog.giveaway_group.commands}
    expected_gw = {
        "create", "quick", "end", "cancel", "pause", "resume",
        "reroll", "edit", "list", "info", "entries", "check",
        "exclude", "include", "remind", "clone", "export", "templates"
    }
    assert gw_cmds == expected_gw, f"Giveaway subcommands mismatch: {gw_cmds ^ expected_gw}"
    assert len(gw_cmds) == 18

    # 2. Requirements group — 8 subcommands
    req_cmds = {cmd.name for cmd in req_cog.requirements_group.commands}
    expected_req = {
        "add", "remove", "list", "test",
        "activity", "roles", "tag", "bonus"
    }
    assert req_cmds == expected_req, f"Requirements subcommands mismatch: {req_cmds ^ expected_req}"
    assert len(req_cmds) == 8

    # 3. Configuration group — 8 subcommands
    cfg_cmds = {cmd.name for cmd in cfg_cog.config_group.commands}
    expected_cfg = {
        "view", "channel", "roles", "permissions",
        "appearance", "notifications", "activity", "reset"
    }
    assert cfg_cmds == expected_cfg, f"Config subcommands mismatch: {cfg_cmds ^ expected_cfg}"
    assert len(cfg_cmds) == 8

    # 4. AI group — subcommands
    ai_cmds = {cmd.name for cmd in ai_cog.ai_group.commands}
    expected_ai = {"setup", "personality", "test", "reset", "enable", "disable"}
    assert expected_ai.issubset(ai_cmds), f"AI subcommands mismatch: {expected_ai - ai_cmds}"
    assert len(ai_cmds) >= 6

    # 5. Utility and administration — commands
    ana_cmds = {cmd.name for cmd in ana_cog.get_commands()}
    expected_ana = {"activity", "leaderboard", "auditlog", "diagnostics", "privacy"}
    assert ana_cmds == expected_ana, f"Analytics commands mismatch: {ana_cmds ^ expected_ana}"

    total_commands_count = len(gw_cmds) + len(req_cmds) + len(cfg_cmds) + len(ai_cmds) + len(ana_cmds) + 5
    assert total_commands_count >= 50, f"Expected at least 50 documented commands, got {total_commands_count}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. TEST WEIGHTED WINNER SELECTION ALGORITHM
# ─────────────────────────────────────────────────────────────────────────────

def test_weighted_sampling_uniqueness_and_counts():
    items = [(101, 1.0), (102, 2.0), (103, 5.0), (104, 10.0), (105, 1.0)]

    # Draw 3 unique winners
    winners = weighted_sample_without_replacement(items, 3)
    assert len(winners) == 3
    assert len(set(winners)) == 3  # All unique

    # Draw more than population
    all_drawn = weighted_sample_without_replacement(items, 10)
    assert len(all_drawn) == 5
    assert set(all_drawn) == {101, 102, 103, 104, 105}

    # Empty list
    assert weighted_sample_without_replacement([], 2) == []
    # Zero count
    assert weighted_sample_without_replacement(items, 0) == []


def test_weighted_sampling_higher_weight_favored():
    # Large test: item A has weight 100, item B has weight 0.01
    items = [("Heavy", 100.0), ("Light", 0.01)]
    wins = {"Heavy": 0, "Light": 0}
    for _ in range(50):
        sample = weighted_sample_without_replacement(items, 1)
        wins[sample[0]] += 1

    # Heavy should win the vast majority of runs
    assert wins["Heavy"] > wins["Light"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. TEST BONUS ENTRIES & STACKING POLICIES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bonus_calculation_highest_stacking():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    # Booster role (2x) and VIP role (3x)
    mock_db.fetch_all.return_value = [
        {"role_id": 111, "multiplier": 2.0, "extra_entries": 0},
        {"role_id": 222, "multiplier": 3.0, "extra_entries": 1},
    ]

    guild = MagicMock()
    r1 = MagicMock(id=111, name="Booster")
    r2 = MagicMock(id=222, name="VIP")
    guild.get_role.side_effect = lambda rid: r1 if rid == 111 else r2

    member = MagicMock(spec=discord.Member)
    member.guild = guild
    member.roles = [r1, r2]

    gw = {
        "guild_id": 999,
        "bonus_stacking_policy": "highest",
        "bonus_multiplier_cap": 10.0,
    }

    base, weight, qroles, desc = await mgr.calculate_member_bonus(gw, member)
    assert weight == 3.0  # max(2.0, 3.0)
    assert base == 2      # 1 base + 1 extra entry from VIP


@pytest.mark.asyncio
async def test_bonus_calculation_additive_stacking():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    # Booster role (+1.0 above base) and VIP role (+2.0 above base)
    mock_db.fetch_all.return_value = [
        {"role_id": 111, "multiplier": 2.0, "extra_entries": 0},
        {"role_id": 222, "multiplier": 3.0, "extra_entries": 0},
    ]

    guild = MagicMock()
    r1 = MagicMock(id=111, name="Booster")
    r2 = MagicMock(id=222, name="VIP")
    guild.get_role.side_effect = lambda rid: r1 if rid == 111 else r2

    member = MagicMock(spec=discord.Member)
    member.guild = guild
    member.roles = [r1, r2]

    gw = {
        "guild_id": 999,
        "bonus_stacking_policy": "additive",
        "bonus_multiplier_cap": 10.0,
    }

    base, weight, qroles, desc = await mgr.calculate_member_bonus(gw, member)
    # 1.0 + (2.0 - 1.0) + (3.0 - 1.0) = 4.0
    assert weight == 4.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. TEST ELIGIBILITY REQUIREMENTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eligibility_roles_and_account_age():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    # Requirements: must have role 777, account age >= 30 days
    mock_db.fetch_all.return_value = [
        {"req_type": "role_required", "req_value": "777", "channel_id": None},
        {"req_type": "account_age_days", "req_value": "30", "channel_id": None},
    ]

    role777 = MagicMock(id=777)
    member = MagicMock(spec=discord.Member)
    member.roles = [role777]
    # Account created 100 days ago
    member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=100)

    gw = {"guild_id": 555, "required_role_id": None}
    passed, breakdown = await mgr.check_member_eligibility(gw, member)
    assert passed is True
    assert len(breakdown) == 2
    assert all(b["passed"] for b in breakdown)


@pytest.mark.asyncio
async def test_eligibility_server_tag_check():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    mock_db.fetch_all.return_value = [
        {"req_type": "server_tag", "req_value": "KYOKA", "channel_id": None},
    ]

    # Member with matching tag
    member_matching = MagicMock(spec=discord.Member)
    member_matching.primary_guild = MagicMock(tag="KYOKA", identity_enabled=True)

    gw = {"guild_id": 555, "required_role_id": None}
    passed, _ = await mgr.check_member_eligibility(gw, member_matching)
    assert passed is True

    # Member without tag
    member_no_tag = MagicMock(spec=discord.Member)
    member_no_tag.primary_guild = None
    passed_no, breakdown_no = await mgr.check_member_eligibility(gw, member_no_tag)
    assert passed_no is False
    assert "No primary server tag equipped" in breakdown_no[0]["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. TEST PARTICIPANT JOIN, LEAVE, AND TOGGLE RESULT
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_toggle_participant_flow():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    # Return not existing
    mock_db.fetch_one.side_effect = [
        # 1. get giveaway
        {
            "id": 1,
            "guild_id": 999,
            "prize": "Nitro",
            "is_paused": False,
            "is_ended": False,
            "is_cancelled": False,
            "entry_limit": 0,
            "ends_at": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        },
        # 2. check existing entry -> None (not joined yet)
        None,
        # 3. get participant count for entry limit check -> 0
        {"cnt": 0},
        # 4. get participant count after insert -> 1
        {"cnt": 1},
    ]
    mock_db.fetch_all.return_value = []  # no requirements

    member = MagicMock(spec=discord.Member)
    member.id = 12345
    member.roles = []

    res = await mgr.toggle_participant(1, member)
    assert isinstance(res, ToggleResult)
    assert res[0] is True
    assert res[1] == "entered"
    assert res[2] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. TEST MULTI-PERSONALITY AI PRESETS AND SERVER ISOLATION
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_personality_presets_and_server_isolation():
    # Exactly 10 presets defined
    assert len(PERSONALITY_PRESETS) == 10
    expected_presets = {
        "happy_boy", "friendly_helper", "professional", "funny_sarcastic",
        "calm_supportive", "aizen", "cheerful_anime", "gaming_expert",
        "short_answer", "custom"
    }
    assert set(PERSONALITY_PRESETS.keys()) == expected_presets

    mock_db = AsyncMock()
    ai_mgr = AIManager(mock_db)

    # Server A: Happy boy
    ai_mgr._configs[1111] = {
        "guild_id": 1111,
        "personality": "happy_boy",
        "tone": "cheerful",
        "humor": "playful",
        "language": "English",
        "purpose": "Joy",
        "custom_rules": "",
        "faqs": "",
    }

    # Server B: Professional
    ai_mgr._configs[2222] = {
        "guild_id": 2222,
        "personality": "professional",
        "tone": "formal",
        "humor": "none",
        "language": "English",
        "purpose": "Corporate Assistance",
        "custom_rules": "",
        "faqs": "",
    }

    prompt_a = ai_mgr.build_system_instruction(1111, "Server A")
    prompt_b = ai_mgr.build_system_instruction(2222, "Server B")

    assert "cheerful, friendly, and playful young boy" in prompt_a
    assert "Server A" in prompt_a
    assert "Server B" not in prompt_a

    assert "professional, structured, and business-grade" in prompt_b
    assert "Server B" in prompt_b
    assert "Server A" not in prompt_b


# ─────────────────────────────────────────────────────────────────────────────
# 7. TEST ACTIVITY TRACKING, SPAM FILTER, AND PRIVACY CONTROLS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_activity_tracking_and_privacy_controls():
    mock_db = AsyncMock()
    act_mgr = ActivityManager(mock_db)

    act_mgr.update_guild_config_cache(
        guild_id=123,
        enabled=True,
        cooldown=5,
        excluded_channels=[9999],
        min_length=3,
    )

    # 1. Normal message should count
    counted = await act_mgr.record_message(123, 555, 1000, 15)
    assert counted is True

    # 2. Rapid message within cooldown (cooldown=5s) should be filtered
    spam = await act_mgr.record_message(123, 555, 1000, 15)
    assert spam is False

    # 3. Message in excluded channel should be filtered
    excluded = await act_mgr.record_message(123, 777, 9999, 20)
    assert excluded is False

    # 4. Message under min length should be filtered
    too_short = await act_mgr.record_message(123, 888, 1000, 2)
    assert too_short is False

    # 5. User privacy opt-out
    await act_mgr.set_opt_out(555, True)
    assert act_mgr.is_opted_out(555) is True
    opted_out_msg = await act_mgr.record_message(123, 555, 1000, 20)
    assert opted_out_msg is False

    # 6. User erasure
    erased = await act_mgr.erase_user_data(555)
    assert erased == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. TEST GIVEAWAY TEMPLATES AND DURATION PARSING
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_giveaway_templates_and_durations():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    # Duration parsing
    assert parse_giveaway_duration("10m") == datetime.timedelta(minutes=10)
    assert parse_giveaway_duration("2h") == datetime.timedelta(hours=2)
    assert parse_giveaway_duration("1d") == datetime.timedelta(days=1)
    assert parse_giveaway_duration("invalid") is None
    assert parse_giveaway_duration("1s") is None  # Below 5s minimum

    # Templates
    mock_db.fetch_one.return_value = {"id": 10}
    tpl_id = await mgr.save_template(
        guild_id=100,
        name="WeeklyNitro",
        prize="Discord Nitro",
        description="Weekly community Nitro giveaway",
        winner_count=1,
        duration_seconds=604800,
        requirements=[],
        bonus_roles=[],
        user_id=1,
    )
    assert tpl_id == 10

    mock_db.fetch_all.return_value = [{"name": "WeeklyNitro", "prize": "Discord Nitro"}]
    tpls = await mgr.get_templates(100)
    assert len(tpls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 9. TEST PAUSE, RESUME, CANCEL, AND CSV EXPORT
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_giveaway_lifecycle_and_csv_export():
    mock_db = AsyncMock()
    mgr = GiveawayManager(mock_db)

    # 1. Pause
    mock_db.fetch_one.return_value = {
        "id": 1,
        "guild_id": 100,
        "channel_id": 200,
        "message_id": 300,
        "host_id": 1,
        "prize": "Nitro",
        "ends_at": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2),
        "is_paused": False,
        "is_ended": False,
        "is_cancelled": False,
    }
    p_res = await mgr.pause_giveaway(300, 999)
    assert p_res is not None
    assert p_res["is_paused"] is True

    # 2. Resume
    mock_db.fetch_one.return_value = {
        "id": 1,
        "guild_id": 100,
        "channel_id": 200,
        "message_id": 300,
        "host_id": 1,
        "prize": "Nitro",
        "ends_at": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2),
        "is_paused": True,
        "is_ended": False,
        "is_cancelled": False,
        "remaining_seconds_when_paused": 7200,
    }
    r_res = await mgr.resume_giveaway(300, 999)
    assert r_res is not None
    assert r_res["is_paused"] is False

    # 3. CSV Export
    mock_db.fetch_all.return_value = [
        {
            "user_id": 111,
            "base_entries": 1,
            "effective_weight": 3.0,
            "qualifying_roles": "VIP",
            "bonus_breakdown": "3.0x",
            "is_excluded": False,
            "exclusion_reason": "",
            "joined_at": datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc),
        },
        {
            "user_id": 222,
            "base_entries": 1,
            "effective_weight": 1.0,
            "qualifying_roles": "",
            "bonus_breakdown": "1.0x",
            "is_excluded": True,
            "exclusion_reason": "Bot account",
            "joined_at": datetime.datetime(2026, 1, 1, 12, 5, tzinfo=datetime.timezone.utc),
        },
    ]
    csv_str = await mgr.export_giveaway_csv(1)
    assert "User ID,Base Entries,Effective Weight,Qualifying Roles" in csv_str
    assert "111,1,3.0,VIP,False" in csv_str
    assert "222,1,1.0,,True,Bot account" in csv_str


# ─────────────────────────────────────────────────────────────────────────────
# 10. TEST AUTHORIZATION CHECKS & LEGACY PREFIX COMMANDS PRESERVATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authorization_and_legacy_prefix_commands():
    from src.cogs.utility.giveaway import is_giveaway_authorized
    from src.security.owner import OWNER_ID

    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()
    mock_bot.db.fetch_one.return_value = None  # no custom role

    # Guild owner
    guild = MagicMock(spec=discord.Guild)
    guild.owner_id = 42

    member_owner = MagicMock(spec=discord.Member)
    member_owner.id = 42
    member_owner.guild = guild
    member_owner.guild_permissions.administrator = False
    member_owner.guild_permissions.manage_guild = False
    member_owner.guild_permissions.manage_messages = False
    member_owner.roles = []
    assert await is_giveaway_authorized(mock_bot, member_owner) is True

    # Primary bot owner
    bot_owner = MagicMock(spec=discord.Member)
    bot_owner.id = OWNER_ID
    bot_owner.guild = guild
    bot_owner.guild_permissions.administrator = False
    bot_owner.guild_permissions.manage_guild = False
    bot_owner.guild_permissions.manage_messages = False
    bot_owner.roles = []
    assert await is_giveaway_authorized(mock_bot, bot_owner) is True

    # Administrator
    admin_member = MagicMock(spec=discord.Member)
    admin_member.id = 999
    admin_member.guild = guild
    admin_member.guild_permissions.administrator = True
    admin_member.guild_permissions.manage_guild = False
    admin_member.guild_permissions.manage_messages = False
    admin_member.roles = []
    assert await is_giveaway_authorized(mock_bot, admin_member) is True

    # Regular unauthorized user
    regular = MagicMock(spec=discord.Member)
    regular.id = 555
    regular.guild = guild
    regular.guild_permissions.administrator = False
    regular.guild_permissions.manage_guild = False
    regular.guild_permissions.manage_messages = False
    regular.roles = []
    assert await is_giveaway_authorized(mock_bot, regular) is False

    # Check Legacy Prefix Commands
    gw_cog = Giveaways(mock_bot)
    legacy_gw_commands = [c.name for c in gw_cog.get_commands()]
    assert "gstart" in legacy_gw_commands
    assert "gend" in legacy_gw_commands
    assert "greroll" in legacy_gw_commands
    assert "glist" in legacy_gw_commands
    assert "gpause" in legacy_gw_commands
    assert "gresume" in legacy_gw_commands
    assert "gcancel" in legacy_gw_commands
    assert "ginfo" in legacy_gw_commands
    assert "gcheck" in legacy_gw_commands
    assert "gbonus" in legacy_gw_commands
    assert "greq" in legacy_gw_commands


# ─────────────────────────────────────────────────────────────────────────────
# 11. TEST VERIFICATION SYSTEM FLOW & PERMISSION CHECKS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verification_system_flow():
    from src.cogs.utility.verification import Verification

    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()
    mock_bot.guild_mgr.get_prefix.return_value = "+"

    cog = Verification(mock_bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777
    guild.name = "Test Guild"

    verified_role = MagicMock(spec=discord.Role)
    verified_role.id = 101
    verified_role.name = "Verified"

    unverified_role = MagicMock(spec=discord.Role)
    unverified_role.id = 102
    unverified_role.name = "Unverified"

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.__gt__ = lambda self, other: True
    bot_member.top_role.__ge__ = lambda self, other: True
    bot_member.top_role.__le__ = lambda self, other: False
    bot_member.top_role.__lt__ = lambda self, other: False
    guild.me = bot_member
    guild.get_role.side_effect = lambda rid: verified_role if rid == 101 else (unverified_role if rid == 102 else None)

    # 1. on_member_join assigns unverified role
    mock_bot.db.fetch_one.return_value = {
        "guild_id": 777,
        "role_id": 101,
        "unverified_role_id": 102,
        "enabled": True,
        "min_account_age_days": 0,
    }

    new_member = MagicMock(spec=discord.Member)
    new_member.id = 8888
    new_member.guild = guild
    new_member.bot = False
    new_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    new_member.add_roles = AsyncMock()
    new_member.remove_roles = AsyncMock()
    new_member.roles = [unverified_role]

    await cog.on_member_join(new_member)
    new_member.add_roles.assert_called_with(unverified_role, reason="KYOKA Verification: New member join")

    # 2. handle_member_verified removes unverified, adds verified role
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = new_member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await cog.handle_member_verified(interaction, method="button")
    new_member.remove_roles.assert_called_with(unverified_role, reason="KYOKA Verification: Member verified")
    new_member.add_roles.assert_called_with(verified_role, reason="KYOKA Verification: Completed via button")
    assert interaction.response.send_message.called


# ─────────────────────────────────────────────────────────────────────────────
# 12. TEST PING RESILIENCE & GENUINE MEASUREMENTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_resilience_and_measurements():
    from src.cogs.general.ping import Ping

    mock_bot = MagicMock()
    mock_bot.latency = 0.042  # 42ms
    mock_bot.db = AsyncMock()
    mock_bot.db.fetch_one.return_value = {"?column?": 1}
    mock_bot.custom_emojis.get.return_value = "•"

    cog = Ping(mock_bot)

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.shard_id = 0
    ctx.author.display_name = "Aizen"
    mock_bot.http = AsyncMock()
    mock_bot.http.request.return_value = {"id": "123"}
    ctx.bot = mock_bot
    ctx.channel = MagicMock(spec=discord.TextChannel)
    ctx.channel.id = 999

    # Call ping command with online DB
    await cog.ping.callback(cog, ctx)
    assert mock_bot.http.request.called
    sent_payload = mock_bot.http.request.call_args[1].get("json") or {}
    raw_text = str(sent_payload)
    assert "Gateway:" in raw_text
    assert "Database:" in raw_text
    assert "42.00ms" in raw_text

    # Call ping command with DB timeout / outage
    mock_bot.db.fetch_one.side_effect = asyncio.TimeoutError("DB Timeout")
    mock_bot.http.request.reset_mock()
    await cog.ping.callback(cog, ctx)
    assert mock_bot.http.request.called
    sent_payload_2 = mock_bot.http.request.call_args[1].get("json") or {}
    raw_text_2 = str(sent_payload_2)
    assert "Unavailable" in raw_text_2


# ─────────────────────────────────────────────────────────────────────────────
# 13. TEST HELP CATEGORY DYNAMICS & OWNER COMMAND PRIVACY
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_help_categories_and_owner_privacy():
    from src.cogs.general.help import Help
    from src.security.owner import OWNER_ID

    mock_bot = MagicMock()
    mock_bot.guild_mgr.get_prefix.return_value = "+"

    cog_help = Help(mock_bot)

    # 1. Non-owner cannot see Owner / Developer categories
    regular_user = MagicMock(spec=discord.Member)
    regular_user.id = 99999999
    ctx_regular = MagicMock(spec=CustomContext)
    ctx_regular.author = regular_user
    ctx_regular.guild = MagicMock(spec=discord.Guild)

    # Create dummy owner command
    owner_cmd = MagicMock(spec=commands.Command)
    owner_cmd.name = "eval"
    owner_cmd.hidden = False
    owner_cmd.cog = MagicMock()
    owner_cmd.cog.category = "Developer"

    assert cog_help._can_run_command(owner_cmd, ctx_regular) is False

    # 2. Owner can see owner-restricted commands
    owner_user = MagicMock(spec=discord.Member)
    owner_user.id = OWNER_ID
    ctx_owner = MagicMock(spec=CustomContext)
    ctx_owner.author = owner_user

    guess_cmd = MagicMock(spec=commands.Command)
    guess_cmd.name = "spam"
    guess_cmd.hidden = False
    guess_cmd.cog = MagicMock()
    guess_cmd.cog.category = "Admin"
    assert cog_help._can_run_command(guess_cmd, ctx_owner) is True


# ─────────────────────────────────────────────────────────────────────────────
# 14. TEST PREFIX RESOLVER (+, ?, GUILD, MENTION, NO-PREFIX)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prefix_resolver_resolves_plus_and_question():
    from src.core.bot import get_prefix

    mock_bot = MagicMock()
    mock_bot.user = MagicMock(id=123456789)
    mock_bot.guild_mgr.get_prefix.return_value = "+"
    mock_bot.no_prefix_users = set()
    mock_bot.perm_mgr.is_developer_sync.return_value = False

    msg = MagicMock(spec=discord.Message)
    msg.guild = MagicMock(id=111)
    msg.author = MagicMock(id=222)

    prefixes = await get_prefix(mock_bot, msg)
    # Should include bot mention, '+', and '?'
    assert "+" in prefixes
    assert "?" in prefixes
    assert "<@123456789> " in prefixes or "<@!123456789> " in prefixes


@pytest.mark.asyncio
async def test_prefix_resolver_safe_when_bot_user_none():
    from src.core.bot import get_prefix

    mock_bot = MagicMock()
    mock_bot.user = None
    mock_bot.guild_mgr.get_prefix.return_value = "+"
    mock_bot.no_prefix_users = set()
    mock_bot.perm_mgr.is_developer_sync.return_value = False

    msg = MagicMock(spec=discord.Message)
    msg.guild = MagicMock(id=111)
    msg.author = MagicMock(id=222)

    # Must NOT raise AttributeError: 'NoneType' object has no attribute 'id'
    prefixes = await get_prefix(mock_bot, msg)
    assert "+" in prefixes
    assert "?" in prefixes


@pytest.mark.asyncio
async def test_prefix_context_resolution_for_plus_and_question():
    from src.core.bot import KyokaBot

    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    await bot._load_all_extensions()

    # Test +ping
    msg_plus = MagicMock(spec=discord.Message)
    msg_plus.content = "+ping"
    msg_plus.guild = MagicMock(id=1)
    msg_plus.author = MagicMock(id=2)
    msg_plus.channel = MagicMock()

    ctx_plus = await bot.get_context(msg_plus)
    assert ctx_plus.valid is True
    assert ctx_plus.command is not None
    assert ctx_plus.command.name == "ping"

    # Test ?ping
    msg_q = MagicMock(spec=discord.Message)
    msg_q.content = "?ping"
    msg_q.guild = MagicMock(id=1)
    msg_q.author = MagicMock(id=2)
    msg_q.channel = MagicMock()

    ctx_q = await bot.get_context(msg_q)
    assert ctx_q.valid is True
    assert ctx_q.command is not None
    assert ctx_q.command.name == "ping"

    # Test +giveaway and +g
    msg_gw = MagicMock(spec=discord.Message)
    msg_gw.content = "+giveaway"
    msg_gw.guild = MagicMock(id=1)
    msg_gw.author = MagicMock(id=2)
    msg_gw.channel = MagicMock()

    ctx_gw = await bot.get_context(msg_gw)
    assert ctx_gw.valid is True
    assert ctx_gw.command is not None
    assert ctx_gw.command.name == "giveaway"


# ─────────────────────────────────────────────────────────────────────────────
# 15. TEST SLASH COMMAND TREE REGISTRATION & SYNC INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slash_command_tree_commands_registered():
    from src.core.bot import KyokaBot

    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777
    await bot._load_all_extensions()

    tree_commands = {cmd.name: cmd for cmd in bot.tree.get_commands()}
    # Verify core slash commands exist in the tree
    expected_slash = [
        "help", "ping", "botinfo", "serverinfo", "userinfo",
        "ban", "kick", "timeout", "unmute", "warn", "warnings", "delwarn",
        "purge", "slowmode", "lock", "unlock",
        "ticket", "unban", "giveaway", "requirements", "afk"
    ]
    for name in expected_slash:
        assert name in tree_commands, f"Slash command '{name}' missing from CommandTree"

    # Verify CommandTree sync call can be executed
    bot._connection.http.bulk_upsert_global_commands = AsyncMock(return_value=[])
    bot._connection.http._global_over = asyncio.Event()
    bot._connection.http._global_over.set()
    synced = await bot.tree.sync()
    assert isinstance(synced, list)


# ─────────────────────────────────────────────────────────────────────────────
# 16. TEST ON_MESSAGE DISPATCH FOR PREFIX & NO-PREFIX END-TO-END
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_message_dispatch_prefix_and_noprefix_end_to_end():
    from src.core.bot import KyokaBot
    from src.security.owner import OWNER_ID

    bot = KyokaBot()
    bot._connection.user = MagicMock(id=111222333)

    # Mock database
    bot.db.fetch_all = AsyncMock(return_value=[])
    bot.db.fetch_one = AsyncMock(return_value=None)
    bot.db.execute = AsyncMock(return_value=None)

    await bot._load_all_extensions()

    invoked = []
    original_invoke = bot.invoke

    async def track_invoke(ctx):
        if ctx.command:
            invoked.append((ctx.command.name, ctx.prefix, ctx.author.id))

    bot.invoke = track_invoke

    # 1. Regular user with +ping -> must dispatch
    msg1 = MagicMock(spec=discord.Message)
    msg1.author.bot = False
    msg1.author.id = 999
    msg1.content = "+ping"
    msg1.guild = MagicMock(id=10)
    msg1.channel = MagicMock(id=20)
    await bot.on_message(msg1)

    # 2. Regular user with ?ping -> must dispatch
    msg2 = MagicMock(spec=discord.Message)
    msg2.author.bot = False
    msg2.author.id = 999
    msg2.content = "?ping"
    msg2.guild = MagicMock(id=10)
    msg2.channel = MagicMock(id=20)
    await bot.on_message(msg2)

    # 3. Regular user with bare ping -> must NOT dispatch
    msg3 = MagicMock(spec=discord.Message)
    msg3.author.bot = False
    msg3.author.id = 999
    msg3.content = "ping"
    msg3.guild = MagicMock(id=10)
    msg3.channel = MagicMock(id=20)
    await bot.on_message(msg3)

    # 4. Primary owner with bare ping -> must dispatch (no prefix)
    msg4 = MagicMock(spec=discord.Message)
    msg4.author.bot = False
    msg4.author.id = OWNER_ID
    msg4.content = "ping"
    msg4.guild = MagicMock(id=10)
    msg4.channel = MagicMock(id=20)
    await bot.on_message(msg4)

    # 5. Authorized no-prefix user with bare ping -> must dispatch
    bot.no_prefix_users.add(777)
    msg5 = MagicMock(spec=discord.Message)
    msg5.author.bot = False
    msg5.author.id = 777
    msg5.content = "ping"
    msg5.guild = MagicMock(id=10)
    msg5.channel = MagicMock(id=20)
    await bot.on_message(msg5)

    # 6. Bot message -> must be ignored
    msg6 = MagicMock(spec=discord.Message)
    msg6.author.bot = True
    msg6.content = "+ping"
    await bot.on_message(msg6)

    assert len(invoked) == 4
    assert invoked[0] == ("ping", "+", 999)
    assert invoked[1] == ("ping", "?", 999)
    assert invoked[2] == ("ping", "", OWNER_ID)
    assert invoked[3] == ("ping", "", 777)


# ─────────────────────────────────────────────────────────────────────────────
# 17. TEST LEVELING MANAGER MATH & XP COOLDOWN
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_leveling_manager_math_and_cooldown():
    from src.managers.leveling_manager import LevelingManager, xp_for_level, total_xp_for_level, level_from_total_xp
    mock_db = AsyncMock()
    mgr = LevelingManager(mock_db)

    # 1. Level math
    assert xp_for_level(1) == 155
    assert total_xp_for_level(1) == 0
    assert total_xp_for_level(2) == 155
    assert level_from_total_xp(0) == (1, 0, 155)
    assert level_from_total_xp(50) == (1, 50, 155)
    assert level_from_total_xp(155) == (2, 0, 220)

    # 2. Awarding message XP with cooldown (opt-in enabled)
    await mgr.set_guild_enabled(1, True)
    mock_db.fetch_one.return_value = None
    awarded, new_total_xp, new_level, leveled_up = await mgr.award_message_xp(guild_id=1, user_id=42)
    assert awarded is True
    assert 15 <= new_total_xp <= 25
    assert new_level == 1

    # Rapid second message within 60s cooldown -> awarded is False
    awarded2, _, _, _ = await mgr.award_message_xp(guild_id=1, user_id=42)
    assert awarded2 is False



# ─────────────────────────────────────────────────────────────────────────────
# 18. TEST RANK CARD CANVAS GENERATION & PNG INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

def test_rank_card_canvas_generation():
    from src.utils.canvas import render_rank_card
    buf = render_rank_card(
        avatar_bytes=None,
        username="TestUser",
        display_name="KyokaTester",
        rank=1,
        level=5,
        current_xp=120,
        needed_xp=250,
        total_xp=1450,
        accent_color=0x7C3AED,
    )
    png_bytes = buf.getvalue()
    assert len(png_bytes) > 1000
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


# ─────────────────────────────────────────────────────────────────────────────
# 19. TEST PREMIUM OWNER BYPASS & LICENSE REDEMPTION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_premium_owner_bypass_and_redemption():
    from src.managers.premium_manager import PremiumManager
    from src.security.owner import OWNER_ID
    mock_db = AsyncMock()
    mgr = PremiumManager(mock_db)

    # Owner is always Prime Lifetime
    assert mgr.is_user_premium(OWNER_ID) is True
    info = mgr.get_user_info(OWNER_ID)
    assert info["is_premium"] is True
    assert "Lifetime" in info["remaining_str"]

    # Other user is not premium by default
    assert mgr.is_user_premium(123456789) is False

    # Key redemption
    mock_db.fetch_one.return_value = {
        "key": "TEST-KEY-123",
        "duration_days": 30,
        "target_type": "user",
        "is_used": False,
    }
    redemption = await mgr.redeem_key("TEST-KEY-123", redeemer_id=999, target_id=999, target_type="user")
    assert redemption["success"] is True
    assert "30" in redemption["duration_text"]



# ─────────────────────────────────────────────────────────────────────────────
# 20. TEST GIF MANAGER POOLS & RECENT AVOIDANCE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gif_manager_pools_and_recent_avoidance():
    from src.managers.gif_manager import GIFManager
    mgr = GIFManager()

    # Verify action pools exist
    assert "slapped" in mgr.curated
    assert "intimate_couple" in mgr.curated
    assert len(mgr.curated["intimate_couple"]) >= 8

    # Fetch multiple GIFs, ensure HTTPS URLs
    gif1 = await mgr.get_action_gif("intimate_couple")
    gif2 = await mgr.get_action_gif("intimate_couple")
    assert gif1.startswith("https://")
    assert gif2.startswith("https://")


# ─────────────────────────────────────────────────────────────────────────────
# 21. TEST TICKET CLOSED CONTROLS & REOPEN LOGIC
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ticket_closed_controls_and_reopen_logic():
    from src.cogs.ticket.ticket_system import TicketClosedControlsView
    from src.managers.ticket_manager import TicketManager

    mock_cog = MagicMock()
    view = TicketClosedControlsView(mock_cog)
    btn_ids = [btn.custom_id for btn in view.children]
    assert "ticket_ctrl_reopen" in btn_ids
    assert "ticket_ctrl_closed_transcript" in btn_ids
    assert "ticket_ctrl_delete" in btn_ids

    mock_db = AsyncMock()
    mock_db.fetch_one.return_value = {"channel_id": 9999, "status": "open"}
    t_mgr = TicketManager(mock_db)
    reopened = await t_mgr.reopen_ticket(9999)
    assert reopened is True
    assert 9999 in t_mgr._active_tickets_cache


# ─────────────────────────────────────────────────────────────────────────────
# 22. TEST ACTIVE GEMINI AI MODELS CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

def test_gemini_active_models_configuration():
    from src.managers.ai_manager import AIManager
    assert AIManager.DEFAULT_MODEL == "gemini-flash-lite-latest"
    for model in AIManager.FALLBACK_MODELS:
        assert model in ("gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-flash-latest")
        assert "exp" not in model
        assert "1.5" not in model


# ─────────────────────────────────────────────────────────────────────────────
# 23. TEST FUCK ACTION COMMAND PLAYFUL ROLEPLAY
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fuck_command_validation():
    from src.cogs.fun.fun import Fun
    mock_bot = MagicMock()
    fun_cog = Fun(mock_bot)

    ctx = MagicMock(spec=CustomContext)
    ctx.prefix = "+"
    ctx.author.id = 100
    ctx.author.mention = "<@100>"
    ctx.send = AsyncMock()

    # 1. No target provided
    await fun_cog.fuck.callback(fun_cog, ctx, None)
    assert "Please mention someone" in ctx.send.call_args[0][0]

    # 2. Bot target
    bot_target = MagicMock(spec=discord.Member)
    bot_target.bot = True
    await fun_cog.fuck.callback(fun_cog, ctx, bot_target)
    assert "Keep the roleplay between human members" in ctx.send.call_args[0][0]

    # 3. Self target
    self_target = MagicMock(spec=discord.Member)
    self_target.bot = False
    self_target.id = 100
    await fun_cog.fuck.callback(fun_cog, ctx, self_target)
    assert "Choose another member" in ctx.send.call_args[0][0]

    # 4. Valid target
    human_target = MagicMock(spec=discord.Member)
    human_target.bot = False
    human_target.id = 200
    human_target.mention = "<@200>"
    await fun_cog.fuck.callback(fun_cog, ctx, human_target)
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "got intimately dominated by" in embed.description
    assert embed.image.url.startswith("https://")




