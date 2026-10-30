from __future__ import annotations

import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from dashboard_api.routes.watch_routes import _player_link
from src.cogs.developer.global_support import GlobalSupport
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
