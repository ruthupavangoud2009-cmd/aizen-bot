import pytest
import unittest.mock as mock
import discord
from discord.ext import commands
from src.core.bot import get_prefix, KyokaBot
from src.cogs.fun.ai_voice import AIVoice
from src.managers.voice_conversation_manager import VoiceConversationManager, CONVERSATIONAL_VIBES, HUMAN_VOICES


@pytest.mark.asyncio
async def test_get_prefix_supports_question_mark_and_standard_fallbacks():
    """Verify get_prefix resolves configured prefix as well as ?, +, , fallbacks."""
    mock_bot = mock.MagicMock(spec=KyokaBot)
    mock_bot.user = None
    mock_bot.no_prefix_users = set()

    mock_guild_mgr = mock.MagicMock()
    mock_guild_mgr.get_prefix.return_value = "+"
    mock_bot.guild_mgr = mock_guild_mgr

    mock_msg = mock.MagicMock(spec=discord.Message)
    mock_msg.guild = mock.MagicMock(id=123456789)
    mock_msg.author = mock.MagicMock(id=987654321)

    prefixes = await get_prefix(mock_bot, mock_msg)
    assert "?" in prefixes, "? prefix must be supported so ?commands work"
    assert "+" in prefixes, "+ prefix must be supported"
    assert "," in prefixes, ", prefix must be supported"


def test_vctalkpartner_command_and_aliases():
    """Verify vctalkpartner is registered with vctalkpatner alias and correct metadata."""
    bot = commands.Bot(command_prefix="+", intents=discord.Intents.none())
    cog = AIVoice(bot)

    cmd = cog.cmd_vctalkpartner
    assert cmd.name == "vctalkpartner"
    assert "vctalkpatner" in cmd.aliases, "Exact user-requested typo vctalkpatner must be an alias"
    assert "vcpartner" in cmd.aliases
    assert "talkpartner" in cmd.aliases
    assert "aipartner" in cmd.aliases


def test_voice_conversation_vibes_and_voices():
    """Verify neural voice personas and human vibes are fully configured."""
    assert "ava" in HUMAN_VOICES
    assert "andrew" in HUMAN_VOICES
    assert "kyoka" in HUMAN_VOICES
    assert "aizen" in HUMAN_VOICES

    assert "normal" in CONVERSATIONAL_VIBES
    assert "gamer" in CONVERSATIONAL_VIBES
    assert "chill" in CONVERSATIONAL_VIBES
    assert "tsundere" in CONVERSATIONAL_VIBES

    # Manager session testing
    mgr = VoiceConversationManager()
    session = mgr.start_session(
        guild_id=111,
        channel_id=222,
        channel_name="lounge",
        text_channel_id=333,
        started_by_id=444,
        started_by_name="User",
        voice_key="ava",
        mode="open",
        vibe="normal",
    )
    assert session.active is True
    assert mgr.is_active(111) is True

    hud = mgr.render_voice_hud(session)
    assert isinstance(hud, discord.Embed)
    assert "NEURAL VOICE HUD" in hud.title

    stopped = mgr.stop_session(111)
    assert stopped.active is False
    assert mgr.is_active(111) is False


@pytest.mark.asyncio
async def test_all_cogs_load_cleanly_and_join_in_tree():
    """Verify that music, events, and ai_voice load with zero collision and /join exists in tree."""
    bot = KyokaBot()
    # Explicitly load in collision-prone reverse order
    await bot.load_extension("src.cogs.utility.events")
    await bot.load_extension("src.cogs.music.music")
    await bot.load_extension("src.cogs.fun.ai_voice")

    join_cmd = bot.tree.get_command("join")
    assert join_cmd is not None, "/join command must be present in bot tree"

    vctalk_cmd = bot.tree.get_command("vctalkpartner")
    assert vctalk_cmd is not None, "/vctalkpartner must be present in bot tree"


@pytest.mark.asyncio
async def test_ticket_ai_interactive_dialogue():
    """Verify ticket AI maintains multi-turn dialogue memory for interactive conversations."""
    from src.cogs.ticket.ticket_system import TicketSystem
    bot = KyokaBot()
    cog = TicketSystem(bot)

    mock_guild = mock.MagicMock(id=999, name="Test Guild")
    mock_user = mock.MagicMock(id=888, display_name="TestUser")

    sol1 = await cog.generate_ticket_solution(
        query="I have a bug with my inventory",
        category="Technical Support",
        guild=mock_guild,
        user=mock_user,
        channel_id=777,
    )
    assert len(sol1) > 10
    assert 777 in cog._ticket_dialogues
    assert len(cog._ticket_dialogues[777]) >= 2
    assert cog._ticket_dialogues[777][0]["speaker"] == "TestUser"
    assert cog._ticket_dialogues[777][1]["speaker"] == "Kyoka AI"


@pytest.mark.asyncio
async def test_compact_help_ui():
    """Verify that Help UI is ultra-compact: minimal fields, single-row buttons, no banner bloat."""
    from src.cogs.general.help import Help, HelpView
    bot = KyokaBot()
    cog = Help(bot)

    mock_guild = mock.MagicMock(id=123)
    mock_author = mock.MagicMock(display_name="Ruthu", display_avatar=mock.MagicMock(url="https://avatar.png"))
    mock_ctx = mock.MagicMock(guild=mock_guild, author=mock_author, interaction=None)

    cmd_sample = mock.MagicMock(qualified_name="play", description="Play music in voice", aliases=["p"])
    visible_cats = {"🎵・MUSIC": [cmd_sample]}

    home_embed = cog.build_home_embed(mock_ctx, visible_cats)
    assert len(home_embed.fields) == 0, "Home embed must have 0 bloated fields for minimal height"
    assert "Help Menu" in home_embed.title
    assert home_embed.image.url is None, "Home embed must not have large banner image"

    cat_embed = cog.build_category_embed(mock_ctx, "🎵・MUSIC", [cmd_sample], visible_cats, page=1)
    assert len(cat_embed.fields) == 0, "Category embed must not have separate field per command"
    assert "`" in cat_embed.description
    assert cat_embed.image.url is None, "Category embed must not have large banner image"

    view = HelpView(cog, mock_ctx, visible_cats, current_category="home")
    rows_used = {item.row for item in view.children}
    assert 2 not in rows_used, "HelpView must not use Row 2 to ensure ultra-small height"

    cat_view = HelpView(cog, mock_ctx, visible_cats, current_category="🎵・MUSIC")
    cat_rows = {item.row for item in cat_view.children}
    assert 2 not in cat_rows, "Category HelpView must not use Row 2"


@pytest.mark.asyncio
async def test_direct_stream_support_and_jiosaavn_unblocked_source():
    """Verify that GuildPlayer supports direct streams from Saavn/SoundCloud and falls back smoothly."""
    from src.cogs.music._player import GuildPlayer
    bot = KyokaBot()
    guild = mock.MagicMock(id=123)
    player = GuildPlayer(bot, guild)

    # Verify _is_direct_stream_url recognizes Saavn and SoundCloud streams
    assert player._is_direct_stream_url("https://aac.saavncdn.com/123/sample_320.mp4") is True
    assert player._is_direct_stream_url("https://playback.media-streaming.soundcloud.cloud/sample/playlist.m3u8") is True
    assert player._is_direct_stream_url("https://youtube.com/watch?v=abc") is False
    assert player._is_direct_stream_url("https://open.spotify.com/track/xyz") is False


