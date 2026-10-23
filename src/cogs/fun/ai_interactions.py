from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.ai_manager import PERSONALITY_PRESETS
from src.security.owner import OWNER_ID, is_primary_owner
from src.utils.containers import KyokaContainer, send_container_response

log = logging.getLogger("Kyoka.AIInteractions")
PURPLE = 0x7C3AED
MAX_HISTORY = 12


class ConfirmAIResetView(discord.ui.View):
    """Confirmation view for resetting server AI configuration."""

    def __init__(self, bot: commands.Bot, guild_id: int, user_id: int) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, custom_id="ai:confirm_reset")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the command author can confirm this.", ephemeral=True)
        if hasattr(self.bot, "ai_mgr"):
            await self.bot.ai_mgr.reset_server_config(self.guild_id)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="✅ AI configuration for this server has been reset to defaults.", view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ai:cancel_reset")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the command author can cancel this.", ephemeral=True)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ AI reset cancelled.", view=self)


class AIInteractions(commands.Cog):
    """Optional Gemini chat and real GIF-provider integrations."""
    category = "⛩️・AIZEN AI SYSTEM"

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

    async def _ask_ai(self, guild_id: int, channel_id: int, user_id: int, prompt: str, server_name: str = "Discord Server") -> str:
        ai_mgr = getattr(self.bot, "ai_mgr", None)
        if ai_mgr:
            return await ai_mgr.generate_response(
                self._session(),
                guild_id,
                channel_id,
                user_id,
                prompt,
                server_name=server_name,
            )

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
            body = {
                "system_instruction": {"parts": [{"text": "You are KYŌKA, an original Aizen-inspired assistant: composed, clever, calm, occasionally dryly witty. Never claim to literally be Sosuke Aizen. Be useful, punchy, concise, and conversational."}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
            }
            models_to_try: list[str] = ["gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-flash-latest"]
            env_model = os.getenv("GEMINI_MODEL", "").strip().strip("/")
            if env_model and env_model not in models_to_try:
                models_to_try.insert(0, env_model)

            answer = ""
            last_error: Exception | None = None
            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                timeout = aiohttp.ClientTimeout(total=20.0)
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
                            raise RuntimeError("Gemini rejected the API key. Please verify your GEMINI_API_KEY in Render environment settings.")
                        elif response.status == 429:
                            raise RuntimeError("Gemini API rate limit exceeded. Please wait a moment before trying again.")
                except (RuntimeError, asyncio.CancelledError):
                    raise
                except Exception as exc:
                    last_error = exc
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
        server_name = ctx.guild.name if ctx.guild else "Discord Server"
        async with ctx.typing():
            try:
                answer = await self._ask_ai(guild_id, ctx.channel.id, ctx.author.id, prompt, server_name=server_name)
            except RuntimeError as exc:
                return await ctx.send(f"🟣 {exc}")
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return await ctx.send("🟣 The connection to the AI service failed. Please try again shortly.")
        for start in range(0, len(answer), 1900):
            await ctx.reply(answer[start:start + 1900], mention_author=False, allowed_mentions=discord.AllowedMentions.none())

    # ─── SLASH COMMAND GROUP (6 SUBCOMMANDS) ────────────────────────────────

    ai_group = app_commands.Group(
        name="ai",
        description="KYOKA 3.0 Multi-Personality AI System",
    )

    # 35. /ai setup
    @ai_group.command(name="setup", description="Configure AI personality, channel, tone, and rules for this server.")
    @app_commands.describe(
        channel="Dedicated channel where the AI will respond",
        personality="Personality preset",
        tone="Conversational tone (e.g. cheerful, composed, formal, witty)",
        humor="Humor style (e.g. none, dry, sarcastic, playful)",
        response_length="Length preference for AI answers",
        respond_mode="When the AI should answer",
        purpose="Custom role or purpose for the AI in this server",
        rules="Special rules or guidelines the AI must follow",
    )
    @app_commands.choices(
        personality=[
            app_commands.Choice(name="Happy and playful boy", value="happy_boy"),
            app_commands.Choice(name="Friendly helper", value="friendly_helper"),
            app_commands.Choice(name="Professional assistant", value="professional"),
            app_commands.Choice(name="Funny and sarcastic", value="funny_sarcastic"),
            app_commands.Choice(name="Calm and supportive", value="calm_supportive"),
            app_commands.Choice(name="Aizen-inspired anime personality", value="aizen"),
            app_commands.Choice(name="Cheerful anime-inspired", value="cheerful_anime"),
            app_commands.Choice(name="Blox Fruits & Gaming expert", value="gaming_expert"),
            app_commands.Choice(name="Short-answer assistant", value="short_answer"),
            app_commands.Choice(name="Custom server personality", value="custom"),
        ],
        response_length=[
            app_commands.Choice(name="Short & punchy (1-3 sentences)", value="short"),
            app_commands.Choice(name="Balanced (conversational)", value="balanced"),
            app_commands.Choice(name="Detailed (in-depth explanations)", value="detailed"),
        ],
        respond_mode=[
            app_commands.Choice(name="Mentions and direct replies only", value="mentions_and_replies"),
            app_commands.Choice(name="Mentions only", value="mentions_only"),
            app_commands.Choice(name="All messages in AI channel", value="all_channel_messages"),
        ],
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_setup(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        personality: Optional[app_commands.Choice[str]] = None,
        tone: Optional[str] = None,
        humor: Optional[str] = None,
        response_length: Optional[app_commands.Choice[str]] = None,
        respond_mode: Optional[app_commands.Choice[str]] = None,
        purpose: Optional[str] = None,
        rules: Optional[str] = None,
    ) -> None:
        gid = interaction.guild.id
        current = self.bot.ai_mgr.get_server_config(gid)

        if channel:
            current["channel_id"] = channel.id
        if personality:
            current["personality"] = personality.value
        if tone:
            current["tone"] = tone[:64]
        if humor:
            current["humor"] = humor[:64]
        if response_length:
            current["response_length"] = response_length.value
        if respond_mode:
            current["respond_mode"] = respond_mode.value
        if purpose:
            current["purpose"] = purpose[:500]
        if rules:
            current["custom_rules"] = rules[:1000]

        current["updated_by"] = interaction.user.id
        await self.bot.ai_mgr.save_server_config(gid, current)

        p_name = PERSONALITY_PRESETS.get(current["personality"], {}).get("name", current["personality"])
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        chan_id = current.get("channel_id")
        chan_str = f"<#{chan_id}>" if chan_id else "All permitted channels"

        container = KyokaContainer()
        container.add_section(content=f"# **AI Configured: {interaction.guild.name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Personality Preset:** `{p_name}`\n"
            f"{dot} **Tone / Humor:** `{current.get('tone')}` / `{current.get('humor')}`\n"
            f"{dot} **Length:** `{current.get('response_length')}`\n"
            f"{dot} **Channel:** {chan_str}\n"
            f"{dot} **Mode:** `{current.get('respond_mode')}`\n"
            f"> Test the new configuration anytime with `/ai test`!"
        )
        await send_container_response(interaction, container, ephemeral=True)

    # 36. /ai personality
    @ai_group.command(name="personality", description="Choose or customize the AI personality preset for this server.")
    @app_commands.describe(
        preset="Choose one of the 10 personality presets",
        custom_prompt="Custom system instructions (used when preset is 'Custom')",
    )
    @app_commands.choices(
        preset=[
            app_commands.Choice(name="Happy and playful boy", value="happy_boy"),
            app_commands.Choice(name="Friendly helper", value="friendly_helper"),
            app_commands.Choice(name="Professional assistant", value="professional"),
            app_commands.Choice(name="Funny and sarcastic", value="funny_sarcastic"),
            app_commands.Choice(name="Calm and supportive", value="calm_supportive"),
            app_commands.Choice(name="Aizen-inspired anime personality", value="aizen"),
            app_commands.Choice(name="Cheerful anime-inspired", value="cheerful_anime"),
            app_commands.Choice(name="Blox Fruits & Gaming expert", value="gaming_expert"),
            app_commands.Choice(name="Short-answer assistant", value="short_answer"),
            app_commands.Choice(name="Custom server personality", value="custom"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_personality(
        self,
        interaction: discord.Interaction,
        preset: app_commands.Choice[str],
        custom_prompt: Optional[str] = None,
    ) -> None:
        gid = interaction.guild.id
        current = self.bot.ai_mgr.get_server_config(gid)
        current["personality"] = preset.value
        if custom_prompt:
            current["custom_system_prompt"] = custom_prompt[:1500]

        await self.bot.ai_mgr.save_server_config(gid, current)
        preset_info = PERSONALITY_PRESETS.get(preset.value, {})
        await interaction.response.send_message(
            f"✅ Switched server AI personality to **{preset_info.get('name', preset.name)}**.\n"
            f"> *{preset_info.get('description', '')}*",
            ephemeral=True,
        )

    # 37. /ai test
    @ai_group.command(name="test", description="Preview and test the server's configured AI personality.")
    @app_commands.describe(prompt="Test question or statement to send to the AI")
    async def slash_test(self, interaction: discord.Interaction, prompt: str) -> None:
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        server_name = interaction.guild.name
        try:
            answer = await self.bot.ai_mgr.generate_response(
                self._session(),
                gid,
                interaction.channel.id,
                interaction.user.id,
                prompt,
                server_name=server_name,
            )
            cfg = self.bot.ai_mgr.get_server_config(gid)
            preset_name = PERSONALITY_PRESETS.get(cfg.get("personality", "aizen"), {}).get("name", "AI")
            container = KyokaContainer()
            container.add_section(content=f"**Personality Preview: {preset_name}**")
            container.add_separator(divider=True)
            container.add_text(f"**You:** {prompt}\n\n**KYOKA:** {answer}")
            await send_container_response(interaction, container, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ AI Preview failed: {e}", ephemeral=True)

    # 38. /ai reset
    @ai_group.command(name="reset", description="Reset AI configuration for this server to default settings.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_reset(self, interaction: discord.Interaction) -> None:
        view = ConfirmAIResetView(self.bot, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            "⚠️ **Are you sure you want to reset the AI configuration for this server?**\n"
            "> This will restore default Aizen settings and clear custom server rules.",
            view=view,
            ephemeral=True,
        )

    # 39. /ai enable
    @ai_group.command(name="enable", description="Enable AI responses in a specific channel or server-wide.")
    @app_commands.describe(channel="Channel to enable AI in (leave blank for server-wide)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_enable(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        gid = interaction.guild.id
        current = self.bot.ai_mgr.get_server_config(gid)
        current["enabled"] = True
        if channel:
            allowed = list(current.get("allowed_channels", []))
            if channel.id not in allowed:
                allowed.append(channel.id)
            current["allowed_channels"] = allowed
            excluded = list(current.get("excluded_channels", []))
            if channel.id in excluded:
                excluded.remove(channel.id)
            current["excluded_channels"] = excluded
            await self.bot.ai_mgr.save_server_config(gid, current)
            await interaction.response.send_message(f"✅ Enabled AI responses in {channel.mention}.", ephemeral=True)
        else:
            await self.bot.ai_mgr.save_server_config(gid, current)
            await interaction.response.send_message("✅ Enabled AI responses server-wide.", ephemeral=True)

    # 40. /ai disable
    @ai_group.command(name="disable", description="Disable AI responses in a specific channel or server-wide.")
    @app_commands.describe(channel="Channel to disable AI in (leave blank for server-wide)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_disable(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        gid = interaction.guild.id
        current = self.bot.ai_mgr.get_server_config(gid)
        if channel:
            excluded = list(current.get("excluded_channels", []))
            if channel.id not in excluded:
                excluded.append(channel.id)
            current["excluded_channels"] = excluded
            allowed = list(current.get("allowed_channels", []))
            if channel.id in allowed:
                allowed.remove(channel.id)
            current["allowed_channels"] = allowed
            await self.bot.ai_mgr.save_server_config(gid, current)
            await interaction.response.send_message(f"✅ Disabled AI responses in {channel.mention}.", ephemeral=True)
        else:
            current["enabled"] = False
            await self.bot.ai_mgr.save_server_config(gid, current)
            await interaction.response.send_message("✅ Disabled AI responses server-wide.", ephemeral=True)

    # ─── LEGACY PREFIX COMMANDS PRESERVED ────────────────────────────────────

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
    @commands.command(name="aipersonality", aliases=["aipreset", "setpersonality"], help="Admin: Set the server's AI personality preset.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def aipersonality(self, ctx: CustomContext, *, preset: str = ""):
        gid = ctx.guild.id
        current = self.bot.ai_mgr.get_server_config(gid)
        presets = self.bot.ai_mgr.get_all_presets()
        if not preset.strip():
            lines = [f"• `{k}` — **{v['name']}**: {v['description']}" for k, v in presets.items()]
            return await ctx.send(
                f"**Available Personality Presets (10 Total):**\n"
                + "\n".join(lines)
                + f"\n\nUsage: `{ctx.prefix}aipersonality <preset_name>`"
            )

        clean = preset.lower().strip().replace(" ", "_").replace("-", "_")
        if clean not in presets:
            return await ctx.send(f"❌ Unknown preset `{preset}`. Use `{ctx.prefix}aipersonality` to view all 10 presets.")

        current["personality"] = clean
        await self.bot.ai_mgr.save_server_config(gid, current)
        await ctx.send(f"✅ Set AI personality to **{presets[clean]['name']}** for this server!")

    @commands.command(name="aiconfig", aliases=["aiview", "aisettings"], help="View current server AI personality configuration.")
    @commands.guild_only()
    async def aiconfig(self, ctx: CustomContext):
        gid = ctx.guild.id
        cfg = self.bot.ai_mgr.get_server_config(gid)
        p_name = cfg.get("personality", "aizen")
        presets = self.bot.ai_mgr.get_all_presets()
        disp = presets.get(p_name, {}).get("name", p_name.title())
        ch = f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "`All / Mentions`"
        status = "🟢 Enabled" if cfg.get("enabled", True) else "🔴 Disabled"
        embed = discord.Embed(title=f"🤖 AI Personality Configuration • {ctx.guild.name}", color=PURPLE)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Personality", value=disp, inline=True)
        embed.add_field(name="Channel", value=ch, inline=True)
        embed.add_field(name="Tone", value=str(cfg.get("tone", "composed")).title(), inline=True)
        embed.add_field(name="Humor", value=str(cfg.get("humor", "dry")).title(), inline=True)
        embed.add_field(name="Response Length", value=str(cfg.get("response_length", "balanced")).title(), inline=True)
        embed.set_footer(text=f"Use {ctx.prefix}aipersonality <name> to switch presets")
        await ctx.send(embed=embed)

    @commands.command(name="aitest", help="Test current AI personality with a test message.")
    @commands.guild_only()
    async def aitest(self, ctx: CustomContext, *, message: str = "Introduce yourself and say hello!"):
        await self._send_ai(ctx, message)

    @commands.command(name="ai", aliases=["chat", "askai", "aizenai"], help="Ask KYŌKA a question using Gemini AI.")
    async def ai(self, ctx: CustomContext, *, message: str = ""):
        await self._send_ai(ctx, message)

    @commands.command(name="aiclear", help="Clear your private KYŌKA conversation history.")
    async def aiclear(self, ctx: CustomContext):
        guild_id = ctx.guild.id if ctx.guild else 0
        self.history.pop((guild_id, ctx.channel.id, ctx.author.id), None)
        if hasattr(self.bot, "ai_mgr"):
            self.bot.ai_mgr.clear_user_history(guild_id, ctx.author.id)
        await ctx.send("🟣 Your conversation history for this channel and companions has been cleared.")

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


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content.strip():
            return
        # If channel is managed by CompanionAI, let CompanionAI handle it
        comp_cog = self.bot.get_cog("CompanionAI")
        if comp_cog and message.channel.id in getattr(comp_cog, "_channel_configs", {}):
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
