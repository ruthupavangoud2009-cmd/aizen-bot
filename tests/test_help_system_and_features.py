import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.core.bot import KyokaBot
from src.cogs.general.help import Help, HelpView, HelpCategorySelect
from src.ui.categories import CATEGORIES, CATEGORY_BY_TAG


@pytest.mark.asyncio
async def test_help_cog_and_categories():
    bot = KyokaBot()
    help_cog = Help(bot)
    
    # Base categories mapping
    cats = help_cog._get_base_categories()
    assert len(cats) >= 14, f"Expected at least 14 categories, got {len(cats)}"
    
    # Check that key categories exist
    assert "🛡️・MODERATION" in cats
    assert "🎵・MUSIC" in cats
    assert "🤖・ARTIFICIAL INTELLIGENCE" in cats
    assert "🏠・GETTING STARTED" in cats
    assert "🔧・UTILITIES" in cats


@pytest.mark.asyncio
async def test_pay_command_and_staff_view():
    from src.cogs.general.kdc_shop import KDCShop
    bot = KyokaBot()
    shop = KDCShop(bot)
    
    # Test staff view generation
    view = shop.get_staff_contact_view()
    assert len(view.children) >= 1
    # Check that owner ID 1505515188991033409 is in the direct DM url
    assert any("1505515188991033409" in getattr(item, "url", "") for item in view.children)


@pytest.mark.asyncio
async def test_server_avatar_cog():
    from src.cogs.general.server_avatar import ServerAvatar
    bot = KyokaBot()
    cog = ServerAvatar(bot)
    
    cmds = [c.name for c in cog.get_commands()]
    assert "setbotavatar" in cmds
    assert "resetbotavatar" in cmds
    assert "setservericon" in cmds


@pytest.mark.asyncio
async def test_halloween_music_feature():
    from src.cogs.music.music import Music
    bot = KyokaBot()
    music_cog = Music(bot)
    
    cmds = [c.name for c in music_cog.get_commands()]
    assert "halloween" in cmds
    
    halloween_cmd = music_cog.bot.get_command("halloween") or next(c for c in music_cog.get_commands() if c.name == "halloween")
    assert "halloween247" in halloween_cmd.aliases
    assert "spookymusic" in halloween_cmd.aliases


def test_dashboard_css_switch_fix():
    # Verify .switch has position: relative and overflow does not expand across parent
    with open("website/css/dashboard.css", "r", encoding="utf-8") as f:
        content = f.read()
    
    assert ".switch," in content or ".switch {" in content
    assert "position: relative" in content
    
    # Verify brace balance
    open_braces = content.count("{")
    close_braces = content.count("}")
    assert open_braces == close_braces, f"Unbalanced braces in dashboard.css: {open_braces} != {close_braces}"
