from __future__ import annotations

import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import discord
from discord.ext import commands

from dashboard_api.routes.watch_routes import _player_link
from src.cogs.developer.global_support import GlobalSupport
from src.cogs.general.watch_party import WatchParty, normalize_youtube_url
from src.core.config import Config
from src.security.owner import OWNER_ID
from src.watch_party import new_token, token_hash, validate_media_url


@pytest.mark.parametrize(
    "url",
    [
        "https://media.example/video.mp4",
        "https://media.example/video.WEBM?download=1",
        "https://media.example/audio.ogg",
    ],
)
def test_watch_party_accepts_supported_https_media(url: str) -> None:
    assert validate_media_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://media.example/video.mp4",
        "https://media.example/video.mp4.evil",
        "https://localhost/video.mp4",
        "https://127.0.0.1/video.mp4",
        "https://user:password@media.example/video.mp4",
        "https://media.example:444/video.mp4",
    ],
)
def test_watch_party_rejects_unsupported_or_private_media(url: str) -> None:
    assert not validate_media_url(url)


def test_watch_player_link_keeps_secrets_in_fragment() -> None:
    link = _player_link(
        "https://aizen-bot.pages.dev",
        "room-123",
        "guest-secret",
        "invite-secret",
    )
    parsed = urlsplit(link)

    assert parsed.scheme == "https"
    assert parsed.path == "/watch.html"
    assert parse_qs(parsed.query) == {"room": ["room-123"]}
    assert parse_qs(parsed.fragment) == {
        "key": ["guest-secret"],
        "invite": ["invite-secret"],
    }


def test_watch_party_tokens_are_unpredictable_and_hashed() -> None:
    first, second = new_token(), new_token()

    assert first != second
    assert token_hash(first) != first
    assert token_hash(first) == token_hash(first)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=Abcdefghijk", "https://www.youtube.com/watch?v=Abcdefghijk"),
        ("https://youtu.be/Abcdefghijk?t=42", "https://www.youtube.com/watch?v=Abcdefghijk"),
        ("https://youtube.com/shorts/Abcdefghijk", "https://www.youtube.com/watch?v=Abcdefghijk"),
        ("https://www.youtube.com/playlist?list=PLabcdefghij", "https://www.youtube.com/playlist?list=PLabcdefghij"),
    ],
)
def test_watch_party_normalizes_supported_youtube_urls(url: str, expected: str) -> None:
    assert normalize_youtube_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=Abcdefghijk",
        "https://youtube.com.attacker.example/watch?v=Abcdefghijk",
        "https://youtube.com@attacker.example/watch?v=Abcdefghijk",
        "https://youtube.com:444/watch?v=Abcdefghijk",
        "https://www.youtube.com/watch?v=short",
    ],
)
def test_watch_party_rejects_unsafe_youtube_urls(url: str) -> None:
    assert normalize_youtube_url(url) is None


def test_watch_party_youtube_request_posts_link_for_discord_native_preview() -> None:
    async def run() -> None:
        class FakeContext:
            author = SimpleNamespace(mention="<@123>")
            interaction = None

            def __init__(self) -> None:
                self.messages: list[str] = []

            async def send(self, content: str, *, embed: object = None) -> None:
                self.messages.append(content)

        context = FakeContext()
        cog = WatchParty(SimpleNamespace())
        await WatchParty.watch_play.callback(cog, context, "https://youtu.be/Abcdefghijk")

        assert len(context.messages) == 1
        assert "https://www.youtube.com/watch?v=Abcdefghijk" in context.messages[0]
        assert "Discord will show its native YouTube preview" in context.messages[0]
        assert "cannot broadcast YouTube audio/video into a voice channel" in context.messages[0]

    asyncio.run(run())


def test_watch_root_accepts_a_youtube_url() -> None:
    async def run() -> None:
        class FakeContext:
            author = SimpleNamespace(mention="<@123>")
            interaction = None

            def __init__(self) -> None:
                self.messages: list[str] = []

            async def send(self, content: str, *, embed: object = None) -> None:
                self.messages.append(content)

        context = FakeContext()
        cog = WatchParty(SimpleNamespace())
        await WatchParty.watch.callback(cog, context, "https://www.youtube.com/watch?v=Abcdefghijk")

        assert len(context.messages) == 1
        assert "https://www.youtube.com/watch?v=Abcdefghijk" in context.messages[0]

    asyncio.run(run())


def test_watch_party_and_monitor_extensions_load_without_command_collisions() -> None:
    async def run() -> None:
        bot = commands.Bot(command_prefix="+", intents=discord.Intents.none())
        try:
            await bot.load_extension("src.cogs.general.watch_party")
            await bot.load_extension("src.cogs.developer.monitor")

            watch = bot.get_command("watch")
            assert watch is not None
            assert watch.cog.__class__.__module__ == "src.cogs.general.watch_party"

            for name in ("botmonitor", "monitor", "htop", "live"):
                command = bot.get_command(name)
                assert command is not None
                assert command.cog.__class__.__module__ == "src.cogs.developer.monitor"
        finally:
            await bot.close()

    asyncio.run(run())


class _FakeDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> None:
        self.calls.append((query, args))


class _FakeContext:
    def __init__(self, user_id: int) -> None:
        self.author = SimpleNamespace(id=user_id)
        self.interaction = None
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


def test_globalsupport_persists_owner_update_and_rejects_non_invites() -> None:
    async def run() -> None:
        original_url = Config.SUPPORT_URL
        database = _FakeDatabase()
        cog = GlobalSupport(SimpleNamespace(db=database))
        owner_context = _FakeContext(OWNER_ID)
        outsider_context = _FakeContext(OWNER_ID + 1)

        try:
            await GlobalSupport.global_support.callback(
                cog, owner_context, "https://discord.gg/new-support"
            )
            assert Config.SUPPORT_URL == "https://discord.gg/new-support"
            assert len(database.calls) == 1
            assert database.calls[0][1] == ("https://discord.gg/new-support",)

            await GlobalSupport.global_support.callback(
                cog, owner_context, "https://example.com/not-a-discord-invite"
            )
            assert len(database.calls) == 1

            await GlobalSupport.global_support.callback(
                cog, outsider_context, "https://discord.gg/unauthorized"
            )
            assert len(database.calls) == 1
            assert "Only the primary bot owner" in outsider_context.sent[-1]
        finally:
            Config.SUPPORT_URL = original_url

    asyncio.run(run())
