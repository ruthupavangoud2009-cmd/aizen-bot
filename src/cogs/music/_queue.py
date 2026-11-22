"""
KYOKA — Smart Queue & Instant Playback Preload Engine
====================================================

Manages thread-safe guild queues, query caching, background track preloading,
and instant queue transitions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from src.cogs.music._models import Track

if TYPE_CHECKING:
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyoka.Music.Queue")


class SearchCache:
    """
    High-Performance Memory Search Cache.
    Caches resolved search results to provide instant (< 1ms) responses for repeated queries.
    """

    def __init__(self, ttl_seconds: float = 7200.0, max_entries: int = 1000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._cache: Dict[str, tuple[float, list[Track]]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(query: str) -> str:
        return query.strip().lower()

    async def get(self, query: str) -> Optional[list[Track]]:
        norm = self._key(query)
        async with self._lock:
            if norm in self._cache:
                timestamp, tracks = self._cache[norm]
                if time.time() - timestamp < self.ttl_seconds:
                    logger.debug(f"Search cache HIT for '{query}' ({len(tracks)} tracks)")
                    return tracks
                else:
                    self._cache.pop(norm, None)
        return None

    async def set(self, query: str, tracks: list[Track]) -> None:
        if not tracks:
            return
        norm = self._key(query)
        async with self._lock:
            if len(self._cache) >= self.max_entries:
                # Remove oldest entry
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                self._cache.pop(oldest_key, None)
            self._cache[norm] = (time.time(), tracks)


class SmartQueue:
    """
    Concurrency-Safe Smart Queue for GuildPlayer with instant preloading,
    duplicate track detection, and state serialization.
    """

    def __init__(self, player: Optional[GuildPlayer] = None) -> None:
        self.player = player
        self._tracks: List[Track] = []
        self._lock = asyncio.Lock()
        self._preload_task: Optional[asyncio.Task] = None

    def __len__(self) -> int:
        return len(self._tracks)

    @property
    def is_empty(self) -> bool:
        return len(self._tracks) == 0

    def get_tracks(self) -> List[Track]:
        """Return a copy of the upcoming tracks."""
        return list(self._tracks)

    async def add(self, track: Track) -> None:
        """Thread-safely append a track and schedule background preloading."""
        async with self._lock:
            self._tracks.append(track)
        self.trigger_preload()

    async def add_all(self, tracks: List[Track]) -> int:
        """Thread-safely append multiple tracks and schedule background preloading."""
        async with self._lock:
            self._tracks.extend(tracks)
        self.trigger_preload()
        return len(tracks)

    async def pop(self) -> Optional[Track]:
        """Thread-safely pop the next track from the front of the queue."""
        async with self._lock:
            if self._tracks:
                track = self._tracks.pop(0)
                self.trigger_preload()
                return track
            return None

    async def remove_at(self, index: int) -> Optional[Track]:
        """Thread-safely remove a track at index (0-based)."""
        async with self._lock:
            if 0 <= index < len(self._tracks):
                track = self._tracks.pop(index)
                self.trigger_preload()
                return track
            return None

    async def clear(self) -> int:
        """Thread-safely clear all tracks from the queue."""
        async with self._lock:
            count = len(self._tracks)
            self._tracks.clear()
            return count

    async def shuffle(self) -> int:
        """Thread-safely shuffle the upcoming tracks."""
        async with self._lock:
            import random
            random.shuffle(self._tracks)
            self.trigger_preload()
            return len(self._tracks)

    def contains_title(self, title: str) -> bool:
        """Check if track with title is already in upcoming queue (duplicate detection)."""
        clean = title.strip().lower()
        return any(t.title.strip().lower() == clean for t in self._tracks)

    def trigger_preload(self) -> None:
        """Trigger background preloading of upcoming tracks."""
        if not self.player:
            return
        if self._preload_task and not self._preload_task.done():
            return
        self._preload_task = asyncio.create_task(self._preload_upcoming())

    async def _preload_upcoming(self) -> None:
        """Pre-resolve upcoming tracks in background so transitions are instant."""
        if not self.player or not self._tracks:
            return
        try:
            # Preload up to top 2 upcoming tracks
            for track in self._tracks[:2]:
                if getattr(track, "_playable", None) or getattr(track, "is_cached", False):
                    continue
                # Try to pre-resolve via player's resolver
                if hasattr(self.player, "_resolve_playable"):
                    p = await self.player._resolve_playable(track)
                    if p:
                        track._playable = p
                        logger.debug(f"SmartQueue: Pre-resolved upcoming track '{track.title}'")
        except Exception as e:
            logger.debug(f"SmartQueue preload background notice: {e}")

    # ── Restart Recovery & Serialization ──

    def serialize(self) -> List[Dict[str, Any]]:
        """Serialize upcoming queue for persistent database storage on restarts."""
        serialized = []
        for t in self._tracks:
            serialized.append({
                "title": t.title,
                "author": t.author,
                "url": t.url,
                "stream_url": t.stream_url,
                "duration": t.duration,
                "thumbnail": t.thumbnail,
                "requester": t.requester,
                "requester_id": t.requester_id,
                "is_autoplay": t.is_autoplay,
                "query": t.query,
                "is_cached": t.is_cached,
                "cache_path": t.cache_path,
            })
        return serialized

    def deserialize(self, data: List[Dict[str, Any]]) -> None:
        """Restore queue tracks from serialized storage."""
        self._tracks.clear()
        for item in data:
            if not isinstance(item, dict):
                continue
            track = Track(
                title=item.get("title", "Unknown"),
                author=item.get("author", "Unknown"),
                url=item.get("url", ""),
                stream_url=item.get("stream_url", ""),
                duration=int(item.get("duration", 0)),
                thumbnail=item.get("thumbnail"),
                requester=item.get("requester", "DJ"),
                requester_id=item.get("requester_id"),
                is_autoplay=bool(item.get("is_autoplay", False)),
                query=item.get("query"),
                is_cached=bool(item.get("is_cached", False)),
                cache_path=item.get("cache_path"),
            )
            self._tracks.append(track)
        self.trigger_preload()
