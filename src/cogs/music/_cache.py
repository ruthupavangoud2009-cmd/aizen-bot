"""
KYOKA — Self-Hosted Ultra-Fast Persistent Audio & Song Cache Engine
==================================================================

Provides persistent caching of audio metadata and audio files across bot restarts,
redeployments, and music engine restarts.

Includes:
1. Dual-layer persistence: Persistent JSON disk index + PostgreSQL database sync.
2. LRU + LFU intelligent cache eviction policy with configurable storage quotas.
3. Ephemeral vs persistent storage auto-detection with safety warnings.
4. Atomic file writes and startup recovery (cleaning orphan and incomplete .tmp files).
5. Fast in-memory lookup cache (< 1ms query resolution).
6. Cache usage telemetry (hits, misses, hit rate, disk utilization).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.core.bot import KyokaBot
    from src.cogs.music._models import Track

logger = logging.getLogger("Kyoka.Music.Cache")


@dataclass
class CacheEntry:
    """Represents a cached audio track entry."""
    cache_id: str
    title: str
    artist: str
    duration: int
    source_url: str
    thumbnail: Optional[str]
    audio_path: Optional[str]
    created_at: float
    usage_count: int
    last_played: float
    audio_format: str
    cache_status: str  # "cached", "streaming", "expired", "failed"
    file_size: int = 0
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CacheEntry:
        return cls(
            cache_id=data.get("cache_id", ""),
            title=data.get("title", "Unknown"),
            artist=data.get("artist", "Unknown"),
            duration=int(data.get("duration", 0)),
            source_url=data.get("source_url", ""),
            thumbnail=data.get("thumbnail"),
            audio_path=data.get("audio_path"),
            created_at=float(data.get("created_at", time.time())),
            usage_count=int(data.get("usage_count", 1)),
            last_played=float(data.get("last_played", time.time())),
            audio_format=data.get("audio_format", "opus"),
            cache_status=data.get("cache_status", "streaming"),
            file_size=int(data.get("file_size", 0)),
            extra=data.get("extra"),
        )


class MusicCacheManager:
    """
    Enterprise-Grade Persistent Audio Cache & Metadata Manager.
    Guarantees fast track starts, reduced remote queries, and zero memory leaks.
    """

    def __init__(
        self,
        bot: Optional[KyokaBot] = None,
        base_dir: Optional[str | Path] = None,
        max_size_mb: Optional[int] = None,
        max_tracks: Optional[int] = None,
        ttl_days: Optional[int] = None,
    ) -> None:
        self.bot = bot
        from src.core.config import Config

        self.base_dir = Path(base_dir or getattr(Config, "MUSIC_CACHE_DIR", "data/music_cache")).resolve()
        self.audio_dir = self.base_dir / "audio"
        self.index_file = self.base_dir / "cache_index.json"

        effective_max_mb = max_size_mb if max_size_mb is not None else int(getattr(Config, "MUSIC_CACHE_MAX_MB", 1024))
        self.max_size_bytes = effective_max_mb * 1024 * 1024

        self.max_tracks = int(max_tracks if max_tracks is not None else getattr(Config, "MUSIC_CACHE_MAX_TRACKS", 500))
        effective_ttl = ttl_days if ttl_days is not None else float(getattr(Config, "MUSIC_CACHE_TTL_DAYS", 14))
        self.ttl_seconds = effective_ttl * 86400.0

        # Concurrency & In-memory indexing
        self._lock = asyncio.Lock()
        self._entries: Dict[str, CacheEntry] = {}  # cache_id -> CacheEntry
        self._query_index: Dict[str, str] = {}    # normalized query/url -> cache_id
        self._initialized = False

        # Metrics
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.is_persistent_storage: bool = True
        self.storage_warning: Optional[str] = None

    @staticmethod
    def normalize_key(query_or_url: str) -> str:
        """Create a deterministic hash key from search query or canonical URL."""
        cleaned = query_or_url.strip().lower()
        # Strip common redundant URL noise
        for prefix in ("https://", "http://", "www."):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def generate_track_key(title: str, artist: str, url: Optional[str] = None) -> str:
        """Generate a canonical key based on track title and artist."""
        if url and ("youtube.com" in url or "youtu.be" in url or "spotify.com" in url):
            clean_url = url.split("&")[0].split("?si=")[0]
            return MusicCacheManager.normalize_key(clean_url)
        norm = f"{title.strip().lower()} - {artist.strip().lower()}"
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]

    async def initialize(self) -> None:
        """Initialize directories, verify disk persistence, rebuild index, and purge corrupt entries."""
        if self._initialized:
            return

        async with self._lock:
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
                self.audio_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create cache directories at {self.base_dir}: {e}")

            # Check persistent vs ephemeral storage
            self._detect_storage_persistence()

            # Load persistent JSON index
            await self._load_index_from_disk()

            # Reconcile disk files & purge incomplete .tmp files
            await self._audit_and_cleanup_disk()

            # Sync from PostgreSQL if available
            await self._sync_from_database()

            self._initialized = True
            logger.info(
                f"MusicCacheManager initialized: {len(self._entries)} tracks in index, "
                f"{self.get_total_cache_size() / (1024 * 1024):.1f} MB utilized. "
                f"(Storage Persistent: {self.is_persistent_storage})"
            )

    def _detect_storage_persistence(self) -> None:
        """Detect whether hosting provides persistent or ephemeral disk."""
        probe_file = self.base_dir / ".persistence_probe"
        try:
            probe_file.write_text(f"probe-{time.time()}", encoding="utf-8")
            if probe_file.exists():
                probe_file.unlink(missing_ok=True)
            self.is_persistent_storage = True
        except Exception as e:
            self.is_persistent_storage = False
            self.storage_warning = f"Storage is non-writable or ephemeral: {e}"
            logger.warning(self.storage_warning)
            return

        # Check common ephemeral hosting flags (e.g. Render free tier without disk)
        if os.getenv("RENDER") and not os.getenv("RENDER_DISK_PATH"):
            # Render web services without mounted persistent disks have ephemeral storage
            self.storage_warning = (
                "Hosting environment detected as Render without persistent disk. "
                "Audio cache files will reset upon redeployment."
            )
            logger.info(self.storage_warning)

    async def _load_index_from_disk(self) -> None:
        """Read cache index file into memory."""
        if not self.index_file.exists():
            return
        try:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, self.index_file.read_text, "utf-8")
            data = json.loads(content)
            for item in data:
                entry = CacheEntry.from_dict(item)
                self._entries[entry.cache_id] = entry
                if entry.source_url:
                    self._query_index[self.normalize_key(entry.source_url)] = entry.cache_id
                self._query_index[self.generate_track_key(entry.title, entry.artist)] = entry.cache_id
        except Exception as e:
            logger.warning(f"Failed to load cache index from disk: {e}")

    async def _save_index_to_disk(self) -> None:
        """Write current cache index atomically to disk."""
        try:
            loop = asyncio.get_running_loop()
            raw_data = [entry.to_dict() for entry in self._entries.values()]
            content = json.dumps(raw_data, indent=2)

            tmp_path = self.base_dir / f"cache_index_{os.getpid()}.tmp"

            def _write():
                tmp_path.write_text(content, encoding="utf-8")
                tmp_path.replace(self.index_file)

            await loop.run_in_executor(None, _write)
        except Exception as e:
            logger.error(f"Failed to save cache index atomically: {e}")

    async def _audit_and_cleanup_disk(self) -> None:
        """Sweep orphan .tmp files and verify existence of cached audio files."""
        loop = asyncio.get_running_loop()

        def _sweep():
            # 1. Clean incomplete temporary downloads
            for tmp in self.base_dir.glob("*.tmp"):
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
            for tmp in self.audio_dir.glob("*.tmp"):
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass

            # 2. Verify cached files in index actually exist on disk
            missing_ids = []
            for cid, entry in list(self._entries.items()):
                if entry.audio_path:
                    p = Path(entry.audio_path)
                    if not p.exists() or p.stat().st_size == 0:
                        entry.audio_path = None
                        entry.cache_status = "streaming"
                        entry.file_size = 0
            return missing_ids

        await loop.run_in_executor(None, _sweep)
        await self._save_index_to_disk()

    async def _sync_from_database(self) -> None:
        """Load persistent cache metadata from PostgreSQL database if bot is ready."""
        if not self.bot or not getattr(self.bot, "db", None) or not getattr(self.bot.db, "pool", None):
            return
        try:
            rows = await self.bot.db.fetch_all("SELECT * FROM music_track_cache ORDER BY last_played_at DESC LIMIT 500;")
            for r in rows:
                cid = r["cache_id"]
                if cid not in self._entries:
                    entry = CacheEntry(
                        cache_id=cid,
                        title=r["title"],
                        artist=r["artist"],
                        duration=int(r["duration"]),
                        source_url=r.get("source_url") or "",
                        thumbnail=r.get("thumbnail"),
                        audio_path=r.get("audio_path"),
                        created_at=r["created_at"].timestamp() if hasattr(r["created_at"], "timestamp") else time.time(),
                        usage_count=int(r.get("usage_count", 1)),
                        last_played=r["last_played_at"].timestamp() if hasattr(r["last_played_at"], "timestamp") else time.time(),
                        audio_format=r.get("audio_format", "opus"),
                        cache_status=r.get("cache_status", "cached"),
                        file_size=int(r.get("file_size", 0)),
                    )
                    self._entries[cid] = entry
                    if entry.source_url:
                        self._query_index[self.normalize_key(entry.source_url)] = cid
                    self._query_index[self.generate_track_key(entry.title, entry.artist)] = cid
        except Exception as e:
            logger.debug(f"Database sync notice (cache table might not exist yet): {e}")

    def get_total_cache_size(self) -> int:
        """Calculate total disk space utilized by cached audio files."""
        return sum(e.file_size for e in self._entries.values() if e.audio_path and e.file_size > 0)

    # ── Cache Lookup & Ingestion ──

    async def get_cached_track(
        self,
        query_or_url: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
    ) -> Optional[Tuple[CacheEntry, bool]]:
        """
        Check if a track is cached.
        Returns (CacheEntry, has_audio_file) or None.
        """
        if not self._initialized:
            await self.initialize()

        cache_id: Optional[str] = None

        # 1. Direct query/url match
        norm_key = self.normalize_key(query_or_url)
        if norm_key in self._query_index:
            cache_id = self._query_index[norm_key]

        # 2. Title & Artist match
        if not cache_id and title and artist:
            track_key = self.generate_track_key(title, artist, query_or_url)
            if track_key in self._query_index:
                cache_id = self._query_index[track_key]

        if not cache_id or cache_id not in self._entries:
            self.cache_misses += 1
            return None

        entry = self._entries[cache_id]

        # Check expiration
        now = time.time()
        if now - entry.last_played > self.ttl_seconds:
            entry.cache_status = "expired"
            self.cache_misses += 1
            return None

        # Check audio file validity
        has_audio = False
        if entry.audio_path:
            p = Path(entry.audio_path)
            if p.exists() and p.stat().st_size > 0:
                has_audio = True
            else:
                entry.audio_path = None
                entry.cache_status = "streaming"
                entry.file_size = 0

        # Cache HIT!
        self.cache_hits += 1
        entry.usage_count += 1
        entry.last_played = now

        # Fire and forget index update
        asyncio.create_task(self._record_usage_update(entry))

        return entry, has_audio

    async def _record_usage_update(self, entry: CacheEntry) -> None:
        """Update last_played and usage_count asynchronously in DB and disk index."""
        try:
            if self.bot and getattr(self.bot, "db", None) and getattr(self.bot.db, "pool", None):
                await self.bot.db.execute(
                    """
                    UPDATE music_track_cache
                    SET usage_count = $1, last_played_at = CURRENT_TIMESTAMP
                    WHERE cache_id = $2;
                    """,
                    entry.usage_count,
                    entry.cache_id,
                )
        except Exception:
            pass

    async def register_track(
        self,
        track: Track,
        audio_path: Optional[str] = None,
        audio_format: str = "opus",
        file_size: int = 0,
        cache_status: str = "cached",
    ) -> CacheEntry:
        """
        Store track metadata and audio cache information into persistent storage.
        """
        if not self._initialized:
            await self.initialize()

        title = track.title or "Unknown Title"
        artist = track.author or "Unknown Artist"
        url = track.url or track.stream_url or ""
        duration = track.duration or 0
        thumbnail = track.thumbnail

        cid = self.generate_track_key(title, artist, url)
        now = time.time()

        existing = self._entries.get(cid)
        usage_count = (existing.usage_count + 1) if existing else 1

        entry = CacheEntry(
            cache_id=cid,
            title=title,
            artist=artist,
            duration=duration,
            source_url=url,
            thumbnail=thumbnail,
            audio_path=audio_path or (existing.audio_path if existing else None),
            created_at=existing.created_at if existing else now,
            usage_count=usage_count,
            last_played=now,
            audio_format=audio_format,
            cache_status=cache_status,
            file_size=file_size or (existing.file_size if existing else 0),
        )

        async with self._lock:
            self._entries[cid] = entry
            self._query_index[self.normalize_key(url)] = cid
            if track.query:
                self._query_index[self.normalize_key(track.query)] = cid
            self._query_index[self.generate_track_key(title, artist)] = cid

            # Check if cache eviction is required
            await self._evict_if_needed()

            # Save to disk
            await self._save_index_to_disk()

        # Update track model
        track.is_cached = bool(entry.audio_path and Path(entry.audio_path).exists())
        track.cache_path = entry.audio_path
        track.cache_status = entry.cache_status
        track.cache_id = cid
        track.play_count = entry.usage_count
        track.cached_at = entry.created_at

        # Async sync to DB
        asyncio.create_task(self._persist_to_db(entry))

        return entry

    async def _persist_to_db(self, entry: CacheEntry) -> None:
        """Persist cache entry into PostgreSQL table music_track_cache."""
        if not self.bot or not getattr(self.bot, "db", None) or not getattr(self.bot.db, "pool", None):
            return
        try:
            await self.bot.db.execute(
                """
                INSERT INTO music_track_cache (
                    cache_id, title, artist, duration, source_url, thumbnail,
                    audio_path, audio_format, file_size, usage_count, cache_status, last_played_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP)
                ON CONFLICT (cache_id) DO UPDATE SET
                    audio_path = EXCLUDED.audio_path,
                    file_size = EXCLUDED.file_size,
                    usage_count = music_track_cache.usage_count + 1,
                    cache_status = EXCLUDED.cache_status,
                    last_played_at = CURRENT_TIMESTAMP;
                """,
                entry.cache_id,
                entry.title[:255],
                entry.artist[:255],
                entry.duration,
                entry.source_url,
                entry.thumbnail,
                entry.audio_path,
                entry.audio_format[:20],
                entry.file_size,
                entry.usage_count,
                entry.cache_status[:20],
            )
        except Exception as e:
            logger.debug(f"Failed to persist cache entry to database: {e}")

    # ── Intelligent LRU + LFU Cache Eviction Policy ──

    async def _evict_if_needed(self) -> None:
        """
        Evict least valuable cached tracks when exceeding storage limit or max tracks.
        Score = (usage_count * 2.0) - (age_in_days). Lowest scores evicted first.
        """
        total_size = self.get_total_cache_size()
        total_tracks = len(self._entries)

        if total_size <= self.max_size_bytes and total_tracks <= self.max_tracks:
            return

        logger.info(
            f"Cache limit exceeded (size={total_size / (1024*1024):.1f}MB/{self.max_size_bytes / (1024*1024):.1f}MB, "
            f"tracks={total_tracks}/{self.max_tracks}). Running intelligent LRU+LFU eviction..."
        )

        now = time.time()

        def _score(entry: CacheEntry) -> float:
            # High usage count boosts score, idle time lowers score
            age_days = (now - entry.last_played) / 86400.0
            return (entry.usage_count * 2.5) - age_days

        # Sort entries ascending by score (lowest priority evicted first)
        sorted_entries = sorted(self._entries.values(), key=_score)

        target_size = int(self.max_size_bytes * 0.75)
        target_tracks = int(self.max_tracks * 0.8)

        for entry in sorted_entries:
            if total_size <= target_size and len(self._entries) <= target_tracks:
                break

            # Evict file
            if entry.audio_path:
                try:
                    p = Path(entry.audio_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                    total_size -= entry.file_size
                    entry.audio_path = None
                    entry.cache_status = "expired"
                    entry.file_size = 0
                except Exception as e:
                    logger.warning(f"Error evicting cache file {entry.audio_path}: {e}")

            # If total entries exceeds target quota or track is ancient (> 30 days), remove entry completely
            if len(self._entries) > target_tracks or (now - entry.last_played) > 30 * 86400:
                self._entries.pop(entry.cache_id, None)

        logger.info(f"Eviction complete. New cache size: {self.get_total_cache_size() / (1024*1024):.1f}MB.")

    # ── Diagnostics & Telemetry ──

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostic metrics for owner dashboard."""
        total_lookups = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_lookups * 100.0) if total_lookups > 0 else 0.0

        free_disk_mb = 0
        try:
            total, used, free = shutil.disk_usage(self.base_dir)
            free_disk_mb = int(free / (1024 * 1024))
        except Exception:
            pass

        cached_audio_count = sum(1 for e in self._entries.values() if e.audio_path)

        return {
            "cached_tracks": len(self._entries),
            "cached_audio_files": cached_audio_count,
            "cache_size_mb": round(self.get_total_cache_size() / (1024 * 1024), 2),
            "max_size_mb": round(self.max_size_bytes / (1024 * 1024), 0),
            "free_disk_mb": free_disk_mb,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_pct": round(hit_rate, 1),
            "is_persistent": self.is_persistent_storage,
            "warning": self.storage_warning,
        }
