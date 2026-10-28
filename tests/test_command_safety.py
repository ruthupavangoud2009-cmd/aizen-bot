from types import SimpleNamespace

import pytest

from src.cogs.developer.owner_system import OwnerSystem
from src.cogs.fun.fun import Fun, parse_guess_bounds
from src.cogs.general.help import Help
from src.cogs.general.ping import parse_repeated_ping


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<@123456789012345678> 3", (123456789012345678, 3)),
        ("3 <@!123456789012345678>", (123456789012345678, 3)),
        ("123456789012345678 5", (123456789012345678, 5)),
    ],
)
def test_ping_parses_target_and_count_in_either_order(value, expected):
    assert parse_repeated_ping(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "<@123456789012345678>",
        "<@123456789012345678> 0",
        "<@123456789012345678> 6",
        "<@123456789012345678> 1 2",
        "no target 3",
    ],
)
def test_ping_rejects_invalid_or_over_limit_arguments(value):
    with pytest.raises(ValueError):
        parse_repeated_ping(value)


@pytest.mark.parametrize(("value", "expected"), [("1-1000", (1, 1000)), ("50 - 70", (50, 70))])
def test_guess_range_is_inclusive_and_validated(value, expected):
    assert parse_guess_bounds(value) == expected


@pytest.mark.parametrize("value", ["", "5-5", "10-1", "-1-100", "1-1000002", "99999999999-100000000000"])
def test_guess_range_rejects_invalid_bounds(value):
    with pytest.raises(ValueError):
        parse_guess_bounds(value)


def test_owner_premium_management_does_not_collide_with_public_premium():
    assert OwnerSystem.owner_premium.name == "owner-premium"
    assert Help.view_plan.name == "premium"


@pytest.mark.parametrize("category", ["Owner", "Developer"])
def test_public_help_hides_owner_and_developer_commands(category):
    command = SimpleNamespace(hidden=False, cog=SimpleNamespace(category=category))
    assert not Help._can_run_command(command)


def test_public_help_keeps_real_public_commands_visible():
    command = SimpleNamespace(hidden=False, cog=SimpleNamespace(category="Fun"))
    assert Help._can_run_command(command)


class FakeDB:
    def __init__(self):
        self.queries = []

    async def fetch_one(self, query, *args):
        self.queries.append((query, args))
        return {"guess": args[-1]}

    async def execute(self, query, *args):
        self.queries.append((query, args))


class FakeMessage:
    def __init__(self, channel_id, guess, user_id=7):
        self.author = SimpleNamespace(bot=False, id=user_id, mention=f"<@{user_id}>")
        self.guild = object()
        self.channel = SimpleNamespace(id=channel_id, sent=[])
        self.content = str(guess)
        self.reactions = []
        self.replies = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def reply(self, content, **kwargs):
        self.replies.append(content)


@pytest.mark.asyncio
async def test_guess_game_low_high_correct_and_concurrent_channels():
    db = FakeDB()
    fun = Fun(SimpleNamespace(db=db))
    future = 4_000_000_000
    fun.games = {
        10: {"game_id": 101, "answer": 50, "low": 1, "high": 100, "starter": 1, "expires_at": future},
        20: {"game_id": 202, "answer": 20, "low": 1, "high": 100, "starter": 2, "expires_at": future},
    }

    low = FakeMessage(10, 25)
    high = FakeMessage(20, 60)
    correct = FakeMessage(10, 50, user_id=8)
    await fun.on_message(low)
    await fun.on_message(high)
    await fun.on_message(correct)

    assert low.reactions == ["➕"]
    assert high.reactions == ["➖"]
    assert "got it" in correct.replies[0]
    assert "The illusion is broken" in correct.replies[0]
    assert 10 not in fun.games and 20 in fun.games


@pytest.mark.asyncio
async def test_guess_game_rejects_out_of_range_and_repeated_guesses():
    db = FakeDB()
    fun = Fun(SimpleNamespace(db=db))
    fun.games[10] = {
        "game_id": 101,
        "answer": 50,
        "low": 1,
        "high": 100,
        "starter": 1,
        "expires_at": 4_000_000_000,
    }

    out_of_range = FakeMessage(10, 101)
    await fun.on_message(out_of_range)
    assert "between 1 and 100" in out_of_range.replies[0]
    assert not db.queries

    repeated = FakeMessage(10, 25)
    db.fetch_one = lambda *args: _resolved(None)
    await fun.on_message(repeated)
    assert repeated.reactions == ["🔁"]


async def _resolved(value):
    return value
