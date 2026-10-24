"""
Unit and integration tests for KYOKA 3.0:
- Command categorization accuracy (AI vs Music isolation)
- Subcommand parent group inheritance (e.g. `aivoice stop` -> AI, not Music)
- AssetManager localized file resolution and fallback safety
- Public Help Command Archive (HCA) accessibility
- Zero regression to existing music or core systems
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import discord
from discord.ext import commands

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ui.categories import (
    CATEGORIES,
    CATEGORY_BY_ID,
    CATEGORY_BY_TAG,
    CATEGORY_SEARCH_ALIASES,
    resolve_command_category,
    get_category_by_query,
)
from src.ui.asset_manager import AssetManager


class TestCategoryClassification:
    """Test suite verifying bulletproof categorization and zero cross-contamination."""

    def test_all_18_standard_categories_defined(self):
        """Verify the 18+ standard categories matching the infographic exist."""
        expected_ids = {
            "general", "moderation", "automod", "welcome", "verification",
            "tickets", "reaction_roles", "giveaways", "music", "afk",
            "vouches", "service_bills", "blox_fruits", "ai",
            "leveling", "premium", "config", "owner",
        }
        actual_ids = set(CATEGORY_BY_ID.keys())
        missing = expected_ids - actual_ids
        assert not missing, f"Missing required categories: {missing}"

    def test_music_commands_classify_strictly_to_music(self):
        """Verify core music commands resolve to Music."""
        music_cog = MagicMock(qualified_name="Music")
        music_cog.category = "Music"

        for cmd_name in ["play", "pause", "resume", "skip", "stop", "queue", "nowplaying", "volume", "loop", "shuffle", "disconnect"]:
            mock_cmd = MagicMock(spec=commands.Command)
            mock_cmd.name = cmd_name
            mock_cmd.qualified_name = cmd_name
            mock_cmd.parent = None
            mock_cmd.root_parent = None
            mock_cmd.cog = music_cog

            meta = resolve_command_category(mock_cmd)
            assert meta.id == "music", f"Command '{cmd_name}' expected music, got '{meta.id}'"
            assert meta.name == "Music"

    def test_ai_voice_subcommands_do_not_leak_into_music(self):
        """CRITICAL TEST: Ensure `aivoice stop`, `aivoice leave`, `aivoice join` resolve to AI, NEVER Music."""
        ai_cog = MagicMock(qualified_name="AIVoice")
        ai_cog.category = "🤖・ARTIFICIAL INTELLIGENCE"

        group_cmd = MagicMock(spec=commands.Group)
        group_cmd.name = "aivoice"
        group_cmd.qualified_name = "aivoice"
        group_cmd.parent = None
        group_cmd.root_parent = None
        group_cmd.cog = ai_cog

        for sub_name in ["stop", "leave", "join", "speak", "ask", "voice", "diag"]:
            sub_cmd = MagicMock(spec=commands.Command)
            sub_cmd.name = sub_name
            sub_cmd.qualified_name = f"aivoice {sub_name}"
            sub_cmd.parent = group_cmd
            sub_cmd.root_parent = group_cmd
            sub_cmd.cog = ai_cog

            meta = resolve_command_category(sub_cmd)
            assert meta.id == "ai", f"Subcommand 'aivoice {sub_name}' leaked to '{meta.id}' instead of 'ai'"
            assert meta.id != "music", f"Subcommand 'aivoice {sub_name}' leaked into MUSIC!"

    def test_ai_chat_commands_classify_to_ai(self):
        """Verify AI chat and companion commands resolve to AI."""
        ai_cog = MagicMock(qualified_name="AIInteractions")
        for cmd_name in ["ai", "chat", "askai", "aizenai", "aigf", "aibaddie", "aichannel", "aidiag"]:
            mock_cmd = MagicMock(spec=commands.Command)
            mock_cmd.name = cmd_name
            mock_cmd.qualified_name = cmd_name
            mock_cmd.parent = None
            mock_cmd.root_parent = None
            mock_cmd.cog = ai_cog

            meta = resolve_command_category(mock_cmd)
            assert meta.id == "ai", f"Command '{cmd_name}' expected 'ai', got '{meta.id}'"

    def test_blox_fruits_commands_classify_to_blox_fruits(self):
        """Verify Blox Fruits commands resolve to Blox Fruits AI."""
        bf_cog = MagicMock(qualified_name="BloxFruitsAI")
        for cmd_name in ["bloxai", "fruitinfo", "grindhelp", "tradehelp", "buildhelp"]:
            mock_cmd = MagicMock(spec=commands.Command)
            mock_cmd.name = cmd_name
            mock_cmd.qualified_name = cmd_name
            mock_cmd.parent = None
            mock_cmd.root_parent = None
            mock_cmd.cog = bf_cog

            meta = resolve_command_category(mock_cmd)
            assert meta.id == "blox_fruits", f"Command '{cmd_name}' expected 'blox_fruits', got '{meta.id}'"

    def test_ticket_commands_classify_to_tickets(self):
        """Verify ticket commands resolve to Tickets & Support."""
        ticket_cog = MagicMock(qualified_name="TicketSystem")
        for cmd_name in ["ticket", "close", "reopen", "claim", "transcript", "ticketpanel"]:
            mock_cmd = MagicMock(spec=commands.Command)
            mock_cmd.name = cmd_name
            mock_cmd.qualified_name = cmd_name
            mock_cmd.parent = None
            mock_cmd.root_parent = None
            mock_cmd.cog = ticket_cog

            meta = resolve_command_category(mock_cmd)
            assert meta.id == "tickets", f"Command '{cmd_name}' expected 'tickets', got '{meta.id}'"

    def test_vouch_commands_classify_to_vouches(self):
        """Verify vouch commands resolve to Vouches & Reputation."""
        vouch_cog = MagicMock(qualified_name="Vouches")
        for cmd_name in ["vouch", "vouchprofile", "vouchleaderboard", "heldvouches"]:
            mock_cmd = MagicMock(spec=commands.Command)
            mock_cmd.name = cmd_name
            mock_cmd.qualified_name = cmd_name
            mock_cmd.parent = None
            mock_cmd.root_parent = None
            mock_cmd.cog = vouch_cog

            meta = resolve_command_category(mock_cmd)
            assert meta.id == "vouches", f"Command '{cmd_name}' expected 'vouches', got '{meta.id}'"

    def test_bill_commands_classify_to_service_bills(self):
        """Verify bill commands resolve to Blox Fruits Service Bills."""
        bill_cog = MagicMock(qualified_name="Bills")
        for cmd_name in ["bill", "bills", "paid", "cancelbill", "refund", "billstats"]:
            mock_cmd = MagicMock(spec=commands.Command)
            mock_cmd.name = cmd_name
            mock_cmd.qualified_name = cmd_name
            mock_cmd.parent = None
            mock_cmd.root_parent = None
            mock_cmd.cog = bill_cog

            meta = resolve_command_category(mock_cmd)
            assert meta.id == "service_bills", f"Command '{cmd_name}' expected 'service_bills', got '{meta.id}'"

    def test_query_alias_resolution(self):
        """Verify alias lookups for `+hca <query>` or `+help <query>`."""
        test_queries = {
            "music": "music",
            "audio": "music",
            "ai": "ai",
            "aivoice": "ai",
            "tts": "ai",
            "bloxai": "blox_fruits",
            "bf": "blox_fruits",
            "tickets": "tickets",
            "ticket": "tickets",
            "support": "tickets",
            "vouch": "vouches",
            "rep": "vouches",
            "bill": "service_bills",
            "bills": "service_bills",
            "verify": "verification",
            "mod": "moderation",
            "afk": "afk",
            "rr": "reaction_roles",
            "giveaway": "giveaways",
            "leveling": "leveling",
            "prime": "premium",
            "config": "config",
            "owner": "owner",
        }
        for query, expected_id in test_queries.items():
            meta = get_category_by_query(query)
            assert meta is not None, f"Query '{query}' failed to resolve"
            assert meta.id == expected_id, f"Query '{query}' expected '{expected_id}', got '{meta.id}'"


class TestAssetManager:
    """Test suite verifying localized asset presence, file creation, and fallbacks."""

    def test_help_category_images_exist_locally(self):
        """Verify distinct help category images exist in assets/kyoka/help/."""
        required_help_categories = [
            "home", "general", "moderation", "automod", "welcome", "verification",
            "tickets", "reaction_roles", "giveaways", "music", "afk",
            "vouches", "service_bills", "blox_fruits", "ai", "leveling",
            "premium", "config", "owner",
        ]
        for cat_id in required_help_categories:
            path = AssetManager.get_help_image_path(cat_id)
            assert path is not None, f"Asset path for category '{cat_id}' not found"
            assert path.is_file(), f"Asset file '{path}' does not exist on disk"
            assert path.stat().st_size > 0, f"Asset file '{path}' is empty"

    def test_create_help_file_returns_discord_file(self):
        """Verify create_help_file returns a valid discord.File object."""
        file_obj = AssetManager.create_help_file("music")
        assert isinstance(file_obj, discord.File)
        assert file_obj.filename == "help_music.png"

        file_obj_ai = AssetManager.create_help_file("ai")
        assert isinstance(file_obj_ai, discord.File)
        assert file_obj_ai.filename == "help_ai.png"

    def test_feature_banner_images_exist_locally(self):
        """Verify distinct feature banner images exist in assets/kyoka/features/."""
        features = [
            "welcome_banner", "music_banner", "ai_banner", "blox_fruits_ai",
            "ticket_panel", "vouch_card_background", "service_bill_background",
            "verification_banner", "giveaway_banner", "rank_card_background",
        ]
        for fid in features:
            path = AssetManager.get_feature_image_path(fid)
            assert path is not None, f"Feature banner path for '{fid}' not found"
            assert path.is_file(), f"Feature banner file '{path}' does not exist on disk"

    def test_attach_help_banner_attaches_correctly(self):
        """Verify attaching a help banner sets image URL to attachment:// and returns file."""
        embed = discord.Embed(title="Test Embed")
        file_obj = AssetManager.attach_help_banner(embed, "music")
        assert file_obj is not None
        assert embed.image.url == f"attachment://{file_obj.filename}"

    def test_fallback_when_category_not_found(self):
        """Verify graceful fallback if a non-existent category is requested."""
        embed = discord.Embed(title="Test Fallback")
        file_obj = AssetManager.attach_help_banner(embed, "non_existent_category_xyz")
        # Should fall back to home or safe fallback
        assert embed.image.url is not None


class TestPublicHCAAccess:
    """Test suite verifying public unrestricted access to +hca."""

    def test_hca_command_is_unrestricted(self):
        """Verify that the hca hybrid command has no permission requirements."""
        from src.cogs.general.help import Help

        # Check checks on hca_command
        mock_bot = MagicMock()
        cog = Help(mock_bot)

        hca_cmd = getattr(cog, "hca_command", None)
        assert hca_cmd is not None
        assert isinstance(hca_cmd, (commands.HybridCommand, commands.Command))

        # Ensure no owner-only or admin check was attached
        checks = getattr(hca_cmd, "checks", [])
        for check in checks:
            # Check function names or modules to ensure is_owner / has_permissions is NOT present
            qual = getattr(check, "__qualname__", "")
            assert "is_owner" not in qual, "HCA must not require owner"
            assert "has_permissions" not in qual, "HCA must not require admin/staff permissions"
