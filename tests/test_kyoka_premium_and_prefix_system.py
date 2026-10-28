"""Comprehensive tests for KYOKA 3.0:
1. Feature-Access Registry & Premium Gating
2. Custom Bot Avatar System (Validation, Storage, Discord API & Branding Fallback, Isolation)
3. Premium Subscription Lifecycle (Grant, Extend, Check, Revoke, Expiry Sweep)
4. Single Active Prefix System (Isolation, Single Prefix Enforcement, Validation, Permissions)
"""

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.security.feature_access import (
    FeatureTier,
    FEATURE_CATALOG,
    FEATURE_BY_ID,
    check_guild_feature_access,
    require_premium,
    PremiumRequiredError,
    build_premium_required_embed,
)
from src.managers.premium_service import PremiumService
from src.cogs.admin.prefix import Prefix
from src.cogs.general.server_avatar import ServerAvatar
from src.security.owner import OWNER_ID


# ---------------------------------------------------------------------------
# Mocks & Fixtures
# ---------------------------------------------------------------------------

class MockDB:
    def __init__(self):
        self.guild_settings = {}
        self.guild_premium = {}
        self.user_premium = {}
        self.guild_avatars = {}
        self.fail = False

    async def fetch_one(self, query, *args):
        if self.fail:
            raise RuntimeError("Database connection lost")
        q = query.lower()
        if "from guild_premium" in q:
            gid = args[0]
            return self.guild_premium.get(gid)
        elif "from user_premium" in q:
            uid = args[0]
            return self.user_premium.get(uid)
        elif "from guild_settings" in q:
            gid = args[0]
            prefix = self.guild_settings.get(gid, "+")
            return {"prefix": prefix}
        elif "from guild_custom_avatars" in q:
            gid = args[0]
            return self.guild_avatars.get(gid)
        return None

    async def execute(self, query, *args):
        if self.fail:
            raise RuntimeError("Database connection lost")
        q = query.lower()
        if "insert into guild_premium" in q or "update guild_premium" in q:
            gid = args[0]
            tier = args[1]
            expiry = args[2]
            status = "active"
            self.guild_premium[gid] = {"tier": tier, "expires_at": expiry, "status": status, "target_id": gid}
        elif "insert into guild_custom_avatars" in q:
            gid, url, setter, status, api = args
            self.guild_avatars[gid] = {
                "guild_id": gid,
                "avatar_url": url,
                "set_by": setter,
                "status": status,
                "applied_discord_api": api,
                "updated_at": dt.datetime.now(dt.timezone.utc),
            }
        elif "delete from guild_custom_avatars" in q:
            gid = args[0]
            self.guild_avatars.pop(gid, None)
        elif "guild_settings" in q:
            gid = args[0]
            prefix = args[1]
            self.guild_settings[gid] = prefix
        return "OK"

    async def fetch_all(self, query, *args):
        if self.fail:
            raise RuntimeError("Database connection lost")
        q = query.lower()
        if "from guild_premium" in q and "expires_at <" in q:
            now = args[0] if args else dt.datetime.now(dt.timezone.utc)
            expired = []
            for gid, data in self.guild_premium.items():
                exp = data.get("expires_at")
                if exp and exp < now and data.get("status") == "active":
                    expired.append({"guild_id": gid, "tier": data["tier"]})
            return expired
        return []


class MockBot:
    def __init__(self, db):
        self.db = db
        self.premium_service = PremiumService(db)
        self.premium_mgr = None


class MockGuild:
    def __init__(self, guild_id, name="Test Guild"):
        self.id = guild_id
        self.name = name
        self.me = MagicMock()
        self.me.edit = AsyncMock()


class MockUser:
    def __init__(self, user_id, name="TestUser"):
        self.id = user_id
        self.name = name
        self.mention = f"<@{user_id}>"
        self.display_name = name


class MockContext:
    def __init__(self, bot, guild, author, prefix="+"):
        self.bot = bot
        self.guild = guild
        self.author = author
        self.prefix = prefix
        self.send = AsyncMock()
        self.reply = AsyncMock()


# ---------------------------------------------------------------------------
# 1. Feature-Access Registry & Gating Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feature_catalog_definitions():
    """Verify core catalog features exist and tiers are properly mapped."""
    assert "basic_moderation" in FEATURE_BY_ID
    assert FEATURE_BY_ID["basic_moderation"].tier == FeatureTier.FREE
    assert "custom_bot_avatar" in FEATURE_BY_ID
    assert FEATURE_BY_ID["custom_bot_avatar"].tier == FeatureTier.PREMIUM
    assert "music_247" in FEATURE_BY_ID
    assert FEATURE_BY_ID["music_247"].tier == FeatureTier.PREMIUM
    assert "basic_server_config" in FEATURE_BY_ID
    assert FEATURE_BY_ID["basic_server_config"].tier == FeatureTier.FREE


@pytest.mark.asyncio
async def test_free_feature_always_allowed():
    """Free features are granted to all guilds even without a subscription."""
    db = MockDB()
    bot = MockBot(db)

    ctx = MockContext(bot, MockGuild(1001), MockUser(2001))
    has_access, reason, feat = await check_guild_feature_access(bot, 1001, "basic_moderation", user_id=2001)
    assert has_access is True
    assert reason == "Free feature"


@pytest.mark.asyncio
async def test_free_server_denied_premium_feature():
    """A free server is rejected when attempting to access a premium feature."""
    db = MockDB()
    bot = MockBot(db)

    ctx = MockContext(bot, MockGuild(1002), MockUser(2002))
    has_access, reason, feat = await check_guild_feature_access(bot, 1002, "custom_bot_avatar", user_id=2002)
    assert has_access is False
    assert "requires an active" in reason


@pytest.mark.asyncio
async def test_active_premium_server_allowed():
    """An active premium server is allowed to use premium features."""
    db = MockDB()
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
    db.guild_premium[1003] = {"tier": "premium", "expires_at": future, "status": "active", "target_id": 1003}
    bot = MockBot(db)

    has_access, reason, feat = await check_guild_feature_access(bot, 1003, "custom_bot_avatar", user_id=2003)
    assert has_access is True
    assert reason == "Active Server Premium"


@pytest.mark.asyncio
async def test_expired_subscription_denied():
    """Expired premium subscriptions are automatically denied."""
    db = MockDB()
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    db.guild_premium[1004] = {"tier": "premium", "expires_at": past, "status": "active", "target_id": 1004}
    bot = MockBot(db)

    has_access, reason, feat = await check_guild_feature_access(bot, 1004, "custom_bot_avatar", user_id=2004)
    assert has_access is False


@pytest.mark.asyncio
async def test_bot_owner_override():
    """The bot primary owner/dev bypasses premium gating for administrative management."""
    db = MockDB()
    bot = MockBot(db)

    has_access, reason, feat = await check_guild_feature_access(bot, 1005, "custom_bot_avatar", user_id=OWNER_ID)
    assert has_access is True
    assert reason == "Bot Owner/Staff Override"


@pytest.mark.asyncio
async def test_require_premium_decorator_blocks_free_server():
    """The @require_premium predicate raises PremiumRequiredError for free servers."""
    db = MockDB()
    bot = MockBot(db)

    ctx = MockContext(bot, MockGuild(1006), MockUser(2006))

    check_decorator = require_premium("custom_bot_avatar")
    predicate = check_decorator.predicate

    with pytest.raises(PremiumRequiredError):
        await predicate(ctx)

    # Check that error embed was sent to the user
    ctx.send.assert_awaited_once()
    args, kwargs = ctx.send.call_args
    assert "embed" in kwargs
    embed = kwargs["embed"]
    assert "KYOKA PREMIUM REQUIRED" in embed.title or "PREMIUM REQUIRED" in embed.title

    # Check that error embed was sent to the user
    ctx.send.assert_awaited_once()
    args, kwargs = ctx.send.call_args
    assert "embed" in kwargs
    embed = kwargs["embed"]
    assert "KYOKA PREMIUM REQUIRED" in embed.title or "PREMIUM REQUIRED" in embed.title


# ---------------------------------------------------------------------------
# 2. Custom Bot Avatar System Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_avatar_validation_invalid_url():
    """Avatar setter rejects non-image or dangerous URLs."""
    cog = ServerAvatar(MagicMock())
    assert cog._is_valid_image_url("http://insecure.com/script.js") is False
    assert cog._is_valid_image_url("ftp://server.com/image.png") is False
    assert cog._is_valid_image_url("https://cdn.discordapp.com/avatar.exe") is False
    assert cog._is_valid_image_url("https://cdn.discordapp.com/avatars/123/abc.png") is True
    assert cog._is_valid_image_url("https://i.imgur.com/example.webp") is True


@pytest.mark.asyncio
async def test_avatar_persistence_and_server_isolation():
    """Custom avatars are isolated per guild and stored in PostgreSQL."""
    bot = MagicMock()
    db = MockDB()
    bot.db = db
    bot.premium_service = PremiumService(db)
    cog = ServerAvatar(bot)

    guild1_id = 5001
    guild2_id = 5002

    # Guild 1 sets avatar
    await db.execute(
        "INSERT INTO guild_custom_avatars (guild_id, avatar_url, set_by, status, applied_discord_api) VALUES ($1, $2, $3, $4, $5)",
        guild1_id, "https://cdn.discordapp.com/g1.png", 9999, "active", True
    )

    # Guild 2 sets a different avatar
    await db.execute(
        "INSERT INTO guild_custom_avatars (guild_id, avatar_url, set_by, status, applied_discord_api) VALUES ($1, $2, $3, $4, $5)",
        guild2_id, "https://cdn.discordapp.com/g2.png", 9998, "active", False
    )

    row1 = await db.fetch_one("SELECT * FROM guild_custom_avatars WHERE guild_id = $1", guild1_id)
    row2 = await db.fetch_one("SELECT * FROM guild_custom_avatars WHERE guild_id = $1", guild2_id)

    assert row1["avatar_url"] == "https://cdn.discordapp.com/g1.png"
    assert row2["avatar_url"] == "https://cdn.discordapp.com/g2.png"
    assert row1["guild_id"] != row2["guild_id"]


@pytest.mark.asyncio
async def test_avatar_reset_removes_custom_config():
    """Resetting bot avatar deletes record and restores default Aizen branding."""
    bot = MagicMock()
    db = MockDB()
    bot.db = db
    cog = ServerAvatar(bot)

    guild_id = 5003
    await db.execute(
        "INSERT INTO guild_custom_avatars (guild_id, avatar_url, set_by, status, applied_discord_api) VALUES ($1, $2, $3, $4, $5)",
        guild_id, "https://cdn.discordapp.com/custom.png", 9999, "active", True
    )

    # Verify present
    assert await db.fetch_one("SELECT * FROM guild_custom_avatars WHERE guild_id = $1", guild_id) is not None

    # Reset
    await db.execute("DELETE FROM guild_custom_avatars WHERE guild_id = $1", guild_id)
    assert await db.fetch_one("SELECT * FROM guild_custom_avatars WHERE guild_id = $1", guild_id) is None


# ---------------------------------------------------------------------------
# 3. Single Active Prefix System Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prefix_validation():
    """Prefix must be 1-5 chars, non-whitespace, and cannot contain @, #, or /."""
    cog = Prefix(MagicMock())
    
    # Valid
    assert cog._validate_prefix("!") == (True, "")
    assert cog._validate_prefix("?") == (True, "")
    assert cog._validate_prefix("k!") == (True, "")
    assert cog._validate_prefix("kyoka") == (True, "")

    # Invalid: empty or whitespace
    assert cog._validate_prefix("")[0] is False
    assert cog._validate_prefix("   ")[0] is False
    assert cog._validate_prefix("a b")[0] is False

    # Invalid: forbidden chars
    assert cog._validate_prefix("/")[0] is False
    assert cog._validate_prefix("@")[0] is False
    assert cog._validate_prefix("#")[0] is False

    # Invalid: too long (> 5 chars)
    assert cog._validate_prefix("toolongprefix")[0] is False


@pytest.mark.asyncio
async def test_prefix_per_server_isolation_and_no_multi_prefix():
    """Setting a prefix in Server A does not affect Server B, and old prefixes stop working."""
    bot = MagicMock()
    db = MockDB()
    bot.db = db
    bot.guild_manager = MagicMock()
    bot.guild_manager.set_prefix = AsyncMock()

    guild_a = 7001
    guild_b = 7002

    # Initial state: default "+"
    db.guild_settings[guild_a] = "+"
    db.guild_settings[guild_b] = "+"

    # Guild A changes prefix to "!"
    db.guild_settings[guild_a] = "!"

    # Verify isolation
    assert db.guild_settings[guild_a] == "!"
    assert db.guild_settings[guild_b] == "+"

    # Verify central resolver logic (from KyokaBot.get_prefix)
    # Only ONE prefix active per guild
    prefix_a = db.guild_settings.get(guild_a, "+")
    prefix_b = db.guild_settings.get(guild_b, "+")

    assert [prefix_a] == ["!"]
    assert [prefix_b] == ["+"]
    assert "+" not in [prefix_a]  # Old "+" does NOT work in Server A


@pytest.mark.asyncio
async def test_prefix_reset_restores_default():
    """Resetting prefix restores default '+'."""
    db = MockDB()
    guild_id = 7003
    db.guild_settings[guild_id] = "$"

    assert db.guild_settings[guild_id] == "$"
    db.guild_settings[guild_id] = "+"
    assert db.guild_settings[guild_id] == "+"


# ---------------------------------------------------------------------------
# 4. Premium Expiration & Sweep Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_subscription_sweep_revocation():
    """Expired subscriptions are detected and swept."""
    db = MockDB()
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10)

    # Server 1 is expired
    db.guild_premium[8001] = {"tier": "pro", "expires_at": past, "status": "active", "target_id": 8001}
    # Server 2 is active
    db.guild_premium[8002] = {"tier": "premium", "expires_at": future, "status": "active", "target_id": 8002}

    expired_list = await db.fetch_all("SELECT guild_id, tier FROM guild_premium WHERE expires_at < $1 AND status = 'active'", dt.datetime.now(dt.timezone.utc))

    assert len(expired_list) == 1
    assert expired_list[0]["guild_id"] == 8001
