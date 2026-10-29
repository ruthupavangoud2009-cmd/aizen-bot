from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.ai_manager import AI_PERSONAS, resolve_persona
from src.managers.gif_manager import GIFManager
from src.security.adult_guard import authorize_adult, is_adult_authorized
from src.security.owner import is_primary_owner

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.CompanionAI")

# Aizen Aesthetics Palette
AIZEN_DARK = 0x1E1435
AIZEN_PURPLE = 0x2D1B69
AIZEN_INDIGO = 0x4C1D95
AIZEN_ACCENT = 0x7C3AED


class PersonaSelectMenu(discord.ui.Select):
    """Interactive selector for all 10 AI personalities."""

    def __init__(self, cog: CompanionAI, is_admin: bool = False) -> None:
        self.cog = cog
        self.is_admin = is_admin

        options = [
            discord.SelectOption(
                label=p["name"],
                value=p["key"],
                description=p["description"][:100],
                emoji=p["title"].split()[0] if p["title"] else "⛩️",
            )
            for p in AI_PERSONAS.values()
        ]
        super().__init__(
            placeholder="⛩️ Choose a personality to inspect or activate...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="kyoka:ai:persona_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_key = self.values[0]
        p_def = resolve_persona(selected_key)

        embed = discord.Embed(
            title=p_def["title"],
            description=f"**Persona Overview:**\n> {p_def['description']}\n\n**System Style:**\n```\n{p_def['prompt'][:350]}...\n```",
            color=p_def["color"],
        )
        embed.add_field(name="Category", value=f"`{p_def.get('category', '⛩️・AIZEN AI SYSTEM')}`", inline=True)
        embed.add_field(name="GIF Theme", value=f"`{p_def.get('gif_category', 'none')}`", inline=True)
        embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in p_def.get("aliases", [])) or "`none`", inline=True)
        embed.set_footer(text=f"Aizen Edition • Use +ai persona {selected_key} to activate")

        await interaction.response.edit_message(embed=embed, view=self.view)


class PersonaSelectView(discord.ui.View):
    """Container view for personality selector."""

    def __init__(self, cog: CompanionAI, is_admin: bool = False) -> None:
        super().__init__(timeout=120)
        self.add_item(PersonaSelectMenu(cog, is_admin=is_admin))


class CompanionAI(commands.Cog):
    """
    KYOKA 3.0 Aizen Edition — Professional AI Engine & Multi-Personality System.
    Includes 10 rich personas, automatic chat channels, unified prefix & slash interfaces,
    instant diagnostics, and fast asynchronous execution.
    """
    category = "⛩️・AIZEN AI SYSTEM"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_mgr = GIFManager()
        # channel_id -> config dict
        self._channel_configs: dict[int, dict[str, Any]] = {}
        self._channel_locks: dict[int, asyncio.Lock] = {}
        self._channel_last_time: dict[int, float] = {}
        self._user_last_time: dict[int, float] = {}
        self._own_session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        session = getattr(self.bot, "session", None)
        if session is not None and not session.closed:
            return session
        if self._own_session is None or self._own_session.closed:
            self._own_session = aiohttp.ClientSession()
        return self._own_session

    async def cog_unload(self) -> None:
        if self._own_session and not self._own_session.closed:
            try:
                await self._own_session.close()
            except Exception:
                pass

    async def cog_load(self) -> None:
        """Load persistent automatic AI channel configurations on startup."""
        try:
            configs = await self.bot.db.get_all_ai_channels()
            self._channel_configs.clear()
            for row in configs:
                cid = int(row["channel_id"])
                self._channel_configs[cid] = row
            logger.info(f"Loaded {len(self._channel_configs)} automatic AI channel configuration(s).")
        except Exception as e:
            logger.warning(f"Could not load AI channel cache: {e}")

    # ─── PERMISSION & ACCESS HELPERS ─────────────────────────────────────────

    def _is_admin_or_owner(self, member_or_user: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
        if is_primary_owner(member_or_user.id):
            return True
        if isinstance(member_or_user, discord.Member):
            return member_or_user.guild_permissions.administrator or member_or_user.guild_permissions.manage_guild
        return False

    # ─── CHANNEL CONFIGURATION LOGIC ─────────────────────────────────────────

    async def _setup_channel(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        persona: str,
        user_id: int,
        mention_only: bool = False,
        send_gifs: bool = True,
        cooldown_seconds: int = 2,
    ) -> discord.Embed:
        p_def = resolve_persona(persona)

        # Check bot permissions in target channel
        bot_member = guild.me
        perms = channel.permissions_for(bot_member)
        missing = []
        if not perms.send_messages:
            missing.append("Send Messages")
        if not perms.embed_links:
            missing.append("Embed Links")
        if not perms.read_messages:
            missing.append("View Channel")

        if missing:
            return discord.Embed(
                title="⚠️ Missing Permissions",
                description=f"I need the following permissions in {channel.mention}:\n" + "\n".join(f"• `{p}`" for p in missing),
                color=discord.Color.red(),
            )

        persona_clean = persona.lower().strip()
        # Upsert in database
        await self.bot.db.set_ai_channel(
            guild_id=guild.id,
            channel_id=channel.id,
            persona=persona_clean,
            enabled=True,
            mention_only=mention_only,
            cooldown_seconds=cooldown_seconds,
            send_gifs=send_gifs,
            configured_by=user_id,
        )

        # Update in-memory cache
        self._channel_configs[channel.id] = {
            "guild_id": guild.id,
            "channel_id": channel.id,
            "persona": persona_clean,
            "enabled": True,
            "mention_only": mention_only,
            "cooldown_seconds": cooldown_seconds,
            "send_gifs": send_gifs,
            "configured_by": user_id,
        }

        mode_str = "Mention & Reply Only" if mention_only else "Natural Chat (All Messages)"
        embed = discord.Embed(
            title="⛩️ Automatic AI Channel Configured",
            description=f"**{p_def['name']}** is now active in {channel.mention}!\nMembers can converse naturally without typing command prefixes.",
            color=p_def["color"],
        )
        embed.add_field(name="Active Persona", value=f"`{p_def['name']}`", inline=True)
        embed.add_field(name="Trigger Mode", value=f"`{mode_str}`", inline=True)
        embed.add_field(name="User Throttle", value=f"`{cooldown_seconds}s per user`", inline=True)
        embed.add_field(name="Reaction GIFs", value=f"`{'Enabled' if send_gifs else 'Disabled'}`", inline=True)
        embed.set_footer(text=f"Aizen Edition • Server: {guild.name}")
        return embed

    async def _status_channel(self, guild: discord.Guild, channel: discord.TextChannel) -> discord.Embed:
        cfg = self._channel_configs.get(channel.id)
        if not cfg:
            server_cfg = self.bot.ai_mgr.get_server_config(guild.id)
            p_def = resolve_persona(server_cfg.get("personality", "aizen"))
            embed = discord.Embed(
                title=f"⛩️ AI System Status — #{channel.name}",
                description=f"{channel.mention} does not have a dedicated automatic AI channel configuration.\n"
                            f"Using global server default personality: **{p_def['name']}**.",
                color=AIZEN_PURPLE,
            )
            embed.add_field(name="Server Default", value=f"`{p_def['name']}`", inline=True)
            embed.add_field(name="Channel Setup", value=f"Run `+ai setup {channel.mention}` to enable natural chat.", inline=False)
            return embed

        persona = cfg.get("persona", "aizen")
        p_def = resolve_persona(persona)
        status_str = "🟢 Active" if cfg.get("enabled", True) else "🔴 Disabled"
        mode_str = "Mention Only" if cfg.get("mention_only", False) else "All Normal Messages"

        embed = discord.Embed(
            title=f"⛩️ AI Channel Status — #{channel.name}",
            description=f"Configuration for {channel.mention}:",
            color=p_def["color"],
        )
        embed.add_field(name="Status", value=f"`{status_str}`", inline=True)
        embed.add_field(name="Active Persona", value=f"`{p_def['name']}`", inline=True)
        embed.add_field(name="Trigger Mode", value=f"`{mode_str}`", inline=True)
        embed.add_field(name="Cooldown", value=f"`{cfg.get('cooldown_seconds', 2)}s`", inline=True)
        embed.add_field(name="GIFs Allowed", value=f"`{'Yes' if cfg.get('send_gifs', True) else 'No'}`", inline=True)
        return embed

    async def _disable_channel(self, guild: discord.Guild, channel: discord.TextChannel) -> discord.Embed:
        cfg = self._channel_configs.get(channel.id)
        if not cfg:
            return discord.Embed(
                title="ℹ️ Channel Not Configured",
                description=f"{channel.mention} does not have an automatic AI persona active.",
                color=AIZEN_DARK,
            )

        await self.bot.db.disable_ai_channel(guild.id, channel.id)
        if channel.id in self._channel_configs:
            self._channel_configs[channel.id]["enabled"] = False

        return discord.Embed(
            title="⏸️ AI Channel Disabled",
            description=f"Automatic AI responses have been paused in {channel.mention}.",
            color=AIZEN_DARK,
        )

    async def _remove_channel(self, guild: discord.Guild, channel: discord.TextChannel) -> discord.Embed:
        cfg = self._channel_configs.get(channel.id)
        if not cfg:
            return discord.Embed(
                title="ℹ️ Channel Not Configured",
                description=f"{channel.mention} does not have an automatic AI persona active.",
                color=AIZEN_DARK,
            )

        await self.bot.db.remove_ai_channel(guild.id, channel.id)
        self._channel_configs.pop(channel.id, None)

        return discord.Embed(
            title="🗑️ AI Channel Removed",
            description=f"Automatic AI companion configuration has been removed from {channel.mention}.",
            color=AIZEN_DARK,
        )

    # ─── DIRECT RESPONSE GENERATION (FAST & CONCURRENT) ──────────────────────

    async def _handle_direct_response(
        self,
        ctx: CustomContext,
        persona_key: str,
        prompt: str,
    ) -> None:
        if not prompt or not prompt.strip():
            p_def = resolve_persona(persona_key)
            await ctx.send(f"💬 Tell me what you seek. Usage: `{ctx.prefix}ai <message>` or `{ctx.prefix}{p_def['key']} <message>`")
            return

        p_def = resolve_persona(persona_key)

        # Check adult authorization for special persona
        if p_def["key"] == "special":
            authorized = await authorize_adult(ctx, action_name="aispecial")
            if not authorized:
                return

        guild_id = ctx.guild.id if ctx.guild else 0
        server_name = ctx.guild.name if ctx.guild else "Direct Message"
        user_id = ctx.author.id

        session = self._get_session()

        # Concurrently launch AI text generation and optional GIF fetch
        should_gif = (
            random.random() < 0.28
            or any(kw in prompt.lower() for kw in ("gif", "show me", "hug", "kiss", "look", "smile", "tease", "roast", "burn"))
        ) and bool(p_def.get("gif_category"))

        async def _fetch_gif() -> str | None:
            if not should_gif:
                return None
            try:
                return await asyncio.wait_for(
                    self.gif_mgr.get_action_gif(p_def["gif_category"], session=session),
                    timeout=2.0,
                )
            except Exception:
                return None

        reply: str = ""
        gif_url: str | None = None

        try:
            async with ctx.typing():
                ai_coro = self.bot.ai_mgr.generate_persona_reply(
                    session=session,
                    guild_id=guild_id,
                    user_id=user_id,
                    persona_key=p_def["key"],
                    prompt=prompt.strip(),
                    server_name=server_name,
                    enforce_cooldown=True,
                )
                # Run AI and GIF concurrently so GIF never adds delay
                reply, gif_url = await asyncio.gather(ai_coro, _fetch_gif())

        except RuntimeError as e:
            reply = self.bot.ai_mgr.get_smart_fallback(prompt, p_def["key"])
            gif_url = None
        except Exception as e:
            logger.error(f"Error generating {p_def['key']} reply: {e}", exc_info=True)
            reply = self.bot.ai_mgr.get_smart_fallback(prompt, p_def["key"])
            gif_url = None

        if p_def["key"] == "normal" and not gif_url:
            # For natural person persona, chat in clean plain text like a real friend rather than a heavy embed
            await ctx.send(reply[:1950])
            return

        embed = discord.Embed(
            title=p_def["title"],
            description=reply[:4000],
            color=p_def["color"],
        )
        embed.set_footer(
            text=f"Aizen AI Engine • Use {ctx.prefix}ai reset to clear memory",
            icon_url=ctx.author.display_avatar.url,
        )
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(embed=embed)

    # ─── AUTOMATIC AI CHANNEL LISTENER ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Listens to ordinary messages in configured channels or when mentioned/replied to,
        and replies naturally like a real person without requiring 'hey' or any formal wake words.
        """
        # 1. Ignore bots, webhooks, empty messages
        if message.author.bot or message.webhook_id or not message.content.strip():
            return

        # 2. Prevent self-responses
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        # 3. Check if in DMs, mentioned, replied to, addressed by name, or if channel is configured
        is_dm = message.guild is None
        is_mentioned = bool(self.bot.user and (
            self.bot.user in message.mentions 
            or f"<@{self.bot.user.id}>" in message.content 
            or f"<@!{self.bot.user.id}>" in message.content
        ))
        is_reply_to_bot = False
        if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
            if self.bot.user and message.reference.resolved.author.id == self.bot.user.id:
                is_reply_to_bot = True

        clean_start = message.content.strip().lower()
        starts_with_bot_name = any(clean_start.startswith(p) for p in ("kyoka ", "kyoka,", "kyoka:", "aizen ", "aizen,", "aizen:"))

        channel_id = message.channel.id
        config = self._channel_configs.get(channel_id) if message.guild else None
        is_configured_channel = bool(config and config.get("enabled", True))

        # Drop message if neither in DM, nor mentioned, nor replied to bot, nor directly addressed, nor in configured channel
        if not (is_dm or is_mentioned or is_reply_to_bot or starts_with_bot_name or is_configured_channel):
            return

        # 4. Skip command messages
        try:
            ctx = await self.bot.get_context(message)
            if ctx.valid and ctx.command is not None:
                return
        except Exception:
            pass

        # 5. Determine settings: configured channel settings or natural human fallback
        if is_configured_channel and config:
            mention_only = config.get("mention_only", False)
            if mention_only and not (is_dm or is_mentioned or is_reply_to_bot or starts_with_bot_name):
                return
            persona_key = config.get("persona", "normal")
            send_gifs = config.get("send_gifs", True)
            cooldown_sec = config.get("cooldown_seconds", 2)
        else:
            persona_key = "normal"
            send_gifs = False
            cooldown_sec = 2

        p_def = resolve_persona(persona_key)

        # 6. Adult check for special persona
        if p_def["key"] == "special":
            if not is_adult_authorized(message.author.id):
                return

        # 7. Cooldown & Concurrency limits
        now = time.monotonic()
        cooldown_val = getattr(getattr(self.bot, "ai_mgr", None), "channel_cooldown_default", 2.0)
        if not isinstance(cooldown_val, (int, float)):
            cooldown_val = 2.0
        last_ch_time = self._channel_last_time.get(channel_id, 0.0)
        last_usr_time = self._user_last_time.get(message.author.id, 0.0)

        # User channel throttle
        if now - last_usr_time < cooldown_val:
            return
        # Channel-wide throttle (exempt if in DM, explicitly mentioned, replied, or addressed by name)
        is_direct_chat = is_dm or is_mentioned or is_reply_to_bot or starts_with_bot_name
        if now - last_ch_time < cooldown_sec and not is_direct_chat:
            return

        self._user_last_time[message.author.id] = now
        self._channel_last_time[channel_id] = now

        # Per-channel concurrency guard
        lock = self._channel_locks.setdefault(channel_id, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), timeout=4.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return

        try:
            session = self._get_session()

            # Strip bot mention tag and leading casual triggers like "hey kyoka,"
            prompt = message.content
            if self.bot.user:
                prompt = re.sub(rf"<@!?{self.bot.user.id}>", "", prompt).strip()
            prompt = re.sub(r"^(hey|hi|yo|hello)?\s*(kyoka|aizen|bot)[,:\s]*", "", prompt, flags=re.IGNORECASE).strip()
            if not prompt:
                prompt = "What's up?"

            should_gif = send_gifs and (
                random.random() < 0.22
                or any(kw in prompt.lower() for kw in ("gif", "show me", "hug", "kiss", "look", "smile", "tease"))
            ) and bool(p_def.get("gif_category"))

            async def _fetch_auto_gif() -> str | None:
                if not should_gif:
                    return None
                try:
                    return await asyncio.wait_for(
                        self.gif_mgr.get_action_gif(p_def["gif_category"], session=session),
                        timeout=1.8,
                    )
                except Exception:
                    return None

            try:
                async with message.channel.typing():
                    ai_task = self.bot.ai_mgr.generate_persona_reply(
                        session=session,
                        guild_id=message.guild.id if message.guild else 0,
                        user_id=message.author.id,
                        persona_key=p_def["key"],
                        prompt=prompt[:3000],
                        server_name=message.guild.name if message.guild else "Direct Message",
                        enforce_cooldown=False,
                    )
                    reply, gif_url = await asyncio.gather(ai_task, _fetch_auto_gif())
            except Exception as e:
                logger.debug(f"Auto AI primary API note in #{getattr(message.channel, 'name', 'DM')}: {e}")
                reply = self.bot.ai_mgr.get_smart_fallback(prompt, p_def["key"])
                gif_url = None

            embed: discord.Embed | None = None
            if gif_url:
                embed = discord.Embed(color=p_def["color"])
                embed.set_image(url=gif_url)

            # Chunk into Discord limit (<= 1950 chars)
            chunks = [reply[i : i + 1950] for i in range(0, len(reply), 1950)]
            for idx, chunk in enumerate(chunks):
                is_last = idx == len(chunks) - 1
                try:
                    await message.reply(
                        chunk,
                        embed=embed if is_last else None,
                        mention_author=False,
                        allowed_mentions=discord.AllowedMentions(
                            everyone=False,
                            roles=False,
                            users=True,
                            replied_user=True,
                        ),
                    )
                except Exception as e:
                    logger.debug(f"Failed to deliver auto AI reply: {e}")
                    break
        finally:
            if lock.locked():
                lock.release()

    # ─── MASTER UNIFIED PREFIX GROUP: +ai ────────────────────────────────────

    @commands.group(
        name="ai",
        aliases=["chat", "ask", "askai", "aizenai"],
        invoke_without_command=True,
        help="Converse with KYOKA like a normal friend, or manage the AI system.",
    )
    async def ai(self, ctx: CustomContext, *, message: str = "") -> None:
        """Master AI command: ask a question or explore personalities."""
        if ctx.invoked_subcommand is None:
            if not message.strip():
                # Display overview and interactive personality selector
                embed = discord.Embed(
                    title="⛩️ KYOKA 3.0 — AIZEN AI SYSTEM",
                    description=(
                        "Welcome to the master AI console. Select a personality below to inspect its style, "
                        "or chat directly with KYOKA.\n\n"
                        f"**Direct Conversation:**\n"
                        f"`{ctx.prefix}ai <message>` — Chat using current persona.\n"
                        f"`{ctx.prefix}ai persona <name>` — Switch active personality.\n\n"
                        f"**Personalities & Browsing:**\n"
                        f"`{ctx.prefix}ai personalities` — Browse all 10 distinct personalities.\n\n"
                        f"**Channel Management (Admin):**\n"
                        f"`{ctx.prefix}ai setup [#channel] [persona]` — Enable natural automatic chat.\n"
                        f"`{ctx.prefix}ai status` — View active AI channel configuration.\n"
                        f"`{ctx.prefix}ai disable` — Pause automatic AI in this channel.\n"
                        f"`{ctx.prefix}ai remove` — Remove AI configuration from this channel.\n"
                        f"`{ctx.prefix}ai settings [mention_only=on/off] [gifs=on/off]` — Adjust settings.\n\n"
                        f"**Memory & Diagnostics:**\n"
                        f"`{ctx.prefix}ai reset` — Clear your conversation memory.\n"
                        f"`{ctx.prefix}aidiag` — Run real-time AI provider diagnostics."
                    ),
                    color=AIZEN_PURPLE,
                )
                is_admin = self._is_admin_or_owner(ctx.author, ctx.guild)
                view = PersonaSelectView(self, is_admin=is_admin)
                await ctx.send(embed=embed, view=view)
                return

            # Determine active persona for this channel or server
            persona_to_use = "normal"
            if ctx.channel.id in self._channel_configs:
                persona_to_use = self._channel_configs[ctx.channel.id].get("persona", "normal")
            elif ctx.guild:
                server_cfg = self.bot.ai_mgr.get_server_config(ctx.guild.id)
                persona_to_use = server_cfg.get("personality", "normal")

            await self._handle_direct_response(ctx=ctx, persona_key=persona_to_use, prompt=message)

    @ai.command(name="personalities", aliases=["list", "personas"])
    async def ai_personalities(self, ctx: CustomContext) -> None:
        """Browse all 10 distinct AI personalities with interactive dropdown."""
        embed = discord.Embed(
            title="⛩️ Available AI Personalities (10 Total)",
            description="KYOKA 3.0 offers 10 specialized conversational personas. Select any from the menu below to preview:",
            color=AIZEN_PURPLE,
        )
        for p in AI_PERSONAS.values():
            aliases = f" (aliases: {', '.join(p['aliases'])})" if p.get("aliases") else ""
            embed.add_field(
                name=f"{p['title']}{aliases}",
                value=f"> {p['description']}",
                inline=False,
            )
        embed.set_footer(text=f"Use {ctx.prefix}ai persona <name> to activate")
        view = PersonaSelectView(self, is_admin=self._is_admin_or_owner(ctx.author, ctx.guild))
        await ctx.send(embed=embed, view=view)

    @ai.command(name="persona", aliases=["setpersona"])
    @commands.guild_only()
    async def ai_persona(self, ctx: CustomContext, *, name: str = "") -> None:
        """Select or switch the active personality for this channel or server."""
        if not name.strip():
            return await ctx.send(f"Usage: `{ctx.prefix}ai persona <name>`. Run `{ctx.prefix}ai personalities` to see choices.")

        p_def = resolve_persona(name)
        if p_def["key"] == "special":
            authorized = await authorize_adult(ctx, action_name="aispecial")
            if not authorized:
                return

        # If user is admin and channel is configured, update channel
        if self._is_admin_or_owner(ctx.author, ctx.guild):
            if ctx.channel.id in self._channel_configs:
                self._channel_configs[ctx.channel.id]["persona"] = p_def["key"]
                await self.bot.db.set_ai_channel(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id,
                    persona=p_def["key"],
                    enabled=self._channel_configs[ctx.channel.id].get("enabled", True),
                    mention_only=self._channel_configs[ctx.channel.id].get("mention_only", False),
                    cooldown_seconds=self._channel_configs[ctx.channel.id].get("cooldown_seconds", 2),
                    send_gifs=self._channel_configs[ctx.channel.id].get("send_gifs", True),
                    configured_by=ctx.author.id,
                )
                return await ctx.send(f"⛩️ Activated **{p_def['name']}** for {ctx.channel.mention}!")
            else:
                server_cfg = self.bot.ai_mgr.get_server_config(ctx.guild.id)
                server_cfg["personality"] = p_def["key"]
                await self.bot.ai_mgr.save_server_config(ctx.guild.id, server_cfg)
                return await ctx.send(f"⛩️ Set server default AI personality to **{p_def['name']}**!")

        await ctx.send(f"Selected **{p_def['name']}**. Use `{ctx.prefix}ai <message>` to chat!")

    @ai.command(name="setup")
    @commands.guild_only()
    async def ai_setup(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        persona: str = "aizen",
    ) -> None:
        """Admin: Configure automatic natural AI chat in a channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required to configure AI channels.")
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            return await ctx.send("❌ Target must be a standard text channel.")

        p_def = resolve_persona(persona)
        if p_def["key"] == "special":
            authorized = await authorize_adult(ctx, action_name="aispecial_setup")
            if not authorized:
                return

        embed = await self._setup_channel(ctx.guild, target, persona=p_def["key"], user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @ai.command(name="status")
    @commands.guild_only()
    async def ai_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """View AI configuration for a channel."""
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @ai.command(name="disable")
    @commands.guild_only()
    async def ai_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Pause automatic AI responses in a channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @ai.command(name="remove")
    @commands.guild_only()
    async def ai_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Permanently remove automatic AI configuration from a channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @ai.command(name="reset")
    async def ai_reset(self, ctx: CustomContext, scope: str = "") -> None:
        """Clear your private conversation memory (or admin: +ai reset server)."""
        guild_id = ctx.guild.id if ctx.guild else 0
        if scope.lower() in ("server", "--server", "all") and ctx.guild:
            if not self._is_admin_or_owner(ctx.author, ctx.guild):
                return await ctx.send("❌ Administrator permissions required to reset server configuration.")
            await self.bot.ai_mgr.reset_server_config(ctx.guild.id)
            return await ctx.send("⛩️ Reset server AI settings to defaults.")

        cleared = self.bot.ai_mgr.clear_user_history(guild_id, ctx.author.id)
        await ctx.send("✨ Your conversation history across all AI personas has been cleared.")

    @ai.command(name="settings")
    @commands.guild_only()
    async def ai_settings(self, ctx: CustomContext, *, args: str = "") -> None:
        """Admin: View or adjust channel settings (mention_only=on/off, gifs=on/off, cooldown=N)."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions required.")

        target = ctx.channel
        cfg = self._channel_configs.get(target.id)
        if not cfg:
            return await ctx.send(f"{target.mention} is not an AI channel. Use `{ctx.prefix}ai setup` first.")

        if not args.strip():
            embed = await self._status_channel(ctx.guild, target)
            embed.set_footer(text=f"Update with {ctx.prefix}ai settings mention_only=on gifs=off cooldown=3")
            return await ctx.send(embed=embed)

        # Parse key=value pairs
        for pair in args.split():
            if "=" in pair:
                k, v = pair.split("=", 1)
                k = k.lower().strip()
                v = v.lower().strip()
                if k in ("mention", "mention_only"):
                    cfg["mention_only"] = v in ("on", "true", "yes", "1")
                elif k in ("gifs", "gif", "send_gifs"):
                    cfg["send_gifs"] = v in ("on", "true", "yes", "1")
                elif k in ("cooldown", "throttle"):
                    try:
                        cfg["cooldown_seconds"] = max(1, min(30, int(v)))
                    except ValueError:
                        pass

        await self.bot.db.set_ai_channel(
            guild_id=ctx.guild.id,
            channel_id=target.id,
            persona=cfg.get("persona", "aizen"),
            enabled=cfg.get("enabled", True),
            mention_only=cfg.get("mention_only", False),
            cooldown_seconds=cfg.get("cooldown_seconds", 2),
            send_gifs=cfg.get("send_gifs", True),
            configured_by=ctx.author.id,
        )
        await ctx.send("✅ AI channel settings updated.")

    # ─── PRESERVED DIRECT COMMANDS (+aigf, +aibaddie, +aispecial) ────────────

    @commands.group(name="aigf", aliases=["girlfriend", "gf"], invoke_without_command=True, help="Chat with AI Girlfriend.")
    async def aigf(self, ctx: CustomContext, *, message: str = "") -> None:
        if ctx.invoked_subcommand is None:
            await self._handle_direct_response(ctx=ctx, persona_key="girlfriend", prompt=message)

    @aigf.command(name="setup")
    @commands.guild_only()
    async def aigf_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._setup_channel(ctx.guild, target, persona="girlfriend", user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aigf.command(name="status")
    @commands.guild_only()
    async def aigf_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aigf.command(name="disable")
    @commands.guild_only()
    async def aigf_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aigf.command(name="remove")
    @commands.guild_only()
    async def aigf_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @commands.group(name="aibaddie", aliases=["baddie"], invoke_without_command=True, help="Chat with AI Baddie.")
    async def aibaddie(self, ctx: CustomContext, *, message: str = "") -> None:
        if ctx.invoked_subcommand is None:
            await self._handle_direct_response(ctx=ctx, persona_key="baddie", prompt=message)

    @aibaddie.command(name="setup")
    @commands.guild_only()
    async def aibaddie_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._setup_channel(ctx.guild, target, persona="baddie", user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aibaddie.command(name="status")
    @commands.guild_only()
    async def aibaddie_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aibaddie.command(name="disable")
    @commands.guild_only()
    async def aibaddie_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aibaddie.command(name="remove")
    @commands.guild_only()
    async def aibaddie_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @commands.group(name="aispecial", aliases=["specialai", "spicyai"], invoke_without_command=True, help="Chat with AI Special Companion [Restricted].")
    async def aispecial(self, ctx: CustomContext, *, message: str = "") -> None:
        authorized = await authorize_adult(ctx, action_name="aispecial")
        if not authorized:
            return
        if ctx.invoked_subcommand is None:
            await self._handle_direct_response(ctx=ctx, persona_key="special", prompt=message)

    @aispecial.command(name="setup")
    @commands.guild_only()
    async def aispecial_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        authorized = await authorize_adult(ctx, action_name="aispecial_setup")
        if not authorized:
            return
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._setup_channel(ctx.guild, target, persona="special", user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aispecial.command(name="status")
    @commands.guild_only()
    async def aispecial_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        authorized = await authorize_adult(ctx, action_name="aispecial_status")
        if not authorized:
            return
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aispecial.command(name="disable")
    @commands.guild_only()
    async def aispecial_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        authorized = await authorize_adult(ctx, action_name="aispecial_disable")
        if not authorized:
            return
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aispecial.command(name="remove")
    @commands.guild_only()
    async def aispecial_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        authorized = await authorize_adult(ctx, action_name="aispecial_remove")
        if not authorized:
            return
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    # ─── CHANNEL SHORTCUT: +aichannel ────────────────────────────────────────

    @commands.group(name="aichannel", aliases=["setcompanionchannel", "aichatsetup"], invoke_without_command=True)
    @commands.guild_only()
    async def aichannel(self, ctx: CustomContext) -> None:
        """Manage automatic AI channels."""
        embed = discord.Embed(
            title="⛩️ Automatic AI Channel Management",
            description=(
                f"**Setup Channel:**\n`{ctx.prefix}ai setup [#channel] [persona]`\n\n"
                f"**Shortcuts:**\n"
                f"`{ctx.prefix}aigf setup [#channel]`\n"
                f"`{ctx.prefix}aibaddie setup [#channel]`\n"
                f"`{ctx.prefix}aispecial setup [#channel]`"
            ),
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed)

    @aichannel.command(name="setup")
    @commands.guild_only()
    async def aichannel_setup(self, ctx: CustomContext, persona: str = "aizen", channel: Optional[discord.TextChannel] = None) -> None:
        await self.ai_setup(ctx, channel=channel, persona=persona)

    @aichannel.command(name="status")
    @commands.guild_only()
    async def aichannel_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        await self.ai_status(ctx, channel=channel)

    @aichannel.command(name="disable")
    @commands.guild_only()
    async def aichannel_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        await self.ai_disable(ctx, channel=channel)

    @aichannel.command(name="remove")
    @commands.guild_only()
    async def aichannel_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        await self.ai_remove(ctx, channel=channel)

    # ─── MEMORY CLEAR: +aiclearcompanion ────────────────────────────────────

    @commands.command(name="aiclearcompanion", aliases=["clearcompanion", "resetcompanion"])
    async def aiclearcompanion(self, ctx: CustomContext) -> None:
        """Reset conversation memory for all companion personas."""
        await self.ai_reset(ctx)

    # ─── PERFORMANCE DIAGNOSTICS: +aidiag ────────────────────────────────────

    @commands.command(name="aidiag", aliases=["aimodel", "aidebug"], help="Owner/Admin diagnostic: test AI connectivity and latency.")
    async def aidiag(self, ctx: CustomContext) -> None:
        """Show active provider, model, latency, errors, and reachability without exposing secrets."""
        session = self._get_session()

        async with ctx.typing():
            diag = await self.bot.ai_mgr.get_diagnostics(session)

        is_healthy = diag.get("provider_reachable", False)
        embed = discord.Embed(
            title="⛩️ Kyoka 3.0 — AI System Diagnostics",
            color=discord.Color.green() if is_healthy else discord.Color.red(),
        )
        embed.add_field(name="Provider", value=f"`{diag.get('provider')}`", inline=True)
        embed.add_field(name="Active Model", value=f"`{diag.get('active_model')}`", inline=True)
        embed.add_field(name="Provider Health", value="`🟢 Reachable (200 OK)`" if is_healthy else "`🔴 Unreachable`", inline=True)

        last_lat = diag.get("last_latency_ms")
        avg_lat = diag.get("average_latency_ms")
        lat_text = f"`{last_lat} ms`" if last_lat else "`No samples yet`"
        avg_text = f"`{avg_lat} ms` (rolling avg)" if avg_lat else "`N/A`"

        embed.add_field(name="Recent Latency", value=lat_text, inline=True)
        embed.add_field(name="Average Latency", value=avg_text, inline=True)

        last_succ = diag.get("last_success_time")
        succ_text = f"<t:{int(last_succ)}:R>" if last_succ else "`None in current session`"
        embed.add_field(name="Last Success", value=succ_text, inline=True)

        embed.add_field(name="Total Requests", value=f"`{diag.get('total_requests', 0)}`", inline=True)
        embed.add_field(name="Error Count", value=f"`{diag.get('error_count', 0)}`", inline=True)
        embed.add_field(name="Timeout Count", value=f"`{diag.get('timeout_count', 0)}`", inline=True)

        db_status = "`🟢 Connected`" if diag.get("database_reachable") else "`🔴 Disconnected`"
        embed.add_field(name="Database", value=db_status, inline=True)
        embed.add_field(name="Active Channels", value=f"`{len(self._channel_configs)} active`", inline=True)
        embed.add_field(
            name="Concurrency",
            value=f"`{diag.get('active_concurrent', 0)} / {diag.get('max_concurrent', 5)} active`",
            inline=True,
        )

        embed.set_footer(text="Aizen Edition • Performance Metrics (Secrets Redacted)")
        await ctx.send(embed=embed)

    # Note: Slash command group /ai is maintained in AIInteractions with its standard 6 subcommands
    # while /companion is maintained below for dedicated companion personas.


    # ─── PRESERVED COMPANION SLASH COMMAND GROUP: /companion ─────────────────

    companion_group = app_commands.Group(
        name="companion",
        description="KYOKA 3.0 AI Companion System (Preserved Compatibility)",
    )

    @companion_group.command(name="girlfriend", description="Chat with your warm AI Girlfriend.")
    async def slash_gf(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.response.defer()
        ctx = await self.bot.get_context(interaction)
        await self._handle_direct_response(ctx=ctx, persona_key="girlfriend", prompt=message)

    @companion_group.command(name="baddie", description="Chat with your witty AI Baddie.")
    async def slash_baddie(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.response.defer()
        ctx = await self.bot.get_context(interaction)
        await self._handle_direct_response(ctx=ctx, persona_key="baddie", prompt=message)

    @companion_group.command(name="special", description="Chat with the adult-humor AI companion [Restricted].")
    async def slash_special(self, interaction: discord.Interaction, message: str) -> None:
        authorized = await authorize_adult(interaction, action_name="aispecial")
        if not authorized:
            return
        await interaction.response.defer()
        ctx = await self.bot.get_context(interaction)
        await self._handle_direct_response(ctx=ctx, persona_key="special", prompt=message)

    # ─── PREFIX COMMAND GROUP ────────────────────────────────────────────────

    @commands.group(name="companion", invoke_without_command=True)
    async def prefix_companion(self, ctx: CustomContext) -> None:
        """AI Companion System via prefix."""
        p = ctx.prefix
        await ctx.send(
            f"**KYOKA AI Companions**\n"
            f"> `{p}companion girlfriend <message>` — Chat with AI Girlfriend\n"
            f"> `{p}companion baddie <message>` — Chat with AI Baddie\n"
            f"> `{p}companion special <message>` — Chat with AI Special companion\n"
            f"> `{p}companion clear` — Clear conversation memory"
        )

    @prefix_companion.command(name="girlfriend", aliases=["gf"])
    async def prefix_gf(self, ctx: CustomContext, *, message: str) -> None:
        await self._handle_direct_response(ctx=ctx, persona_key="girlfriend", prompt=message)

    @prefix_companion.command(name="baddie")
    async def prefix_baddie(self, ctx: CustomContext, *, message: str) -> None:
        await self._handle_direct_response(ctx=ctx, persona_key="baddie", prompt=message)

    @prefix_companion.command(name="special")
    async def prefix_special(self, ctx: CustomContext, *, message: str) -> None:
        authorized = await authorize_adult(ctx, action_name="aispecial")
        if not authorized:
            return
        await self._handle_direct_response(ctx=ctx, persona_key="special", prompt=message)

    @prefix_companion.command(name="clear", aliases=["reset"])
    async def prefix_clear(self, ctx: CustomContext) -> None:
        self.bot.ai_mgr.clear_user_history(ctx.author.id)
        await ctx.send("🧹 Your conversation history with AI companions has been cleared.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(CompanionAI(bot))
