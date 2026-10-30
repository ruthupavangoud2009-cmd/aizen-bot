import discord
import pytest
from discord import app_commands
from discord.ext import commands

from src.core.permissions import install_bot_staff_permission_overrides
from src.security import owner as owner_security


@pytest.mark.asyncio
async def test_bot_staff_bypass_guild_permission_checks_without_granting_dm_access(monkeypatch):
    install_bot_staff_permission_overrides()
    monkeypatch.setattr("src.core.permissions.is_bot_staff", lambda user_id: user_id == 42)

    check = commands.has_guild_permissions(manage_messages=True)
    ctx = type("Context", (), {})()
    ctx.guild = object()
    ctx.author = type("Author", (), {"id": 42, "guild_permissions": discord.Permissions.none()})()

    assert await check.predicate(ctx)

    ctx.author.id = 43
    with pytest.raises(commands.MissingPermissions):
        await check.predicate(ctx)

    ctx.author.id = 42
    ctx.guild = None
    with pytest.raises(commands.NoPrivateMessage):
        await check.predicate(ctx)


@pytest.mark.asyncio
async def test_bot_staff_bypass_slash_permission_checks(monkeypatch):
    install_bot_staff_permission_overrides()
    monkeypatch.setattr("src.core.permissions.is_bot_staff", lambda user_id: user_id == 42)
    monkeypatch.setattr(owner_security, "is_bot_staff", lambda user_id: user_id == 42)

    @app_commands.checks.has_permissions(manage_messages=True)
    async def callback():
        return None

    predicate = callback.__discord_app_commands_checks__[0]
    interaction = type("Interaction", (), {})()
    interaction.guild_id = 123
    interaction.user = type("User", (), {"id": 42})()
    interaction.permissions = discord.Permissions.none()

    assert await predicate(interaction)


@pytest.mark.asyncio
async def test_bot_staff_can_manage_premium_but_not_global_owner_controls(monkeypatch):
    monkeypatch.setattr(owner_security, "is_bot_staff", lambda user_id: user_id == 42)
    ctx = type("Context", (), {})()
    ctx.author = type("Author", (), {"id": 42, "send": _async_noop})()
    ctx.bot = type("Bot", (), {"db": type("Database", (), {"execute": _async_noop})()})()
    ctx.interaction = None
    ctx.send = _async_noop

    assert await owner_security.authorize_owner(ctx, "premium-grant")
    assert not await owner_security.authorize_owner(ctx, "restart-request")


async def _async_noop(*args, **kwargs):
    return None
