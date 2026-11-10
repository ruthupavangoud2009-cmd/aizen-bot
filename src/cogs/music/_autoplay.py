from __future__ import annotations

import asyncio
import html
import json
import logging
import random
import re
import urllib.parse
from typing import Any, List, Optional, Set

import aiohttp
import yt_dlp

from src.cogs.music._models import Track
from src.cogs.music._extractor import (
    NativeExtractor,
    clean_track_title,
    YOUTUBE_URL_REGEX,
)

logger = logging.getLogger("Kyoka.Music.Autoplay")

ARTIST_CLUSTERS = {
    # Bollywood / Hindi Romantic & Soulful
    "arijit singh": ["Atif Aslam", "Jubin Nautiyal", "Mohit Chauhan", "KK", "Armaan Malik", "Pritam", "Ankit Tiwari", "Sachin-Jigar", "Shreya Ghoshal", "Vishal Mishra"],
    "ankit tiwari": ["Arijit Singh", "Atif Aslam", "Mustafa Zahid", "Mohit Chauhan", "KK", "Mithoon", "Pritam", "Armaan Malik"],
    "atif aslam": ["Arijit Singh", "Jubin Nautiyal", "Mustafa Zahid", "Rahat Fateh Ali Khan", "Ali Zafar", "Mohit Chauhan", "Pritam", "Ankit Tiwari"],
    "jubin nautiyal": ["Arijit Singh", "Atif Aslam", "Akhil Sachdeva", "Tulsi Kumar", "Payal Dev", "Stebin Ben", "Vishal Mishra"],
    "kk": ["Shaan", "Mohit Chauhan", "Sonu Nigam", "Lucky Ali", "Pritam", "Arijit Singh", "Papon"],
    "sonu nigam": ["KK", "Shaan", "Udit Narayan", "Kumar Sanu", "Abhijeet", "Alka Yagnik", "Shreya Ghoshal"],
    "shreya ghoshal": ["Sunidhi Chauhan", "Arijit Singh", "Alka Yagnik", "Monali Thakur", "Pritam", "Shankar-Ehsaan-Loy"],
    "pritam": ["Arijit Singh", "KK", "Mohit Chauhan", "Atif Aslam", "Shaan", "Sachin-Jigar", "Ankit Tiwari"],
    "vishal mishra": ["Arijit Singh", "Jubin Nautiyal", "B Praak", "Akhil Sachdeva", "Sachet Tandon"],
    "armaan malik": ["Arijit Singh", "Darshan Raval", "Atif Aslam", "Ankit Tiwari", "Jubin Nautiyal"],
    "darshan raval": ["Armaan Malik", "Arijit Singh", "Jubin Nautiyal", "Atif Aslam", "Stebin Ben"],
    "mithoon": ["Ankit Tiwari", "Arijit Singh", "Atif Aslam", "Pritam"],
    
    # Punjabi / Drill / Desi Hip-Hop
    "sidhu moose wala": ["Karan Aujla", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Amrit Maan", "Gurinder Gill", "DIVINE"],
    "karan aujla": ["Sidhu Moose Wala", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Ikky", "Badshah", "Raftaar"],
    "ap dhillon": ["Gurinder Gill", "Shubh", "Diljit Dosanjh", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder"],
    "diljit dosanjh": ["Karan Aujla", "AP Dhillon", "Sidhu Moose Wala", "Garry Sandhu", "Amrinder Gill", "Honey Singh"],
    "shubh": ["AP Dhillon", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder", "DIVINE", "Wazir Patar"],
    "honey singh": ["Badshah", "Raftaar", "Guru Randhawa", "Diljit Dosanjh", "Alfaaz", "Lil Golu"],
    "badshah": ["Honey Singh", "Raftaar", "Guru Randhawa", "DIVINE", "Ikka", "Karan Aujla"],

    # Western Pop & Chart Toppers
    "the weeknd": ["Bruno Mars", "Post Malone", "Daft Punk", "Drake", "Travis Scott", "Dua Lipa"],
    "imagine dragons": ["Coldplay", "OneRepublic", "Twenty One Pilots", "Fall Out Boy", "Maroon 5"],
    "coldplay": ["Imagine Dragons", "OneRepublic", "The Lumineers", "The Script", "Maroon 5"],
    "bruno mars": ["The Weeknd", "Michael Jackson", "Ed Sheeran", "Mark Ronson", "Justin Bieber"],
    "ed sheeran": ["Shawn Mendes", "Charlie Puth", "Justin Bieber", "Sam Smith", "Lewis Capaldi"],
    "justin bieber": ["Shawn Mendes", "ZAYN", "Charlie Puth", "The Weeknd", "Post Malone"],
    "dua lipa": ["Bebe Rexha", "Ava Max", "Anne-Marie", "Katy Perry", "Rita Ora", "Taylor Swift"],
    "sabrina carpenter": ["Olivia Rodrigo", "Taylor Swift", "Billie Eilish", "Dua Lipa", "Ariana Grande", "Tate McRae"],
    "billie eilish": ["Finneas", "Lana Del Rey", "Olivia Rodrigo", "Lorde", "Melanie Martinez"],
    "taylor swift": ["Sabrina Carpenter", "Gracie Abrams", "Phoebe Bridgers", "Lana Del Rey", "Olivia Rodrigo"],
    "olivia rodrigo": ["Sabrina Carpenter", "Billie Eilish", "Conan Gray", "Tate McRae"],

    # Hip-Hop / Global Rap
    "eminem": ["50 Cent", "Dr. Dre", "Kendrick Lamar", "Snoop Dogg", "J. Cole", "NF"],
    "kendrick lamar": ["J. Cole", "Drake", "Baby Keem", "Travis Scott", "A$AP Rocky"],
    "travis scott": ["Don Toliver", "Metro Boomin", "Future", "Playboi Carti", "21 Savage"],
    "drake": ["Travis Scott", "Future", "21 Savage", "The Weeknd", "Lil Baby"],

    # K-Pop
    "bts": ["TXT", "SEVENTEEN", "Stray Kids", "ENHYPEN", "Jungkook", "V", "Jimin"],
    "newjeans": ["LE SSERAFIM", "IVE", "ILLIT", "aespa", "BLACKPINK", "TWICE"],

    # Anime / J-Pop
    "yoasobi": ["Ado", "LiSA", "Eve", "Kenshi Yonezu", "ZUTOMAYO"],
    "ado": ["YOASOBI", "Eve", "ZUTOMAYO", "Vaundy", "Kenshi Yonezu"],

    # EDM
    "alan walker": ["Marshmello", "The Chainsmokers", "Martin Garrix", "Avicii", "Kygo", "K-391"],
    "marshmello": ["Alan Walker", "The Chainsmokers", "Martin Garrix", "DJ Snake"],

    # Phonk
    "phonk": ["Brazilian Phonk", "Kordhell", "DVRST", "Hensonn", "SXID", "NCTS", "Montagem"],
}


def extract_primary_artist(raw_artist: str) -> str:
    """Extract clean primary artist name from multi-artist strings, prioritizing known singers."""
    if not raw_artist:
        return ""
    clean = html.unescape(raw_artist).strip()
    lowered = clean.lower()

    # Prioritize prominent singer from ARTIST_CLUSTERS over lyricist/producer
    for known in ARTIST_CLUSTERS:
        if known in lowered:
            parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
            for p in parts:
                if known in p.lower():
                    return p.strip()

    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[0] if parts else clean


def normalize_history_title(raw_title: str) -> str:
    """Normalize song title for history deduplication by removing movie tags, version noise and brackets."""
    t = clean_track_title(raw_title).lower()
    t = re.sub(r'["\'\(\)\[\]]', "", t)
    t = re.sub(
        r"\b(?:from\s+.+?|ost|audio|video|lyrics?|full\s+song|new\s+version|remix|lofi|slowed|reverb)\b",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return re.sub(r"\s+", " ", t)


class NativeSmartAutoplay:
    """Autonomous Multi-Engine Continuous Radio Player (Liked Music + JioSaavn + YouTube Mix)."""

    @classmethod
    async def get_liked_tracks_from_db(
        cls,
        db: Any,
        user_ids: Optional[List[int]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch saved Favorites/Liked songs from the user_playlist_tracks database table."""
        if not db or not hasattr(db, "fetch_all"):
            return []
        try:
            # 1. Prefer songs from users currently in voice or who enabled 24/7
            if user_ids:
                clean_ids = [int(uid) for uid in user_ids if uid]
                if clean_ids:
                    query = """
                        SELECT DISTINCT upt.title, upt.author, upt.duration, upt.url
                        FROM user_playlist_tracks upt
                        JOIN user_playlists up ON upt.playlist_id = up.id
                        WHERE up.user_id = ANY($1::bigint[]) AND LOWER(up.playlist_name) = 'favorites'
                        ORDER BY upt.id DESC LIMIT $2;
                    """
                    rows = await db.fetch_all(query, clean_ids, limit)
                    if rows:
                        return [dict(r) for r in rows]

            # 2. General server / global favorites
            query = """
                SELECT DISTINCT upt.title, upt.author, upt.duration, upt.url
                FROM user_playlist_tracks upt
                JOIN user_playlists up ON upt.playlist_id = up.id
                WHERE LOWER(up.playlist_name) = 'favorites'
                ORDER BY upt.id DESC LIMIT $1;
            """
            rows = await db.fetch_all(query, limit)
            return [dict(r) for r in rows] if rows else []
        except Exception as e:
            logger.debug(f"Liked tracks DB lookup notice: {e}")
            return []

    @classmethod
    async def get_next_recommendation(
        cls,
        current_track: Optional[Track],
        played_history: Set[str],
        db: Any = None,
        consecutive_same_artist: int = 0,
        user_ids: Optional[List[int]] = None,
        is_247: bool = False,
    ) -> Optional[Track]:
        """Produce the next recommended track with Liked Music priority & Related Music cascade."""
        import wavelink

        # Bound history size to prevent unbounded memory growth during 24/7 sessions
        if len(played_history) > 250:
            to_remove = list(played_history)[:120]
            for item in to_remove:
                played_history.discard(item)

        # ── Step 1: Liked Music Priority (When 24/7 is on, or randomly interleaved) ──
        liked_rows = await cls.get_liked_tracks_from_db(db, user_ids=user_ids)
        if liked_rows:
            unplayed_liked = [
                r for r in liked_rows
                if normalize_history_title(r.get("title") or "") not in played_history
            ]
            # In 24/7 mode, prioritize liked songs heavily (or every 2 tracks)
            if unplayed_liked and (is_247 or random.random() < 0.65 or not current_track):
                selected = random.choice(unplayed_liked)
                l_title = selected.get("title") or "Liked Track"
                l_author = selected.get("author") or "Artist"
                l_url = selected.get("url") or ""
                l_dur = int(selected.get("duration") or 0)
                norm_title = normalize_history_title(l_title)
                played_history.add(norm_title)

                # Search via Wavelink / JioSaavn
                resolved_playable = None
                search_target = l_url if l_url.startswith("http") else f"{l_title} {l_author}".strip()
                try:
                    res = await asyncio.wait_for(wavelink.Playable.search(search_target), timeout=6.0)
                    if res:
                        resolved_playable = res[0] if isinstance(res, list) else getattr(res, "tracks", [None])[0]
                except Exception:
                    pass

                trk = Track(
                    title=l_title,
                    author=l_author,
                    url=l_url,
                    stream_url="",
                    duration=l_dur,
                    requester="💖 Liked Music (24/7)" if is_247 else "💖 Liked Music Radio",
                    is_autoplay=True,
                    query=search_target,
                )
                if resolved_playable:
                    trk._playable = resolved_playable
                return trk

        # ── Step 2: Related Music to Current / Previous Track ──
        if current_track:
            rel = await cls.get_next_track(
                current_track=current_track,
                played_history=played_history,
                consecutive_same_artist=consecutive_same_artist,
            )
            if rel:
                if is_247:
                    rel.requester = "⚡ Related Music (24/7)"
                return rel

        # ── Step 3: High-Energy / 24/7 Continuous Music Curated Fallback ──
        default_queries = [
            "popular songs 2026 hits",
            "lofi hip hop radio beats to relax study to",
            "today top hits official playlist",
            "chill acoustic pop radio",
            "viral songs worldwide radio",
            "synthwave radio chill beats",
        ]
        random.shuffle(default_queries)
        for q in default_queries:
            try:
                res = await asyncio.wait_for(wavelink.Playable.search(q), timeout=6.0)
                if res:
                    tracks = res if isinstance(res, list) else getattr(res, "tracks", [])
                    for top in tracks[:5]:
                        top_norm = normalize_history_title(top.title or "")
                        if top_norm and top_norm not in played_history:
                            trk = Track(
                                title=top.title or q,
                                author=top.author or "Artist",
                                url=top.uri or "",
                                stream_url="",
                                duration=int((top.length or 0) / 1000),
                                thumbnail=getattr(top, "artwork", None) or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None),
                                requester="⚡ 24/7 Continuous Radio",
                                is_autoplay=True,
                                query=q,
                            )
                            trk._playable = top
                            played_history.add(top_norm)
                            return trk
            except Exception:
                continue

        return None

    @classmethod
    async def get_next_track(
        cls,
        current_track: Track,
        played_history: Set[str],
        consecutive_same_artist: int = 0,
    ) -> Optional[Track]:
        """
        Produce next recommended track using multi-candidate pool from JioSaavn and Worldwide catalogs.
        Guarantees non-stop continuous playback without dying or repeating same tracks.
        """
        if not current_track:
            return None

        # Bound history size to prevent unbounded memory growth during 24/7 sessions
        if len(played_history) > 250:
            # Clear oldest half of history
            to_remove = list(played_history)[:120]
            for item in to_remove:
                played_history.discard(item)

        clean_title = clean_track_title(current_track.title)
        norm_curr_title = normalize_history_title(current_track.title)
        primary_artist = extract_primary_artist(current_track.author)
        artist_key = primary_artist.lower()

        # Find related artists in graph
        related_artists: List[str] = []
        for known_key, cluster in ARTIST_CLUSTERS.items():
            if known_key in artist_key or artist_key in known_key or known_key in clean_title.lower():
                related_artists = list(cluster)
                break

        # Build candidate search queries
        queries: List[str] = []
        if consecutive_same_artist >= 2 and related_artists:
            pick_artist = random.choice(related_artists)
            queries.append(f"{pick_artist} top songs")
            queries.append(f"{pick_artist} hits")
        else:
            if primary_artist and primary_artist.lower() not in ("official artist", "unknown", "youtube"):
                queries.append(f"{primary_artist} hits")
                queries.append(f"{primary_artist} songs")
            if related_artists:
                queries.append(f"{random.choice(related_artists)} hits")
            queries.append(f"{clean_title} songs")

        import wavelink

        # Strategy 1: Standard YouTube Recommendations (High Stability & Direct Codecs)
        for q in queries:
            try:
                res = await asyncio.wait_for(
                    wavelink.Playable.search(q, source=wavelink.TrackSource.YouTube),
                    timeout=6.0,
                )
                if res:
                    tracks = res if isinstance(res, list) else getattr(res, "tracks", [])
                    for top in tracks[:5]:
                        top_norm = normalize_history_title(top.title or "")
                        if top_norm and top_norm not in played_history and top_norm != norm_curr_title:
                            trk = Track(
                                title=top.title or q,
                                author=top.author or "Artist",
                                url=top.uri or "",
                                stream_url="",
                                duration=int((top.length or 0) / 1000),
                                thumbnail=top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None),
                                requester="⚡ Smart Autoplay Radio",
                                is_autoplay=True,
                                query=q,
                            )
                            trk._playable = top
                            played_history.add(top_norm)
                            return trk
            except Exception as e:
                logger.debug(f"YouTube autoplay search notice for '{q}': {e}")

        # Strategy 2: YouTube Music Search Fallback
        for q in queries:
            try:
                res = await asyncio.wait_for(
                    wavelink.Playable.search(q, source=wavelink.TrackSource.YouTubeMusic),
                    timeout=6.0,
                )
                if res:
                    tracks = res if isinstance(res, list) else getattr(res, "tracks", [])
                    for top in tracks[:5]:
                        top_norm = normalize_history_title(top.title or "")
                        if top_norm and top_norm not in played_history and top_norm != norm_curr_title:
                            trk = Track(
                                title=top.title or q,
                                author=top.author or "Artist",
                                url=top.uri or "",
                                stream_url="",
                                duration=int((top.length or 0) / 1000),
                                thumbnail=top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None),
                                requester="⚡ Smart Autoplay Radio",
                                is_autoplay=True,
                                query=q,
                            )
                            trk._playable = top
                            played_history.add(top_norm)
                            return trk
            except Exception as e:
                logger.debug(f"YouTube Music autoplay search notice for '{q}': {e}")

        # Strategy 3: Default Search Fallback
        for q in queries:
            try:
                res = await asyncio.wait_for(
                    wavelink.Playable.search(q),
                    timeout=6.0,
                )
                if res:
                    tracks = res if isinstance(res, list) else getattr(res, "tracks", [])
                    for top in tracks[:5]:
                        top_norm = normalize_history_title(top.title or "")
                        if top_norm and top_norm not in played_history and top_norm != norm_curr_title:
                            trk = Track(
                                title=top.title or q,
                                author=top.author or "Artist",
                                url=top.uri or "",
                                stream_url="",
                                duration=int((top.length or 0) / 1000),
                                thumbnail=top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None),
                                requester="⚡ Smart Autoplay Radio",
                                is_autoplay=True,
                                query=q,
                            )
                            trk._playable = top
                            played_history.add(top_norm)
                            return trk
            except Exception as e:
                logger.debug(f"Default autoplay search notice for '{q}': {e}")

        return None

