from unittest.mock import AsyncMock, MagicMock

import pytest

from src.cogs.fun.ai_voice import AIVoice
from src.cogs.fun.games import (
    Games,
    HideAndSeekView,
    ReactionRaceView,
    TwoTruthsView,
)


def interaction(user_id: int, voice_channel_id: int | None = None) -> MagicMock:
    item = MagicMock()
    item.user.id = user_id
    item.user.mention = f"<@{user_id}>"
    item.user.voice.channel.id = voice_channel_id
    item.response.send_message = AsyncMock()
    item.response.edit_message = AsyncMock()
    item.followup.send = AsyncMock()
    return item


@pytest.mark.asyncio
async def test_games_list_uses_server_prefix_and_lists_new_games():
    cog = Games(MagicMock())
    ctx = MagicMock()
    ctx.prefix = "!"
    ctx.send = AsyncMock()

    await cog.game_list.callback(cog, ctx)

    description = ctx.send.await_args.kwargs["embed"].description
    assert "`!vctrivia`" in description
    assert "`!reactionrace`" in description
    assert "`!hideandseek`" in description
    assert "`!twotruths" in description
    assert "`!tod`" in description


@pytest.mark.asyncio
async def test_voice_trivia_awards_first_correct_answer_from_voice():
    cog = AIVoice(MagicMock())
    guild = MagicMock(id=300)
    channel = MagicMock()
    channel.id = 400
    channel.send = AsyncMock()
    member = MagicMock(id=2, mention="<@2>", bot=False)
    member.voice.channel.id = 500
    message = MagicMock()
    message.author = member
    message.guild = guild
    message.channel = channel
    message.content = "Kyoka Suigetsu!"
    message.reply = AsyncMock()

    cog._active_voice_trivia[guild.id] = {
        "answer": "kyoka suigetsu",
        "answer_display": "Kyoka Suigetsu",
        "question": "What is Aizen's sword?",
        "voice_channel_id": 500,
        "text_channel_id": 400,
        "expires_at": 9999999999,
    }

    outsider_message = MagicMock()
    outsider_message.author = MagicMock(id=1, bot=False)
    outsider_message.author.voice.channel.id = 501
    outsider_message.guild = guild
    outsider_message.channel = channel
    outsider_message.content = "Kyoka Suigetsu!"
    outsider_message.reply = AsyncMock()
    await cog.on_message(outsider_message)
    outsider_message.reply.assert_not_awaited()
    assert guild.id in cog._active_voice_trivia

    await cog.on_message(message)

    message.reply.assert_awaited_once()
    channel.send.assert_awaited_once()
    embed = channel.send.await_args.kwargs["embed"]
    assert "Voice Trivia Champion" in embed.title
    assert embed.image.url.startswith("https://")
    assert guild.id not in cog._active_voice_trivia


@pytest.mark.asyncio
async def test_reaction_race_eliminates_early_click_and_announces_first_valid_click():
    view = ReactionRaceView()
    button = view.children[0]

    early = interaction(10)
    await button.callback(early)
    assert 10 in view.disqualified

    view.started = True
    still_early = interaction(10)
    await button.callback(still_early)
    still_early.response.send_message.assert_awaited_once()
    assert view.winner_id is None

    winner = interaction(11)
    await button.callback(winner)
    assert view.winner_id == 11
    embed = winner.response.edit_message.await_args.kwargs["embed"]
    assert "Reaction Race Winner" in embed.title
    assert embed.image.url.startswith("https://")
    assert view.is_finished()


@pytest.mark.asyncio
async def test_hide_and_seek_reveals_treasure_to_first_finder():
    view = HideAndSeekView(hidden_index=0)

    searcher = interaction(20)
    await view.children[1].callback(searcher)
    searcher.followup.send.assert_awaited_once()
    assert view.children[1].disabled

    winner = interaction(21)
    await view.children[0].callback(winner)
    embed = winner.response.edit_message.await_args.kwargs["embed"]
    assert "Scavenger Hunt Winner" in embed.title
    assert embed.image.url.startswith("https://")
    assert view.is_finished()


@pytest.mark.asyncio
async def test_two_truths_reveal_shows_correct_voters_and_celebration():
    view = TwoTruthsView(30, ["A", "B", "C"], lie_index=1)

    voter = interaction(31)
    await view.children[1].callback(voter)
    voter.response.send_message.assert_awaited_once()

    host = interaction(30)
    await view.children[3].callback(host)
    embed = host.response.edit_message.await_args.kwargs["embed"]
    assert "statement 2" in embed.description
    assert "<@31>" in embed.description
    assert embed.image.url.startswith("https://")
    assert view.is_finished()
