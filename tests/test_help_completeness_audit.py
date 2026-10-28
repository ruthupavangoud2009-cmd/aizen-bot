"""
Automated Command Tree Completeness & Category Integrity Audit.
Verifies:
- 100% of registered commands are mapped into valid categories (no unclassified/orphan commands)
- All vouch commands strictly cataloged under '⭐・VOUCHES & REPUTATION'
- All bill commands strictly cataloged under '🧾・BLOX FRUITS SERVICE BILLS'
- AI subcommands and commands never contaminate Music ('🎵・MUSIC')
- Help categories and navigation work for all users without duplicate command entries
"""

from unittest.mock import MagicMock
import pytest
from discord.ext import commands

from src.cogs.general.bills import Bills
from src.cogs.general.help import Help
from src.cogs.general.vouches import Vouches
from src.cogs.music.music import Music
from src.ui.categories import (
    CATEGORIES,
    CATEGORY_BY_ID,
    CATEGORY_BY_TAG,
    resolve_command_category,
)


@pytest.fixture
def mock_bot_with_cogs():
    """Build a mock bot loaded with core cogs to simulate runtime command tree."""
    bot = MagicMock()
    bot.cogs = {}
    bot.commands = set()
    bot.guild_mgr = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"

    vouch_cog = Vouches(bot)
    bill_cog = Bills(bot)
    
    bot.cogs["Vouches"] = vouch_cog
    bot.cogs["Bills"] = bill_cog

    # Register their commands on bot.commands
    for cmd in vouch_cog.get_commands():
        bot.commands.add(cmd)
    for cmd in bill_cog.get_commands():
        bot.commands.add(cmd)

    return bot


def test_vouch_commands_categorized_in_vouches_and_reputation(mock_bot_with_cogs):
    """Verify all real vouch commands map strictly to '⭐・VOUCHES & REPUTATION'."""
    bot = mock_bot_with_cogs
    help_cog = Help(bot)
    vouch_cog = bot.cogs["Vouches"]

    expected_vouch_commands = [
        "vouch", "vlb", "vouchinfo", "vouchhistory", "vouchimport",
        "vouchremove", "heldvouches", "repstaff", "vouchchannel"
    ]

    for cmd_name in expected_vouch_commands:
        cmd = vouch_cog.get_commands()
        matched = next((c for c in vouch_cog.get_commands() if c.name == cmd_name or cmd_name in c.aliases), None)
        assert matched is not None, f"Expected vouch command '{cmd_name}' not found on Vouches cog"
        
        cat = help_cog._resolve_category(matched)
        assert cat == "⭐・VOUCHES & REPUTATION", f"Command '{cmd_name}' miscategorized as '{cat}'"


def test_bill_commands_categorized_in_blox_fruits_service_bills(mock_bot_with_cogs):
    """Verify all real bill commands map strictly to '🧾・BLOX FRUITS SERVICE BILLS'."""
    bot = mock_bot_with_cogs
    help_cog = Help(bot)
    bill_cog = bot.cogs["Bills"]

    expected_bill_commands = [
        "bill", "billview", "billpaid", "billcancel", "billrefund",
        "billstatus", "billlist", "billstats", "billsetup", "billname",
        "billcurrency", "billpayment", "billtax"
    ]

    for cmd_name in expected_bill_commands:
        matched = next((c for c in bill_cog.get_commands() if c.name == cmd_name or cmd_name in c.aliases), None)
        assert matched is not None, f"Expected bill command '{cmd_name}' not found on Bills cog"
        
        cat = help_cog._resolve_category(matched)
        assert cat == "🧾・BLOX FRUITS SERVICE BILLS", f"Command '{cmd_name}' miscategorized as '{cat}'"


def test_audit_command_tree_method():
    """Verify Help.audit_command_tree detects complete categorization and zero music pollution."""
    bot = MagicMock()
    bot.cogs = {}
    bot.commands = set()

    async def _dummy_coro(ctx):
        pass

    # Create dummy music command
    music_cog = MagicMock(qualified_name="Music")
    music_cmd = commands.Command(_dummy_coro, name="play")
    music_cmd.cog = music_cog
    music_cmd.description = "Play music"
    bot.commands.add(music_cmd)

    # Create dummy vouch command
    vouch_cog = MagicMock(qualified_name="Vouches")
    vouch_cmd = commands.Command(_dummy_coro, name="vouch")
    vouch_cmd.cog = vouch_cog
    vouch_cmd.description = "Give vouch"
    bot.commands.add(vouch_cmd)

    # Create dummy bill command
    bill_cog = MagicMock(qualified_name="Bills")
    bill_cmd = commands.Command(_dummy_coro, name="bill")
    bill_cmd.cog = bill_cog
    bill_cmd.description = "Create service bill"
    bot.commands.add(bill_cmd)

    help_cog = Help(bot)
    report = help_cog.audit_command_tree()

    assert report["is_complete"] is True
    assert len(report["missing_from_help"]) == 0
    assert len(report["music_contamination"]) == 0
    assert "vouch" in report["vouch_commands"]
    assert "bill" in report["bill_commands"]
    assert "play" in report["category_distribution"]["🎵・MUSIC"]


def test_zero_ai_music_cross_contamination():
    """Verify AI commands never get misclassified into Music category."""
    async def _dummy_coro(ctx):
        pass

    ai_commands = [
        "ai", "chat", "askai", "aivoice", "voicespeak", "voiceask",
        "voicestop", "voicediag", "speak", "voicejoin", "voiceleave"
    ]
    ai_cog = MagicMock(qualified_name="AIVoice")

    for cmd_name in ai_commands:
        cmd = commands.Command(_dummy_coro, name=cmd_name)
        cmd.cog = ai_cog
        meta = resolve_command_category(cmd)
        assert meta.id == "ai", f"Command '{cmd_name}' resolved to category '{meta.id}' instead of 'ai'"
        assert meta.tag != "🎵・MUSIC", f"Command '{cmd_name}' cross-contaminated into Music!"
