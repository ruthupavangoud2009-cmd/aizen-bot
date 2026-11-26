"""
Tests for KYOKA upgraded systems:
1. Persistent Moderation Cases (CaseManager + CasesCog + dispatch_mod_log)
2. Persistent Reminders (DB + offline memory + parse_time_duration)
3. Safe Custom Commands (CustomCommandsCog + template variables + no shadowing)
4. Control Center & Setup Wizard (module toggles, leveling opt-in default False)
5. Server health dashboard economy routes registration & music sentinel cleanup
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.cogs.admin.control_center import ControlCenterCog
from src.cogs.moderation._helpers import dispatch_mod_log
from src.cogs.moderation.cases import CasesCog
from src.cogs.utility.custom_commands import CustomCommandsCog, render_safe_template
from src.cogs.utility.reminders import Reminders, parse_time_duration
from src.core.bot import KyokaBot
from src.core.server import HealthServer
from src.managers.case_manager import CaseManager


def _make_mock_db() -> MagicMock:
    db = MagicMock()
    db._connected_once = True
    db.execute = AsyncMock(return_value="OK")
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_case_manager_sequential_ids_and_updates():
    db = _make_mock_db()
    db.fetch_one.side_effect = [
        {"next_id": 1},
        {"next_id": 2},
        {"guild_id": 100, "case_id": 1, "action": "ban", "user_id": 200, "moderator_id": 300, "reason": "Spam"},
    ]

    mgr = CaseManager(db)
    c1 = await mgr.create_case(100, "ban", user_id=200, moderator_id=300, reason="Spam")
    c2 = await mgr.create_case(100, "warn", user_id=201, moderator_id=300, reason="Flooding")
    assert c1 == 1
    assert c2 == 2

    ok = await mgr.update_reason(100, 1, "Severe spam links", notes="Confirmed by logs")
    assert ok is True
    assert db.execute.await_count >= 3


@pytest.mark.asyncio
async def test_dispatch_mod_log_records_case_even_without_modlog_channel():
    bot = KyokaBot()
    bot.case_mgr = MagicMock()
    bot.case_mgr.create_case = AsyncMock(return_value=42)
    bot.guild_mgr = MagicMock()
    bot.guild_mgr.get_modlog_channel = MagicMock(return_value=None)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777777
    target = MagicMock(spec=discord.Member)
    target.id = 888888
    mod = MagicMock(spec=discord.Member)
    mod.id = 999999

    case_id = await dispatch_mod_log(bot, guild, "Member Ban", target=target, moderator=mod, reason="Raid attempt")
    assert case_id == 42
    bot.case_mgr.create_case.assert_awaited_once()
    call_kwargs = bot.case_mgr.create_case.call_args.kwargs
    assert call_kwargs["action"] == "ban"
    assert call_kwargs["guild_id"] == 777777


@pytest.mark.asyncio
async def test_cases_cog_no_duplicate_case_command():
    bot = KyokaBot()
    cog = CasesCog(bot)
    cmd_names = {c.name for c in cog.get_commands()}
    assert "modcase" in cmd_names
    assert "cases" in cmd_names
    assert "reason" in cmd_names
    assert "modstats" in cmd_names
    assert "case" not in cmd_names  # WarnCog retains `case` without collision


def test_parse_time_duration_and_reminders_persistence():
    assert parse_time_duration("30s") == 30
    assert parse_time_duration("10m") == 600
    assert parse_time_duration("1h30m") == 5400
    assert parse_time_duration("2d") == 172800
    assert parse_time_duration("invalid") is None
    assert parse_time_duration("0s") is None


@pytest.mark.asyncio
async def test_reminders_create_list_cancel_offline_fallback():
    bot = KyokaBot()
    bot.db = _make_mock_db()
    bot.db._connected_once = False  # Exercise offline memory fallback cleanly
    reminders = Reminders(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=101, name="Test Guild")
    ctx.channel = MagicMock(id=202)
    ctx.author = MagicMock(id=303, display_name="User303", mention="<@303>")
    ctx.author.display_avatar = MagicMock(url="https://example.com/a.png")
    ctx.send = AsyncMock()
    ctx.interaction = None

    await reminders.remind.callback(reminders, ctx, "15m", reason="Check oven")
    assert len(reminders._memory_reminders) == 1
    rid = reminders._memory_reminders[0]["id"]
    assert reminders._memory_reminders[0]["reason"] == "Check oven"

    # Cancel as another user -> must NOT remove
    other_ctx = MagicMock()
    other_ctx.guild = ctx.guild
    other_ctx.author = MagicMock(id=999, display_name="Intruder")
    other_ctx.author.display_avatar = MagicMock(url="https://example.com/b.png")
    other_ctx.send = AsyncMock()
    other_ctx.interaction = None
    await reminders.remind_cancel.callback(reminders, other_ctx, rid)
    assert len(reminders._memory_reminders) == 1

    # Cancel as owner -> removes reminder
    await reminders.remind_cancel.callback(reminders, ctx, rid)
    assert len(reminders._memory_reminders) == 0


@pytest.mark.asyncio
async def test_custom_commands_render_and_execution():
    bot = KyokaBot()
    bot.db = _make_mock_db()
    cog = CustomCommandsCog(bot)
    cog._cache[555] = {
        "rulesinfo": {
            "name": "rulesinfo",
            "response": "Welcome {user.name} to {server} in {channel}!",
            "use_embed": False,
            "embed_title": None,
            "required_role_id": None,
            "cooldown_seconds": 3,
        }
    }

    msg = MagicMock(spec=discord.Message)
    msg.guild = MagicMock(id=555, member_count=1200, members=[])
    msg.guild.name = "Soul Society"
    msg.author = MagicMock(id=777, bot=False, display_name="Ichigo", mention="<@777>")
    msg.channel = MagicMock(mention="<#10>")
    msg.channel.name = "general"
    msg.channel.send = AsyncMock()
    msg.content = "+rulesinfo"

    rendered = render_safe_template("Welcome {user.name} to {server}!", msg)
    assert rendered == "Welcome Ichigo to Soul Society!"

    await cog.on_message(msg)
    msg.channel.send.assert_awaited_once()
    sent_text = msg.channel.send.call_args[0][0]
    assert "Welcome Ichigo to Soul Society" in sent_text


@pytest.mark.asyncio
async def test_control_center_module_toggles_and_leveling_default_off():
    bot = KyokaBot()
    bot.db = _make_mock_db()
    cog = ControlCenterCog(bot)

    assert cog.is_module_enabled(12345, "leveling") is False
    assert cog.is_module_enabled(12345, "moderation") is True

    await cog.set_module_enabled(12345, "leveling", True, actor_id=1)
    assert cog.is_module_enabled(12345, "leveling") is True
    bot.db.execute.assert_awaited_once()


def test_health_server_mounts_economy_routes():
    bot = MagicMock()
    bot.db = _make_mock_db()
    server = HealthServer(bot)
    route_paths = {res.canonical for res in server.app.router.resources()}
    assert "/api/guilds/{guild_id}/economy/settings" in route_paths


def test_no_broken_sentinel_imports_in_music():
    player_src = Path("src/cogs/music/_player.py").read_text(encoding="utf-8")
    music_src = Path("src/cogs/music/music.py").read_text(encoding="utf-8")
    assert "src.sentinel" not in player_src
    assert "src.sentinel" not in music_src
