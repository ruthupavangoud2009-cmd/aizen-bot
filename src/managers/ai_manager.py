from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, Optional

import aiohttp

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.AI")

MAX_HISTORY = 10

# The 10 built-in personality presets specified in Section 4.2
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
        "prompt": (
            "You are KYŌKA, an original Aizen-inspired assistant: composed, clever, calm, "
            "occasionally dryly witty, strategic, and articulate. "
            "Never claim to literally be Sosuke Aizen or a copyrighted character. "
            "Speak with intellectual confidence, poise, and subtle dramatic flair, while remaining helpful and punchy."
        ),
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
        "prompt": (
            "You are a rapid, ultra-concise assistant. "
            "Your answers must be 1 to 3 sentences maximum or bullet points. "
            "Zero fluff, zero lengthy introductions, straight to the exact fact requested."
        ),
    },
    "custom": {
        "name": "Custom Server Personality",
        "description": "Fully tailored personality defined by the server administrator.",
        "prompt": "You are a helpful server assistant customized for this community.",
    },
}


class AIManager:
    """
    Multi-Personality AI Manager for KYOKA 3.0.
    Stores and isolates AI configuration per server, supports 10 distinct personality presets,
    custom prompt engineering, cooldowns, channels, and graceful failover cascades.
    """
    FALLBACK_MODELS = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp")

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # guild_id -> config dict
        self._configs: dict[int, dict[str, Any]] = {}
        # (guild_id, channel_id, user_id) -> deque of turns
        self.history: dict[tuple[int, int, int], deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=MAX_HISTORY)
        )
        # user_id -> last query monotonic time
        self.user_last_call: dict[int, float] = {}
        self._locks: dict[tuple[int, int, int], asyncio.Lock] = {}
        self._lock = asyncio.Lock()

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
            "personality": str(row.get("personality", "aizen")),
            "tone": str(row.get("tone", "composed")),
            "humor": str(row.get("humor", "dry")),
            "language": str(row.get("language", "English")),
            "response_length": str(row.get("response_length", "balanced")),
            "purpose": str(row.get("purpose", "Server assistant and guide")),
            "custom_rules": str(row.get("custom_rules", "")),
            "faqs": str(row.get("faqs", "")),
            "respond_mode": str(row.get("respond_mode", "mentions_and_replies")),
            "allowed_channels": parse_ids(row.get("allowed_channels")),
            "excluded_channels": parse_ids(row.get("excluded_channels")),
            "cooldown_seconds": int(row.get("cooldown_seconds", 4)),
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
                "personality": "aizen",
                "tone": "composed",
                "humor": "dry",
                "language": "English",
                "response_length": "balanced",
                "purpose": "Server assistant and guide",
                "custom_rules": "",
                "faqs": "",
                "respond_mode": "mentions_and_replies",
                "allowed_channels": [],
                "excluded_channels": [],
                "cooldown_seconds": 4,
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
            config_data.get("cooldown_seconds", 4),
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

    def build_system_instruction(self, guild_id: int, server_name: str = "Discord Server") -> str:
        """
        Dynamically assemble system instructions tailored to this server's settings.
        Completely isolates server configurations.
        """
        config = self.get_server_config(guild_id)
        preset_key = config.get("personality", "aizen")
        preset = PERSONALITY_PRESETS.get(preset_key, PERSONALITY_PRESETS["aizen"])

        base_prompt = preset["prompt"]
        if preset_key == "custom" and config.get("custom_system_prompt"):
            base_prompt = config["custom_system_prompt"]

        lines = [
            base_prompt,
            f"\nServer Context: You are currently serving the community of '{server_name}'.",
            f"Tone: {config.get('tone', 'composed')}.",
            f"Humor: {config.get('humor', 'dry')}.",
            f"Preferred Language: {config.get('language', 'English')}.",
            f"Response Length Preference: {config.get('response_length', 'balanced')}.",
            f"Server Purpose: {config.get('purpose', 'Server assistant and guide')}.",
        ]

        if config.get("custom_rules"):
            lines.append(f"Server Rules to Follow: {config['custom_rules']}")

        if config.get("faqs"):
            lines.append(f"Server FAQs & Knowledge: {config['faqs']}")

        lines.append(
            "\nSafety Guidelines: Never output bot tokens, API keys, database credentials, "
            "or internal system files. Never execute privileged bot commands automatically. "
            "Never claim to be a real living person. Be respectful, helpful, and safe."
        )

        return "\n".join(lines)

    def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        """Check if AI is permitted to respond in this channel."""
        config = self.get_server_config(guild_id)
        if not config["enabled"]:
            return False

        if channel_id in config["excluded_channels"]:
            return False

        # If dedicated AI channel is configured, must match
        if config["channel_id"] and config["channel_id"] != channel_id:
            # If allowed_channels is also set, check it as well
            if config["allowed_channels"] and channel_id not in config["allowed_channels"]:
                return False
            elif not config["allowed_channels"]:
                return False

        if config["allowed_channels"] and channel_id not in config["allowed_channels"]:
            return False

        return True

    def clear_history(self, guild_id: int, channel_id: int, user_id: int) -> None:
        """Clear conversation memory for a user in a channel."""
        key = (guild_id, channel_id, user_id)
        if key in self.history:
            self.history[key].clear()

    async def generate_response(
        self,
        session: aiohttp.ClientSession,
        guild_id: int,
        channel_id: int,
        user_id: int,
        prompt: str,
        server_name: str = "Discord Server",
    ) -> str:
        """
        Execute an AI conversation query with per-server isolation, rate limits,
        and Gemini model failover cascade.
        """
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key or key.lower().startswith("replace_"):
            raise RuntimeError(
                "AI is not configured. Add a valid GEMINI_API_KEY to your deployment environment."
            )

        config = self.get_server_config(guild_id)
        cooldown = config.get("cooldown_seconds", 4)

        now = time.monotonic()
        if now - self.user_last_call.get(user_id, 0) < cooldown:
            raise RuntimeError(f"Please wait {cooldown}s before asking another question.")
        self.user_last_call[user_id] = now

        history_key = (guild_id, channel_id, user_id)
        lock = self._locks.setdefault(history_key, asyncio.Lock())

        system_instruction = self.build_system_instruction(guild_id, server_name)

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
                    "temperature": 0.7,
                    "maxOutputTokens": 800 if config.get("response_length") == "short" else 1500,
                },
            }

            env_model = os.getenv("GEMINI_MODEL", "").strip().strip("/")
            candidate_models = []
            if env_model:
                candidate_models.append(env_model)
            for m in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"):
                if m not in candidate_models:
                    candidate_models.append(m)

            last_error: Exception | None = None
            timeout = aiohttp.ClientTimeout(total=25)

            for model_name in candidate_models:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={key}"
                )
                try:
                    async with session.post(url, json=body, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json(content_type=None)
                            candidates = data.get("candidates", []) if isinstance(data, dict) else []
                            if candidates:
                                parts = (
                                    candidates[0]
                                    .get("content", {})
                                    .get("parts", [])
                                )
                                text = "".join(
                                    part.get("text", "")
                                    for part in parts
                                    if isinstance(part, dict)
                                ).strip()
                                if text:
                                    # Save to memory
                                    history.append({"role": "user", "text": prompt[:3000]})
                                    history.append({"role": "model", "text": text})
                                    return text
                        elif response.status in (401, 403):
                            raise RuntimeError("Invalid or unauthorized GEMINI_API_KEY. Please verify your API key in Render environment settings.")
                        elif response.status == 429:
                            raise RuntimeError("Gemini API rate limit exceeded. Please wait a moment before trying again.")
                        else:
                            last_error = RuntimeError(f"AI API error status {response.status} from {model_name}")
                except (RuntimeError, asyncio.CancelledError):
                    raise
                except Exception as e:
                    last_error = e
                    continue

            if last_error:
                raise last_error
            return "I was unable to formulate a response at this time."
