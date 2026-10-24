"""
Tests for Absolute AFK Safety:
1. Enabling AFK never modifies usernames or server nicknames.
2. Mentioning an AFK member never modifies usernames or server nicknames.
3. Returning from AFK never modifies usernames or server nicknames.
4. Clearing AFK never modifies usernames or server nicknames.
5. Verifies zero calls to member.edit(nick=...) in the entire AFK system.
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import pytest

from src.cogs.utility.afk import AFKCog, AFKData


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.execute = AsyncMock()
    bot.db.fetch_all = AsyncMock(return_value=[])
    bot.get_context = AsyncMock()
    bot.custom_emojis = {}
    return bot


@pytest.fixture
def afk_cog(mock_bot):
    cog = AFKCog(mock_bot)
    cog._loaded = True
    for attr in dir(cog):
        val = getattr(cog, attr)
        if isinstance(val, (commands.Command, commands.HybridCommand)):
            val.cog = cog
    return cog


@pytest.fixture
def mock_member():
    m = MagicMock(spec=discord.Member)
    m.id = 123456789
    m.name = "AizenTaicho"
    m.display_name = "AizenTaicho"
    m.nick = "LordAizen"
    m.mention = "<@123456789>"
    m.bot = False
    m.display_avatar.url = "https://example.com/avatar.png"
    m.edit = AsyncMock()
    return m


@pytest.fixture
def mock_ctx(mock_member):
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 999888777
    ctx.guild.name = "Las Noches"
    ctx.guild.owner_id = 111222333
    ctx.guild.me = MagicMock()
    ctx.guild.me.guild_permissions.manage_nicknames = True
    ctx.guild.me.guild_permissions.administrator = True
    ctx.guild.me.top_role = MagicMock()
    mock_member.top_role = MagicMock()

    ctx.author = mock_member
    ctx.reply = AsyncMock()
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


@pytest.mark.asyncio
async def test_afk_command_never_changes_nickname(afk_cog, mock_ctx, mock_member):
    """Enabling AFK must store status but NEVER call member.edit(nick=...)."""
    with patch("src.cogs.utility.afk.send_container_response", new_callable=AsyncMock) as mock_send:
        await afk_cog.afk(mock_ctx, reason="Planning Karakura Town invasion")

        # Verify AFK cache was updated
        key = (mock_member.id, mock_ctx.guild.id)
        assert key in afk_cog._afk_cache
        entry = afk_cog._afk_cache[key]
        assert entry.reason == "Planning Karakura Town invasion"
        assert entry.nickname_changed is False
        assert entry.original_nickname is None

        # Absolute rule verification: member.edit MUST NEVER be called
        mock_member.edit.assert_not_called()
        assert mock_member.nick == "LordAizen"
        assert mock_member.display_name == "AizenTaicho"

        # Verify response was sent
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_afk_mention_never_changes_nickname(afk_cog, mock_member):
    """Mentioning an AFK member notifies chat but NEVER alters nicknames."""
    # Seed AFK cache
    guild_id = 999888777
    afk_cog._afk_cache[(mock_member.id, guild_id)] = AFKData(
        user_id=mock_member.id,
        guild_id=guild_id,
        reason="In Las Noches",
        created_at=discord.utils.utcnow(),
    )

    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(spec=discord.Member)
    msg.author.id = 555666777
    msg.author.name = "Gin"
    msg.author.bot = False
    msg.guild = MagicMock()
    msg.guild.id = guild_id
    msg.channel = MagicMock()
    msg.mentions = [mock_member]
    msg.content = "Where is <@123456789>?"

    with patch("src.cogs.utility.afk.send_container_response", new_callable=AsyncMock) as mock_send:
        await afk_cog.on_message(msg)

        # Verification: member.edit was NOT called
        mock_member.edit.assert_not_called()
        assert mock_member.nick == "LordAizen"
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_afk_return_never_changes_nickname(afk_cog, mock_member):
    """Returning from AFK clears status and welcomes back but NEVER modifies nicknames."""
    guild_id = 999888777
    afk_cog._afk_cache[(mock_member.id, guild_id)] = AFKData(
        user_id=mock_member.id,
        guild_id=guild_id,
        reason="Meditating with Hōgyoku",
        created_at=discord.utils.utcnow(),
        nickname_changed=False,
        original_nickname=None,
    )

    msg = MagicMock(spec=discord.Message)
    msg.author = mock_member
    msg.guild = MagicMock()
    msg.guild.id = guild_id
    msg.channel = MagicMock()
    msg.mentions = []
    msg.content = "I have returned to the throne."

    # get_context returns invalid command so welcome back triggers
    ctx = MagicMock()
    ctx.valid = False
    afk_cog.bot.get_context.return_value = ctx

    with patch("src.cogs.utility.afk.send_container_response", new_callable=AsyncMock) as mock_send:
        await afk_cog.on_message(msg)

        # Status cleared from cache
        assert (mock_member.id, guild_id) not in afk_cog._afk_cache

        # Absolute rule verification: member.edit was NEVER called
        mock_member.edit.assert_not_called()
        assert mock_member.nick == "LordAizen"
        mock_send.assert_called_once()


def test_afk_source_code_has_zero_nickname_modifications():
    """Static AST audit of afk.py to guarantee no member.edit(nick=...) exists anywhere."""
    afk_file = Path("src/cogs/utility/afk.py")
    assert afk_file.exists()

    tree = ast.parse(afk_file.read_text(encoding="utf-8"))

    # Search for any function call to .edit with keyword argument 'nick'
    forbidden_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "edit":
                for kw in node.keywords:
                    if kw.arg == "nick":
                        forbidden_calls.append(node.lineno)

    assert len(forbidden_calls) == 0, f"Found forbidden member.edit(nick=...) at lines: {forbidden_calls}"
