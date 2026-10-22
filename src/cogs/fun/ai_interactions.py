from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import quote

import aiohttp
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import OWNER_ID, is_primary_owner

log = logging.getLogger("Kyoka.AIInteractions")
PURPLE = 0x7C3AED
MAX_HISTORY = 12


class AIInteractions(commands.Cog):
    """Optional Gemini chat and real GIF-provider integrations."""
    category = "AI & Chat"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.history: dict[tuple[int, int, int], deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))
        self.user_last_call: dict[int, float] = {}
        self._locks: dict[tuple[int, int, int], asyncio.Lock] = {}
        self._gif_cache: dict[str, tuple[float, str | None]] = {}

    async def cog_load(self) -> None:
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS kyoka_ai_settings (
            guild_id BIGINT PRIMARY KEY, channel_id BIGINT, updated_by BIGINT, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );""")
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS kyoka_guess_hosts (
            guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, added_by BIGINT NOT NULL,
            added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (guild_id, user_id)
        );""")
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS kyoka_guess_results (
            id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL,
            host_id BIGINT NOT NULL, winner_id BIGINT, lower_bound INTEGER NOT NULL,
            upper_bound INTEGER NOT NULL, answer INTEGER NOT NULL, status VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, ended_at TIMESTAMPTZ
        );""")

    def _session(self) -> aiohttp.ClientSession:
        session = getattr(self.bot, "session", None)
        if session is None or session.closed:
            raise RuntimeError("HTTP session is not ready")
        return session

    async def get_gif(self, query: str) -> str | None:
        """Fetch a validated GIF URL from GIPHY or Tenor; never fabricate URLs."""
        query = query.strip()[:120]
        if not query:
            return None
        now = time.monotonic()
        cached = self._gif_cache.get(query.lower())
        if cached and cached[0] > now:
            return cached[1]
        giphy_key = os.getenv("GIPHY_API_KEY", "").strip()
        tenor_key = os.getenv("TENOR_API_KEY", "").strip()
        try:
            timeout = aiohttp.ClientTimeout(total=7)
            async with self._session().get("https://api.giphy.com/v1/gifs/search", params={
                "api_key": giphy_key, "q": query, "limit": 10, "rating": "pg-13"
            }, timeout=timeout) if giphy_key else _null_async_context() as response:
                if response is not None and response.status == 200:
                    payload = await response.json(content_type=None)
                    items = payload.get("data", []) if isinstance(payload, dict) else []
                    urls = [item.get("images", {}).get("original", {}).get("url") for item in items if isinstance(item, dict)]
                    urls = [url for url in urls if isinstance(url, str) and url.startswith("https://") and ".giphy.com/" in url]
                    if urls:
                        import random
                        result = random.choice(urls)
                        self._gif_cache[query.lower()] = (now + 300, result)
                        return result
            if tenor_key:
                async with self._session().get("https://tenor.googleapis.com/v2/search", params={
                    "q": query, "key": tenor_key, "limit": 10, "contentfilter": "medium", "media_filter": "gif"
                }, timeout=timeout) as response:
                    if response.status == 200:
                        payload = await response.json(content_type=None)
                        items = payload.get("results", []) if isinstance(payload, dict) else []
                        urls = []
                        for item in items:
                            media = item.get("media_formats", {}) if isinstance(item, dict) else {}
                            gif = media.get("gif", {}) or media.get("mediumgif", {})
                            url = gif.get("url") if isinstance(gif, dict) else None
                            if isinstance(url, str) and url.startswith("https://") and "tenor.com" in url:
                                urls.append(url)
                        if urls:
                            import random
                            result = random.choice(urls)
                            self._gif_cache[query.lower()] = (now + 300, result)
                            return result
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as exc:
            log.info("GIF lookup failed (%s)", type(exc).__name__)
        self._gif_cache[query.lower()] = (now + 60, None)
        return None

    async def _ask_ai(self, guild_id: int, channel_id: int, user_id: int, prompt: str) -> str:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key or key.lower().startswith("replace_"):
            raise RuntimeError("AI is not configured. Add a valid GEMINI_API_KEY to your deployment environment.")
        now = time.monotonic()
        if now - self.user_last_call.get(user_id, 0) < 4:
            raise RuntimeError("Give me a moment before asking another question.")
        self.user_last_call[user_id] = now
        history_key = (guild_id, channel_id, user_id)
        lock = self._locks.setdefault(history_key, asyncio.Lock())
        async with lock:
            history = self.history[history_key]
            contents = []
            for turn in history:
                contents.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})
            contents.append({"role": "user", "parts": [{"text": prompt[:4000]}]})
            body = {"system_instruction": {"parts": [{"text": "You are KYŌKA, an original Aizen-inspired assistant: composed, clever, calm, occasionally dryly witty. Never claim to literally be Sosuke Aizen. Be useful and conversational."}]}, "contents": contents, "generationConfig": {"temperature": 0.8, "maxOutputTokens": 700}}
            models_to_try: list[str] = []
            env_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip().strip("/")
            if env_model:
                models_to_try.append(env_model)
            for fallback in ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"):
                if fallback not in models_to_try:
                    models_to_try.append(fallback)

            answer = ""
            last_error: Exception | None = None

            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                timeout = aiohttp.ClientTimeout(total=7)
                try:
                    async with self._session().post(url, params={"key": key}, json=body, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json(content_type=None)
                            try:
                                parts = data["candidates"][0]["content"]["parts"]
                                answer = "".join(part.get("text", "") for part in parts).strip()
                                if answer:
                                    break
                            except (KeyError, IndexError, TypeError):
                                continue
                        elif response.status in (401, 403):
                            raise RuntimeError("Gemini rejected the API key. Please check GEMINI_API_KEY in Render.")
                        else:
                            log.debug("Gemini model %s returned status %s; trying next candidate...", model, response.status)
                except asyncio.TimeoutError:
                    log.debug("Gemini model %s timed out; trying next candidate...", model)
                    continue
                except RuntimeError:
                    raise
                except Exception as exc:
                    last_error = exc
                    log.debug("Gemini model %s error: %s; trying next candidate...", model, exc)
                    continue

            if not answer:
                if last_error:
                    raise last_error
                raise RuntimeError("The AI service is currently unavailable. Please try again shortly.")

            history.append({"role": "user", "text": prompt[:4000]})
            history.append({"role": "model", "text": answer[:5000]})
            return answer

    async def _send_ai(self, ctx: CustomContext, prompt: str) -> None:
        if not prompt.strip():
            return await ctx.send(f"Tell me what you seek. Usage: `{ctx.prefix}ai <message>`")
        guild_id = ctx.guild.id if ctx.guild else 0
        async with ctx.typing():
            try:
                answer = await self._ask_ai(guild_id, ctx.channel.id, ctx.author.id, prompt)
            except RuntimeError as exc:
                return await ctx.send(f"🟣 {exc}")
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return await ctx.send("🟣 The connection to the AI service failed. Please try again shortly.")
        for start in range(0, len(answer), 1900):
            await ctx.reply(answer[start:start + 1900], mention_author=False, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="aisetup", help="Admin: configure automatic AI replies in a channel, or turn them off.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def aisetup(self, ctx: CustomContext, channel: discord.TextChannel | str):
        if isinstance(channel, str) and channel.lower() == "off":
            await self.bot.db.execute("INSERT INTO kyoka_ai_settings (guild_id, channel_id, updated_by) VALUES (?, NULL, ?) ON CONFLICT (guild_id) DO UPDATE SET channel_id = NULL, updated_by = EXCLUDED.updated_by, updated_at = CURRENT_TIMESTAMP;", ctx.guild.id, ctx.author.id)
            return await ctx.send("🟣 Automatic AI replies are disabled for this server.")
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send(f"Usage: `{ctx.prefix}aisetup #channel` or `{ctx.prefix}aisetup off`.")
        await self.bot.db.execute("INSERT INTO kyoka_ai_settings (guild_id, channel_id, updated_by) VALUES (?, ?, ?) ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id, updated_by = EXCLUDED.updated_by, updated_at = CURRENT_TIMESTAMP;", ctx.guild.id, channel.id, ctx.author.id)
        await ctx.send(f"🟣 Automatic AI conversation is now configured for {channel.mention}.")

    @commands.command(name="ai", aliases=["chat", "askai", "aizenai"], help="Ask KYŌKA a question using Gemini AI.")
    async def ai(self, ctx: CustomContext, *, message: str = ""):
        await self._send_ai(ctx, message)

    @commands.command(name="aiclear", help="Clear your private KYŌKA conversation history.")
    async def aiclear(self, ctx: CustomContext):
        guild_id = ctx.guild.id if ctx.guild else 0
        self.history.pop((guild_id, ctx.channel.id, ctx.author.id), None)
        await ctx.send("🟣 Your conversation history for this channel has been cleared.")

    @commands.command(name="aistatus", help="Show AI and GIF integration configuration without revealing secrets.")
    async def aistatus(self, ctx: CustomContext):
        ai = bool(os.getenv("GEMINI_API_KEY", "").strip() and not os.getenv("GEMINI_API_KEY", "").lower().startswith("replace_"))
        gifs = bool(os.getenv("GIPHY_API_KEY", "").strip() or os.getenv("TENOR_API_KEY", "").strip())
        channel = None
        if ctx.guild:
            row = await self.bot.db.fetch_one("SELECT channel_id FROM kyoka_ai_settings WHERE guild_id = ?;", ctx.guild.id)
            channel = row.get("channel_id") if row else None
        embed = discord.Embed(title="KYŌKA Integrations", color=PURPLE, description=f"**Gemini AI:** {'Configured' if ai else 'Not configured'}\n**GIF provider:** {'Configured' if gifs else 'Not configured'}\n**Auto-chat channel:** {f'<#{channel}>' if channel else 'Disabled'}")
        await ctx.send(embed=embed)

    @commands.command(name="gif", help="Search for a real GIF using the configured GIF provider.")
    async def gif(self, ctx: CustomContext, *, search: str):
        url = await self.get_gif(search)
        if not url:
            return await ctx.send("I couldn't find a GIF. Check the configured GIPHY_API_KEY or TENOR_API_KEY and try again.")
        embed = discord.Embed(title=f"GIF: {search[:200]}", color=PURPLE)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.command(name="meme", help="Search for an anime meme GIF, optionally by topic.")
    async def meme(self, ctx: CustomContext, *, topic: str = "anime"):
        query = f"anime meme {topic}"[:120]
        url = await self.get_gif(query)
        if not url:
            return await ctx.send("I couldn't find a meme GIF. Check your configured GIF provider API key.")
        embed = discord.Embed(title=f"🌀 KYŌKA meme: {topic[:150]}", color=PURPLE)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.command(name="randomgif", help="Get a random GIF, optionally by search topic.")
    async def randomgif(self, ctx: CustomContext, *, search: str = "anime reaction"):
        url = await self.get_gif(search)
        if not url:
            return await ctx.send("No GIF result was available. Check your GIF provider API key.")
        embed = discord.Embed(title="KYŌKA GIF", color=PURPLE)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    async def _interaction(self, ctx: CustomContext, member: discord.Member | None, action: str, query: str, line: str):
        if member is None:
            return await ctx.send(f"Mention someone. Example: `{ctx.prefix}{action} @member`.")
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("Choose another human member for this interaction.")
        await ctx.send(line.format(target=member.mention, actor=ctx.author.mention), allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False))
        url = await self.get_gif(query)
        if url:
            embed = discord.Embed(color=PURPLE)
            embed.set_image(url=url)
            await ctx.send(embed=embed)

    @commands.command(name="wave", help="Wave at a member with an optional GIF.")
    async def wave(self, ctx: CustomContext, member: discord.Member | None = None):
        if member:
            await self._interaction(ctx, member, "wave", "anime wave", "👋 {actor} waves at {target}.")
        else:
            await ctx.send(f"👋 {ctx.author.mention} waves at everyone.", allowed_mentions=discord.AllowedMentions.none())
            url = await self.get_gif("anime wave")
            if url:
                e = discord.Embed(color=PURPLE); e.set_image(url=url); await ctx.send(embed=e)

    @commands.command(name="wink", help="Wink at a member with an optional GIF.")
    async def wink(self, ctx: CustomContext, member: discord.Member | None = None):
        if member:
            await self._interaction(ctx, member, "wink", "anime wink", "😉 {actor} winks at {target}.")
        else:
            await ctx.send(f"😉 {ctx.author.mention} winks. Aizen knows something you don't.", allowed_mentions=discord.AllowedMentions.none())
            url = await self.get_gif("anime wink")
            if url:
                e = discord.Embed(color=PURPLE); e.set_image(url=url); await ctx.send(embed=e)

    async def _solo_reaction(self, ctx: CustomContext, name: str, query: str, text: str | None = None):
        await ctx.send(text or f"✨ {ctx.author.mention} {name}.", allowed_mentions=discord.AllowedMentions.none())
        url = await self.get_gif(query)
        if url:
            embed = discord.Embed(color=PURPLE)
            embed.set_image(url=url)
            await ctx.send(embed=embed)

    @commands.command(name="dance", help="Celebrate with an anime dance GIF.")
    async def dance(self, ctx: CustomContext): await self._solo_reaction(ctx, "starts dancing", "anime dance")

    @commands.command(name="blush", help="Show a blushing anime reaction.")
    async def blush(self, ctx: CustomContext): await self._solo_reaction(ctx, "blushes", "anime blush")

    @commands.command(name="cry", help="Show a crying anime reaction.")
    async def cry(self, ctx: CustomContext): await self._solo_reaction(ctx, "is crying dramatically", "anime cry")

    @commands.command(name="laugh", help="Show a laughing anime reaction.")
    async def laugh(self, ctx: CustomContext): await self._solo_reaction(ctx, "laughs", "anime laugh")

    @commands.command(name="happy", help="Show a happy anime reaction.")
    async def happy(self, ctx: CustomContext): await self._solo_reaction(ctx, "looks delighted", "anime happy")

    @commands.command(name="angry", help="Show an angry anime reaction.")
    async def angry(self, ctx: CustomContext): await self._solo_reaction(ctx, "looks furious", "anime angry")

    @commands.command(name="sleepy", help="Show a sleepy anime reaction.")
    async def sleepy(self, ctx: CustomContext): await self._solo_reaction(ctx, "is getting sleepy", "anime sleepy")

    @commands.command(name="thumbsup", help="Give a thumbs-up reaction.")
    async def thumbsup(self, ctx: CustomContext): await self._solo_reaction(ctx, "gives a thumbs-up", "anime thumbs up")

    @commands.command(name="facepalm", help="Show a dramatic facepalm reaction.")
    async def facepalm(self, ctx: CustomContext): await self._solo_reaction(ctx, "facepalms", "anime facepalm")

    @commands.command(name="shrug", help="Show a shrug reaction.")
    async def shrug(self, ctx: CustomContext): await self._solo_reaction(ctx, "shrugs", "anime shrug")

    @commands.command(name="killme", help="A harmless, comedic anime reaction; not an encouragement of self-harm.")
    async def killme(self, ctx: CustomContext): await self._solo_reaction(ctx, "dramatically collapses from embarrassment (comedy only)", "anime dramatic collapse")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content.strip():
            return
        # Do not answer command messages, regardless of the configured prefix.
        try:
            parsed_context = await self.bot.get_context(message)
            if parsed_context.valid:
                return
        except Exception:
            pass
        if self.bot.user and self.bot.user in message.mentions:
            return
        try:
            row = await self.bot.db.fetch_one("SELECT channel_id FROM kyoka_ai_settings WHERE guild_id = ?;", message.guild.id)
        except Exception:
            return
        if not row or not row.get("channel_id") or int(row["channel_id"]) != message.channel.id:
            return
        if len(message.content) > 4000:
            return
        guild_id = message.guild.id
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key or key.lower().startswith("replace_"):
            return await message.reply(
                "🟣 AI chat is enabled here, but the bot owner still needs to configure `GEMINI_API_KEY`.",
                mention_author=False, allowed_mentions=discord.AllowedMentions.none()
            )
        async with message.channel.typing():
            try:
                answer = await self._ask_ai(guild_id, message.channel.id, message.author.id, message.content)
            except Exception as exc:
                log.info("Automatic AI response failed (%s)", type(exc).__name__)
                return await message.reply(
                    "🟣 I couldn't generate a reply right now. Check the AI model/API configuration or try again shortly.",
                    mention_author=False, allowed_mentions=discord.AllowedMentions.none()
                )
        await message.reply(answer[:1900], mention_author=False, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="guesshostadd", help="Owner-only: authorize a number-game host in this server.")
    @commands.guild_only()
    async def guesshostadd(self, ctx: CustomContext, member: discord.Member):
        if not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the primary bot owner can manage the number-game host allowlist.")
        await self.bot.db.execute("INSERT INTO kyoka_guess_hosts (guild_id, user_id, added_by) VALUES (?, ?, ?) ON CONFLICT (guild_id, user_id) DO NOTHING;", ctx.guild.id, member.id, OWNER_ID)
        await ctx.send(f"Added {member.mention} to this server's number-game host allowlist.", allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="guesshostremove", help="Owner-only: remove a number-game host in this server.")
    @commands.guild_only()
    async def guesshostremove(self, ctx: CustomContext, member: discord.Member):
        if not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the primary bot owner can manage the number-game host allowlist.")
        await self.bot.db.execute("DELETE FROM kyoka_guess_hosts WHERE guild_id = ? AND user_id = ?;", ctx.guild.id, member.id)
        await ctx.send(f"Removed {member.mention} from the number-game host allowlist.", allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="guesshosts", help="Owner-only: list authorized number-game hosts for this server.")
    @commands.guild_only()
    async def guesshosts(self, ctx: CustomContext):
        if not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the primary bot owner can view the number-game host allowlist.")
        rows = await self.bot.db.fetch_all("SELECT user_id FROM kyoka_guess_hosts WHERE guild_id = ? ORDER BY user_id;", ctx.guild.id)
        value = "\n".join(f"• <@{int(row['user_id'])}> (`{int(row['user_id'])}`)" for row in rows) or "No hosts authorized yet."
        await ctx.send(embed=discord.Embed(title="Number-game hosts", description=value, color=PURPLE), allowed_mentions=discord.AllowedMentions.none())


class _null_async_context:
    async def __aenter__(self): return None
    async def __aexit__(self, exc_type, exc, tb): return False


async def setup(bot: commands.Bot):
    await bot.add_cog(AIInteractions(bot))
