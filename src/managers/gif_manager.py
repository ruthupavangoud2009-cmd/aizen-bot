from __future__ import annotations

import logging
import os
import random
import time
from collections import defaultdict, deque
from typing import Optional

import aiohttp

logger = logging.getLogger("Kyoka.Managers.GIF")

# Curated, verified, safe HTTPS anime GIFs for each supported action
CURATED_ACTION_GIFS: dict[str, list[str]] = {
    "slapped": [
        "https://media.giphy.com/media/jLeyZWgtwvis8/giphy.gif",
        "https://media.giphy.com/media/Gf3AUz3eBNbTW/giphy.gif",
        "https://media.giphy.com/media/Zau0yrl15uzdK/giphy.gif",
        "https://media.giphy.com/media/vxvNnKRug7SCs/giphy.gif",
        "https://media.giphy.com/media/mEtSQlxqBtWWA/giphy.gif",
        "https://media.giphy.com/media/tXMPB9cHxUE7NbadYQ/giphy.gif",
        "https://media.giphy.com/media/lX03hULhgCYQ8/giphy.gif",
        "https://media.giphy.com/media/uqSU9GLjK337W/giphy.gif",
    ],
    "hugged": [
        "https://media.giphy.com/media/u9BxQbM5bxvwY/giphy.gif",
        "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
        "https://media.giphy.com/media/lrr9rHuoJOE0w/giphy.gif",
        "https://media.giphy.com/media/wnsgren9NtITS/giphy.gif",
        "https://media.giphy.com/media/PHZ7vmgbWLxbox5MsP/giphy.gif",
        "https://media.giphy.com/media/LIqFOpO9Qh0uA/giphy.gif",
        "https://media.giphy.com/media/BXrwT46vod06A/giphy.gif",
        "https://media.giphy.com/media/QFPoctlgZ5s0E/giphy.gif",
    ],
    "patted": [
        "https://media.giphy.com/media/L2z7dnOduqEow/giphy.gif",
        "https://media.giphy.com/media/ARSp9T7wwxNcs/giphy.gif",
        "https://media.giphy.com/media/4HP0ddZnNVnKU/giphy.gif",
        "https://media.giphy.com/media/5tmRHwTlHAA9WkVxTU/giphy.gif",
        "https://media.giphy.com/media/ye7OTQgwmVuNTY22s3/giphy.gif",
        "https://media.giphy.com/media/osYdfUptPqVDNRAw5G/giphy.gif",
        "https://media.giphy.com/media/N0CIxcyPLputW/giphy.gif",
        "https://media.giphy.com/media/109LtuoSQT212w/giphy.gif",
    ],
    "kissed": [
        "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
        "https://media.giphy.com/media/FqBTvSNjNzeZG/giphy.gif",
        "https://media.giphy.com/media/flmwZUupnj6Ew/giphy.gif",
        "https://media.giphy.com/media/KH1CTZtw1iP3W/giphy.gif",
        "https://media.giphy.com/media/wOtkVwroA6yzK/giphy.gif",
        "https://media.giphy.com/media/bm2O3nXTcKJeU/giphy.gif",
        "https://media.giphy.com/media/nyGFcsP0kAobm/giphy.gif",
        "https://media.giphy.com/media/Ka2NAhEGAnQKdTOZFu/giphy.gif",
    ],
    "bonked": [
        "https://media.giphy.com/media/6gLyE15StY3PC/giphy.gif",
        "https://media.giphy.com/media/pPs4HVuYB46foxfSSNL/giphy.gif",
        "https://media.giphy.com/media/RodyInaeK9vK3tuiIB/giphy.gif",
        "https://media.giphy.com/media/qs427c9qVc1Us/giphy.gif",
        "https://media.giphy.com/media/WB9Nq2Gg2jE839kS9b/giphy.gif",
        "https://media.giphy.com/media/8TweEdaxxfuElKkRxz/giphy.gif",
    ],
    "cuddled": [
        "https://media.giphy.com/media/49mdjsMrH7oze/giphy.gif",
        "https://media.giphy.com/media/Vz58J8shFW6BvqnYTm/giphy.gif",
        "https://media.giphy.com/media/sUIZWMnfd4Mb6/giphy.gif",
        "https://media.giphy.com/media/3bqtLDeiDtwhq/giphy.gif",
        "https://media.giphy.com/media/EvYHHSntaIl5m/giphy.gif",
        "https://media.giphy.com/media/l2QDM9Jnim1YV5bxC/giphy.gif",
    ],
    "poked": [
        "https://media.giphy.com/media/pWd3gD577gOqs/giphy.gif",
        "https://media.giphy.com/media/y0NFayaBeiWEU/giphy.gif",
        "https://media.giphy.com/media/WvF3Z8qfU2KFUev3HI/giphy.gif",
        "https://media.giphy.com/media/10hO3rDNqqg2Xe/giphy.gif",
        "https://media.giphy.com/media/aZ4sQUpybai5y/giphy.gif",
    ],
    "high-fived": [
        "https://media.giphy.com/media/b5L1Lt3k4GYms/giphy.gif",
        "https://media.giphy.com/media/pHb82xtBPfqEg/giphy.gif",
        "https://media.giphy.com/media/3oEjHV0z8S7WM4MwnK/giphy.gif",
        "https://media.giphy.com/media/10LKovKon8PuQw/giphy.gif",
        "https://media.giphy.com/media/HX3lSnGXZnaWk/giphy.gif",
    ],
    "defeated": [
        "https://media.giphy.com/media/arbHBDAq95uDc3xvLv/giphy.gif",
        "https://media.giphy.com/media/d2YWTOsVtuHgOHhC/giphy.gif",
        "https://media.giphy.com/media/11HeubZNXOasBi/giphy.gif",
        "https://media.giphy.com/media/xUPGcAfeh68pJds6T6/giphy.gif",
        "https://media.giphy.com/media/3o7btQ8jDTPGDpgc6I/giphy.gif",
    ],
    # Playful suggestive romantic/intimate anime couples (consenting adult fictional characters, non-explicit)
    "intimate_couple": [
        "https://media.giphy.com/media/V53jWRd057IZa/giphy.gif",
        "https://media.giphy.com/media/KZZXL9TDzT3u8/giphy.gif",
        "https://media.giphy.com/media/12VXIxjdR5Bup7/giphy.gif",
        "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
        "https://media.giphy.com/media/xThuWpnGQHBGvaPrVK/giphy.gif",
        "https://media.giphy.com/media/1081l36IGVT3io/giphy.gif",
        "https://media.giphy.com/media/26AHG5KGFxSkUWw1i/giphy.gif",
        "https://media.giphy.com/media/l41lT4at60nIVoxHO/giphy.gif",
    ],
}


class GIFManager:
    """
    Enhanced GIF service with categorized pools, recent-result avoidance,
    and fallback resilience against API limits or outages.
    """
    curated = CURATED_ACTION_GIFS
    POOLS = CURATED_ACTION_GIFS

    def __init__(self) -> None:
        self.curated = CURATED_ACTION_GIFS
        # action_key -> deque of up to 5 recently served URLs
        self._recent_served: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=5))

    async def get_action_gif(
        self,
        action: str,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[str]:
        """
        Fetch a varied, non-repeating GIF URL for a given action.
        Uses external API if available and non-empty, falling back smoothly
        to the extensive curated pool with recent-avoidance.
        """
        action_key = action.lower().strip()
        pool = CURATED_ACTION_GIFS.get(action_key)
        if not pool:
            # Fallback for unknown action
            pool = CURATED_ACTION_GIFS.get("hugged", [])

        # Try live Tenor / GIPHY API if session and keys exist
        tenor_key = os.getenv("TENOR_API_KEY", "").strip()
        giphy_key = os.getenv("GIPHY_API_KEY", "").strip()
        recent = set(self._recent_served[action_key])

        if session and not session.closed and (tenor_key or giphy_key):
            try:
                query = f"anime {action_key}"
                timeout = aiohttp.ClientTimeout(total=3.0)
                if tenor_key:
                    url = "https://tenor.googleapis.com/v2/search"
                    params = {"q": query, "key": tenor_key, "limit": "15", "contentfilter": "medium", "media_filter": "gif"}
                    async with session.get(url, params=params, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            results = data.get("results", [])
                            urls = []
                            for it in results:
                                media = it.get("media_formats", {})
                                g_url = media.get("gif", {}).get("url") or media.get("mediumgif", {}).get("url")
                                if g_url and g_url.startswith("https://"):
                                    urls.append(g_url)
                            avail = [u for u in urls if u not in recent]
                            if avail:
                                chosen = random.choice(avail)
                                self._recent_served[action_key].append(chosen)
                                return chosen
            except Exception as e:
                logger.debug(f"Live GIF lookup notice: {e}")

        # Fallback to curated pool with recent avoidance
        avail = [u for u in pool if u not in recent]
        if not avail:
            avail = pool

        chosen = random.choice(avail)
        self._recent_served[action_key].append(chosen)
        return chosen
