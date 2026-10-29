from unittest.mock import AsyncMock, MagicMock

import pytest

from src.cogs.fun.games import InteractivePollView
from src.cogs.fun.games import Games


@pytest.mark.asyncio
async def test_poll_command_keeps_message_for_timeout_cleanup():
    message = MagicMock()
    ctx = MagicMock()
    ctx.prefix = "+"
    ctx.author = MagicMock(display_name="Poll author")
    ctx.send = AsyncMock(return_value=message)

    games = Games(MagicMock())
    await games.poll.callback(games, ctx, poll_input="Favorite color? | Blue | Green")

    sent_view = ctx.send.await_args.kwargs["view"]
    assert sent_view.message is message


@pytest.mark.asyncio
async def test_poll_timeout_disables_controls_and_edits_message():
    view = InteractivePollView("Favorite color?", ["Blue", "Green"], MagicMock(display_name="Poll author"))
    message = MagicMock()
    message.edit = AsyncMock()
    view.message = message

    await view.on_timeout()

    assert all(button.disabled for button in view.children)
    message.edit.assert_awaited_once_with(view=view)
