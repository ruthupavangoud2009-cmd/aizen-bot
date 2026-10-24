"""
Tests for ErrorHandler and Diagnostic Incident Tracking:
1. User argument errors (MissingRequiredArgument, MemberNotFound) produce friendly guidance instead of unhandled internal error.
2. Genuine unexpected exceptions generate unique diagnostic incident IDs (INC-XXXX).
3. Stack traces and private paths are never leaked to Discord users.
4. Slash command errors are acknowledged with incident IDs.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord import app_commands
from discord.ext import commands
import pytest

from src.errors.handler import ErrorHandler


@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=commands.Bot)
    bot.custom_emojis = {}
    bot.tree = MagicMock()
    return bot


@pytest.fixture
def error_handler(mock_bot):
    return ErrorHandler(mock_bot)


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=commands.Context)
    ctx.prefix = "+"
    ctx.command = MagicMock()
    ctx.command.qualified_name = "vouch"
    ctx.command.signature = "@user <reason>"
    ctx.command.on_error = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.display_name = "TraderSam"
    ctx.author.name = "TraderSam"
    ctx.reply = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_missing_required_argument_produces_friendly_usage(error_handler, mock_ctx):
    """MissingRequiredArgument must display usage syntax rather than an unhandled internal error."""
    param = MagicMock()
    param.name = "member"
    err = commands.MissingRequiredArgument(param)

    with patch("src.errors.handler.send_container_response", new_callable=AsyncMock) as mock_send:
        await error_handler.on_command_error(mock_ctx, err)

        mock_send.assert_called_once()
        container = mock_send.call_args[0][1]
        text_content = str(container.components)
        assert "Invalid Command Usage" in text_content
        assert "Missing required parameter: `member`" in text_content
        assert "+vouch @user <reason>" in text_content


@pytest.mark.asyncio
async def test_member_not_found_produces_friendly_tip(error_handler, mock_ctx):
    """MemberNotFound must provide helpful resolution tips instead of an unhandled internal error."""
    err = commands.MemberNotFound("GhostUser123")

    with patch("src.errors.handler.send_container_response", new_callable=AsyncMock) as mock_send:
        await error_handler.on_command_error(mock_ctx, err)

        mock_send.assert_called_once()
        container = mock_send.call_args[0][1]
        text_content = str(container.components)
        assert "User Not Found" in text_content
        assert "GhostUser123" in text_content
        assert "Tip: Try mentioning the user" in text_content


@pytest.mark.asyncio
async def test_unexpected_error_generates_incident_id(error_handler, mock_ctx):
    """Genuine unexpected exceptions must log securely and display a unique Incident ID (INC-XXXX)."""
    err = RuntimeError("Unexpected connection failure in external database")

    with patch("src.errors.handler.send_container_response", new_callable=AsyncMock) as mock_send:
        await error_handler.on_command_error(mock_ctx, err)

        mock_send.assert_called_once()
        container = mock_send.call_args[0][1]
        text_content = str(container.components)
        assert "Internal Error" in text_content
        assert "INC-" in text_content
        # Ensure raw exception message or paths are NOT exposed to user
        assert "Unexpected connection failure in external database" not in text_content


@pytest.mark.asyncio
async def test_slash_command_error_acknowledged_with_incident_id(error_handler):
    """Slash command exceptions must acknowledge interaction and provide incident ID."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.command = MagicMock()
    interaction.command.name = "vouch"
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()

    slash_err = app_commands.AppCommandError("Uncaught interaction exception")
    await error_handler.on_app_command_error(interaction, slash_err)

    interaction.response.send_message.assert_called_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert "Internal Error" in msg
    assert "INC-" in msg
