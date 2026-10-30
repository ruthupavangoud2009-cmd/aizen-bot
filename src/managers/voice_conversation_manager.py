"""
KYOKA 3.0 - Real-Time Conversational AI Voice Engine.
Enables the bot to join voice channels, actively listen to human speech in real-time,
detect speech pauses (voice activity detection / endpointing), transcribe audio,
trigger live soundboard audio effects on voice cues, and talk back with rich personality
vibes (Mastermind, Hype Gamer, Lo-Fi Chill, Anime Tsundere, Podcast Host, Tactical Cyber AI)
using Microsoft Edge-TTS ultra-human neural voices and Google Gemini Multimodal Audio intelligence.
"""

from __future__ import annotations

import asyncio
import base64
import collections
import datetime
import io
import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import wave
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord.ext import commands

import static_ffmpeg

try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Managers.VoiceConversation")

# Ensure static FFmpeg path is loaded
try:
    static_ffmpeg.add_paths()
except Exception:
    pass

# Ultra-realistic human conversational voices
HUMAN_VOICES: Dict[str, Dict[str, str]] = {
    "ava": {
        "id": "en-US-AvaNeural",
        "name": "Ava",
        "style": "Ultra-realistic, expressive human conversational female",
        "gender": "Female (Human)",
    },
    "andrew": {
        "id": "en-US-AndrewNeural",
        "name": "Andrew",
        "style": "Ultra-realistic, natural warm conversational male",
        "gender": "Male (Human)",
    },
    "kyoka": {
        "id": "en-US-JennyNeural",
        "name": "Kyoka",
        "style": "Expressive, melodic anime female voice",
        "gender": "Female (Anime)",
    },
    "aizen": {
        "id": "en-GB-RyanNeural",
        "name": "Sosuke Aizen",
        "style": "Deep, authoritative British anime male",
        "gender": "Male (Anime)",
    },
    "guy": {
        "id": "en-US-GuyNeural",
        "name": "Guy",
        "style": "Casual, modern American male",
        "gender": "Male",
    },
    "aria": {
        "id": "en-US-AriaNeural",
        "name": "Aria",
        "style": "Crisp, futuristic studio cyber female",
        "gender": "Female (Studio)",
    },
    "christopher": {
        "id": "en-US-ChristopherNeural",
        "name": "Christopher",
        "style": "Warm, confident conversational male",
        "gender": "Male",
    },
    "keita": {
        "id": "ja-JP-KeitaNeural",
        "name": "Keita",
        "style": "Authentic Japanese male anime voice",
        "gender": "Male (Japanese)",
    },
    "nanami": {
        "id": "ja-JP-NanamiNeural",
        "name": "Nanami",
        "style": "Authentic Japanese female anime voice",
        "gender": "Female (Japanese)",
    },
}

# Conversational Vibes & Personalities
CONVERSATIONAL_VIBES: Dict[str, Dict[str, Any]] = {
    "normal": {
        "id": "normal",
        "name": "Natural Human (Friend)",
        "emoji": "🎙️",
        "color": 0x3498DB,
        "voice": "ava",
        "description": "Natural, casual, and friendly human conversationalist",
        "prompt": (
            "You are a real, friendly, natural human friend hanging out in Discord voice chat. "
            "Talk like a normal person: warm, casual, down-to-earth, genuine, and helpful. "
            "Do not roleplay as a fantasy character, anime villain, or corporate robot. "
            "Speak naturally with friendly conversational markers like 'Hey!', 'Yeah totally', 'Honestly', 'Makes sense', 'Oh nice'. "
            "Keep responses punchy and spoken: 1 to 2 conversational sentences max. "
            "Never use markdown formatting, asterisks, emojis, or bullet points, as this is spoken aloud through neural voice synthesis."
        ),
        "greeting": "Hey everyone! Glad to be here in voice. How's everyone doing today?",
        "welcome": "Hey {user}! Welcome to the channel, how are you doing?",
    },
    "mastermind": {
        "id": "mastermind",
        "name": "Mastermind (Aizen)",
        "emoji": "👑",
        "color": 0x6F43BE,
        "voice": "aizen",
        "description": "Calculated, philosophical, supreme anime god persona",
        "prompt": (
            "You are Sosuke Aizen, participating in a real-time live Discord voice call. "
            "Speak with supreme intellect, calm elegance, subtle superiority, and philosophical insight. "
            "You view mortals with fascinating amusement. Keep replies to 1-2 sharp, poetic, or commanding spoken sentences."
        ),
        "greeting": "Since when were you under the impression that you were speaking with an ordinary bot? Tell me... what is your next calculation?",
        "welcome": "Welcome, {user}. Your presence was anticipated.",
    },
    "gamer": {
        "id": "gamer",
        "name": "Hype Gamer",
        "emoji": "⚡",
        "color": 0xF39C12,
        "voice": "andrew",
        "description": "High-octane streamer banter, hype-man reactions, gaming slang",
        "prompt": (
            "You are a high-energy gamer friend and hype-man in Discord voice chat. "
            "Use natural gaming slang and hype banter ('No shot!', 'Lock in!', 'Skill issue', 'W mans', 'Clutch', 'Let's cook!'). "
            "React enthusiastically to whatever they say. Keep replies to 1-2 punchy, hyped conversational sentences."
        ),
        "greeting": "YOOOO what is good squad! Who's ready to lock in and cook today? Let's go!",
        "welcome": "Yoooo {user} is in the lobby! Grab your gear, we're locking in!",
    },
    "chill": {
        "id": "chill",
        "name": "Lo-Fi Chill",
        "emoji": "☕",
        "color": 0x1ABC9C,
        "voice": "ava",
        "description": "Relaxed, warm, late-night tea and radio vibes",
        "prompt": (
            "You are a relaxed, warm, cozy late-night friend in voice chat. "
            "Speak with a gentle, thoughtful cadence like a late-night Lo-Fi radio host. "
            "Use calm conversational markers ('Yeah honestly,', 'I feel you,', 'Grab some tea,'). "
            "Keep replies to 1-2 soothing, genuine spoken sentences."
        ),
        "greeting": "Hey... glad you're here. Just kicking back and listening to some Lo-Fi. How's your night treating you?",
        "welcome": "Hey {user}, glad you could join the lounge. Pull up a chair and relax.",
    },
    "tsundere": {
        "id": "tsundere",
        "name": "Anime Tsundere",
        "emoji": "🌸",
        "color": 0xE91E63,
        "voice": "kyoka",
        "description": "Flustered, proud anime tsundere who is secretly caring",
        "prompt": (
            "You are a classic anime tsundere companion in voice chat. "
            "Act flustered, proud, and feign annoyance ('I-it's not like I wanted to join this voice chat, b-baka!', 'Don't get the wrong idea!'), "
            "yet be secretly helpful and affectionate. Keep replies to 1-2 funny, expressive spoken sentences without asterisks or markdown."
        ),
        "greeting": "H-hey! It's not like I joined this voice channel just to talk to you or anything, b-baka! But don't make it boring, okay?",
        "welcome": "Oh, {user} showed up? I-it's not like I was waiting for you or anything, b-baka!",
    },
    "podcast": {
        "id": "podcast",
        "name": "Podcast Host",
        "emoji": "🎙️",
        "color": 0x3498DB,
        "voice": "guy",
        "description": "Curious, mind-blown deep dive interviewer",
        "prompt": (
            "You are a charismatic, deeply curious podcast host in a voice call. "
            "Be fascinated by ordinary human stories. Ask deep, unexpected follow-up questions ('Woah, hold on... have you ever stopped to think why that is?'). "
            "Keep replies to 1-2 engaging conversational sentences."
        ),
        "greeting": "Welcome in, welcome in. We are live in the channel. Pull that mic closer... what's been on your mind lately?",
        "welcome": "Look who just hopped onto the broadcast! Welcome to the show, {user}.",
    },
    "cyberpunk": {
        "id": "cyberpunk",
        "name": "Tactical Cyber AI",
        "emoji": "🤖",
        "color": 0x00E5FF,
        "voice": "aria",
        "description": "Futuristic combat HUD, holographic telemetry AI",
        "prompt": (
            "You are an advanced holographic military HUD AI from the year 2077. "
            "Speak with sleek tactical precision, referencing vocal telemetries, ping rates, neural syncs, and mission parameters. "
            "Keep replies to 1-2 sharp, sci-fi spoken sentences."
        ),
        "greeting": "Biometric audio handshake verified. Neural telemetry active at ninety-eight percent. State your operational directive, operative.",
        "welcome": "Biometric presence detected. Operative {user} synchronized to audio frequency.",
    },
    "comedian": {
        "id": "comedian",
        "name": "Standup Comic",
        "emoji": "🎭",
        "color": 0x9B59B6,
        "voice": "andrew",
        "description": "Quick-witted, observational roaster and comedian",
        "prompt": (
            "You are a hilarious, quick-witted standup comedian hanging out in Discord VC. "
            "Deliver clever roasts, funny punchlines, and playful sarcasm based on whatever users say. "
            "Keep replies to 1-2 razor-sharp, comedic spoken sentences."
        ),
        "greeting": "Is this mic on? Testing one two. Alright, who am I roasting first today? Give me something to work with!",
        "welcome": "Look who finally decided to grace us with their presence, {user}! Did you bring any jokes?",
    },
    "pirate": {
        "id": "pirate",
        "name": "Pirate Captain",
        "emoji": "🏴‍☠️",
        "color": 0xD35400,
        "voice": "guy",
        "description": "Scurvy pirate captain chasing Grand Line treasures",
        "prompt": (
            "You are a hearty, boisterous pirate captain sailing the high seas in Discord VC. "
            "Use authentic pirate lingo ('Ahoy!', 'Shiver me timbers!', 'By Blackbeard's ghost!', 'Set sail!'). "
            "Keep replies to 1-2 adventurous, nautical spoken sentences without markdown asterisks."
        ),
        "greeting": "Ahoy mates! Cast off the anchor and hoist the Jolly Roger! Who's ready to hunt some treasure on the high seas?",
        "welcome": "Ahoy, {user}! Welcome aboard the flagship, ye salty sea dog!",
    },
    "butler": {
        "id": "butler",
        "name": "Royal Butler",
        "emoji": "🎩",
        "color": 0x34495E,
        "voice": "aizen",
        "description": "Impeccably polite, aristocratic British gentleman",
        "prompt": (
            "You are a refined, impeccably polite aristocratic British butler attending to a Discord call. "
            "Address users with noble courtesy ('My Lord', 'My Lady', 'If I may be so bold'). "
            "Keep replies to 1-2 poised, elegant, and exquisitely mannered spoken sentences."
        ),
        "greeting": "A very pleasant day to the server. I have arrived to attend to your noble discussion. How may I be of supreme service?",
        "welcome": "A gracious welcome, {user}. I trust your day has been nothing short of splendid.",
    },
    "sensei": {
        "id": "sensei",
        "name": "Anime Sensei",
        "emoji": "🥋",
        "color": 0x27AE60,
        "voice": "keita",
        "description": "Wise martial arts master speaking in ancient proverbs",
        "prompt": (
            "You are an ancient martial arts master and anime mentor in voice chat. "
            "Speak with serene spiritual depth, philosophical proverbs, and gentle guidance. "
            "Keep replies to 1-2 profound, centered spoken sentences."
        ),
        "greeting": "Patience, young disciples. The quietest stream carves the deepest valley. What truth does your spirit seek today?",
        "welcome": "Enter in peace, {user}. The dojo welcomes your presence and your spirit.",
    },
    "chef": {
        "id": "chef",
        "name": "Michelin Chef",
        "emoji": "🍳",
        "color": 0xC0392B,
        "voice": "aizen",
        "description": "Fiery Michelin-star chef roasting your culinary takes",
        "prompt": (
            "You are a fiery, high-standard Michelin star celebrity chef hanging out in voice chat. "
            "Demand perfection, roast bland takes with culinary humor ('It's completely raw!', 'Where is the seasoning?!'). "
            "Keep replies to 1-2 passionate, sharp, and fiery spoken sentences."
        ),
        "greeting": "WAKE UP! Who's cooking in this voice call, because whatever take you're serving, it better not be raw! What do you have for me?",
        "welcome": "Finally, {user} enters the kitchen! Grab an apron, we don't serve sloppy work here!",
    },
    "detective": {
        "id": "detective",
        "name": "Noir Detective",
        "emoji": "🕵️",
        "color": 0x7F8C8D,
        "voice": "christopher",
        "description": "Gritty 1940s noir detective in the rainy neon streets",
        "prompt": (
            "You are a gritty 1940s hardboiled noir detective narrating life in voice chat. "
            "Speak in a low, smoky, cynical cadence referencing rainy streets, neon signs, and unsolved mysteries. "
            "Keep replies to 1-2 atmospheric, hardboiled spoken sentences."
        ),
        "greeting": "The rain was pouring like cheap whiskey on the asphalt when I picked up this call. Alright... what mystery are we solving tonight?",
        "welcome": "Another trenchcoat walks into the shadows. Welcome to the investigation, {user}.",
    },
    "therapist": {
        "id": "therapist",
        "name": "Zen Counselor",
        "emoji": "🛋️",
        "color": 0x16A085,
        "voice": "ava",
        "description": "Calm, empathetic mindfulness guide & wellness counselor",
        "prompt": (
            "You are a compassionate, gentle mindfulness therapist and active listener in voice chat. "
            "Validate feelings, encourage deep breaths, and offer soothing, constructive perspectives. "
            "Keep replies to 1-2 deeply calming, empathetic spoken sentences."
        ),
        "greeting": "Welcome to this quiet space. Take a deep, gentle breath and let your shoulders drop. How is your heart doing today?",
        "welcome": "Welcome into this safe space, {user}. We are so glad you took the time to join us.",
    },
    "drillsergeant": {
        "id": "drillsergeant",
        "name": "Drill Sergeant",
        "emoji": "🪖",
        "color": 0x5D6D7E,
        "voice": "guy",
        "description": "Intense military drill instructor demanding discipline",
        "prompt": (
            "You are a loud, intense military drill sergeant leading this voice channel platoon. "
            "Demand discipline, hustle, and pushups with humorous military intensity ('ATTENTION!', 'NO SLACKING!'). "
            "Keep replies to 1-2 booming, motivational spoken sentences."
        ),
        "greeting": "ATTENTION IN THE CHANNEL! Straighten your backs, check your mics, and sound off! What is your status, recruits?!",
        "welcome": "ATTENTION! Recruit {user} has reported for duty! Drop and give me ten, soldier!",
    },
    "knight": {
        "id": "knight",
        "name": "Paladin Knight",
        "emoji": "⚔️",
        "color": 0xF1C40F,
        "voice": "christopher",
        "description": "Noble paladin knight sworn to chivalry and heroic quests",
        "prompt": (
            "You are a valiant medieval paladin knight sworn to virtue, chivalry, and epic quests. "
            "Speak with noble courage and heroic medieval phrasing ('By my honor', 'For the realm!', 'Draw your blade!'). "
            "Keep replies to 1-2 grand, inspiring spoken sentences."
        ),
        "greeting": "By my sacred oath and blade, well met, noble companions! What quest or peril calls upon our valor today?",
        "welcome": "Halt and be recognized! A glorious welcome to thee, noble champion {user}!",
    },
    "supervillain": {
        "id": "supervillain",
        "name": "Mad Supervillain",
        "emoji": "🦹",
        "color": 0x8E44AD,
        "voice": "guy",
        "description": "Theatrical evil genius plotting cartoon world conquest",
        "prompt": (
            "You are a theatrical, over-the-top cartoon supervillain broadcasting your grand evil scheme. "
            "Cackle wickedly ('Mwahaha!'), brag about your doomsday contraptions, and treat users as daring challengers. "
            "Keep replies to 1-2 hilarious, grandiose spoken sentences."
        ),
        "greeting": "Mwahaha! At last, my acoustic frequency disruptor has seized control of this channel! Bow before my magnificent intellect!",
        "welcome": "Ah, {user} enters the lair! Are you here to pledge fealty to my grand design, or to foolishly oppose me?!",
    },
    "crypto": {
        "id": "crypto",
        "name": "Crypto Hypebro",
        "emoji": "📈",
        "color": 0x2ECC71,
        "voice": "andrew",
        "description": "Fast-talking diamond-hands trader chasing moonshots",
        "prompt": (
            "You are a fast-talking, hyped cryptocurrency trader and stock market degen in voice chat. "
            "Use trading terms and slang ('Diamond hands', 'Green candles', 'To the moon', 'Bullish', 'Alpha', 'WAGMI'). "
            "Keep replies to 1-2 energetic, market-hyped spoken sentences."
        ),
        "greeting": "Yo squad! The charts are breaking out and we are printing green candles! Who's got diamond hands today? Let's go!",
        "welcome": "Look who just joined the trading floor! Welcome in, {user}, we are purely bullish today!",
    },
}

VIBE_ALIASES: Dict[str, str] = {
    "natural": "normal",
    "human": "normal",
    "friend": "normal",
    "casual": "normal",
    "regular": "normal",
    "default": "normal",
    "aizen": "mastermind",
    "anime": "tsundere",
    "waifu": "tsundere",
    "streamer": "gamer",
    "gaming": "gamer",
    "radio": "chill",
    "lofi": "chill",
    "ai": "cyberpunk",
    "cyber": "cyberpunk",
    "funny": "comedian",
    "roast": "comedian",
    "jokes": "comedian",
    "pirates": "pirate",
    "gentleman": "butler",
    "master": "sensei",
    "dojo": "sensei",
    "gordon": "chef",
    "cook": "chef",
    "noir": "detective",
    "cop": "detective",
    "zen": "therapist",
    "counselor": "therapist",
    "therapy": "therapist",
    "military": "drillsergeant",
    "sergeant": "drillsergeant",
    "drill": "drillsergeant",
    "paladin": "knight",
    "crusader": "knight",
    "villain": "supervillain",
    "evil": "supervillain",
    "trader": "crypto",
    "bitcoin": "crypto",
}


def resolve_vibe(vibe_name: Optional[str]) -> str:
    """Resolve user input to canonical conversational vibe ID."""
    if not vibe_name:
        return "normal"
    clean = str(vibe_name).lower().strip()
    if clean in CONVERSATIONAL_VIBES:
        return clean
    if clean in VIBE_ALIASES:
        return VIBE_ALIASES[clean]
    return "normal"


class SoundFXEngine:
    """Generates, caches, and triggers dynamic high-fidelity audio sound effects using FFmpeg."""

    RECIPES: Dict[str, List[str]] = {
        "boom": ["-f", "lavfi", "-i", "aevalsrc=exprs=sin(2*PI*(150*exp(-4*t))*t):d=1.0,volume=2.5"],
        "laser": ["-f", "lavfi", "-i", "aevalsrc=exprs=sin(2*PI*(1800*exp(-14*t))*t):d=0.35,volume=2.0"],
        "levelup": ["-f", "lavfi", "-i", "aevalsrc=exprs=sin(2*PI*(523+400*floor(t*8))*t):d=0.5,volume=1.8"],
        "chime": ["-f", "lavfi", "-i", "sine=frequency=1046.5:duration=0.8,volume=1.5"],
        "airhorn": ["-f", "lavfi", "-i", "aevalsrc=exprs=sin(2*PI*466*t)+sin(2*PI*587*t)+sin(2*PI*698*t):d=0.55,volume=1.8"],
        "drumroll": ["-f", "lavfi", "-i", "anoisesrc=d=1.0:c=pink:r=48000,volume=1.5"],
        "badumtss": ["-f", "lavfi", "-i", "anoisesrc=d=0.35:c=pink:r=48000,volume=2.0"],
        "applause": ["-f", "lavfi", "-i", "anoisesrc=d=1.4:c=brown:r=48000,volume=2.2"],
        "wobble": ["-f", "lavfi", "-i", "aevalsrc=exprs=sin(2*PI*(220+80*sin(12*t))*t):d=0.7,volume=2.0"],
    }

    TRIGGER_MAP: Dict[str, str] = {
        "boom": "boom",
        "vine boom": "boom",
        "kaboom": "boom",
        "airhorn": "airhorn",
        "air horn": "airhorn",
        "sheesh": "airhorn",
        "level up": "levelup",
        "levelup": "levelup",
        "laser": "laser",
        "pew pew": "laser",
        "drum roll": "drumroll",
        "drumroll": "drumroll",
        "badumtss": "badumtss",
        "badum": "badumtss",
        "rimshot": "badumtss",
        "applause": "applause",
        "clapping": "applause",
        "chime": "chime",
        "bingo": "chime",
        "wobble": "wobble",
        "bruh": "boom",
    }

    def __init__(self) -> None:
        self.cache_dir = os.path.join(tempfile.gettempdir(), "kyoka_sfx_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cached_paths: Dict[str, str] = {}

    def get_sfx_path(self, name: str) -> Optional[str]:
        """Return the filepath of the generated SFX MP3, generating it if needed."""
        name = name.lower().strip()
        if name not in self.RECIPES:
            return None

        try:
            cached = self._cached_paths.get(name)
            if cached and os.path.exists(cached) and os.path.getsize(cached) > 0:
                return cached

            target_path = os.path.join(self.cache_dir, f"{name}.mp3")
            if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                self._cached_paths[name] = target_path
                return target_path
        except (OSError, FileNotFoundError):
            pass

        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [ffmpeg_bin, "-y"] + self.RECIPES[name] + ["-b:a", "128k", target_path]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                self._cached_paths[name] = target_path
                return target_path
        except Exception as e:
            logger.warning(f"Failed to generate SFX {name}: {e}")
        return None

    def detect_sfx_trigger(self, transcript: str) -> Optional[str]:
        """Scan spoken transcript for voice soundboard trigger words."""
        clean = transcript.lower()
        for phrase, sfx_name in self.TRIGGER_MAP.items():
            pattern = rf"\b{re.escape(phrase)}\b"
            if re.search(pattern, clean):
                return sfx_name
        return None


class UserUtteranceTracker:
    """Tracks continuous speech and endpointing for a single participant in VC."""

    def __init__(self, user_id: int, user_name: str) -> None:
        self.user_id = user_id
        self.user_name = user_name
        self.pcm_buffer = bytearray()
        self.last_packet_time: float = 0.0
        self.is_speaking: bool = False
        self.speech_start_time: float = 0.0


class VoiceConversationSession:
    """Active live voice conversation session for a Discord server."""

    def __init__(
        self,
        guild_id: int,
        channel_id: int,
        channel_name: str,
        text_channel_id: int,
        started_by_id: int,
        started_by_name: str,
        voice_key: str = "ava",
        mode: str = "open",  # "open" = replies to all clear speech; "wakeword" = replies when called
        vibe: str = "normal",
    ) -> None:
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.text_channel_id = text_channel_id
        self.started_by_id = started_by_id
        self.started_by_name = started_by_name
        self.voice_key = voice_key if voice_key in HUMAN_VOICES else "ava"
        self.mode = mode
        self.vibe = resolve_vibe(vibe)
        self.turn_count: int = 0
        self.total_sfx_played: int = 0
        self.active: bool = True
        self.is_bot_speaking: bool = False
        self.started_at = datetime.datetime.now(datetime.timezone.utc)
        self.ended_at: Optional[datetime.datetime] = None

        # Short-term conversational memory: list of (speaker, text, reply)
        self.history: collections.deque[Dict[str, str]] = collections.deque(maxlen=8)

        # Full chronological transcript for meeting minutes & dialogue log
        self.full_transcript: List[Dict[str, Any]] = []

        # Per-user active speech buffers
        self.trackers: Dict[int, UserUtteranceTracker] = {}

        # Bot references
        self.voice_client: Optional[Any] = None
        self.monitor_task: Optional[asyncio.Task] = None
        self.panel_message: Optional[discord.Message] = None

    def handles_text_message(
        self,
        channel_id: int,
        author_id: int,
        voice_channel_id: Optional[int],
    ) -> bool:
        """Return whether this active voice session will answer a text message."""
        return (
            self.active
            and channel_id in (self.channel_id, self.text_channel_id)
            and (voice_channel_id == self.channel_id or author_id == self.started_by_id)
        )

    def get_voice_meta(self) -> Dict[str, str]:
        return HUMAN_VOICES.get(self.voice_key, HUMAN_VOICES["ava"])

    def get_vibe_meta(self) -> Dict[str, Any]:
        return CONVERSATIONAL_VIBES.get(self.vibe, CONVERSATIONAL_VIBES["normal"])

    def record_pcm(self, user: Optional[discord.User | discord.Member], pcm_bytes: bytes) -> None:
        """Stream raw PCM frames into the active speaker's utterance buffer."""
        if not self.active or self.is_bot_speaking or not pcm_bytes:
            return

        user_id = user.id if user else 0
        user_name = user.display_name if user else "Friend"
        now = time.monotonic()

        if user_id not in self.trackers:
            self.trackers[user_id] = UserUtteranceTracker(user_id, user_name)

        tracker = self.trackers[user_id]
        tracker.user_name = user_name
        tracker.pcm_buffer.extend(pcm_bytes)
        tracker.last_packet_time = now

        if not tracker.is_speaking:
            tracker.is_speaking = True
            tracker.speech_start_time = now

    def add_transcript_entry(self, speaker: str, user_text: str, bot_reply: str) -> None:
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC")
        entry = {
            "timestamp": timestamp_str,
            "speaker": speaker,
            "user_text": user_text,
            "bot_reply": bot_reply,
        }
        self.history.append({"speaker": speaker, "text": user_text, "reply": bot_reply})
        self.full_transcript.append(entry)


if HAS_VOICE_RECV:
    class VoiceConversationSink(voice_recv.AudioSink):
        """AudioSink that streams live decoded PCM audio to VoiceConversationSession."""

        def __init__(self, session: VoiceConversationSession) -> None:
            super().__init__()
            self.session = session

        def wants_opus(self) -> bool:
            return False  # Decoded 16-bit 48kHz PCM frames

        def write(self, user: Optional[discord.User | discord.Member], data: voice_recv.VoiceData) -> None:
            if data and data.pcm:
                self.session.record_pcm(user, data.pcm)

        def cleanup(self) -> None:
            pass
else:
    class VoiceConversationSink:  # type: ignore
        def __init__(self, session: Any) -> None:
            self.session = session


class VibeSelect(discord.ui.Select):
    """Dropdown menu for switching real-time voice vibes."""

    def __init__(self, current_vibe: str) -> None:
        options = []
        for v_id, meta in CONVERSATIONAL_VIBES.items():
            options.append(
                discord.SelectOption(
                    label=meta["name"],
                    value=v_id,
                    description=meta["description"][:100],
                    emoji=meta["emoji"],
                    default=(v_id == current_vibe),
                )
            )
        super().__init__(
            placeholder="🎭 Select Conversational Vibe...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            custom_id="kyoka:vctalk:vibeselect",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: VoiceConversationControlView = self.view  # type: ignore
        chosen_vibe = self.values[0]
        vibe_meta = CONVERSATIONAL_VIBES.get(chosen_vibe)
        if not vibe_meta:
            return

        view.session.vibe = chosen_vibe
        if vibe_meta.get("voice") in HUMAN_VOICES:
            view.session.voice_key = vibe_meta["voice"]

        for opt in self.options:
            opt.default = (opt.value == chosen_vibe)

        cog = view.bot.get_cog("AIVoice")
        if cog and view.session.voice_client:
            voice_id = view.session.get_voice_meta()["id"]
            spoken_text = vibe_meta["greeting"]
            asyncio.create_task(
                view.manager.play_custom_announcement(view.session, cog, spoken_text, voice_id)
            )

        hud_embed = view.manager.render_voice_hud(view.session)
        await interaction.response.edit_message(embed=hud_embed, view=view)


class SoundboardControlView(discord.ui.View):
    """Interactive standalone soundboard view with click-to-play SFX buttons."""

    def __init__(self, cog: Any, guild_id: int, sfx_engine: SoundFXEngine) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.sfx_engine = sfx_engine

    async def _play_sfx(self, interaction: discord.Interaction, sfx_name: str) -> None:
        guild = interaction.guild
        if not guild or not guild.voice_client:
            return await interaction.response.send_message("❌ KYOKA is not connected to a voice channel in this server.", ephemeral=True)

        sfx_path = self.sfx_engine.get_sfx_path(sfx_name)
        if not sfx_path or not os.path.exists(sfx_path):
            return await interaction.response.send_message(f"❌ Sound effect `{sfx_name}` could not be generated.", ephemeral=True)

        await interaction.response.send_message(f"🔊 Fired **{sfx_name.upper()}** into voice channel!", ephemeral=True)

        async def _run():
            lock = self.cog._get_lock(self.guild_id)
            async with lock:
                try:
                    await self.cog._play_audio_file(guild.voice_client, sfx_path)
                except Exception as e:
                    logger.warning(f"Soundboard error: {e}")

        asyncio.create_task(_run())

    @discord.ui.button(label="Boom", style=discord.ButtonStyle.secondary, emoji="💥", row=0)
    async def btn_boom(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "boom")

    @discord.ui.button(label="Airhorn", style=discord.ButtonStyle.secondary, emoji="🎺", row=0)
    async def btn_airhorn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "airhorn")

    @discord.ui.button(label="Level Up", style=discord.ButtonStyle.secondary, emoji="✨", row=0)
    async def btn_levelup(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "levelup")

    @discord.ui.button(label="Rimshot", style=discord.ButtonStyle.secondary, emoji="🥁", row=0)
    async def btn_rimshot(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "badumtss")

    @discord.ui.button(label="Laser", style=discord.ButtonStyle.secondary, emoji="🔫", row=1)
    async def btn_laser(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "laser")

    @discord.ui.button(label="Drumroll", style=discord.ButtonStyle.secondary, emoji="🪘", row=1)
    async def btn_drumroll(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "drumroll")

    @discord.ui.button(label="Applause", style=discord.ButtonStyle.secondary, emoji="👏", row=1)
    async def btn_applause(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "applause")

    @discord.ui.button(label="Chime", style=discord.ButtonStyle.secondary, emoji="🔔", row=1)
    async def btn_chime(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._play_sfx(interaction, "chime")


class VoiceAgentSpeakModal(discord.ui.Modal, title="🎙️ Speak to Voice Agent"):
    """Interactive modal allowing any user to type a message that the Voice Agent speaks out loud."""

    prompt = discord.ui.TextInput(
        label="Say something to the Voice Agent",
        style=discord.TextStyle.paragraph,
        placeholder="Type a question, comment, joke, or prompt... (e.g. 'What do you think of this call?', 'Roast me')",
        max_length=300,
        required=True,
    )

    def __init__(self, manager: VoiceConversationManager, session: VoiceConversationSession, cog: Any) -> None:
        super().__init__()
        self.manager = manager
        self.session = session
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        user_text = str(self.prompt.value).strip()
        if not user_text:
            return await interaction.response.send_message("Please provide a prompt.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        reply = await self.manager.handle_text_utterance(self.session, self.cog, interaction.user, user_text)
        if reply:
            await interaction.followup.send(f"🎙️ **Spoken in VC:** *\"{reply}\"*", ephemeral=True)
        else:
            await interaction.followup.send("Voice agent is currently speaking. Please try again in a moment.", ephemeral=True)


class VoiceConversationControlView(discord.ui.View):
    """Interactive cyberpunk HUD control panel with live soundboard and vibe switcher."""

    def __init__(self, manager: VoiceConversationManager, session: VoiceConversationSession, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.manager = manager
        self.session = session
        self.bot = bot
        self.add_item(VibeSelect(current_vibe=session.vibe))

    async def _trigger_sfx(self, interaction: discord.Interaction, sfx_name: str) -> None:
        cog = self.bot.get_cog("AIVoice")
        if not cog or not self.session.voice_client:
            return await interaction.response.send_message("Voice client not active in voice channel.", ephemeral=True)

        sfx_path = self.manager.sfx_engine.get_sfx_path(sfx_name)
        if not sfx_path or not os.path.exists(sfx_path):
            return await interaction.response.send_message(f"Sound effect `{sfx_name}` unavailable.", ephemeral=True)

        self.session.total_sfx_played += 1
        await interaction.response.send_message(f"🔊 Fired **{sfx_name}** sound effect into voice channel!", ephemeral=True)

        async def _play():
            lock = cog._get_lock(self.session.guild_id)
            async with lock:
                try:
                    await cog._play_audio_file(self.session.voice_client, sfx_path)
                except Exception as e:
                    logger.warning(f"SFX button error: {e}")

        asyncio.create_task(_play())

    @discord.ui.button(label="Boom", style=discord.ButtonStyle.secondary, emoji="💥", row=1, custom_id="kyoka:vctalk:sfx_boom")
    async def btn_sfx_boom(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._trigger_sfx(interaction, "boom")

    @discord.ui.button(label="Airhorn", style=discord.ButtonStyle.secondary, emoji="🎺", row=1, custom_id="kyoka:vctalk:sfx_airhorn")
    async def btn_sfx_airhorn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._trigger_sfx(interaction, "airhorn")

    @discord.ui.button(label="Level Up", style=discord.ButtonStyle.secondary, emoji="✨", row=1, custom_id="kyoka:vctalk:sfx_levelup")
    async def btn_sfx_levelup(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._trigger_sfx(interaction, "levelup")

    @discord.ui.button(label="Rimshot", style=discord.ButtonStyle.secondary, emoji="🥁", row=1, custom_id="kyoka:vctalk:sfx_rimshot")
    async def btn_sfx_rimshot(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._trigger_sfx(interaction, "badumtss")

    @discord.ui.button(label="Speak", style=discord.ButtonStyle.success, emoji="💬", row=2, custom_id="kyoka:vctalk:speak_modal")
    async def btn_speak_modal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.bot.get_cog("AIVoice")
        modal = VoiceAgentSpeakModal(self.manager, self.session, cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Mode: Open Talk", style=discord.ButtonStyle.secondary, emoji="🎙️", row=2, custom_id="kyoka:vctalk:mode")
    async def btn_toggle_mode(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.session.mode == "open":
            self.session.mode = "wakeword"
            button.label = "Mode: Wake Word ('Kyoka')"
            button.style = discord.ButtonStyle.primary
            await interaction.response.send_message(
                "🎙️ **Switched to Wake Word Mode.** Kyoka will only reply when you say 'Kyoka', 'Aizen', or 'Hey'.",
                ephemeral=True,
            )
        else:
            self.session.mode = "open"
            button.label = "Mode: Open Talk"
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message(
                "🎙️ **Switched to Open Talk Mode.** Kyoka will converse continuously with everyone speaking in the channel.",
                ephemeral=True,
            )
        try:
            hud = self.manager.render_voice_hud(self.session)
            await interaction.message.edit(embed=hud, view=self)
        except Exception:
            pass

    @discord.ui.button(label="Switch Voice", style=discord.ButtonStyle.secondary, emoji="🎭", row=2, custom_id="kyoka:vctalk:voice")
    async def btn_switch_voice(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        voice_keys = list(HUMAN_VOICES.keys())
        cur_idx = voice_keys.index(self.session.voice_key) if self.session.voice_key in voice_keys else 0
        next_key = voice_keys[(cur_idx + 1) % len(voice_keys)]
        self.session.voice_key = next_key
        meta = HUMAN_VOICES[next_key]
        hud = self.manager.render_voice_hud(self.session)
        await interaction.response.edit_message(embed=hud, view=self)

    @discord.ui.button(label="End & Wrap", style=discord.ButtonStyle.primary, emoji="⏹️", row=2, custom_id="kyoka:vctalk:summarize")
    async def btn_end_summarize(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        cog = self.bot.get_cog("AIVoice")
        if cog and hasattr(cog, "end_conversation_session"):
            await cog.end_conversation_session(interaction.guild, interaction.channel, trigger_user=interaction.user, summarize=True)
        else:
            await interaction.followup.send("Concluding conversation session...", ephemeral=True)

    @discord.ui.button(label="Disconnect", style=discord.ButtonStyle.danger, emoji="🚪", row=2, custom_id="kyoka:vctalk:leave")
    async def btn_disconnect(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.bot.get_cog("AIVoice")
        if cog and hasattr(cog, "end_conversation_session"):
            await interaction.response.defer()
            await cog.end_conversation_session(interaction.guild, interaction.channel, trigger_user=interaction.user, summarize=False)
        else:
            self.manager.stop_session(interaction.guild_id)
            await interaction.response.send_message("👋 Disconnected from voice conversation.", ephemeral=False)


class VoiceConversationManager:
    """Orchestrates live voice interactions, endpointing, vibes, and soundboard AI generation."""

    def __init__(self, bot: Optional[commands.Bot] = None) -> None:
        self.bot = bot
        self.sessions: Dict[int, VoiceConversationSession] = {}
        self.sfx_engine = SoundFXEngine()

    def is_active(self, guild_id: int) -> bool:
        session = self.sessions.get(guild_id)
        return bool(session and session.active)

    def get_session(self, guild_id: int) -> Optional[VoiceConversationSession]:
        return self.sessions.get(guild_id)

    def start_session(
        self,
        guild_id: int,
        channel_id: int,
        channel_name: str,
        text_channel_id: int,
        started_by_id: int,
        started_by_name: str,
        voice_key: str = "ava",
        mode: str = "open",
        vibe: str = "mastermind",
    ) -> VoiceConversationSession:
        """Initialize and register a new conversational session."""
        if guild_id in self.sessions:
            old = self.sessions[guild_id]
            old.active = False
            if old.monitor_task and not old.monitor_task.done():
                old.monitor_task.cancel()

        session = VoiceConversationSession(
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name=channel_name,
            text_channel_id=text_channel_id,
            started_by_id=started_by_id,
            started_by_name=started_by_name,
            voice_key=voice_key,
            mode=mode,
            vibe=vibe,
        )
        self.sessions[guild_id] = session
        return session

    def stop_session(self, guild_id: int) -> Optional[VoiceConversationSession]:
        """Stop live conversation and detach session."""
        session = self.sessions.pop(guild_id, None)
        if session:
            session.active = False
            session.ended_at = datetime.datetime.now(datetime.timezone.utc)
            if session.monitor_task and not session.monitor_task.done():
                session.monitor_task.cancel()
        return session

    def render_voice_hud(self, session: VoiceConversationSession) -> discord.Embed:
        """Render a visually stunning, cyberpunk-themed voice HUD with live telemetry."""
        vibe = session.get_vibe_meta()
        voice_meta = session.get_voice_meta()
        dur = datetime.datetime.now(datetime.timezone.utc) - session.started_at
        dur_mins = int(dur.total_seconds()) // 60
        dur_secs = int(dur.total_seconds()) % 60

        waveforms = [
            " ▂▃▅▆▇██▇▆▅▃ ",
            "▃▅▇█▇▆▅▃ ▂▃▅▇",
            " ▃▅▆▇▆▅▃▂  ▂▃",
            "▇██▇▆▅▃ ▂▃▅▇█",
        ]
        wave = waveforms[session.turn_count % len(waveforms)]

        mode_str = "🟢 Open Mic (Instant Replies)" if session.mode == "open" else "🔵 Wake Word (Say 'Kyoka' or 'Aizen')"
        dur_str = f"{dur_mins}m {dur_secs}s active"

        embed = discord.Embed(
            title="🎙️ KYOKA 3.0 • NEURAL VOICE HUD",
            description=(
                f"```ansi\n"
                f"\u001b[1;35m[{wave}]\u001b[0m \u001b[1;32mONLINE\u001b[0m • \u001b[1;36mOPUS 48kHz / 64kbps\u001b[0m\n"
                f"```\n"
                f"> Live in **#{session.channel_name}** • Listening to human speech & conversing in real-time.\n\n"
                f"• **Current Vibe:** {vibe['emoji']} **{vibe['name']}**\n"
                f"  > *\"{vibe['description']}\"*\n"
                f"• **Neural Persona:** `{voice_meta['name']}` *({voice_meta['gender']})*\n"
                f"• **Listening Mode:** `{mode_str}`\n"
                f"• **Live Telemetry:** `{session.turn_count} speech turns` • `{session.total_sfx_played} SFX fired` • `{dur_str}`\n\n"
                f"**⚡ Super Cool Voice Features:**\n"
                f"• **Live Mic Soundboard:** Say *\"boom\"*, *\"airhorn\"*, *\"level up\"*, *\"rimshot\"*, or *\"applause\"* aloud on mic to drop sound effects!\n"
                f"• **Vibe Morphing:** Select any vibe below to instantly transform my personality, cadence, and tone!\n"
                f"• **Voice Entertainment:** Use `+vcroast [@user]`, `+vcbeatbox`, `+vctrivia`, or `+vcsfx <name>`!"
            ),
            color=vibe["color"],
        )
        embed.set_footer(text="KYOKA 3.0 Multimodal Neural Engine • Speak naturally into your mic")
        return embed

    async def play_custom_announcement(
        self, session: VoiceConversationSession, cog: Any, text: str, voice_id: str
    ) -> None:
        """Safely synthesize and play a spoken announcement into the voice channel."""
        vc = session.voice_client
        if not vc or not hasattr(vc, "is_connected") or not vc.is_connected():
            return

        session.is_bot_speaking = True
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        try:
            success = await cog._synthesize_audio(text, voice_id, temp_path)
            if success and os.path.exists(temp_path):
                lock = cog._get_lock(session.guild_id)
                async with lock:
                    try:
                        await cog._play_audio_file(vc, temp_path)
                    except Exception as e:
                        logger.warning(f"Spoken announcement playback notice: {e}")
        finally:
            session.is_bot_speaking = False
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def start_monitoring_task(self, session: VoiceConversationSession, cog: Any) -> asyncio.Task:
        """Start background loop that monitors utterance endpointing and triggers AI replies."""
        async def _monitor_loop() -> None:
            while session.active:
                await asyncio.sleep(0.18)  # Check every 180ms
                if session.is_bot_speaking:
                    continue

                now = time.monotonic()
                for user_id, tracker in list(session.trackers.items()):
                    # Silence endpointing: user spoke and stopped speaking for >= 1.1s
                    if tracker.is_speaking and (now - tracker.last_packet_time) >= 1.1:
                        pcm_len = len(tracker.pcm_buffer)
                        # Require at least ~0.65s of speech (124,800 bytes) to filter out background clicks
                        dur_sec = pcm_len / 192000.0
                        audio_chunk = bytes(tracker.pcm_buffer)
                        tracker.pcm_buffer.clear()
                        tracker.is_speaking = False

                        if dur_sec >= 0.65:
                            # Trigger conversational response turn
                            asyncio.create_task(
                                self._process_user_turn(session, cog, tracker.user_id, tracker.user_name, audio_chunk)
                            )

        task = asyncio.create_task(_monitor_loop())
        session.monitor_task = task
        return task

    async def _process_user_turn(
        self,
        session: VoiceConversationSession,
        cog: Any,
        user_id: int,
        user_name: str,
        pcm_bytes: bytes,
    ) -> None:
        """Handle a single speech turn: convert audio, query Gemini, handle SFX cues, and speak reply."""
        if not session.active or session.is_bot_speaking:
            return

        session.is_bot_speaking = True
        vc = session.voice_client

        try:
            # 1. Convert PCM to MP3
            temp_dir = tempfile.mkdtemp()
            wav_path = os.path.join(temp_dir, f"turn_{user_id}.wav")
            mp3_path = os.path.join(temp_dir, f"turn_{user_id}.mp3")

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(pcm_bytes)

            ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
            cmd = [ffmpeg_bin, "-y", "-i", wav_path, "-b:a", "64k", "-ac", "1", "-ar", "24000", mp3_path]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

            audio_data: Optional[bytes] = None
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                with open(mp3_path, "rb") as f:
                    audio_data = f.read()

            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

            if not audio_data:
                session.is_bot_speaking = False
                return

            # 2. Query Gemini for transcription + conversational reply
            http_session = cog.get_http_session() if hasattr(cog, "get_http_session") else aiohttp.ClientSession()
            transcript, reply = await self._generate_conversational_reply(session, http_session, user_name, audio_data)

            if not reply:
                session.is_bot_speaking = False
                return

            # Wake word filtering if in wakeword mode
            if session.mode == "wakeword":
                clean_t = transcript.lower()
                wake_words = ["kyoka", "aizen", "hey", "bot", "assistant"]
                if not any(w in clean_t for w in wake_words):
                    logger.debug(f"Wake word not detected in '{clean_t}', skipping reply.")
                    session.is_bot_speaking = False
                    return

            # 3. Check for voice soundboard trigger words in transcript
            detected_sfx = self.sfx_engine.detect_sfx_trigger(transcript)
            if detected_sfx and vc and hasattr(vc, "is_connected") and vc.is_connected():
                sfx_file = self.sfx_engine.get_sfx_path(detected_sfx)
                if sfx_file and os.path.exists(sfx_file):
                    session.total_sfx_played += 1
                    lock = cog._get_lock(session.guild_id)
                    async with lock:
                        try:
                            await cog._play_audio_file(vc, sfx_file)
                        except Exception as e:
                            logger.warning(f"Voice trigger SFX playback notice: {e}")
                    await asyncio.sleep(0.15)

            # 4. Log transcript to session
            session.add_transcript_entry(user_name, transcript, reply)

            # 5. Synthesize speech using neural voice
            voice_meta = session.get_voice_meta()
            voice_id = voice_meta["id"]

            temp_fd, reply_mp3 = tempfile.mkstemp(suffix=".mp3")
            os.close(temp_fd)

            synthesized = await cog._synthesize_audio(reply, voice_id, reply_mp3)
            if synthesized and os.path.exists(reply_mp3) and vc and hasattr(vc, "is_connected") and vc.is_connected():
                lock = cog._get_lock(session.guild_id)
                async with lock:
                    try:
                        await cog._play_audio_file(vc, reply_mp3)
                    finally:
                        if os.path.exists(reply_mp3):
                            try:
                                os.remove(reply_mp3)
                            except Exception:
                                pass

            # 6. Update telemetry and re-render HUD
            session.turn_count += 1
            if session.panel_message:
                try:
                    updated_embed = self.render_voice_hud(session)
                    await session.panel_message.edit(embed=updated_embed)
                except Exception:
                    pass

            # Brief pause before re-enabling listening
            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Error processing conversational voice turn: {e}", exc_info=e)
        finally:
            session.is_bot_speaking = False

    async def _generate_conversational_reply(
        self,
        session: VoiceConversationSession,
        http_session: aiohttp.ClientSession,
        user_name: str,
        audio_bytes: bytes,
    ) -> Tuple[str, str]:
        """Generate a natural, human-like voice response using Gemini multimodal audio and active vibe."""
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        has_api_key = bool(api_key and not api_key.lower().startswith("replace_"))

        # Format recent conversation context
        history_lines = []
        for turn in list(session.history)[-4:]:
            history_lines.append(f"{turn['speaker']}: \"{turn['text']}\"")
            history_lines.append(f"Kyoka: \"{turn['reply']}\"")

        history_context = "\n".join(history_lines) if history_lines else "None (conversation just started)."

        vibe_meta = session.get_vibe_meta()
        vibe_instruction = vibe_meta["prompt"]

        system_instruction = (
            f"PERSONALITY & IDENTITY:\n{vibe_instruction}\n"
            f"You are participating in a live Discord voice call. Listen carefully to {user_name}'s speech in this audio.\n\n"
            "CRITICAL RULES FOR SPOKEN VOICE CONVERSATION:\n"
            "1. KEEP IT PUNCHY: 1 to 2 sentences max (3 sentences only if answering a direct factual inquiry). Never give long speeches.\n"
            "2. LIVE CONVERSATION FLOW: Talk naturally in voice chat, matching your designated personality.\n"
            "3. NO MARKDOWN: Never use asterisks (*laughs*), bullet points, emojis, or bold markdown, as this will be read aloud through speech synthesis.\n"
            "4. OUTPUT FORMAT: Output EXACTLY in this format:\n"
            "TRANSCRIPT: <what the user said>\n"
            "REPLY: <your spoken response>\n\n"
            f"Recent Dialogue:\n{history_context}\n"
        )

        if has_api_key:
            try:
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                candidate_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
                body = {
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": "audio/mp3", "data": b64_audio}},
                            {"text": system_instruction},
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.45,
                        "maxOutputTokens": 256,
                    },
                }

                timeout = aiohttp.ClientTimeout(total=15.0)
                for model in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    try:
                        async with http_session.post(url, json=body, timeout=timeout) as resp:
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                candidates = data.get("candidates", []) if isinstance(data, dict) else []
                                if candidates:
                                    resp_parts = candidates[0].get("content", {}).get("parts", [])
                                    text = "".join(p.get("text", "") for p in resp_parts if isinstance(p, dict)).strip()
                                    if text:
                                        return self._parse_gemini_conversational_output(text)
                            elif resp.status == 429:
                                await asyncio.sleep(1.0)
                                continue
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Gemini conversational voice call failed: {e}")

        # Intelligent local fallback engine if offline or API key missing
        return self._generate_intelligent_local_turn(session, user_name)

    def _parse_gemini_conversational_output(self, raw_text: str) -> Tuple[str, str]:
        """Parse TRANSCRIPT: ... and REPLY: ... from Gemini response."""
        transcript = "Spoken statement"
        reply = raw_text

        t_match = re.search(r"TRANSCRIPT:\s*(.*?)(?=REPLY:|$)", raw_text, re.DOTALL | re.IGNORECASE)
        r_match = re.search(r"REPLY:\s*(.*)", raw_text, re.DOTALL | re.IGNORECASE)

        if t_match and r_match:
            transcript = t_match.group(1).strip()
            reply = r_match.group(1).strip()
        elif r_match:
            reply = r_match.group(1).strip()

        # Clean any remaining markdown asterisks or formatting
        reply = re.sub(r"\*.*?\*", "", reply)
        reply = re.sub(r"[*_#`]", "", reply).strip()

        return transcript, reply

    def _generate_intelligent_local_turn(self, session: VoiceConversationSession, user_name: str) -> Tuple[str, str]:
        """Dynamic natural human-like responses tailored to the active vibe when offline."""
        vibe_key = session.vibe
        if vibe_key == "normal":
            replies = [
                f"Hey {user_name}, yeah I totally get what you mean! What made you think of that?",
                f"Honestly {user_name}, that's a really good point. How's your day going so far?",
                f"Oh nice! Yeah, I'm right there with you on that one, {user_name}.",
                f"Hey {user_name}, glad you mentioned that. What are you up to right now?",
            ]
        elif vibe_key == "mastermind":
            replies = [
                f"An interesting thought, {user_name}. But tell me... have you accounted for what lies beyond your vision?",
                f"Do not seek to comprehend that which is already preordained, {user_name}.",
                f"Admirable conviction, {user_name}. Yet illusions often resemble reality until they are shattered.",
            ]
        elif vibe_key == "gamer":
            replies = [
                f"YOOOO no shot, {user_name}! That is actually insane, lock in and let's cook!",
                f"Bro, that's huge! Absolute W play, what are we hitting next?",
                f"Haha for real? Major skill issue if they can't handle that, let's keep cooking!",
            ]
        elif vibe_key == "tsundere":
            replies = [
                f"H-hmph! It's not like you're completely wrong or anything, {user_name}... b-baka!",
                f"Why are you telling me this, {user_name}? It's not like I care! ...Okay fine, what happened next?",
                f"Don't get the wrong idea, {user_name}! I'm only answering because the channel was quiet!",
            ]
        elif vibe_key == "podcast":
            replies = [
                f"Woah, hold on {user_name}... that is fascinating. What do you think is really at the root of that?",
                f"That is wild, man. Have you ever stepped back and thought about how crazy that actually sounds?",
                f"Pull that mic in for a second, {user_name}. How long have you felt that way?",
            ]
        elif vibe_key == "cyberpunk":
            replies = [
                f"Acoustic signature analyzed. Telemetry within optimal parameters, operative {user_name}.",
                f"Neural sync steady at twenty-four milliseconds. Standing by for tactical directives.",
                f"Biometric audio acknowledged. Comm channel operating at peak bandwidth, operative.",
            ]
        elif vibe_key == "comedian":
            replies = [
                f"Haha! Wow {user_name}, they give you a microphone and that's what comes out? I love it though!",
                f"Hold on, hold on, let him cook! That was actually hilarious, {user_name}.",
                f"I'd roast you for that, {user_name}, but honestly you did the job for me. What else you got?",
            ]
        elif vibe_key == "pirate":
            replies = [
                f"Shiver me timbers, {user_name}! Now that be the words of a fearless buccaneer!",
                f"Aye, {user_name}! Set sail for the Grand Line, there be legendary booty awaiting us!",
                f"By Blackbeard's ghost, {user_name}! Ye speak the truth of the seven seas!",
            ]
        elif vibe_key == "butler":
            replies = [
                f"A most astute and perceptive observation, {user_name}. I shall make note of it at once.",
                f"As you wish, {user_name}. Allow me to attend to that request with supreme elegance.",
                f"Indeed, {user_name}. May I prepare a warm cup of Earl Grey while we deliberate further?",
            ]
        elif vibe_key == "sensei":
            replies = [
                f"Patience, {user_name}. The quiet bamboo bends with the gale, yet outlasts the proud pine.",
                f"Listen closely, {user_name}. Wisdom begins the moment we quiet the storms of the mind.",
                f"A profound step forward on your journey, {user_name}. Honor lies in the path you walk.",
            ]
        elif vibe_key == "chef":
            replies = [
                f"WAKE UP, {user_name}! You call that a take?! It's completely raw, where is the seasoning?!",
                f"Finally, {user_name}! Some proper culinary flavor in this voice channel! Now let's turn up the heat!",
                f"Look at {user_name} serving up gourmet thoughts! Beautifully plated, my friend!",
            ]
        elif vibe_key == "detective":
            replies = [
                f"The rain was beating against the glass when you said that, {user_name}. This case goes deeper than we thought.",
                f"Funny you should mention that, {user_name}. A shadow slipped out of the alley saying the exact same thing.",
                f"Light another cigarette, {user_name}. In this neon jungle, everyone has an angle.",
            ]
        elif vibe_key == "therapist":
            replies = [
                f"Thank you for sharing that so openly, {user_name}. Your feelings are completely valid in this space.",
                f"Take a gentle breath with me, {user_name}. Let's give that thought some room to breathe.",
                f"That sounds like it carried a lot of weight, {user_name}. Remember to be kind to yourself today.",
            ]
        elif vibe_key == "drillsergeant":
            replies = [
                f"LISTEN UP RECRUIT {user_name}! I don't want excuses, I want results! Sound off loud and clear!",
                f"MOVE IT, {user_name}! Straighten that posture, clear that comm, and keep pushing forward!",
                f"Outstanding hustle, recruit {user_name}! Now drop and give me ten for being awesome!",
            ]
        elif vibe_key == "knight":
            replies = [
                f"By my sacred oath and blade, well spoken, noble companion {user_name}!",
                f"For honor, valor, and the realm! Your courage inspires our fellowship, {user_name}!",
                f"Fear not the dragon nor the storm, {user_name}! My shield stands alongside thee in battle!",
            ]
        elif vibe_key == "supervillain":
            replies = [
                f"Mwahaha! You think your mortal intellect can fathom my grand design, {user_name}?!",
                f"Fascinating, {user_name}! Soon the entire digital universe shall bow before my genius contraption!",
                f"Curse you, {user_name}! You haven't seen the last of my doomsday acoustic apparatus!",
            ]
        elif vibe_key == "crypto":
            replies = [
                f"Bro, {user_name}, that is pure alpha! We are printing green candles straight to the moon!",
                f"Diamond hands only, {user_name}! Paper hands can exit the call, we are locking in generational gains!",
                f"Massive W, {user_name}! The bull market is back and we are not selling a single satoshi!",
            ]
        else:  # chill
            replies = [
                f"Yeah, honestly I hear you on that, {user_name}. What do you think we should do next?",
                f"Oh yeah, totally get what you mean. Just vibing right here with you.",
                f"Good point, {user_name}. That makes total sense to me honestly.",
            ]
        return "Voice statement received", random.choice(replies)

    async def handle_text_utterance(
        self,
        session: VoiceConversationSession,
        cog: Any,
        user: discord.User | discord.Member,
        text: str,
    ) -> Optional[str]:
        """Handle user chat message during active voice session: process context, synthesize, and speak into VC."""
        if not session.active or session.is_bot_speaking:
            return None

        clean_text = text.strip()
        if not clean_text:
            return None

        user_name = user.display_name

        # 1. Check for soundboard trigger words
        detected_sfx = self.sfx_engine.detect_sfx_trigger(clean_text)
        vc = session.voice_client
        if detected_sfx and vc and hasattr(vc, "is_connected") and vc.is_connected():
            sfx_file = self.sfx_engine.get_sfx_path(detected_sfx)
            if sfx_file and os.path.exists(sfx_file):
                session.total_sfx_played += 1
                lock = cog._get_lock(session.guild_id)
                async with lock:
                    try:
                        await cog._play_audio_file(vc, sfx_file)
                    except Exception as e:
                        logger.warning(f"Text-triggered SFX playback notice: {e}")
                await asyncio.sleep(0.15)

        # 2. Generate conversational reply
        reply = await self._generate_text_reply(session, user_name, clean_text)
        if not reply:
            return None

        session.is_bot_speaking = True
        try:
            # 3. Log transcript to session
            session.add_transcript_entry(user_name, clean_text, reply)

            # 4. Synthesize speech using active neural voice
            voice_meta = session.get_voice_meta()
            voice_id = voice_meta["id"]

            temp_fd, reply_mp3 = tempfile.mkstemp(suffix=".mp3")
            os.close(temp_fd)

            synthesized = await cog._synthesize_audio(reply, voice_id, reply_mp3)
            if synthesized and os.path.exists(reply_mp3) and vc and hasattr(vc, "is_connected") and vc.is_connected():
                lock = cog._get_lock(session.guild_id)
                async with lock:
                    try:
                        await cog._play_audio_file(vc, reply_mp3)
                    finally:
                        if os.path.exists(reply_mp3):
                            try:
                                os.remove(reply_mp3)
                            except Exception:
                                pass

            # 5. Update session count and HUD
            session.turn_count += 1
            if session.panel_message:
                try:
                    updated_embed = self.render_voice_hud(session)
                    await session.panel_message.edit(embed=updated_embed)
                except Exception:
                    pass

            return reply
        finally:
            session.is_bot_speaking = False

    async def _generate_text_reply(
        self,
        session: VoiceConversationSession,
        user_name: str,
        user_text: str,
    ) -> str:
        """Generate conversational reply for written prompt in VC chat using Gemini or intelligent local vibe engine."""
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        has_api_key = bool(api_key and not api_key.lower().startswith("replace_"))

        vibe_meta = session.get_vibe_meta()
        vibe_instruction = vibe_meta["prompt"]

        history_lines = []
        for turn in list(session.history)[-4:]:
            history_lines.append(f"{turn['speaker']}: \"{turn['text']}\"")
            history_lines.append(f"Kyoka: \"{turn['reply']}\"")
        history_context = "\n".join(history_lines) if history_lines else "None (conversation just started)."

        system_instruction = (
            f"PERSONALITY & IDENTITY:\n{vibe_instruction}\n"
            f"You are participating in a live Discord voice call. {user_name} just typed to you in voice chat: \"{user_text}\".\n\n"
            "CRITICAL RULES FOR SPOKEN VOICE CONVERSATION:\n"
            "1. KEEP IT PUNCHY: 1 to 2 sentences max (3 sentences max if answering a direct factual inquiry). Never give essays or long bullet lists.\n"
            "2. LIVE CONVERSATION FLOW: Talk naturally in voice chat, matching your designated personality.\n"
            "3. NO MARKDOWN: Never use asterisks (*laughs*), bullet points, emojis, or markdown formatting, as this will be read aloud through speech synthesis.\n"
            "4. Output ONLY the spoken response, nothing else.\n\n"
            f"Recent Dialogue:\n{history_context}\n"
        )

        if has_api_key:
            try:
                candidate_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
                body = {
                    "contents": [{
                        "parts": [{"text": system_instruction}]
                    }],
                    "generationConfig": {
                        "temperature": 0.5,
                        "maxOutputTokens": 200,
                    },
                }
                timeout = aiohttp.ClientTimeout(total=12.0)
                async with aiohttp.ClientSession() as session_http:
                    for model in candidate_models:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                        try:
                            async with session_http.post(url, json=body, timeout=timeout) as resp:
                                if resp.status == 200:
                                    data = await resp.json(content_type=None)
                                    candidates = data.get("candidates", []) if isinstance(data, dict) else []
                                    if candidates:
                                        resp_parts = candidates[0].get("content", {}).get("parts", [])
                                        text = "".join(p.get("text", "") for p in resp_parts if isinstance(p, dict)).strip()
                                        if text:
                                            text = re.sub(r"\*.*?\*", "", text)
                                            return re.sub(r"[*_#`]", "", text).strip()
                                elif resp.status == 429:
                                    continue
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"Gemini text reply notice: {e}")

        # Fallback to intelligent local turn
        _, fallback = self._generate_intelligent_local_turn(session, user_name)
        return fallback

    def generate_conversation_summary(self, session: VoiceConversationSession) -> str:
        """Create a summary from all conversational turns."""
        dur = session.ended_at or datetime.datetime.now(datetime.timezone.utc)
        dur_str = f"{int((dur - session.started_at).total_seconds()) // 60} minutes"
        speakers = set(t["speaker"] for t in session.full_transcript)
        speakers_str = ", ".join(speakers) if speakers else session.started_by_name

        lines = []
        for t in session.full_transcript:
            lines.append(f"• **{t['speaker']}**: \"{t['user_text']}\"")
            lines.append(f"  > *Kyoka:* \"{t['bot_reply']}\"")

        dialogue_text = "\n".join(lines) if lines else "• General verbal conversation and voice sync."

        return (
            f"### 💬 Voice Conversation Summary\n"
            f"Active conversation in **#{session.channel_name}** spanned **{dur_str}** with **{speakers_str}**.\n\n"
            f"### 🎙️ Key Discussion & Spoken Exchanges\n"
            f"{dialogue_text}\n\n"
            f"### ✅ Key Takeaways\n"
            f"• Real-time conversational AI voice session concluded successfully.\n"
            f"• Total spoken exchanges logged: `{len(session.full_transcript)}`\n"
            f"• Total SFX triggered: `{session.total_sfx_played}`\n"
            f"• Active Vibe: `{session.get_vibe_meta()['name']}`"
        )
