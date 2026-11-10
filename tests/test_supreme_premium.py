import pytest
from unittest.mock import MagicMock
from src.core.config import Config
from src.security.feature_access import FeatureTier, check_guild_feature_access, get_feature
from src.managers.premium_manager import PremiumManager
from src.security.owner import OWNER_ID, is_primary_owner

@pytest.mark.asyncio
async def test_supreme_premium_config_and_tier():
    assert Config.SUPREME_PREMIUM is True
    assert FeatureTier.SUPREME.value == "supreme"

@pytest.mark.asyncio
async def test_supreme_feature_access_bypass():
    bot_mock = MagicMock()
    bot_mock.premium_mgr = None

    # Check premium features: music_247, custom_bot_avatar, advanced_tickets, premium_ai
    for feat_id in ["music_247", "custom_bot_avatar", "advanced_tickets", "premium_ai"]:
        has_access, reason, feat = await check_guild_feature_access(
            bot=bot_mock,
            guild_id=987654321,
            feature_id=feat_id,
            user_id=123456789,
        )
        assert has_access is True
        assert "Supreme" in reason

@pytest.mark.asyncio
async def test_supreme_premium_manager_status():
    db_mock = MagicMock()
    prem_mgr = PremiumManager(db=db_mock)

    # Guild check
    assert prem_mgr.is_guild_premium(111222333) is True
    guild_info = prem_mgr.get_guild_info(111222333)
    assert guild_info["is_premium"] is True
    assert "Supreme" in guild_info["tier"]
    assert "SUPREME PREMIUM" in guild_info.get("badge", "")

    # User check
    assert prem_mgr.is_user_premium(444555666) is True
    user_info = prem_mgr.get_user_info(444555666)
    assert user_info["is_premium"] is True
    assert "Supreme" in user_info["tier"]
    assert "SUPREME PREMIUM" in user_info.get("badge", "")

@pytest.mark.asyncio
async def test_hardcoded_owner_supreme_status():
    assert OWNER_ID == 1505515188991033409
    assert is_primary_owner(OWNER_ID) is True

    db_mock = MagicMock()
    prem_mgr = PremiumManager(db=db_mock)
    owner_info = prem_mgr.get_user_info(OWNER_ID)
    assert owner_info["is_premium"] is True
    assert "Owner" in owner_info["tier"] or "Supreme" in owner_info.get("badge", "")

