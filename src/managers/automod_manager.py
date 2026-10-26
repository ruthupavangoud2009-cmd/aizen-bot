"""
Kyoka Discord Bot - AutoMod & Content Moderation Engine
Per-server configurable anti-spam, invite blocking, mass-mentions, bad words,
caps filtering, and repeated messages with role/channel exemptions and action hierarchy.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import datetime
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import discord

if TYPE_CHECKING:
    from src.core.bot import KyokaBot
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.AutoModManager")

# Standard Discord Invite pattern (discord.gg, discord.com/invite, discordapp.com/invite)
INVITE_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com\/invite)\/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)


class AutoModManager:
    """Enterprise-grade AutoMod filter engine with L1 memory caching and bounded sliding-window rate tracking."""

    def __init__(self, db: PostgresDatabase, bot: Optional[KyokaBot] = None) -> None:
        self.db = db
        self.bot = bot

        # Cache: guild_id -> (timestamp, settings_dict)
        self._cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}

        # Anti-Spam sliding window: (guild_id, user_id) -> deque of message timestamps
        self._message_history: Dict[Tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=20))

        # Anti-Repeated content: (guild_id, user_id) -> (last_cleaned_text, repeat_count, last_ts)
        self._repeat_history: Dict[Tuple[int, int], Tuple[str, int, float]] = {}

        # Cooldown per user to prevent duplicate action spam: (guild_id, user_id) -> timestamp
        self._action_cooldowns: Dict[Tuple[int, int], float] = {}

    def invalidate_cache(self, guild_id: int) -> None:
        """Evict guild AutoMod configuration from memory cache."""
        self._cache.pop(guild_id, None)

    async def get_settings(self, guild_id: int) -> Dict[str, Any]:
        """Fetch guild AutoMod configuration with 30s L1 memory cache and safe defaults."""
        now = time.monotonic()
        if guild_id in self._cache:
            ts, data = self._cache[guild_id]
            if now - ts < 30.0:
                return data

        query = """
            SELECT guild_id, enabled, anti_spam, spam_threshold, anti_mentions, mention_threshold,
                   anti_invites, anti_badwords, badwords_list, anti_repeated, anti_caps, caps_threshold,
                   action, timeout_duration, exempt_roles, exempt_channels, log_channel_id, updated_at
            FROM guild_automod
            WHERE guild_id = $1;
        """
        try:
            row = await self.db.fetch_one(query, guild_id)
            if row:
                bw_raw = row.get("badwords_list") or ""
                bw_list = [w.strip().lower() for w in bw_raw.split(",") if w.strip()]

                er_raw = row.get("exempt_roles") or ""
                er_list = [r.strip() for r in er_raw.split(",") if r.strip()]

                ec_raw = row.get("exempt_channels") or ""
                ec_list = [c.strip() for c in ec_raw.split(",") if c.strip()]

                cfg = {
                    "guild_id": guild_id,
                    "enabled": bool(row["enabled"]),
                    "anti_spam": bool(row["anti_spam"]),
                    "spam_threshold": int(row["spam_threshold"] or 5),
                    "anti_mentions": bool(row["anti_mentions"]),
                    "mention_threshold": int(row["mention_threshold"] or 4),
                    "anti_invites": bool(row["anti_invites"]),
                    "anti_badwords": bool(row["anti_badwords"]),
                    "badwords_list": bw_list,
                    "anti_repeated": bool(row["anti_repeated"]),
                    "anti_caps": bool(row["anti_caps"]),
                    "caps_threshold": int(row["caps_threshold"] or 70),
                    "action": str(row["action"] or "delete").lower(),
                    "timeout_duration": int(row["timeout_duration"] or 60),
                    "exempt_roles": er_list,
                    "exempt_channels": ec_list,
                    "log_channel_id": str(row["log_channel_id"]) if row["log_channel_id"] else None,
                }
            else:
                cfg = self._default_settings(guild_id)
        except Exception as e:
            logger.debug(f"Could not load AutoMod settings for guild {guild_id}: {e}")
            cfg = self._default_settings(guild_id)

        self._cache[guild_id] = (now, cfg)
        return cfg

    @staticmethod
    def _default_settings(guild_id: int) -> Dict[str, Any]:
        return {
            "guild_id": guild_id,
            "enabled": False,
            "anti_spam": True,
            "spam_threshold": 5,
            "anti_mentions": True,
            "mention_threshold": 4,
            "anti_invites": True,
            "anti_badwords": False,
            "badwords_list": [],
            "anti_repeated": True,
            "anti_caps": False,
            "caps_threshold": 70,
            "action": "delete",
            "timeout_duration": 60,
            "exempt_roles": [],
            "exempt_channels": [],
            "log_channel_id": None,
        }

    async def update_settings(self, guild_id: int, **kwargs: Any) -> bool:
        """Atomically persist AutoMod settings to PostgreSQL and update cache."""
        cur = await self.get_settings(guild_id)
        cur.update(kwargs)

        bw_str = ",".join(cur.get("badwords_list", [])) if isinstance(cur.get("badwords_list"), list) else str(cur.get("badwords_list", ""))
        er_str = ",".join(str(r) for r in cur.get("exempt_roles", [])) if isinstance(cur.get("exempt_roles"), list) else str(cur.get("exempt_roles", ""))
        ec_str = ",".join(str(c) for c in cur.get("exempt_channels", [])) if isinstance(cur.get("exempt_channels"), list) else str(cur.get("exempt_channels", ""))
        log_ch = int(cur["log_channel_id"]) if cur.get("log_channel_id") else None

        query = """
            INSERT INTO guild_automod (
                guild_id, enabled, anti_spam, spam_threshold, anti_mentions, mention_threshold,
                anti_invites, anti_badwords, badwords_list, anti_repeated, anti_caps, caps_threshold,
                action, timeout_duration, exempt_roles, exempt_channels, log_channel_id, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                anti_spam = EXCLUDED.anti_spam,
                spam_threshold = EXCLUDED.spam_threshold,
                anti_mentions = EXCLUDED.anti_mentions,
                mention_threshold = EXCLUDED.mention_threshold,
                anti_invites = EXCLUDED.anti_invites,
                anti_badwords = EXCLUDED.anti_badwords,
                badwords_list = EXCLUDED.badwords_list,
                anti_repeated = EXCLUDED.anti_repeated,
                anti_caps = EXCLUDED.anti_caps,
                caps_threshold = EXCLUDED.caps_threshold,
                action = EXCLUDED.action,
                timeout_duration = EXCLUDED.timeout_duration,
                exempt_roles = EXCLUDED.exempt_roles,
                exempt_channels = EXCLUDED.exempt_channels,
                log_channel_id = EXCLUDED.log_channel_id,
                updated_at = CURRENT_TIMESTAMP;
        """
        try:
            await self.db.execute(
                query,
                guild_id,
                bool(cur["enabled"]),
                bool(cur["anti_spam"]),
                int(cur["spam_threshold"]),
                bool(cur["anti_mentions"]),
                int(cur["mention_threshold"]),
                bool(cur["anti_invites"]),
                bool(cur["anti_badwords"]),
                bw_str,
                bool(cur["anti_repeated"]),
                bool(cur["anti_caps"]),
                int(cur["caps_threshold"]),
                str(cur["action"]).lower(),
                int(cur["timeout_duration"]),
                er_str,
                ec_str,
                log_ch,
            )
            self._cache[guild_id] = (time.monotonic(), cur)
            logger.info(f"Updated AutoMod settings for guild {guild_id} (enabled={cur['enabled']}, action={cur['action']})")
            return True
        except Exception as e:
            logger.error(f"Failed to save AutoMod settings for guild {guild_id}: {e}", exc_info=e)
            return False

    def is_exempt(self, member: discord.Member, channel: discord.abc.GuildChannel, cfg: Dict[str, Any]) -> bool:
        """Check if author or channel is exempt from AutoMod enforcement."""
        # 1. Primary Owner / Developer is always exempt
        from src.security.owner import is_primary_owner
        if is_primary_owner(member.id):
            return True

        # 2. Server Owner is exempt
        if member.guild and member.id == member.guild.owner_id:
            return True

        # 3. Members with Administrator / Manage Guild are exempt
        perms = member.guild_permissions
        if perms.administrator or perms.manage_guild:
            return True

        # 4. Check exempt channels
        exempt_channels = set(cfg.get("exempt_channels") or [])
        if str(channel.id) in exempt_channels:
            return True

        # 5. Check exempt roles
        exempt_roles = set(cfg.get("exempt_roles") or [])
        if any(str(r.id) in exempt_roles for r in member.roles):
            return True

        return False

    def check_content(
        self,
        content: str,
        user_id: int,
        guild_id: int,
        cfg: Dict[str, Any],
        mentions_count: int = 0,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Evaluate a text string and metadata against active filters.
        Returns (is_violation, filter_name, reason_description).
        """
        if not cfg.get("enabled"):
            return False, None, None

        cleaned = content.strip()

        # 1. Filter: Anti-Invites
        if cfg.get("anti_invites") and INVITE_REGEX.search(cleaned):
            return True, "anti_invites", "Discord invite links are prohibited."

        # 2. Filter: Bad Words
        if cfg.get("anti_badwords") and cfg.get("badwords_list"):
            lower_content = cleaned.lower()
            for badword in cfg["badwords_list"]:
                if not badword:
                    continue
                # Word boundary check or substring if special characters present
                pattern = rf"\b{re.escape(badword)}\b" if badword.isalnum() else re.escape(badword)
                if re.search(pattern, lower_content):
                    return True, "anti_badwords", f"Message contains blacklisted keyword/phrase."

        # 3. Filter: Mass Mentions
        if cfg.get("anti_mentions"):
            threshold = int(cfg.get("mention_threshold") or 4)
            if mentions_count >= threshold:
                return True, "anti_mentions", f"Mass mentions detected ({mentions_count} >= threshold {threshold})."

        # 4. Filter: Anti-Caps
        if cfg.get("anti_caps") and len(cleaned) >= 10:
            threshold = int(cfg.get("caps_threshold") or 70)
            letters = [c for c in cleaned if c.isalpha()]
            if len(letters) >= 8:
                caps_ratio = (sum(1 for c in letters if c.isupper()) / len(letters)) * 100.0
                if caps_ratio >= threshold:
                    return True, "anti_caps", f"Excessive uppercase text ({caps_ratio:.0f}% caps)."

        # 5. Filter: Repeated Messages
        if cfg.get("anti_repeated") and len(cleaned) >= 5:
            now = time.monotonic()
            key = (guild_id, user_id)
            last_text, count, last_ts = self._repeat_history.get(key, ("", 0, 0.0))
            if cleaned == last_text and (now - last_ts < 20.0):
                count += 1
                self._repeat_history[key] = (cleaned, count, now)
                if count >= 3:
                    return True, "anti_repeated", f"Repeated identical message content ({count} consecutive messages)."
            else:
                self._repeat_history[key] = (cleaned, 1, now)

        # 6. Filter: Anti-Spam Rate Limit (messages per time window)
        if cfg.get("anti_spam"):
            now = time.monotonic()
            key = (guild_id, user_id)
            history = self._message_history[key]
            history.append(now)
            threshold = int(cfg.get("spam_threshold") or 5)
            # Count messages sent in last 4 seconds
            recent_count = sum(1 for ts in history if now - ts <= 4.0)
            if recent_count >= threshold:
                return True, "anti_spam", f"Chat rate limit exceeded ({recent_count} msgs in 4s; limit is {threshold})."

        return False, None, None

    async def execute_action(
        self,
        guild: discord.Guild,
        member: discord.Member,
        channel: discord.TextChannel,
        message: Optional[discord.Message],
        filter_name: str,
        reason: str,
        cfg: Dict[str, Any],
    ) -> bool:
        """Safely execute the configured punishment action respecting Discord hierarchy and bot permissions."""
        action = cfg.get("action", "delete").lower()
        bot_member = guild.me
        if not bot_member:
            return False

        # Prevent duplicate punishment actions in a 3-second window
        now = time.monotonic()
        key = (guild.id, member.id)
        if now - self._action_cooldowns.get(key, 0.0) < 3.0:
            if message and action == "delete" and channel.permissions_for(bot_member).manage_messages:
                try:
                    await message.delete()
                except Exception:
                    pass
            return True
        self._action_cooldowns[key] = now

        # Delete message first if message exists and bot has permissions
        deleted = False
        if message and channel.permissions_for(bot_member).manage_messages:
            try:
                await message.delete()
                deleted = True
            except Exception as e:
                logger.debug(f"Could not delete AutoMod offending message in {guild.id}: {e}")

        # Hierarchy check before timeout
        can_moderate = (
            bot_member.guild_permissions.moderate_members
            and bot_member.top_role > member.top_role
            and member.id != guild.owner_id
        )

        # Execute punishment
        action_taken = "Message Deleted"
        if action == "timeout" and can_moderate:
            duration = int(cfg.get("timeout_duration") or 60)
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
            try:
                await member.timeout(until, reason=f"Kyoka AutoMod: {reason}")
                action_taken = f"Timed out for {duration}s"
            except Exception as e:
                logger.warning(f"Could not timeout member {member.id} in guild {guild.id}: {e}")
                action_taken = "Message Deleted (Timeout Failed: Missing Permissions)"
        elif action == "warn":
            try:
                await self.db.execute(
                    "INSERT INTO guild_warns (guild_id, user_id, moderator_id, reason) VALUES ($1, $2, $3, $4);",
                    guild.id, member.id, bot_member.id, f"AutoMod: {reason}"
                )
                action_taken = "Official Warning Issued"
            except Exception as e:
                logger.debug(f"Could not record warning for {member.id}: {e}")

        # Dispatch structured warning / mod log
        try:
            log_ch_id = cfg.get("log_channel_id")
            log_channel = guild.get_channel(int(log_ch_id)) if log_ch_id else None
            if not log_channel and hasattr(self.bot, "log_mgr"):
                log_channel = self.bot.log_mgr.get_log_channel(guild, "mod")

            if log_channel and log_channel.permissions_for(bot_member).send_messages:
                embed = discord.Embed(
                    title="🛡️ AutoMod Violation Triggered",
                    description=(
                        f"**User:** {member.mention} (`{member.id}`)\n"
                        f"**Channel:** {channel.mention}\n"
                        f"**Filter:** `{filter_name}`\n"
                        f"**Reason:** {reason}\n"
                        f"**Action Taken:** **{action_taken}**"
                    ),
                    color=0xFF3366,
                    timestamp=discord.utils.utcnow(),
                )
                embed.set_footer(text=f"Kyoka 3.0 AutoMod • Guild ID: {guild.id}")
                await log_channel.send(embed=embed)
        except Exception as log_err:
            logger.debug(f"AutoMod log dispatch notice: {log_err}")

        return True
