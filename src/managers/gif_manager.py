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
    # ─── ANIME & COMEDY ACTIONS ───────────────────────────────────────────────
    "slapped": [
        "https://media.giphy.com/media/jLeyZWgtwvis8/giphy.gif",
        "https://media.giphy.com/media/Gf3AUz3eBNbTW/giphy.gif",
        "https://media.giphy.com/media/Zau0yrl15uzdK/giphy.gif",
        "https://media.giphy.com/media/vxvNnKRug7SCs/giphy.gif",
        "https://media.giphy.com/media/mEtSQlxqBtWWA/giphy.gif",
        "https://media.giphy.com/media/tXMPB9cHxUE7NbadYQ/giphy.gif",
        "https://media.giphy.com/media/lX03hULhgCYQ8/giphy.gif",
        "https://media.giphy.com/media/uqSU9GLjK337W/giphy.gif",
        "https://media.giphy.com/media/k1uEYPEtfEF4k/giphy.gif",
        "https://media.giphy.com/media/xUNd9HZq1itMkiK652/giphy.gif",
    ],
    "punched": [
        "https://media.giphy.com/media/arbHBDAq95uDc3xvLv/giphy.gif",
        "https://media.giphy.com/media/xUO4t2gkWBxDi/giphy.gif",
        "https://media.giphy.com/media/yo3TC0yeHd53G/giphy.gif",
        "https://media.giphy.com/media/Dra32i42hV55u/giphy.gif",
        "https://media.giphy.com/media/3oFzmmX8weSxudICHe/giphy.gif",
        "https://media.giphy.com/media/11HeubZNXOasBi/giphy.gif",
        "https://media.giphy.com/media/3o7btQ8jDTPGDpgc6I/giphy.gif",
        "https://media.giphy.com/media/d2YWTOsVtuHgOHhC/giphy.gif",
        "https://media.giphy.com/media/xUPGcAfeh68pJds6T6/giphy.gif",
        "https://media.giphy.com/media/Gnh8nS5TVOT3q/giphy.gif",
    ],
    "kicked": [
        "https://media.giphy.com/media/wOly8pa4s4W88/giphy.gif",
        "https://media.giphy.com/media/3o7TKOCXul7MptWPbq/giphy.gif",
        "https://media.giphy.com/media/u2LJ0n4lx6j2E/giphy.gif",
        "https://media.giphy.com/media/l4pTfx2qLszoacZRS/giphy.gif",
        "https://media.giphy.com/media/xUOxeZUc8UFwUBH2es/giphy.gif",
        "https://media.giphy.com/media/3o6Zt6ML6BklcajjsA/giphy.gif",
        "https://media.giphy.com/media/l0HlIDueXmcWNTPO0/giphy.gif",
        "https://media.giphy.com/media/26Ff4vV9fSfZ1gM5W/giphy.gif",
    ],
    "blasted": [
        "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
        "https://media.giphy.com/media/arbHBDAq95uDc3xvLv/giphy.gif",
        "https://media.giphy.com/media/3o7btQ8jDTPGDpgc6I/giphy.gif",
        "https://media.giphy.com/media/xUPGcAfeh68pJds6T6/giphy.gif",
        "https://media.giphy.com/media/d2YWTOsVtuHgOHhC/giphy.gif",
        "https://media.giphy.com/media/xUO4t2gkWBxDi/giphy.gif",
        "https://media.giphy.com/media/3oFzmmX8weSxudICHe/giphy.gif",
        "https://media.giphy.com/media/yo3TC0yeHd53G/giphy.gif",
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
        "https://media.giphy.com/media/EvYHHSntaIl5m/giphy.gif",
        "https://media.giphy.com/media/49mdjsMrH7oze/giphy.gif",
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
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/M3a51DMeWvYUo/giphy.gif",
    ],
    "bonked": [
        "https://media.giphy.com/media/6gLyE15StY3PC/giphy.gif",
        "https://media.giphy.com/media/pPs4HVuYB46foxfSSNL/giphy.gif",
        "https://media.giphy.com/media/RodyInaeK9vK3tuiIB/giphy.gif",
        "https://media.giphy.com/media/qs427c9qVc1Us/giphy.gif",
        "https://media.giphy.com/media/WB9Nq2Gg2jE839kS9b/giphy.gif",
        "https://media.giphy.com/media/8TweEdaxxfuElKkRxz/giphy.gif",
        "https://media.giphy.com/media/mEtSQlxqBtWWA/giphy.gif",
        "https://media.giphy.com/media/vxvNnKRug7SCs/giphy.gif",
    ],
    "cuddled": [
        "https://media.giphy.com/media/49mdjsMrH7oze/giphy.gif",
        "https://media.giphy.com/media/Vz58J8shFW6BvqnYTm/giphy.gif",
        "https://media.giphy.com/media/sUIZWMnfd4Mb6/giphy.gif",
        "https://media.giphy.com/media/3bqtLDeiDtwhq/giphy.gif",
        "https://media.giphy.com/media/EvYHHSntaIl5m/giphy.gif",
        "https://media.giphy.com/media/l2QDM9Jnim1YV5bxC/giphy.gif",
        "https://media.giphy.com/media/u9BxQbM5bxvwY/giphy.gif",
        "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
    ],
    "poked": [
        "https://media.giphy.com/media/pWd3gD577gOqs/giphy.gif",
        "https://media.giphy.com/media/y0NFayaBeiWEU/giphy.gif",
        "https://media.giphy.com/media/WvF3Z8qfU2KFUev3HI/giphy.gif",
        "https://media.giphy.com/media/10hO3rDNqqg2Xe/giphy.gif",
        "https://media.giphy.com/media/aZ4sQUpybai5y/giphy.gif",
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/4HP0ddZnNVnKU/giphy.gif",
        "https://media.giphy.com/media/L2z7dnOduqEow/giphy.gif",
    ],
    "high-fived": [
        "https://media.giphy.com/media/b5L1Lt3k4GYms/giphy.gif",
        "https://media.giphy.com/media/pHb82xtBPfqEg/giphy.gif",
        "https://media.giphy.com/media/3oEjHV0z8S7WM4MwnK/giphy.gif",
        "https://media.giphy.com/media/10LKovKon8PuQw/giphy.gif",
        "https://media.giphy.com/media/HX3lSnGXZnaWk/giphy.gif",
        "https://media.giphy.com/media/26Ff4vV9fSfZ1gM5W/giphy.gif",
        "https://media.giphy.com/media/l0HlIDueXmcWNTPO0/giphy.gif",
        "https://media.giphy.com/media/3o7TKOCXul7MptWPbq/giphy.gif",
    ],
    "yeeted": [
        "https://media.giphy.com/media/wOly8pa4s4W88/giphy.gif",
        "https://media.giphy.com/media/d2YWTOsVtuHgOHhC/giphy.gif",
        "https://media.giphy.com/media/arbHBDAq95uDc3xvLv/giphy.gif",
        "https://media.giphy.com/media/3o7btQ8jDTPGDpgc6I/giphy.gif",
        "https://media.giphy.com/media/xUPGcAfeh68pJds6T6/giphy.gif",
        "https://media.giphy.com/media/3o6Zt6ML6BklcajjsA/giphy.gif",
    ],
    "bitten": [
        "https://media.giphy.com/media/pWd3gD577gOqs/giphy.gif",
        "https://media.giphy.com/media/6gLyE15StY3PC/giphy.gif",
        "https://media.giphy.com/media/vxvNnKRug7SCs/giphy.gif",
        "https://media.giphy.com/media/osYdfUptPqVDNRAw5G/giphy.gif",
        "https://media.giphy.com/media/jLeyZWgtwvis8/giphy.gif",
    ],
    "danced": [
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/blSTtZehjAZ8I/giphy.gif",
        "https://media.giphy.com/media/mKMGLhoD8L4yc/giphy.gif",
        "https://media.giphy.com/media/13CoXDiaCcCoyk/giphy.gif",
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/7NoNw427RetMrdUsj3/giphy.gif",
    ],
    "cried": [
        "https://media.giphy.com/media/ROF8OQvDmxjHy/giphy.gif",
        "https://media.giphy.com/media/BEob5qwvuKJ97JREBW/giphy.gif",
        "https://media.giphy.com/media/26FPImXfDlv4AFbBC/giphy.gif",
        "https://media.giphy.com/media/d2lcHJTG5Tscg/giphy.gif",
        "https://media.giphy.com/media/OPU6wzx8JrHna/giphy.gif",
    ],
    "screamed": [
        "https://media.giphy.com/media/11tTNkNy1SdXGg/giphy.gif",
        "https://media.giphy.com/media/L95W4wv8nnb9K/giphy.gif",
        "https://media.giphy.com/media/4LXQcnVOjAZLRpIR6a/giphy.gif",
        "https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy.gif",
    ],
    "facepalmed": [
        "https://media.giphy.com/media/3og0INyCmHlNylks9O/giphy.gif",
        "https://media.giphy.com/media/ADr3eVMMPnjri/giphy.gif",
        "https://media.giphy.com/media/xsF1FSDbjguis/giphy.gif",
        "https://media.giphy.com/media/NFA61GS9qKZ68/giphy.gif",
    ],
    "laughed": [
        "https://media.giphy.com/media/10JhviFuU2gWD6/giphy.gif",
        "https://media.giphy.com/media/Mjl0BsspHSSuY/giphy.gif",
        "https://media.giphy.com/media/GpyS1lJXJYupG/giphy.gif",
        "https://media.giphy.com/media/ZqlvCTNHpqrio/giphy.gif",
    ],
    "vibed": [
        "https://media.giphy.com/media/blSTtZehjAZ8I/giphy.gif",
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/mKMGLhoD8L4yc/giphy.gif",
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
    ],

    # ─── ROMANCE & RELATIONSHIPS ──────────────────────────────────────────────
    "kissed": [
        "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
        "https://media.giphy.com/media/FqBTvSNjNzeZG/giphy.gif",
        "https://media.giphy.com/media/flmwZUupnj6Ew/giphy.gif",
        "https://media.giphy.com/media/KH1CTZtw1iP3W/giphy.gif",
        "https://media.giphy.com/media/wOtkVwroA6yzK/giphy.gif",
        "https://media.giphy.com/media/bm2O3nXTcKJeU/giphy.gif",
        "https://media.giphy.com/media/nyGFcsP0kAobm/giphy.gif",
        "https://media.giphy.com/media/Ka2NAhEGAnQKdTOZFu/giphy.gif",
        "https://media.giphy.com/media/zkppEMFvRX5FC/giphy.gif",
        "https://media.giphy.com/media/fB1pQq6hlt5nhtfzyu/giphy.gif",
    ],
    "married": [
        "https://media.giphy.com/media/V53jWRd057IZa/giphy.gif",
        "https://media.giphy.com/media/12VXIxjdR5Bup7/giphy.gif",
        "https://media.giphy.com/media/KZZXL9TDzT3u8/giphy.gif",
        "https://media.giphy.com/media/xThuWpnGQHBGvaPrVK/giphy.gif",
        "https://media.giphy.com/media/1081l36IGVT3io/giphy.gif",
        "https://media.giphy.com/media/26AHG5KGFxSkUWw1i/giphy.gif",
        "https://media.giphy.com/media/l41lT4at60nIVoxHO/giphy.gif",
        "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
    ],
    "loved": [
        "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
        "https://media.giphy.com/media/KZZXL9TDzT3u8/giphy.gif",
        "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
        "https://media.giphy.com/media/wnsgren9NtITS/giphy.gif",
        "https://media.giphy.com/media/PHZ7vmgbWLxbox5MsP/giphy.gif",
        "https://media.giphy.com/media/LIqFOpO9Qh0uA/giphy.gif",
    ],
    "flirted": [
        "https://media.giphy.com/media/zkppEMFvRX5FC/giphy.gif",
        "https://media.giphy.com/media/nyGFcsP0kAobm/giphy.gif",
        "https://media.giphy.com/media/Ka2NAhEGAnQKdTOZFu/giphy.gif",
        "https://media.giphy.com/media/wOtkVwroA6yzK/giphy.gif",
        "https://media.giphy.com/media/bm2O3nXTcKJeU/giphy.gif",
    ],
    "heartbroken": [
        "https://media.giphy.com/media/ROF8OQvDmxjHy/giphy.gif",
        "https://media.giphy.com/media/BEob5qwvuKJ97JREBW/giphy.gif",
        "https://media.giphy.com/media/26FPImXfDlv4AFbBC/giphy.gif",
        "https://media.giphy.com/media/d2lcHJTG5Tscg/giphy.gif",
    ],

    # ─── ADULT HUMOR & THIRST REACTIONS (Strictly non-explicit / adult characters) ───
    "intimate_couple": [
        "https://media.giphy.com/media/V53jWRd057IZa/giphy.gif",
        "https://media.giphy.com/media/KZZXL9TDzT3u8/giphy.gif",
        "https://media.giphy.com/media/12VXIxjdR5Bup7/giphy.gif",
        "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
        "https://media.giphy.com/media/xThuWpnGQHBGvaPrVK/giphy.gif",
        "https://media.giphy.com/media/1081l36IGVT3io/giphy.gif",
        "https://media.giphy.com/media/26AHG5KGFxSkUWw1i/giphy.gif",
        "https://media.giphy.com/media/l41lT4at60nIVoxHO/giphy.gif",
        "https://media.giphy.com/media/zkppEMFvRX5FC/giphy.gif",
        "https://media.giphy.com/media/nyGFcsP0kAobm/giphy.gif",
    ],
    "thirst": [
        "https://media.giphy.com/media/zkppEMFvRX5FC/giphy.gif",
        "https://media.giphy.com/media/1081l36IGVT3io/giphy.gif",
        "https://media.giphy.com/media/26AHG5KGFxSkUWw1i/giphy.gif",
        "https://media.giphy.com/media/xThuWpnGQHBGvaPrVK/giphy.gif",
        "https://media.giphy.com/media/Ka2NAhEGAnQKdTOZFu/giphy.gif",
        "https://media.giphy.com/media/wOtkVwroA6yzK/giphy.gif",
        "https://media.giphy.com/media/nyGFcsP0kAobm/giphy.gif",
        "https://media.giphy.com/media/bm2O3nXTcKJeU/giphy.gif",
    ],
    "hornybonk": [
        "https://media.giphy.com/media/6gLyE15StY3PC/giphy.gif",
        "https://media.giphy.com/media/pPs4HVuYB46foxfSSNL/giphy.gif",
        "https://media.giphy.com/media/RodyInaeK9vK3tuiIB/giphy.gif",
        "https://media.giphy.com/media/qs427c9qVc1Us/giphy.gif",
        "https://media.giphy.com/media/WB9Nq2Gg2jE839kS9b/giphy.gif",
        "https://media.giphy.com/media/8TweEdaxxfuElKkRxz/giphy.gif",
    ],

    # ─── AI PERSONAS ──────────────────────────────────────────────────────────
    "aigf": [
        "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
        "https://media.giphy.com/media/flmwZUupnj6Ew/giphy.gif",
        "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
        "https://media.giphy.com/media/wnsgren9NtITS/giphy.gif",
        "https://media.giphy.com/media/PHZ7vmgbWLxbox5MsP/giphy.gif",
        "https://media.giphy.com/media/LIqFOpO9Qh0uA/giphy.gif",
        "https://media.giphy.com/media/zkppEMFvRX5FC/giphy.gif",
        "https://media.giphy.com/media/ye7OTQgwmVuNTY22s3/giphy.gif",
    ],
    "aibaddie": [
        "https://media.giphy.com/media/arbHBDAq95uDc3xvLv/giphy.gif",
        "https://media.giphy.com/media/Ka2NAhEGAnQKdTOZFu/giphy.gif",
        "https://media.giphy.com/media/nyGFcsP0kAobm/giphy.gif",
        "https://media.giphy.com/media/bm2O3nXTcKJeU/giphy.gif",
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/Mjl0BsspHSSuY/giphy.gif",
    ],
    "aispecial": [
        "https://media.giphy.com/media/V53jWRd057IZa/giphy.gif",
        "https://media.giphy.com/media/12VXIxjdR5Bup7/giphy.gif",
        "https://media.giphy.com/media/KZZXL9TDzT3u8/giphy.gif",
        "https://media.giphy.com/media/1081l36IGVT3io/giphy.gif",
        "https://media.giphy.com/media/26AHG5KGFxSkUWw1i/giphy.gif",
        "https://media.giphy.com/media/l41lT4at60nIVoxHO/giphy.gif",
    ],
}

# Action key normalization mapping
ACTION_KEY_MAP: dict[str, str] = {
    # Anime actions
    "blast": "blasted", "punched": "punched", "punch": "punched",
    "animekick": "kicked", "akick": "kicked", "kick": "kicked",
    "slap": "slapped", "slapped": "slapped", "bonk": "bonked", "bonked": "bonked",
    "pat": "patted", "patted": "patted", "poke": "poked", "poked": "poked",
    "bite": "bitten", "bitten": "bitten", "yeet": "yeeted", "yeeted": "yeeted",
    "highfive": "high-fived", "high-fived": "high-fived",
    "dance": "danced", "danced": "danced", "cry": "cried", "cried": "cried",
    "scream": "screamed", "facepalm": "facepalmed", "laugh": "laughed", "laughat": "laughed",
    "vibe": "vibed", "comfort": "hugged", "cheer": "high-fived", "celebrate": "danced",
    "hug": "hugged", "hugged": "hugged", "cuddle": "cuddled", "cuddled": "cuddled",
    "stare": "poked", "scare": "screamed", "rage": "screamed", "wave": "high-fived",
    "embarrass": "facepalmed", "dramatic": "screamed", "angry": "screamed", "shy": "patted",
    "crywith": "cried", "mock": "laughed", "explode": "blasted", "dodge": "danced",
    "flex": "punched", "sleep": "cuddled", "wake": "slapped", "reaction": "vibed",

    # Romance
    "kiss": "kissed", "kissed": "kissed", "makeout": "kissed", "propose": "married",
    "marry": "married", "married": "married", "love": "loved", "crush": "loved",
    "ship": "loved", "couple": "married", "date": "loved", "jealous": "patted",
    "pickup": "flirted", "flirt": "flirted", "flirted": "flirted", "compliment": "loved",
    "romance": "loved", "heartbreak": "heartbroken", "divorce": "heartbroken",
    "breakup": "heartbroken", "reject": "heartbroken", "confess": "loved",
    "rizz": "flirted", "compatibility": "loved", "soulmate": "married", "loveletter": "loved",

    # Adult Humor (Restricted)
    "fuck": "intimate_couple", "goon": "thirst", "goonreaction": "thirst",
    "smash": "intimate_couple", "thirst": "thirst", "downbad": "thirst",
    "hornybonk": "hornybonk", "seduce": "thirst", "spank": "hornybonk",
    "wildreaction": "intimate_couple", "simp": "thirst", "obsessed": "loved",
    "fantasize": "intimate_couple", "tease": "flirted", "bedroomeyes": "thirst",
    "caughtlacking": "hornybonk", "rateattraction": "flirted",
    "downbadcheck": "thirst", "adultreaction": "intimate_couple",

    # AI Personas
    "aigf": "aigf", "aibaddie": "aibaddie", "aispecial": "aispecial",
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
        raw_key = action.lower().strip()
        canonical_key = ACTION_KEY_MAP.get(raw_key, raw_key)
        pool = CURATED_ACTION_GIFS.get(canonical_key)
        if not pool:
            pool = CURATED_ACTION_GIFS.get("hugged", [])

        # Try live Tenor / GIPHY API if session and keys exist
        tenor_key = os.getenv("TENOR_API_KEY", "").strip()
        giphy_key = os.getenv("GIPHY_API_KEY", "").strip()
        recent = set(self._recent_served[canonical_key])

        if session and not session.closed and (tenor_key or giphy_key):
            try:
                query = f"anime {canonical_key}"
                timeout = aiohttp.ClientTimeout(total=3.0)
                if tenor_key:
                    url = "https://tenor.googleapis.com/v2/search"
                    params = {
                        "q": query,
                        "key": tenor_key,
                        "limit": "15",
                        "contentfilter": "medium",
                        "media_filter": "gif",
                    }
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
                                self._recent_served[canonical_key].append(chosen)
                                return chosen
            except Exception as e:
                logger.debug(f"Live GIF lookup notice: {e}")

        # Fallback to curated pool with recent avoidance
        avail = [u for u in pool if u not in recent]
        if not avail:
            avail = pool

        chosen = random.choice(avail)
        self._recent_served[canonical_key].append(chosen)
        return chosen
