"""
Kyoka 3.0 - Server-Specific Branding System Automated Tests
Verifies:
1. Strict server isolation across multiple guilds (Guild A vs Guild B vs unconfigured vs DMs).
2. Resetting one server does not impact other servers.
3. Setting each field independently (name, avatar, banner, bio).
4. Cache invalidation on updates and resets.
5. Permission security (Manage Server, Administrator, Guild Owner, Bot Owner vs unauthorized members).
6. Input validation (name length, bio length, invalid URLs, file formats, size checks).
7. Discord API limitation handling (genuine nickname changes vs Discord member avatar restrictions).
8. Integration with Help and BotInfo UI embeds.
9. Hybrid command registration for prefix and slash compatibility.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord.ext import commands

from src.managers.branding_manager import BrandingManager
from src.cogs.admin.branding import Branding
from src.cogs.general.help import Help
from src.cogs.general.botinfo import BotInfo
from src.core.bot import KyokaBot
from src.security.owner import OWNER_ID


class InMemoryBrandingDB:
    """Mock database storing guild_branding rows for reliable unit testing."""

    def __init__(self) -> None:
        self.rows: dict[int, dict[str, Any]] = {}

    async def fetch_one(self, query: str, guild_id: int) -> dict[str, Any] | None:
        row = self.rows.get(guild_id)
        return dict(row) if row else None

    async def execute(self, query: str, *args: Any) -> None:
        clean_q = query.strip().upper()
        if clean_q.startswith("INSERT INTO GUILD_BRANDING"):
            # Arguments: guild_id, value, set_by
            guild_id = args[0]
            val = args[1]
            set_by = args[2]

            field = "display_name"
            if "bio" in query.lower().split("values")[0]:
                field = "bio"
            elif "avatar_url" in query.lower().split("values")[0]:
                field = "avatar_url"
            elif "banner_url" in query.lower().split("values")[0]:
                field = "banner_url"

            applied_nick = False
            applied_avatar = False
            if "applied_nickname" in query:
                applied_nick = "TRUE" in query
            if "applied_discord_avatar" in query:
                applied_avatar = "TRUE" in query

            if guild_id not in self.rows:
                self.rows[guild_id] = {
                    "guild_id": guild_id,
                    "display_name": None,
                    "bio": None,
                    "avatar_url": None,
                    "banner_url": None,
                    "set_by": set_by,
                    "applied_nickname": applied_nick,
                    "applied_discord_avatar": applied_avatar,
                    "updated_at": "2026-10-28T20:00:00Z",
                }
            self.rows[guild_id][field] = val
            self.rows[guild_id]["set_by"] = set_by
            if "applied_nickname" in query:
                self.rows[guild_id]["applied_nickname"] = applied_nick
            if "applied_discord_avatar" in query:
                self.rows[guild_id]["applied_discord_avatar"] = applied_avatar

        elif clean_q.startswith("DELETE FROM GUILD_BRANDING"):
            guild_id = args[0]
            self.rows.pop(guild_id, None)


@pytest.fixture
def mock_db() -> InMemoryBrandingDB:
    return InMemoryBrandingDB()


@pytest.fixture
def branding_mgr(mock_db: InMemoryBrandingDB) -> BrandingManager:
    return BrandingManager(mock_db)  # type: ignore


@pytest.fixture
def mock_bot(branding_mgr: BrandingManager, mock_db: InMemoryBrandingDB) -> KyokaBot:
    bot = KyokaBot()
    bot.branding_mgr = branding_mgr
    bot.db = mock_db  # type: ignore
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777
    bot.guild_mgr = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "?"
    bot.session = MagicMock()
    return bot


@pytest.fixture
def branding_cog(mock_bot: KyokaBot) -> Branding:
    return Branding(mock_bot)


@pytest.mark.asyncio
async def test_branding_default_unconfigured_and_dm(branding_mgr: BrandingManager):
    """Verify DMs and unconfigured servers safely fall back to global default KYOKA branding."""
    # 1. DM context (guild_id is None)
    dm_brand = await branding_mgr.get_branding(None)
    assert dm_brand["guild_id"] is None
    assert dm_brand["display_name"] == "KYOKA 3.0"
    assert "Sosuke Aizen" in dm_brand["bio"]
    assert dm_brand["is_custom"] is False

    # 2. Unconfigured guild (e.g. guild 3003)
    unconf_brand = await branding_mgr.get_branding(3003)
    assert unconf_brand["guild_id"] == 3003
    assert unconf_brand["display_name"] == "KYOKA 3.0"
    assert "Sosuke Aizen" in unconf_brand["bio"]
    assert unconf_brand["is_custom"] is False


@pytest.mark.asyncio
async def test_strict_server_isolation(branding_mgr: BrandingManager):
    """Verify Server A, Server B, and Unconfigured Server C remain completely isolated."""
    guild_a = 1001
    guild_b = 2002
    guild_c = 3003

    # Server A customizes name and avatar
    await branding_mgr.set_field(guild_a, "display_name", "Soul Society Kyoka", set_by=111)
    await branding_mgr.set_field(guild_a, "avatar_url", "https://cdn.discordapp.com/avatars/1/a.png", set_by=111)

    # Server B customizes bio and banner
    await branding_mgr.set_field(guild_b, "display_name", "Hueco Mundo Bot", set_by=222)
    await branding_mgr.set_field(guild_b, "bio", "The Espada Commander.", set_by=222)
    await branding_mgr.set_field(guild_b, "banner_url", "https://cdn.discordapp.com/attachments/2/b.png", set_by=222)

    # Retrieve all three
    brand_a = await branding_mgr.get_branding(guild_a)
    brand_b = await branding_mgr.get_branding(guild_b)
    brand_c = await branding_mgr.get_branding(guild_c)

    # Verify Server A
    assert brand_a["display_name"] == "Soul Society Kyoka"
    assert brand_a["avatar_url"] == "https://cdn.discordapp.com/avatars/1/a.png"
    assert "Sosuke Aizen" in brand_a["bio"]  # Unset field falls back to default
    assert brand_a["is_custom"] is True

    # Verify Server B
    assert brand_b["display_name"] == "Hueco Mundo Bot"
    assert brand_b["bio"] == "The Espada Commander."
    assert brand_b["banner_url"] == "https://cdn.discordapp.com/attachments/2/b.png"
    assert brand_b["avatar_url"] == branding_mgr.get_default_branding()["avatar_url"]  # Fallback
    assert brand_b["is_custom"] is True

    # Verify Server C is unaffected
    assert brand_c["display_name"] == "KYOKA 3.0"
    assert brand_c["is_custom"] is False

    # Reset Server A
    await branding_mgr.reset_branding(guild_a)

    reset_a = await branding_mgr.get_branding(guild_a)
    assert reset_a["display_name"] == "KYOKA 3.0"
    assert reset_a["is_custom"] is False

    # Verify Server B is STILL completely intact after Server A was reset!
    fresh_b = await branding_mgr.get_branding(guild_b)
    assert fresh_b["display_name"] == "Hueco Mundo Bot"
    assert fresh_b["bio"] == "The Espada Commander."
    assert fresh_b["banner_url"] == "https://cdn.discordapp.com/attachments/2/b.png"


@pytest.mark.asyncio
async def test_setting_fields_independently_and_caching(branding_mgr: BrandingManager):
    """Verify each branding field can be set independently with proper cache invalidation."""
    gid = 4004
    defaults = branding_mgr.get_default_branding()

    # Step 1: Set only name
    await branding_mgr.set_field(gid, "display_name", "Custom Name", set_by=999)
    b1 = await branding_mgr.get_branding(gid)
    assert b1["display_name"] == "Custom Name"
    assert b1["bio"] == defaults["bio"]
    assert b1["avatar_url"] == defaults["avatar_url"]
    assert b1["banner_url"] == defaults["banner_url"]

    # Verify cache is populated
    assert gid in branding_mgr._cache

    # Step 2: Set bio
    await branding_mgr.set_field(gid, "bio", "Custom Bio 123", set_by=999)
    b2 = await branding_mgr.get_branding(gid)
    assert b2["display_name"] == "Custom Name"
    assert b2["bio"] == "Custom Bio 123"

    # Step 3: Invalidate cache manually
    branding_mgr.invalidate_cache(gid)
    assert gid not in branding_mgr._cache

    # Subsequent fetch pulls freshly from DB and re-caches
    b3 = await branding_mgr.get_branding(gid)
    assert b3["display_name"] == "Custom Name"
    assert b3["bio"] == "Custom Bio 123"
    assert gid in branding_mgr._cache


def test_permission_enforcement(branding_cog: Branding):
    """Verify only authorized roles (Admin, Manage Server, Guild Owner, Bot Owner) can modify branding."""
    # 1. Non-admin regular user -> Rejected
    ctx_normal = MagicMock()
    ctx_normal.guild = MagicMock(owner_id=1111)
    ctx_normal.author = MagicMock(id=9999)
    ctx_normal.author.guild_permissions = discord.Permissions(send_messages=True)
    assert branding_cog._can_manage_branding(ctx_normal) is False

    # 2. Administrator -> Allowed
    ctx_admin = MagicMock()
    ctx_admin.guild = MagicMock(owner_id=1111)
    ctx_admin.author = MagicMock(id=2222)
    ctx_admin.author.guild_permissions = discord.Permissions(administrator=True)
    assert branding_cog._can_manage_branding(ctx_admin) is True

    # 3. Manage Guild -> Allowed
    ctx_mgr = MagicMock()
    ctx_mgr.guild = MagicMock(owner_id=1111)
    ctx_mgr.author = MagicMock(id=3333)
    ctx_mgr.author.guild_permissions = discord.Permissions(manage_guild=True)
    assert branding_cog._can_manage_branding(ctx_mgr) is True

    # 4. Guild Owner -> Allowed
    ctx_owner = MagicMock()
    ctx_owner.guild = MagicMock(owner_id=4444)
    ctx_owner.author = MagicMock(id=4444)
    ctx_owner.author.guild_permissions = discord.Permissions(send_messages=True)
    assert branding_cog._can_manage_branding(ctx_owner) is True

    # 5. Bot Primary Owner -> Allowed
    ctx_botowner = MagicMock()
    ctx_botowner.guild = MagicMock(owner_id=1111)
    ctx_botowner.author = MagicMock(id=OWNER_ID)
    assert branding_cog._can_manage_branding(ctx_botowner) is True


@pytest.mark.asyncio
async def test_input_validation(branding_cog: Branding):
    """Verify validation on empty names, name length limits, bio limits, and invalid URLs."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=5005, name="Validation Guild")
    ctx.author = MagicMock(id=OWNER_ID)
    ctx.send = AsyncMock()
    ctx.send_warning = AsyncMock()

    # 1. Empty name
    await branding_cog.setbot_name.callback(branding_cog, ctx, name="   ")
    assert ctx.send_warning.called
    assert "empty" in ctx.send_warning.call_args[0][0].lower()

    # 2. Overlong name (>32 chars)
    ctx.send_warning.reset_mock()
    await branding_cog.setbot_name.callback(branding_cog, ctx, name="A" * 33)
    assert ctx.send_warning.called
    assert "32" in ctx.send_warning.call_args[0][0]

    # 3. Overlong bio (>300 chars)
    ctx.send_warning.reset_mock()
    await branding_cog.setbot_bio.callback(branding_cog, ctx, text="B" * 301)
    assert ctx.send_warning.called
    assert "300" in ctx.send_warning.call_args[0][0]

    # 4. Invalid URL scheme/extension for avatar
    assert branding_cog._is_valid_image_url("http://insecure.com/pic.png") is False
    assert branding_cog._is_valid_image_url("https://example.com/malicious.exe") is False
    assert branding_cog._is_valid_image_url("https://cdn.discordapp.com/avatars/1/abc.png") is True


@pytest.mark.asyncio
async def test_discord_api_nickname_success_and_forbidden_handling(branding_cog: Branding, mock_bot: KyokaBot):
    """Verify setbot name edits Discord bot nickname when permitted, and explains restrictions when forbidden."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=6006, name="Nick Guild")
    ctx.author = MagicMock(id=OWNER_ID, mention="<@123>")
    ctx.send = AsyncMock()
    ctx.send_warning = AsyncMock()

    # Case A: Discord API succeeds
    ctx.guild.me.edit = AsyncMock()
    await branding_cog.setbot_name.callback(branding_cog, ctx, name="Kyoka Aizen")
    assert ctx.guild.me.edit.called
    assert ctx.guild.me.edit.call_args[1]["nick"] == "Kyoka Aizen"
    assert ctx.send.called
    embed = ctx.send.call_args[1]["embed"]
    assert "Updated Successfully" in embed.description

    # Case B: Discord API raises Forbidden (bot lacks change nickname permission or role hierarchy)
    ctx.guild.me.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing Permissions"))
    ctx.send.reset_mock()
    await branding_cog.setbot_name.callback(branding_cog, ctx, name="Kyoka Sovereign")
    assert ctx.send.called
    embed2 = ctx.send.call_args[1]["embed"]
    assert "Preserved (Embeds Only)" in embed2.description
    # Visual branding is still saved in DB
    brand = await mock_bot.branding_mgr.get_branding(6006)
    assert brand["display_name"] == "Kyoka Sovereign"


@pytest.mark.asyncio
async def test_discord_api_avatar_nitro_restriction_handling(branding_cog: Branding, mock_bot: KyokaBot):
    """Verify setbot avatar attempts member avatar edit, handles Discord Nitro limitation, and activates visual engine."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=7007, name="Avatar Guild")
    ctx.author = MagicMock(id=OWNER_ID, mention="<@123>")
    ctx.send = AsyncMock()
    ctx.send_warning = AsyncMock()
    ctx.message = MagicMock(attachments=[])

    valid_url = "https://cdn.discordapp.com/attachments/123/avatar.png"

    # Mock HTTP response downloading valid image
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "image/png"}
    mock_resp.read = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfakeimagebytes")
    mock_bot.session.get.return_value.__aenter__.return_value = mock_resp

    # Discord API returns 400 Bad Request because bot user lacks Nitro for per-guild avatar
    mock_response = MagicMock(status=400, reason="Bad Request")
    ctx.guild.me.edit = AsyncMock(side_effect=discord.HTTPException(mock_response, "Member avatar restricted"))

    await branding_cog.setbot_avatar.callback(branding_cog, ctx, image_url=valid_url)

    assert ctx.send.called
    embed = ctx.send.call_args[1]["embed"]
    assert "Strict Server Isolation" in embed.description
    assert "successfully updated" in embed.description

    # Ensure branding is stored in DB and cached
    brand = await mock_bot.branding_mgr.get_branding(7007)
    assert brand["avatar_url"] == valid_url


@pytest.mark.asyncio
async def test_setbot_view_and_reset(branding_cog: Branding, mock_bot: KyokaBot):
    """Verify setbot view shows configured settings and setbot reset returns all fields to defaults."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=8008, name="Reset Guild")
    ctx.author = MagicMock(id=OWNER_ID, mention="<@123>")
    ctx.send = AsyncMock()

    # Configure custom fields
    await mock_bot.branding_mgr.set_field(8008, "display_name", "Temporary Kyoka", set_by=111)
    await mock_bot.branding_mgr.set_field(8008, "bio", "Temporary bio description", set_by=111)

    # 1. View
    await branding_cog.setbot_view.callback(branding_cog, ctx)
    assert ctx.send.called
    view_embed = ctx.send.call_args[1]["embed"]
    assert "Temporary Kyoka" in view_embed.fields[0].value
    assert "Temporary bio description" in view_embed.fields[1].value

    # 2. Reset
    ctx.guild.me.edit = AsyncMock()
    ctx.send.reset_mock()
    await branding_cog.setbot_reset.callback(branding_cog, ctx)
    assert ctx.send.called
    reset_embed = ctx.send.call_args[1]["embed"]
    assert "DEFAULT BRANDING RESTORED" in reset_embed.title

    # 3. View again after reset
    ctx.send.reset_mock()
    await branding_cog.setbot_view.callback(branding_cog, ctx)
    view_embed2 = ctx.send.call_args[1]["embed"]
    assert "Default KYOKA Branding" in view_embed2.description
    assert "KYOKA 3.0" in view_embed2.fields[0].value


def test_branding_hybrid_command_structure(branding_cog: Branding):
    """Verify setbot command group and all subcommands are hybrid commands."""
    assert isinstance(branding_cog.setbot, commands.HybridGroup)
    expected_subcommands = {"name", "avatar", "banner", "bio", "reset", "view"}
    registered_subcommands = {sub.name for sub in branding_cog.setbot.commands}
    assert expected_subcommands.issubset(registered_subcommands)


@pytest.mark.asyncio
async def test_help_and_botinfo_branding_integration(mock_bot: KyokaBot):
    """Verify Help and BotInfo UI embeds utilize server-specific branding."""
    gid = 9009
    await mock_bot.branding_mgr.set_field(gid, "display_name", "Aizen Kyoka Custom", set_by=123)
    await mock_bot.branding_mgr.set_field(gid, "bio", "Sovereign of Las Noches custom bio.", set_by=123)
    await mock_bot.branding_mgr.set_field(gid, "avatar_url", "https://cdn.discordapp.com/avatars/9009/custom.png", set_by=123)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=gid, name="Integration Guild")
    ctx.author = MagicMock(id=555, display_name="Captain")
    ctx.author.display_avatar.url = "https://cdn.discord.com/avatars/555/avatar.png"
    ctx.clean_prefix = "?"

    # 1. Test Help Cog Home Embed
    help_cog = Help(mock_bot)
    # Pre-populate cache
    await mock_bot.branding_mgr.get_branding(gid)
    home_embed = help_cog.build_home_embed(ctx, {"🛡️・MODERATION": [MagicMock(qualified_name="ban")]})
    assert "Aizen Kyoka Custom" in home_embed.title
    assert "Sovereign of Las Noches custom bio." in home_embed.description
    assert home_embed.thumbnail.url == "https://cdn.discordapp.com/avatars/9009/custom.png"

    # 2. Test BotInfo Container
    from src.cogs.general.botinfo import build_botinfo_container
    container = build_botinfo_container(mock_bot, gid)
    text_content = "\n".join(c.get("content", "") for c in container.components if isinstance(c, dict))
    assert "Aizen Kyoka Custom" in text_content
    assert "Sovereign of Las Noches custom bio." in text_content


def test_botedit_command_and_subcommand_aliases(branding_cog: Branding):
    """Verify botedit is a valid alias for setbot, and avater is an alias for avatar."""
    # Group alias check
    assert "botedit" in branding_cog.setbot.aliases
    assert "botbrand" in branding_cog.setbot.aliases

    # Subcommand aliases
    avatar_cmd = branding_cog.setbot.get_command("avatar")
    assert avatar_cmd is not None
    assert "avater" in avatar_cmd.aliases
    assert "pfp" in avatar_cmd.aliases

    banner_cmd = branding_cog.setbot.get_command("banner")
    assert banner_cmd is not None
    assert "header" in banner_cmd.aliases

    bio_cmd = branding_cog.setbot.get_command("bio")
    assert bio_cmd is not None
    assert "about" in bio_cmd.aliases
    assert "desc" in bio_cmd.aliases


@pytest.mark.asyncio
async def test_server_bio_visibility_isolation(mock_bot: KyokaBot, branding_cog: Branding):
    """
    Verify botedit bio:
    - People in THIS server see the custom bio.
    - People in ANY OTHER server or DMs see the normal global bio.
    """
    server_a = 5111
    server_b = 5222

    # Configure custom bio only in Server A
    await mock_bot.branding_mgr.set_field(
        server_a, "bio", "Only people in Server A can see this bio!", set_by=123
    )
    # Pre-cache Server A
    await mock_bot.branding_mgr.get_branding(server_a)

    # 1. Inspect Server A via botinfo
    from src.cogs.general.botinfo import build_botinfo_container
    container_a = build_botinfo_container(mock_bot, server_a)
    text_a = "\n".join(c.get("content", "") for c in container_a.components if isinstance(c, dict))
    assert "Only people in Server A can see this bio!" in text_a

    # 2. Inspect Server B (unconfigured) via botinfo -> Must see normal bio!
    container_b = build_botinfo_container(mock_bot, server_b)
    text_b = "\n".join(c.get("content", "") for c in container_b.components if isinstance(c, dict))
    assert "Only people in Server A can see this bio!" not in text_b
    assert "Sosuke Aizen" in text_b

    # 3. Inspect in DMs (guild_id is None) via botinfo -> Must see normal bio!
    container_dm = build_botinfo_container(mock_bot, None)
    text_dm = "\n".join(c.get("content", "") for c in container_dm.components if isinstance(c, dict))
    assert "Only people in Server A can see this bio!" not in text_dm
    assert "Sosuke Aizen" in text_dm

    # 4. Running botedit bio with no args in Server A shows current bio and confirms isolation
    ctx_a = MagicMock()
    ctx_a.guild = MagicMock(id=server_a, name="Server A")
    ctx_a.send = AsyncMock()
    await branding_cog.setbot_bio.callback(branding_cog, ctx_a, text=None)
    assert ctx_a.send.called
    embed_a = ctx_a.send.call_args[1]["embed"]
    assert "Only people in Server A can see this bio!" in embed_a.description
    assert "Only people in this server can see this bio" in embed_a.description
    assert "normal global bio" in embed_a.description


@pytest.mark.asyncio
async def test_botedit_no_argument_views(branding_cog: Branding, mock_bot: KyokaBot):
    """Verify running botedit avatar, banner, or name without arguments safely displays the current setting."""
    gid = 6333
    await mock_bot.branding_mgr.set_field(gid, "display_name", "Cool Bot", set_by=1)
    await mock_bot.branding_mgr.set_field(gid, "avatar_url", "https://cdn.discordapp.com/avatars/6333/cool.png", set_by=1)
    await mock_bot.branding_mgr.set_field(gid, "banner_url", "https://cdn.discordapp.com/attachments/6333/banner.png", set_by=1)
    await mock_bot.branding_mgr.get_branding(gid)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=gid, name="View Guild")
    ctx.message = MagicMock(attachments=[])
    ctx.send = AsyncMock()
    ctx.send_warning = AsyncMock()

    # 1. Avatar view
    await branding_cog.setbot_avatar.callback(branding_cog, ctx, image=None, image_url=None)
    assert ctx.send.called
    av_embed = ctx.send.call_args[1]["embed"]
    assert "SERVER BOT AVATAR" in av_embed.title
    assert av_embed.thumbnail.url == "https://cdn.discordapp.com/avatars/6333/cool.png"

    # 2. Banner view
    ctx.send.reset_mock()
    await branding_cog.setbot_banner.callback(branding_cog, ctx, image=None, image_url=None)
    assert ctx.send.called
    banner_embed = ctx.send.call_args[1]["embed"]
    assert "SERVER BOT BANNER" in banner_embed.title
    assert banner_embed.image.url == "https://cdn.discordapp.com/attachments/6333/banner.png"

    # 3. Name view
    ctx.send.reset_mock()
    await branding_cog.setbot_name.callback(branding_cog, ctx, name=None)
    assert ctx.send.called
    name_embed = ctx.send.call_args[1]["embed"]
    assert "Cool Bot" in name_embed.description

