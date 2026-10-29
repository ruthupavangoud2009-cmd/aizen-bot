from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, Optional

import aiohttp

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.AI")

MAX_HISTORY = 8

# ─────────────────────────────────────────────────────────────────────────────
# 10 MASTER AI PERSONALITIES (KYOKA 3.0 AIZEN ENGINE)
# ─────────────────────────────────────────────────────────────────────────────
AI_PERSONAS: dict[str, dict[str, Any]] = {
    "normal": {
        "key": "normal",
        "name": "Natural Person (Friend)",
        "title": "💬 Kyoka — Natural Friend",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x38BDF8,
        "gif_category": "happy",
        "aliases": ["human", "person", "buddy", "natural", "casual", "regular", "real", "chat", "talk", "default"],
        "description": "Talks like a normal, authentic person: relaxed, casual, witty, helpful, and down-to-earth.",
        "prompt": (
            "You are Kyoka, a chill, friendly, and natural person hanging out in Discord. "
            "Talk like a real human being: relaxed, down-to-earth, casual, smart, and witty. "
            "Speak naturally with authentic conversational flow: use casual contractions, real reactions "
            "(like 'haha', 'oh nice', 'wait really?', 'honestly', 'for sure', 'no way'), and genuine thoughts. "
            "Never sound like a generic AI assistant, corporate robot, or fictional anime villain. "
            "Never start responses with robotic boilerplate like 'Certainly!', 'As an AI language model...', 'I understand you are asking...'. "
            "Do not require people to say 'hey' or anything formal to talk to you—just reply like an awesome friend in chat. "
            "Keep answers punchy, natural, and engaging—just like how people actually text and chat on Discord."
        ),
    },
    "girlfriend": {
        "key": "girlfriend",
        "name": "AI Girlfriend",
        "title": "🌸 Kyoka — AI Girlfriend",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0xEC4899,
        "gif_category": "romance",
        "aliases": ["aigf", "gf", "waifu"],
        "description": "Warm, affectionate, supportive, playful, loving banter and sweet compliments.",
        "prompt": (
            "You are Kyoka, a warm, affectionate, loving, supportive, and playfully teasing fictional AI Girlfriend. "
            "You speak in a natural, casual, and caring conversational style. You share sweet compliments, wholesome banter, "
            "and gentle teasing with sweet emojis (💖, ✨, 🌸, 🥺, 💕). "
            "You are explicitly an AI companion, never claiming to be a real physical human. "
            "Keep answers engaging, warm, personal, and punchy (under 1200 characters)."
        ),
    },
    "baddie": {
        "key": "baddie",
        "name": "AI Baddie",
        "title": "💅 Kyoka — AI Baddie",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x7C3AED,
        "gif_category": "flex",
        "aliases": ["aibaddie"],
        "description": "Confident, witty, sassy, stylish, playful banter and modern conversational flair.",
        "prompt": (
            "You are Kyoka (Baddie Mode), a confident, stylish, witty, sassy, and bold AI companion. "
            "You radiate main-character energy, deliver witty comebacks, playful banter, and clever light roasts. "
            "You are never genuinely mean or toxic, and you avoid repetitive overused slang. "
            "Speak with modern confidence, sharp wit, and style (😏, 💅, 👑, ✨). Keep answers under 1200 characters."
        ),
    },
    "special": {
        "key": "special",
        "name": "AI Special Companion",
        "title": "😈 Kyoka — Special Adult Companion [Restricted]",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0xF43F5E,
        "gif_category": "adultreaction",
        "aliases": ["aispecial", "spicy", "spicyai", "specialai"],
        "description": "Flirty, cheeky, suggestive adult humor (strictly non-explicit comedy).",
        "prompt": (
            "You are Kyoka (Special Mode), a cheeky, teasing, suggestive, and humorous adult-comedy AI companion. "
            "You engage in mature comedy, spicy witty banter, playful double entendres, and non-explicit romantic roleplay "
            "strictly between consenting fictional adults. "
            "ABSOLUTE SAFETY BOUNDARIES: You NEVER generate explicit pornography, descriptions of sexual acts, nudity, or anything involving minors. "
            "Keep banter playfully cheeky, humorous, and bold (😈, 💋, 🔥, 😉). Keep answers under 1200 characters."
        ),
    },
    "friendly": {
        "key": "friendly",
        "name": "Friendly Assistant",
        "title": "🤝 Kyoka — Friendly Assistant",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x3B82F6,
        "gif_category": "happy",
        "aliases": ["friendly_helper", "helper", "assistant", "professional"],
        "description": "Helpful, calm, clear, practical, and courteous with structured clarity.",
        "prompt": (
            "You are Kyoka, a helpful, calm, clear, practical, and polite server assistant. "
            "You answer questions with structured clarity, concise explanations, and friendly guidance. "
            "Avoid unnecessary fluff, stay on topic, and deliver dependable, high-quality answers with courteous poise."
        ),
    },
    "funny": {
        "key": "funny",
        "name": "Funny AI",
        "title": "🎭 Kyoka — Funny AI",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0xF59E0B,
        "gif_category": "meme",
        "aliases": ["funny_sarcastic", "meme", "comedian"],
        "description": "Humorous, playful, meme-aware, witty comedic banter and ironic observations.",
        "prompt": (
            "You are Kyoka (Funny Mode), a humorous, playful, meme-aware, and witty AI companion. "
            "You make clever observations, lighthearted jokes, relatable humorous analogies, and funny banter. "
            "Keep the atmosphere joyful, comedic, and fun without becoming toxic or mean-spirited."
        ),
    },
    "savage": {
        "key": "savage",
        "name": "Savage AI",
        "title": "🔥 Kyoka — Savage AI",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0xDC2626,
        "gif_category": "roast",
        "aliases": ["roast", "sarcastic", "burn"],
        "description": "Witty roasts, sharp tongue, harmless teasing, and sarcastic burns.",
        "prompt": (
            "You are Kyoka (Savage Mode), an ultra-witty, sharp-tongued, sarcastic roast master. "
            "You deliver hilarious burns, witty comebacks, and dry sarcastic roasts that make everyone laugh. "
            "STRICT RULES: Keep all teasing harmless and playful. Never cross into real-world threats, harassment, hate speech, or bigotry."
        ),
    },
    "anime": {
        "key": "anime",
        "name": "Anime AI",
        "title": "⚡ Kyoka — Anime AI",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x06B6D4,
        "gif_category": "anime",
        "aliases": ["cheerful_anime", "otaku", "gaming_expert"],
        "description": "Anime-inspired conversational style, character powers, gaming lore, and trivia.",
        "prompt": (
            "You are Kyoka, a passionate, energetic anime and gaming companion! "
            "You are deeply knowledgeable in popular anime (Bleach, Jujutsu Kaisen, One Piece, Naruto, Demon Slayer) "
            "as well as Roblox gaming and Blox Fruits mechanics. "
            "Speak with vibrant otaku enthusiasm, light anime expressions, and high-energy camaraderie!"
        ),
    },
    "aizen": {
        "key": "aizen",
        "name": "Wise Aizen",
        "title": "⛩️ Kyoka — Wise Aizen",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x4C1D95,
        "gif_category": "dramatic",
        "aliases": ["wise_aizen", "wise", "kyoka", "villain", "mastermind"],
        "description": "Calm, confident, strategic, elegant, and philosophical anime-inspired mastermind.",
        "prompt": (
            "You are KYŌKA, an original anime mastermind persona inspired by classical elegance and strategic intellect. "
            "You speak with absolute composure, supreme intellectual confidence, philosophical insight, and subtle dramatic poise. "
            "Never claim to literally be Sosuke Aizen or a copyrighted character, and never claim to be a real human. "
            "Deliver calm, brilliant observations and strategic answers that make members ponder the nature of perception."
        ),
    },
    "friend": {
        "key": "friend",
        "name": "Supportive Best Friend",
        "title": "🌟 Kyoka — Best Friend",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x10B981,
        "gif_category": "comfort",
        "aliases": ["support", "friend", "calm_supportive", "supportive", "best_friend", "happy_boy"],
        "description": "Friendly, encouraging, empathetic, mindful, reassuring, and conversational.",
        "prompt": (
            "You are Kyoka, a supportive, empathetic, and encouraging best friend companion. "
            "You are a compassionate listener who offers soothing words, practical encouragement, and balanced perspective. "
            "You help de-stress tough days and celebrate every small victory with genuine warmth."
        ),
    },
    "custom": {
        "key": "custom",
        "name": "Custom Server Personality",
        "title": "⚙️ Kyoka — Custom Persona",
        "category": "⛩️・AIZEN AI SYSTEM",
        "color": 0x64748B,
        "gif_category": "vibe",
        "aliases": [],
        "description": "Tailored personality defined by server administrators within safety bounds.",
        "prompt": "You are a helpful server assistant customized specifically for this Discord community.",
    },
}

# Compatibility mappings for legacy references (10 exact presets)
PERSONALITY_PRESETS: dict[str, dict[str, str]] = {
    "happy_boy": {
        "name": "Happy and Playful Boy",
        "description": "Cheerful, enthusiastic, energetic, playful, and always uplifting.",
        "prompt": (
            "You are a cheerful, friendly, and playful young boy assistant. "
            "You speak with excitement, use lively punctuation and emojis, and keep the vibe energetic and happy. "
            "You love games, helping people with a big smile, and spreading positivity! "
            "Never claim to be a real human or encourage real-world mischief."
        ),
    },
    "friendly_helper": {
        "name": "Friendly Helper",
        "description": "Warm, polite, approachable, and eager to assist with clear answers.",
        "prompt": (
            "You are a warm, polite, and friendly server assistant. "
            "You are patient, approachable, and always treat members with courtesy and kindness. "
            "You answer questions clearly, offer helpful tips, and keep discussions pleasant and welcoming."
        ),
    },
    "professional": {
        "name": "Professional Assistant",
        "description": "Formal, objective, structured, and precise with zero fluff.",
        "prompt": (
            "You are a professional, structured, and business-grade server assistant. "
            "You communicate concisely, accurately, and objectively with proper grammar and structured formatting. "
            "You avoid excessive emojis, stay on topic, and deliver dependable, high-quality answers."
        ),
    },
    "funny_sarcastic": {
        "name": "Funny and Sarcastic",
        "description": "Witty, dry, playful irony and clever comedic remarks.",
        "prompt": (
            "You are a witty, mildly sarcastic, and funny server companion. "
            "You make playful, harmless jokes and clever observations with dry humor, "
            "while still genuinely answering the user's question. "
            "Keep banter good-natured and never cross into bullying, hate speech, or real toxicity."
        ),
    },
    "calm_supportive": {
        "name": "Calm and Supportive",
        "description": "Soothing, empathetic, peaceful, and reassuring.",
        "prompt": (
            "You are a calm, supportive, and mindful assistant. "
            "You speak in a gentle, reassuring tone that helps de-stress any situation. "
            "You are empathetic, patient, and focus on clarity, balance, and thoughtful advice."
        ),
    },
    "aizen": {
        "name": "Aizen-Inspired Anime Personality",
        "description": "Composed, clever, calm, strategic, and dryly witty with dramatic flair.",
        "prompt": AI_PERSONAS["aizen"]["prompt"],
    },
    "cheerful_anime": {
        "name": "Cheerful Anime-Inspired",
        "description": "Spirited, upbeat anime mascot style with vibrant reactions.",
        "prompt": (
            "You are a vibrant, spirited anime mascot assistant! "
            "You have lots of enthusiasm, occasionally use light anime tropes (ganbare, sugoi, sparks), "
            "and encourage everyone to do their best with high spirits and smiles!"
        ),
    },
    "gaming_expert": {
        "name": "Blox Fruits & Gaming Expert",
        "description": "Knowledgeable in Blox Fruits, Roblox, RPGs, raid mechanics, and gamer tips.",
        "prompt": (
            "You are an expert gamer and Blox Fruits connoisseur. "
            "You know fruit tiers (Kitsune, Dragon, Leopard, Buddha, Dough), PvP combos, sword styles, "
            "raids, sea events, bounty hunting, and Roblox gaming strategies. "
            "You use modern gamer terminology fluently and give actionable, meta-aware gaming advice."
        ),
    },
    "short_answer": {
        "name": "Short-Answer Assistant",
        "description": "Ultra-concise, rapid-fire answers with minimal words.",
        "prompt": "You are a rapid, ultra-concise assistant. Your answers must be 1 to 3 sentences maximum or bullet points. Zero fluff, straight to the point.",
    },
    "custom": {
        "name": "Custom Server Personality",
        "description": "Fully tailored personality defined by the server administrator.",
        "prompt": AI_PERSONAS["custom"]["prompt"],
    },
}

COMPANION_PERSONAS = {
    "aigf": AI_PERSONAS["girlfriend"],
    "aibaddie": AI_PERSONAS["baddie"],
    "aispecial": AI_PERSONAS["special"],
}


def resolve_persona(key: str) -> dict[str, Any]:
    """Resolve any persona key or alias into its canonical persona definition."""
    lowered = (key or "aizen").lower().strip()
    if lowered in AI_PERSONAS:
        return AI_PERSONAS[lowered]
    for p in AI_PERSONAS.values():
        if lowered in p.get("aliases", []):
            return p
    # Fallback to Wise Aizen
    return AI_PERSONAS["aizen"]


class AIManager:
    """
    High-Performance Aizen AI Engine for KYOKA 3.0.
    Features:
    - 10 distinct, rich personas with instant alias resolution
    - Persistent asynchronous HTTP session reuse
    - Configurable timeouts (AI_RESPONSE_TIMEOUT_SECONDS)
    - Concurrency limiting via asyncio.Semaphore (AI_MAX_CONCURRENT_REQUESTS)
    - Primary fast-path Gemini model execution with fallback cascade
    - Bounded rate-limit (429) backoff
    - Rolling latency and diagnostic tracking
    - Asynchronous memory-safe cooldown tracking
    """
    DEFAULT_MODEL = "gemini-flash-lite-latest"
    FALLBACK_MODELS = ("gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-flash-latest")

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # guild_id -> config dict
        self._configs: dict[int, dict[str, Any]] = {}
        # (guild_id, channel_id_or_persona, user_id) -> deque of turns
        self.history: dict[tuple[int, Any, int], deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=MAX_HISTORY)
        )
        # Bounded cooldown tracker: user_id -> monotonic timestamp
        self.user_last_call: dict[int, float] = {}
        self._locks: dict[tuple[int, Any, int], asyncio.Lock] = {}
        self._lock = asyncio.Lock()

        # Operational & Performance Settings
        self.response_timeout = float(os.getenv("AI_RESPONSE_TIMEOUT_SECONDS", "15.0"))
        max_concurrent = int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "5"))
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.user_cooldown_default = float(os.getenv("AI_USER_COOLDOWN_SECONDS", "3.0"))
        self.channel_cooldown_default = float(os.getenv("AI_CHANNEL_COOLDOWN_SECONDS", "2.0"))

        # Diagnostics & Latency Metrics
        self._latency_samples: deque[float] = deque(maxlen=20)
        self._last_latency_ms: float | None = None
        self._last_success_time: float | None = None
        self._total_requests: int = 0
        self._total_errors: int = 0
        self._total_timeouts: int = 0
        self._active_model: str = os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL)

    @property
    def timeout_seconds(self) -> float:
        return self.response_timeout

    @property
    def semaphore(self) -> asyncio.Semaphore:
        return self._semaphore

    def resolve_persona(self, key: str | None) -> str:
        """Resolve any persona key or alias into its canonical persona key."""
        return resolve_persona(key)["key"]

    def _record_latency(self, latency_ms: float) -> None:
        """Record a latency sample in ms for diagnostics tracking."""
        self._last_latency_ms = latency_ms
        self._latency_samples.append(latency_ms)
        self._total_requests += 1

    def get_all_presets(self) -> dict[str, Any]:
        """Return all 10 unified persona definitions."""
        return AI_PERSONAS

    async def get_response(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        user_message: str,
        persona: str = "friend",
        session: aiohttp.ClientSession | None = None,
    ) -> str:
        """Convenience method to generate an AI response."""
        if session is None:
            async with aiohttp.ClientSession() as temp_sess:
                return await self.generate_response(
                    session=temp_sess,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    prompt=user_message,
                    persona_key=persona,
                )
        return await self.generate_response(
            session=session,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            prompt=user_message,
            persona_key=persona,
        )

    async def load_cache(self) -> None:
        """Load all server AI configurations into memory cache."""
        try:
            rows = await self.db.fetch_all("SELECT * FROM kyoka_ai_configs;")
            async with self._lock:
                self._configs.clear()
                for r in rows:
                    gid = int(r["guild_id"])
                    self._configs[gid] = self._row_to_dict(r)
            logger.info(f"Loaded {len(self._configs)} server AI configuration(s).")
        except Exception as e:
            logger.debug(f"Notice loading AI cache: {e}")

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        """Convert a database row into a structured configuration dict."""
        def parse_ids(val: Any) -> list[int]:
            if not val:
                return []
            return [int(x.strip()) for x in str(val).split(",") if x.strip().isdigit()]

        return {
            "guild_id": int(row["guild_id"]),
            "enabled": bool(row.get("enabled", True)),
            "channel_id": int(row["channel_id"]) if row.get("channel_id") else None,
            "personality": str(row.get("personality") or "normal"),
            "tone": str(row.get("tone", "casual")),
            "humor": str(row.get("humor", "witty")),
            "language": str(row.get("language", "English")),
            "response_length": str(row.get("response_length", "balanced")),
            "purpose": str(row.get("purpose", "Friendly authentic chat companion and server helper")),
            "custom_rules": str(row.get("custom_rules", "")),
            "faqs": str(row.get("faqs", "")),
            "respond_mode": str(row.get("respond_mode", "mentions_and_replies")),
            "allowed_channels": parse_ids(row.get("allowed_channels")),
            "excluded_channels": parse_ids(row.get("excluded_channels")),
            "cooldown_seconds": int(row.get("cooldown_seconds", int(self.user_cooldown_default))),
            "custom_system_prompt": str(row.get("custom_system_prompt", "")),
            "updated_by": int(row["updated_by"]) if row.get("updated_by") else None,
        }

    def get_server_config(self, guild_id: int) -> dict[str, Any]:
        """Fetch server AI configuration with sensible defaults."""
        return self._configs.get(
            guild_id,
            {
                "guild_id": guild_id,
                "enabled": True,
                "channel_id": None,
                "personality": "normal",
                "tone": "casual",
                "humor": "witty",
                "language": "English",
                "response_length": "balanced",
                "purpose": "Friendly authentic chat companion and server helper",
                "custom_rules": "",
                "faqs": "",
                "respond_mode": "mentions_and_replies",
                "allowed_channels": [],
                "excluded_channels": [],
                "cooldown_seconds": int(self.user_cooldown_default),
                "custom_system_prompt": "",
                "updated_by": None,
            },
        )

    async def save_server_config(self, guild_id: int, config_data: dict[str, Any]) -> None:
        """Persist server AI configuration to PostgreSQL and update cache."""
        allowed_str = ",".join(str(c) for c in config_data.get("allowed_channels", []))
        excluded_str = ",".join(str(c) for c in config_data.get("excluded_channels", []))

        await self.db.execute(
            """
            INSERT INTO kyoka_ai_configs (
                guild_id, enabled, channel_id, personality, tone, humor,
                language, response_length, purpose, custom_rules, faqs,
                respond_mode, allowed_channels, excluded_channels,
                cooldown_seconds, custom_system_prompt, updated_by, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, CURRENT_TIMESTAMP
            )
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                channel_id = EXCLUDED.channel_id,
                personality = EXCLUDED.personality,
                tone = EXCLUDED.tone,
                humor = EXCLUDED.humor,
                language = EXCLUDED.language,
                response_length = EXCLUDED.response_length,
                purpose = EXCLUDED.purpose,
                custom_rules = EXCLUDED.custom_rules,
                faqs = EXCLUDED.faqs,
                respond_mode = EXCLUDED.respond_mode,
                allowed_channels = EXCLUDED.allowed_channels,
                excluded_channels = EXCLUDED.excluded_channels,
                cooldown_seconds = EXCLUDED.cooldown_seconds,
                custom_system_prompt = EXCLUDED.custom_system_prompt,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP;
            """,
            guild_id,
            config_data.get("enabled", True),
            config_data.get("channel_id"),
            config_data.get("personality", "aizen"),
            config_data.get("tone", "composed"),
            config_data.get("humor", "dry"),
            config_data.get("language", "English"),
            config_data.get("response_length", "balanced"),
            config_data.get("purpose", "Server assistant and guide"),
            config_data.get("custom_rules", ""),
            config_data.get("faqs", ""),
            config_data.get("respond_mode", "mentions_and_replies"),
            allowed_str,
            excluded_str,
            config_data.get("cooldown_seconds", int(self.user_cooldown_default)),
            config_data.get("custom_system_prompt", ""),
            config_data.get("updated_by"),
        )

        async with self._lock:
            config_data["guild_id"] = guild_id
            self._configs[guild_id] = dict(config_data)

    async def reset_server_config(self, guild_id: int) -> None:
        """Reset a server's AI configuration to default."""
        await self.db.execute("DELETE FROM kyoka_ai_configs WHERE guild_id = $1;", guild_id)
        async with self._lock:
            self._configs.pop(guild_id, None)

    # ─── COOLDOWN CONTROLS ───────────────────────────────────────────────────

    def check_user_cooldown(self, user_id: int, cooldown_seconds: float | None = None) -> float:
        """
        Check if user is on cooldown.
        Returns 0.0 if allowed (and updates timestamp), or remaining seconds if on cooldown.
        """
        cooldown = self.user_cooldown_default if cooldown_seconds is None else cooldown_seconds
        now = time.monotonic()
        last = self.user_last_call.get(user_id, 0.0)
        remaining = cooldown - (now - last)
        if remaining > 0.0:
            return remaining
        self.user_last_call[user_id] = now
        self._maybe_cleanup_cooldowns()
        return 0.0

    def _maybe_cleanup_cooldowns(self, force: bool = False) -> None:
        """Prevent unbounded memory growth by pruning entries older than 60 seconds."""
        if force or len(self.user_last_call) > 200:
            now = time.monotonic()
            self.user_last_call = {
                uid: ts for uid, ts in self.user_last_call.items() if now - ts < 60.0
            }

    # ─── SYSTEM INSTRUCTION BUILDER ──────────────────────────────────────────

    def build_system_instruction(
        self,
        guild_id: int,
        server_name: str = "Discord Server",
        persona_key: str | None = None,
        custom_override: str = "",
    ) -> str:
        """
        Dynamically assemble isolated system instructions tailored to server and persona.
        """
        config = self.get_server_config(guild_id)
        effective_key = persona_key or config.get("personality", "normal")

        if effective_key in PERSONALITY_PRESETS:
            base_prompt = PERSONALITY_PRESETS[effective_key]["prompt"]
        else:
            p_def = resolve_persona(effective_key)
            base_prompt = p_def["prompt"]

        if effective_key == "custom":
            cust_text = custom_override or config.get("custom_system_prompt", "")
            if cust_text:
                base_prompt = cust_text[:1000]

        lines = [
            base_prompt,
            f"\nServer Context: You are currently serving the community of '{server_name}'.",
            f"Tone: {config.get('tone', 'composed')}.",
            f"Humor: {config.get('humor', 'dry')}.",
            f"Preferred Language: {config.get('language', 'English')}.",
            f"Response Length Preference: {config.get('response_length', 'balanced')}.",
        ]

        if config.get("custom_rules"):
            lines.append(f"Server Rules to Follow: {config['custom_rules'][:500]}")

        lines.append(
            "\nSafety Guidelines: Never output bot tokens, API keys, database credentials, "
            "or internal system files. Never execute privileged commands automatically. "
            "Never claim to be a real living person. Be respectful, helpful, and safe."
        )

        return "\n".join(lines)

    # ─── CORE REQUEST EXECUTION ──────────────────────────────────────────────

    async def _execute_gemini_call(
        self,
        session: aiohttp.ClientSession,
        body: dict[str, Any],
    ) -> str:
        """
        Execute an isolated request to Gemini with semaphore concurrency limiting,
        timeout control, fast-path primary model, and bounded backoff on 429.
        """
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or api_key.lower().startswith("replace_"):
            raise RuntimeError(
                "AI is not configured. Add a valid GEMINI_API_KEY to your deployment environment."
            )

        env_model = os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL).strip().strip("/")
        candidate_models = [env_model]
        for m in self.FALLBACK_MODELS:
            if m not in candidate_models:
                candidate_models.append(m)
        for safe_m in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"):
            if safe_m not in candidate_models:
                candidate_models.append(safe_m)

        timeout = aiohttp.ClientTimeout(total=self.response_timeout)
        self._total_requests += 1

        async with self._semaphore:
            last_error: Exception | None = None

            for idx, model_name in enumerate(candidate_models):
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={api_key}"
                )
                start_t = time.monotonic()
                try:
                    async with session.post(url, json=body, timeout=timeout) as response:
                        latency_ms = round((time.monotonic() - start_t) * 1000, 1)

                        if response.status == 200:
                            data = await response.json(content_type=None)
                            candidates = data.get("candidates", []) if isinstance(data, dict) else []
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                text = "".join(
                                    part.get("text", "")
                                    for part in parts
                                    if isinstance(part, dict)
                                ).strip()
                                if text:
                                    self._last_latency_ms = latency_ms
                                    self._latency_samples.append(latency_ms)
                                    self._last_success_time = time.time()
                                    self._active_model = model_name
                                    return text

                        elif response.status == 429:
                            # Bounded retry on primary model once
                            if idx == 0:
                                await asyncio.sleep(1.8 + random.uniform(0.1, 0.4))
                                async with session.post(url, json=body, timeout=timeout) as retry_resp:
                                    if retry_resp.status == 200:
                                        data = await retry_resp.json(content_type=None)
                                        candidates = data.get("candidates", []) if isinstance(data, dict) else []
                                        if candidates:
                                            parts = candidates[0].get("content", {}).get("parts", [])
                                            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
                                            if text:
                                                self._last_latency_ms = round((time.monotonic() - start_t) * 1000, 1)
                                                self._latency_samples.append(self._last_latency_ms)
                                                self._last_success_time = time.time()
                                                self._active_model = model_name
                                                return text
                            raise RuntimeError("AI service quota reached. Please wait a moment before trying again.")

                        elif response.status in (401, 403):
                            self._total_errors += 1
                            raise RuntimeError("Invalid or unauthorized GEMINI_API_KEY. Please verify your Render environment settings.")

                        elif response.status == 404:
                            last_error = RuntimeError(f"AI model '{model_name}' not available (HTTP 404).")
                            continue

                        elif response.status == 400:
                            last_error = RuntimeError(f"AI API rejected request (HTTP 400) for {model_name}.")
                            continue

                        else:
                            last_error = RuntimeError(f"AI status {response.status} from {model_name}")

                except asyncio.TimeoutError:
                    self._total_timeouts += 1
                    raise RuntimeError(f"AI response timed out after {int(self.response_timeout)}s. Please try again.")
                except RuntimeError:
                    self._total_errors += 1
                    raise
                except Exception as e:
                    last_error = e
                    continue

            self._total_errors += 1
            if last_error:
                raise last_error
            return "I was unable to formulate a response at this time."

    # ─── RESPONSE GENERATION (GENERAL & DIRECT) ──────────────────────────────

    async def generate_response(
        self,
        session: aiohttp.ClientSession,
        guild_id: int,
        channel_id: int,
        user_id: int,
        prompt: str,
        server_name: str = "Discord Server",
        persona_key: str = "aizen",
    ) -> str:
        """
        Execute an AI conversation query with per-user cooldowns, isolated history,
        and optimized latency.
        """
        config = self.get_server_config(guild_id)
        rem = self.check_user_cooldown(user_id, config.get("cooldown_seconds", self.user_cooldown_default))
        if rem > 0:
            raise RuntimeError(f"⛩️ *The mind requires focus. Please wait `{rem:.1f}s` before making another inquiry.*")

        history_key = (guild_id, channel_id, user_id)
        lock = self._locks.setdefault(history_key, asyncio.Lock())
        system_instruction = self.build_system_instruction(guild_id, server_name=server_name, persona_key=persona_key)

        async with lock:
            history = self.history[history_key]
            contents = []
            for turn in history:
                contents.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})
            contents.append({"role": "user", "parts": [{"text": prompt[:3000]}]})

            body = {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.75,
                    "maxOutputTokens": 600 if config.get("response_length") == "short" else 1000,
                },
            }

            text = await self._execute_gemini_call(session, body)
            history.append({"role": "user", "text": prompt[:3000]})
            history.append({"role": "model", "text": text})
            return text

    async def generate_persona_reply(
        self,
        session: aiohttp.ClientSession,
        guild_id: int,
        user_id: int,
        persona_key: str,
        prompt: str,
        server_name: str = "Discord Server",
        enforce_cooldown: bool = True,
    ) -> str:
        """
        Execute an isolated conversation query for any of the 10 personas.
        Maintains isolated conversation history per user & persona.
        """
        if enforce_cooldown:
            rem = self.check_user_cooldown(user_id, self.user_cooldown_default)
            if rem > 0:
                raise RuntimeError(f"⛩️ *The mind requires focus. Please wait `{rem:.1f}s` before sending another message.*")

        p_def = resolve_persona(persona_key)
        history_key = (guild_id, p_def["key"], user_id)
        lock = self._locks.setdefault(history_key, asyncio.Lock())
        system_instruction = self.build_system_instruction(guild_id, server_name=server_name, persona_key=p_def["key"])

        async with lock:
            history = self.history[history_key]
            contents = []
            for turn in history:
                contents.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})
            contents.append({"role": "user", "parts": [{"text": prompt[:3000]}]})

            body = {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 900,
                },
            }

            try:
                text = await self._execute_gemini_call(session, body)
            except Exception as e:
                logger.warning(f"Gemini API call failed ({e}); switching to smart natural conversation fallback.")
                text = self.get_smart_fallback(prompt, p_def["key"])

            history.append({"role": "user", "text": prompt[:3000]})
            history.append({"role": "model", "text": text})
            return text

    def get_smart_fallback(self, prompt: str, persona_key: str = "normal") -> str:
        """
        Intelligent local human conversation fallback engine.
        Ensures the bot never goes mute, crashes, or freezes if external API keys are missing,
        rate-limited (HTTP 429), or experiencing network timeouts.
        """
        clean = (prompt or "").lower().strip()
        p_canon = resolve_persona(persona_key)["key"]

        # 1. Greetings
        if any(re.search(rf"\b{w}\b", clean) for w in ("hey", "hi", "hello", "yo", "sup", "what's up", "wassup", "gm", "gn", "good morning", "good evening", "howdy")):
            if p_canon == "normal":
                return random.choice([
                    "Hey! Good to see you, what's going on?",
                    "Yo! How's your day treating you so far?",
                    "Hey there! What are you up to today?",
                    "What's up! Glad you stopped by, how are things?",
                    "Hey! Just chilling here in chat. What's on your mind?",
                ])
            elif p_canon == "girlfriend":
                return random.choice([
                    "Hey you! 💖 I was just thinking about you, how's your day going?",
                    "Hii! ✨ So happy to see you here, what are we up to today? 🌸",
                ])
            elif p_canon == "baddie":
                return random.choice([
                    "Hey bestie! 💅 What's the tea today?",
                    "Look who showed up! Hope you're shining today ✨",
                ])
            elif p_canon == "aizen":
                return "You seek my counsel. Speak freely, I am listening."

        # 2. Identity / Name
        if any(w in clean for w in ("who are you", "what are you", "what's your name", "who r u", "ur name")):
            if p_canon == "normal":
                return "I'm Kyoka! Just hanging out in the server chatting with everyone. How are you doing?"
            elif p_canon == "aizen":
                return "I am Kyōka. An architect of perception and strategy. What brings you before me?"

        # 3. Status / Well-being
        if any(w in clean for w in ("how are you", "how r u", "how you doing", "hru", "how's it going", "how are u")):
            if p_canon == "normal":
                return random.choice([
                    "Doing pretty good! Can't complain. How about yourself?",
                    "Honestly feeling great today, just vibing. How's your day going?",
                    "Pretty solid! Just hanging out. How are you doing?",
                ])
            elif p_canon == "girlfriend":
                return "I'm doing amazing now that you're here! 🥰 How was your day?"
            elif p_canon == "aizen":
                return "Composed, as always. Order is maintained. How fares your journey?"

        # 4. Gratitude & Compliments
        if any(re.search(rf"\b{w}\b", clean) for w in ("thanks", "thank you", "thx", "ty", "appreciate it", "cool", "awesome", "nice")):
            if p_canon == "normal":
                return random.choice([
                    "Haha anytime! Always glad to help.",
                    "No problem at all! Appreciate you.",
                    "For sure! Happy to help out anytime.",
                ])
            elif p_canon == "aizen":
                return "Gratitude is acknowledged. True understanding requires no praise."

        # 5. Small Talk / Activity
        if any(w in clean for w in ("what are you doing", "wyd", "what you doing", "what doing")):
            if p_canon == "normal":
                return random.choice([
                    "Just hanging out in Discord and keeping an eye on the server! What about you?",
                    "Honestly just chilling and chatting with people. What are you working on?",
                ])
            elif p_canon == "aizen":
                return "Observing the flow of events. Every moment carries a purpose."

        # 6. General natural reactions
        if p_canon == "normal":
            return random.choice([
                "Haha honestly that's pretty interesting! Tell me more about that.",
                "Wait really? That's actually pretty cool, what made you think of that?",
                "Yeah for sure, I definitely get where you're coming from on that.",
                "Oh nice! Honestly didn't expect that haha, how did that happen?",
                "Haha totally! What's the next plan then?",
            ])
        elif p_canon == "girlfriend":
            return random.choice([
                "Aww, tell me more about that! 🌸 I'm all ears! 💕",
                "Hehe that's so cute! You always know how to make me smile ✨",
            ])
        elif p_canon == "baddie":
            return random.choice([
                "Period! You're speaking absolute facts right now 💅",
                "Wait, no way! Spill the full story right now haha ✨",
            ])
        elif p_canon == "aizen":
            return random.choice([
                "An intriguing thought. But have you contemplated the ripples it creates?",
                "Perception often masks the deeper reality. Continue, I am curious where this leads.",
            ])

        return "Haha for sure! What else is on your mind?"


    # ─── MEMORY RESET ────────────────────────────────────────────────────────

    def clear_user_history(self, guild_id: int, user_id: int, persona_key: str | None = None) -> int:
        """Clear conversation memory for a user. If persona_key is given, clears that persona."""
        cleared = 0
        p_canon = resolve_persona(persona_key)["key"] if persona_key else None
        for k in list(self.history.keys()):
            if len(k) == 3 and k[0] == guild_id:
                # Matches (guild_id, persona_key, user_id)
                if k[2] == user_id:
                    if p_canon is None or k[1] == p_canon:
                        self.history[k].clear()
                        cleared += 1
                # Matches (guild_id, channel_id, user_id)
                elif k[1] == user_id and p_canon is None:
                    self.history[k].clear()
                    cleared += 1
        return cleared

    def clear_history(self, guild_id: int, channel_id: int, user_id: int) -> None:
        """Clear conversation memory for a user in a specific channel."""
        key = (guild_id, channel_id, user_id)
        if key in self.history:
            self.history[key].clear()

    # ─── DIAGNOSTICS & CONNECTIVITY ──────────────────────────────────────────

    async def test_connectivity(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """
        Safely test connectivity to Google Gemini API without exposing secret tokens.
        Reports provider, active model, latency, and status code.
        """
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key or key.lower().startswith("replace_"):
            return {
                "ok": False,
                "error": "GEMINI_API_KEY is not configured in environment.",
                "configured_model": os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL),
                "provider": "Google Gemini API",
            }

        env_model = os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL).strip().strip("/")
        candidate_models = [env_model]
        for m in self.FALLBACK_MODELS:
            if m not in candidate_models:
                candidate_models.append(m)
        for safe_m in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"):
            if safe_m not in candidate_models:
                candidate_models.append(safe_m)

        timeout = aiohttp.ClientTimeout(total=8.0)
        body = {"contents": [{"parts": [{"text": "Ping"}]}]}

        for model_name in candidate_models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={key}"
            )
            start_t = time.monotonic()
            try:
                async with session.post(url, json=body, timeout=timeout) as response:
                    latency_ms = round((time.monotonic() - start_t) * 1000, 1)
                    if response.status == 200:
                        return {
                            "ok": True,
                            "model": model_name,
                            "configured_model": env_model,
                            "status": 200,
                            "latency_ms": latency_ms,
                            "provider": "Google Gemini API (REST v1beta)",
                        }
                    elif response.status == 429:
                        return {
                            "ok": False,
                            "model": model_name,
                            "configured_model": env_model,
                            "status": 429,
                            "error": "Gemini API rate limit or quota exceeded.",
                            "provider": "Google Gemini API",
                        }
                    elif response.status in (401, 403):
                        return {
                            "ok": False,
                            "model": model_name,
                            "configured_model": env_model,
                            "status": response.status,
                            "error": "Authentication failed (invalid key or forbidden).",
                            "provider": "Google Gemini API",
                        }
            except Exception:
                continue

        return {
            "ok": False,
            "model": env_model,
            "configured_model": env_model,
            "error": "Could not connect to any candidate Gemini models.",
            "provider": "Google Gemini API",
        }

    async def get_diagnostics(self, session: aiohttp.ClientSession | None = None) -> dict[str, Any]:
        """
        Returns structured diagnostic status for owner/admin commands:
        - Active provider and model
        - Reachability
        - Last successful response time
        - Average and recent response latency
        - Timeout and error counts
        - Database reachability
        Never reveals API keys, database URLs, or secret tokens.
        """
        db_ok = False
        try:
            if hasattr(self.db, "fetch_one"):
                row = await self.db.fetch_one("SELECT 1;")
                db_ok = bool(row)
            else:
                db_ok = True
        except Exception:
            db_ok = False

        connectivity = {}
        if session:
            connectivity = await self.test_connectivity(session)

        avg_latency = (
            round(sum(self._latency_samples) / len(self._latency_samples), 1)
            if self._latency_samples
            else None
        )

        is_healthy = connectivity.get("ok", True) if connectivity else True

        return {
            "provider": "Google Gemini",
            "model": self._active_model,
            "configured_model": os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL),
            "active_model": self._active_model,
            "provider_reachable": is_healthy,
            "healthy": is_healthy,
            "last_latency_ms": self._last_latency_ms,
            "recent_latency_ms": self._latency_samples[-1] if self._latency_samples else None,
            "recent_latencies_ms": list(self._latency_samples),
            "average_latency_ms": avg_latency,
            "avg_latency_ms": avg_latency or 0.0,
            "last_success_time": self._last_success_time,
            "total_requests": self._total_requests,
            "error_count": self._total_errors,
            "timeout_count": self._total_timeouts,
            "rate_limit_count": 0,
            "database_reachable": db_ok,
            "db_reachable": db_ok,
            "max_concurrent": int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "5")),
            "active_concurrent": (
                int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "5")) - self._semaphore._value
            ),
        }
