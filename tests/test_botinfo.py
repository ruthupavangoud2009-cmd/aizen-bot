from datetime import timedelta
from types import SimpleNamespace

import discord

from src.cogs.general.botinfo import BotInfoView, build_botinfo_container
from src.core.config import Config


def _text(container):
    return "\n".join(
        component["content"]
        for component in container.components
        if component["type"] == 10
    )


def test_botinfo_contains_public_identity_runtime_and_support_details():
    now = discord.utils.utcnow()
    bot = SimpleNamespace(
        start_time=now - timedelta(hours=2, minutes=5),
        latency=0.042,
        guilds=[SimpleNamespace(member_count=10), SimpleNamespace(member_count=25)],
        user=SimpleNamespace(
            name="KYOKA 2.0",
            id=123456789012345678,
            display_avatar=SimpleNamespace(url="https://cdn.example.test/avatar.png"),
        ),
        guild_mgr=SimpleNamespace(get_prefix=lambda guild_id: "&"),
        premium_mgr=SimpleNamespace(
            get_guild_info=lambda guild_id: {
                "is_premium": True,
                "tier": "Premium",
                "remaining_str": "30 days",
            }
        ),
    )

    text = _text(build_botinfo_container(bot, 1))

    assert "KYOKA 2.0" in text
    assert "1505515188991033409" in text
    assert "123456789012345678" in text
    assert "2h 5m" in text
    assert "42 ms" in text
    assert "Servers:** `2`" in text
    assert "Members across servers:** `35`" in text
    assert "discord.py" in text
    assert "Python" in text
    assert "`&`" in text and "`&help`" in text
    assert "Premium" in text
    assert "https://discord.gg/5DBQTQJa9" in text


def test_botinfo_handles_missing_optional_state_and_omits_invalid_invite():
    bot = SimpleNamespace(
        guilds=[],
        latency=float("nan"),
        user=None,
        application_id=None,
    )
    text = _text(build_botinfo_container(bot))

    assert "Bot ID:** `Unavailable`" in text
    assert "API latency:** `Unavailable`" in text
    assert "0 Members" in text

    view = BotInfoView("not-a-url")
    assert [button.label for button in view.children] == ["Support Server"]
    assert view.children[0].url == "https://discord.gg/5DBQTQJa9"


def test_botinfo_view_adds_only_a_valid_optional_invite():
    view = BotInfoView("https://discord.com/oauth2/authorize?client_id=1")

    assert [button.label for button in view.children] == [
        "Invite KYOKA",
        "Support Server",
    ]
    assert Config.BOT_NAME in ("KYOKA 2.0", "KYOKA 3.0")
