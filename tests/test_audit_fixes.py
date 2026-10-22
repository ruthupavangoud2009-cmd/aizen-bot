from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from src.core.config import Config
from src.core.bot import KyroBot, KyokaBot
from src.utils.containers import KyroContainer, KyokaContainer, build_container_payload
from src.cogs.general.channelinfo import ChannelInfo
from src.cogs.music._commands.nowplaying import execute_nowplaying
from src.cogs.utility.giveaway import Giveaways
from src.managers.dev_pulse_manager import DevPulseManager


def test_containers_backward_compatibility():
    assert KyroContainer is KyokaContainer
    assert KyroBot is KyokaBot
    container = KyroContainer()
    container.add_text("Hello world")
    payload = build_container_payload([container])
    assert "components" in payload


@pytest.mark.asyncio
async def test_channelinfo_builds_container_without_name_error():
    bot = SimpleNamespace()
    cog = ChannelInfo(bot)
    ctx = SimpleNamespace(
        channel=SimpleNamespace(
            name="general",
            id=123456789,
            type=discord.ChannelType.text,
            category=SimpleNamespace(name="Chat"),
            created_at=discord.utils.utcnow(),
            topic="Test topic",
            slowmode_delay=0,
            nsfw=False,
            bitrate=None,
        ),
        author=SimpleNamespace(display_name="TestUser"),
        guild=SimpleNamespace(id=1),
    )
    # mock send_container_response
    sent_containers = []
    async def fake_send(target, container, **kwargs):
        sent_containers.append(container)
        return MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.cogs.general.channelinfo.send_container_response", fake_send)
        await cog.channelinfo.callback(cog, ctx, None)

    assert len(sent_containers) == 1
    text_content = sent_containers[0].components[0]["content"]
    assert "#general" in text_content
    assert "123456789" in text_content


@pytest.mark.asyncio
async def test_nowplaying_handles_stopped_and_playing_without_name_error():
    cog = SimpleNamespace(
        controller=SimpleNamespace(
            get_player=lambda guild_id: None
        ),
        bot=SimpleNamespace(custom_emojis=None),
    )
    ctx = SimpleNamespace(
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(),
    )
    sent = []
    async def fake_send(target, container, **kwargs):
        sent.append(container)
        return MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.cogs.music._commands.nowplaying.send_container_response", fake_send)
        await execute_nowplaying(cog, ctx)

    assert len(sent) == 1
    assert "Nothing is currently playing" in sent[0].components[0]["content"]


@pytest.mark.asyncio
async def test_giveaway_role_requirement_check_with_dot():
    bot = SimpleNamespace(
        db=SimpleNamespace(
            fetch_one=AsyncMock(return_value={
                "id": 99,
                "is_ended": False,
                "required_role_id": 555,
            })
        ),
        giveaway_mgr=SimpleNamespace(
            active_giveaways={
                123: {
                    "id": 99,
                    "is_ended": False,
                    "required_role_id": 555,
                }
            },
            get_giveaway_by_message_id=lambda mid: {
                "id": 99,
                "is_ended": False,
                "required_role_id": 555,
            },
        ),
        custom_emojis=SimpleNamespace(get=lambda k, d="": d),
        add_view=MagicMock(),
    )
    role = SimpleNamespace(id=555, mention="<@&555>")
    guild = SimpleNamespace(get_role=lambda rid: role)
    member = MagicMock(spec=discord.Member)
    member.roles = []
    member.display_name = "LuckyGuy"

    interaction = SimpleNamespace(
        message=SimpleNamespace(id=123),
        guild=guild,
        user=member,
        response=SimpleNamespace(
            is_done=lambda: False,
            defer=AsyncMock(),
        ),
    )

    from src.cogs.utility.giveaway import PersistentGiveawayView
    view = PersistentGiveawayView(bot)

    sent = []
    async def fake_send(target, container, **kwargs):
        sent.append(container)
        return MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.cogs.utility.giveaway.send_container_response", fake_send)
        await view.enter_giveaway.callback(interaction)

    assert len(sent) == 1
    content = sent[0].components[2]["content"]
    assert "You need the <@&555> role to enter this giveaway" in content


def test_permission_manager_is_developer_check():
    from src.managers.permission_manager import is_developer
    check = is_developer()
    assert callable(check.predicate)
