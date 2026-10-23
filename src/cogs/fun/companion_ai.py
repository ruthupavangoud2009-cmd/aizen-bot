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
from src.managers.gif_manager import GIFManager
from src.security.adult_guard import authorize_adult, is_adult_authorized
from src.security.owner import is_primary_owner

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.CompanionAI")

# Aizen-inspired Palette
AIZEN_DARK = 0x1E1435
AIZEN_PURPLE = 0x2D1B69
AIZEN_INDIGO = 0x4C1D95
PINK = 0xEC4899
PURPLE = 0x7C3AED
ROSE = 0xF43F5E

PERSONA_METADATA = {
    "aigf": {
        "title": "🌸 Kyoka — AI Girlfriend",
        "name": "AI Girlfriend",
        "color": PINK,
        "gif_category": "romance",
        "description": "Warm, affectionate, caring, and playful fictional companion.",
    },
    "aibaddie": {
        "title": "💅 Kyoka — AI Baddie",
        "name": "AI Baddie",
        "color": PURPLE,
        "gif_category": "flex",
        "description": "Confident, witty, sassy, stylish, and playful companion.",
    },
    "aispecial": {
        "title": "😈 Kyoka — Special Adult Companion [Restricted]",
        "name": "Special Adult Companion",
        "color": ROSE,
        "gif_category": "adultreaction",
        "description": "Cheeky, suggestive adult humor strictly guarded by ADULT_COMMAND_ALLOWLIST.",
    },
}


class CompanionAI(commands.Cog):
    """
    KYOKA 3.0 Aizen Edition — Automatic AI Companion Channels & Personas.
    Supports AI Girlfriend, AI Baddie, and Special Companion with automatic channel participation.
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

    # ─── HELPER: PERMISSION CHECK ─────────────────────────────────────────────

    def _is_admin_or_owner(self, member_or_user: discord.Member | discord.User, guild: discord.Guild | None) -> bool:
        if is_primary_owner(member_or_user.id):
            return True
        if isinstance(member_or_user, discord.Member):
            return member_or_user.guild_permissions.administrator or member_or_user.guild_permissions.manage_guild
        return False

    # ─── HELPER: CONFIGURATION LOGIC ──────────────────────────────────────────

    async def _setup_channel(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        persona: str,
        user_id: int,
        mention_only: bool = False,
        send_gifs: bool = True,
        cooldown_seconds: int = 3,
    ) -> discord.Embed:
        meta = PERSONA_METADATA.get(persona, PERSONA_METADATA["aigf"])

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
            embed = discord.Embed(
                title="⚠️ Missing Permissions",
                description=f"I need the following permissions in {channel.mention}:\n" + "\n".join(f"• `{p}`" for p in missing),
                color=discord.Color.red(),
            )
            return embed

        # Upsert in database
        await self.bot.db.set_ai_channel(
            guild_id=guild.id,
            channel_id=channel.id,
            persona=persona,
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
            "persona": persona,
            "enabled": True,
            "mention_only": mention_only,
            "cooldown_seconds": cooldown_seconds,
            "send_gifs": send_gifs,
            "configured_by": user_id,
        }

        mode_str = "Mention & Reply Only" if mention_only else "Automatic (All Messages)"
        embed = discord.Embed(
            title="⛩️ Automatic AI Channel Configured",
            description=f"**{meta['name']}** is now active in {channel.mention}!\nNo prefixes required—members can chat naturally.",
            color=AIZEN_PURPLE,
        )
        embed.add_field(name="Persona", value=f"`{meta['name']}`", inline=True)
        embed.add_field(name="Chat Mode", value=f"`{mode_str}`", inline=True)
        embed.add_field(name="Cooldown", value=f"`{cooldown_seconds}s per user`", inline=True)
        embed.add_field(name="GIF Reactions", value=f"`{'Enabled' if send_gifs else 'Disabled'}`", inline=True)
        embed.set_footer(text=f"Aizen Edition • Server: {guild.name}")
        return embed

    async def _status_channel(self, guild: discord.Guild, channel: discord.TextChannel) -> discord.Embed:
        cfg = self._channel_configs.get(channel.id)
        if not cfg:
            return discord.Embed(
                title="ℹ️ Channel Not Configured",
                description=f"{channel.mention} does not have an automatic AI persona active.",
                color=AIZEN_DARK,
            )

        persona = cfg.get("persona", "aigf")
        meta = PERSONA_METADATA.get(persona, PERSONA_METADATA["aigf"])
        status_str = "🟢 Active" if cfg.get("enabled", True) else "🔴 Disabled"
        mode_str = "Mention Only" if cfg.get("mention_only", False) else "All Normal Messages"

        embed = discord.Embed(
            title=f"⛩️ AI Channel Status — #{channel.name}",
            description=f"Configuration for {channel.mention}:",
            color=AIZEN_PURPLE,
        )
        embed.add_field(name="Status", value=f"`{status_str}`", inline=True)
        embed.add_field(name="Persona", value=f"`{meta['name']}`", inline=True)
        embed.add_field(name="Trigger Mode", value=f"`{mode_str}`", inline=True)
        embed.add_field(name="Cooldown", value=f"`{cfg.get('cooldown_seconds', 3)}s`", inline=True)
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

    # ─── HELPER: DIRECT RESPONSE GENERATION ───────────────────────────────────

    async def _handle_companion_response(
        self,
        ctx: CustomContext,
        persona_key: str,
        prompt: str,
        embed_color: int,
        title: str,
        gif_category: str | None = None,
    ) -> None:
        if not prompt or not prompt.strip():
            await ctx.send(f"💬 Tell me something! Usage: `{ctx.prefix}{ctx.invoked_with} <message>`")
            return

        guild_id = ctx.guild.id if ctx.guild else 0
        server_name = ctx.guild.name if ctx.guild else "Direct Message"
        user_id = ctx.author.id

        session = getattr(self.bot, "session", None)
        if not session or session.closed:
            await ctx.send("❌ Internal network session is not ready. Please try again in a few moments.")
            return

        try:
            async with ctx.typing():
                reply = await self.bot.ai_mgr.generate_persona_reply(
                    session=session,
                    guild_id=guild_id,
                    user_id=user_id,
                    persona_key=persona_key,
                    prompt=prompt.strip(),
                    server_name=server_name,
                )
        except RuntimeError as e:
            await ctx.send(f"⚠️ {e}")
            return
        except Exception as e:
            logger.error(f"Error generating {persona_key} reply: {e}", exc_info=True)
            await ctx.send("💔 I had a little trouble thinking of what to say. Please try asking again shortly!")
            return

        gif_url: str | None = None
        prompt_lower = prompt.lower()
        should_send_gif = (
            random.random() < 0.35
            or any(kw in prompt_lower for kw in ("gif", "show me", "hug", "kiss", "look", "smile", "tease"))
        )
        if should_send_gif and gif_category:
            try:
                gif_url = await self.gif_mgr.get_action_gif(gif_category, session=session)
            except Exception as e:
                logger.debug(f"Failed to fetch optional GIF for {persona_key}: {e}")

        embed = discord.Embed(
            title=title,
            description=reply[:4000],
            color=embed_color,
        )
        embed.set_footer(
            text=f"Fictional AI Companion • Use {ctx.prefix}aiclear to reset history",
            icon_url=ctx.author.display_avatar.url,
        )
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(embed=embed)

    # ─── AUTOMATIC AI CHANNEL MESSAGE LISTENER ────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Automatic AI channel listener:
        Listens to ordinary messages in configured channels and replies as the configured persona.
        """
        # 1. Ignore bots, webhooks, non-guild messages
        if message.author.bot or message.webhook_id or not message.guild or not message.content.strip():
            return

        # 2. Prevent self-responses
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        # 3. Check if channel is configured
        channel_id = message.channel.id
        config = self._channel_configs.get(channel_id)
        if not config or not config.get("enabled", True):
            return

        # 4. Skip command messages so we do not interfere with real bot commands
        try:
            ctx = await self.bot.get_context(message)
            if ctx.valid:
                return
        except Exception:
            pass

        # 5. Check mention_only mode
        mention_only = config.get("mention_only", False)
        is_mentioned = self.bot.user and self.bot.user in message.mentions
        is_reply_to_bot = False
        if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
            if self.bot.user and message.reference.resolved.author.id == self.bot.user.id:
                is_reply_to_bot = True

        if mention_only and not (is_mentioned or is_reply_to_bot):
            return

        persona = config.get("persona", "aigf")

        # 6. Adult check for aispecial
        if persona == "aispecial":
            if not is_adult_authorized(message.author.id):
                return

        # 7. Cooldown & Concurrency limits
        now = time.monotonic()
        cooldown_sec = config.get("cooldown_seconds", 3)
        last_ch_time = self._channel_last_time.get(channel_id, 0)
        last_usr_time = self._user_last_time.get(message.author.id, 0)

        if now - last_usr_time < 3.0:
            return
        if now - last_ch_time < cooldown_sec and not (is_mentioned or is_reply_to_bot):
            return

        self._user_last_time[message.author.id] = now
        self._channel_last_time[channel_id] = now

        # Acquire per-channel lock so rapid concurrent queries do not flood
        lock = self._channel_locks.setdefault(channel_id, asyncio.Lock())
        if lock.locked():
            return

        session = getattr(self.bot, "session", None)
        if not session or session.closed:
            return

        # Clean prompt by stripping bot mention tag
        prompt = message.content
        if self.bot.user:
            prompt = re.sub(rf"<@!?{self.bot.user.id}>", "", prompt).strip()
        if not prompt:
            prompt = "Hello!"

        meta = PERSONA_METADATA.get(persona, PERSONA_METADATA["aigf"])

        async with lock:
            try:
                async with message.channel.typing():
                    reply = await self.bot.ai_mgr.generate_persona_reply(
                        session=session,
                        guild_id=message.guild.id,
                        user_id=message.author.id,
                        persona_key=persona,
                        prompt=prompt[:3000],
                        server_name=message.guild.name,
                    )
            except Exception as e:
                logger.debug(f"Auto AI response error in #{message.channel.name}: {e}")
                return

            # Check GIF setting
            send_gifs = config.get("send_gifs", True)
            gif_url: str | None = None
            prompt_lower = prompt.lower()
            should_gif = send_gifs and (
                random.random() < 0.25
                or any(kw in prompt_lower for kw in ("gif", "show me", "hug", "kiss", "look", "smile", "tease"))
            )
            if should_gif and meta.get("gif_category"):
                try:
                    gif_url = await self.gif_mgr.get_action_gif(meta["gif_category"], session=session)
                except Exception:
                    pass

            # Safe reply delivery with allowed_mentions
            embed: discord.Embed | None = None
            if gif_url:
                embed = discord.Embed(color=meta["color"])
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
                    logger.debug(f"Failed to deliver auto AI reply chunk: {e}")
                    break

    # ─── SLASH COMMAND GROUP: /companion ─────────────────────────────────────

    companion_group = app_commands.Group(
        name="companion",
        description="KYOKA 3.0 Aizen AI Companion System",
    )

    @companion_group.command(name="girlfriend", description="Chat with your warm, affectionate AI Girlfriend companion.")
    @app_commands.describe(message="What would you like to say to your AI Girlfriend?")
    async def slash_gf(self, interaction: discord.Interaction, message: str) -> None:
        ctx = await self.bot.get_context(interaction)
        await self._handle_companion_response(
            ctx=ctx,
            persona_key="aigf",
            prompt=message,
            embed_color=PINK,
            title="🌸 Kyoka — AI Girlfriend",
            gif_category="romance",
        )

    @companion_group.command(name="baddie", description="Chat with your witty, sassy, stylish AI Baddie companion.")
    @app_commands.describe(message="What do you want to say to the baddie?")
    async def slash_baddie(self, interaction: discord.Interaction, message: str) -> None:
        ctx = await self.bot.get_context(interaction)
        await self._handle_companion_response(
            ctx=ctx,
            persona_key="aibaddie",
            prompt=message,
            embed_color=PURPLE,
            title="💅 Kyoka — AI Baddie",
            gif_category="flex",
        )

    @companion_group.command(name="special", description="Chat with the cheeky adult-humor AI companion [Restricted].")
    @app_commands.describe(message="Playful, suggestive adult-humor chat or scenario")
    async def slash_special(self, interaction: discord.Interaction, message: str) -> None:
        authorized = await authorize_adult(interaction, action_name="aispecial")
        if not authorized:
            return
        ctx = await self.bot.get_context(interaction)
        await self._handle_companion_response(
            ctx=ctx,
            persona_key="aispecial",
            prompt=message,
            embed_color=ROSE,
            title="😈 Kyoka — Special Adult Companion [Restricted]",
            gif_category="adultreaction",
        )

    @companion_group.command(name="clear", description="Clear your conversation memory across all AI companion personas.")
    async def slash_clear(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        user_id = interaction.user.id
        if hasattr(self.bot, "ai_mgr"):
            self.bot.ai_mgr.clear_user_history(guild_id, user_id)
        embed = discord.Embed(
            title="✨ Memory Cleared",
            description="Your conversation history for all AI companions has been reset.",
            color=AIZEN_PURPLE,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @companion_group.command(name="setup", description="Admin: Configure an automatic AI companion channel.")
    @app_commands.describe(
        persona="AI persona to activate",
        channel="Channel to activate in (defaults to current)",
        mention_only="Require mentioning the bot to get a reply",
        send_gifs="Allow the AI to send reaction GIFs",
    )
    @app_commands.choices(
        persona=[
            app_commands.Choice(name="🌸 AI Girlfriend (Warm & Affectionate)", value="aigf"),
            app_commands.Choice(name="💅 AI Baddie (Sassy & Stylish)", value="aibaddie"),
            app_commands.Choice(name="😈 Special Adult Companion [Restricted]", value="aispecial"),
        ]
    )
    async def slash_setup(
        self,
        interaction: discord.Interaction,
        persona: str,
        channel: Optional[discord.TextChannel] = None,
        mention_only: bool = False,
        send_gifs: bool = True,
    ) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        if not self._is_admin_or_owner(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ Administrator permissions are required to configure AI channels.", ephemeral=True)

        if persona == "aispecial":
            authorized = await authorize_adult(interaction, action_name="aispecial_setup")
            if not authorized:
                return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Target must be a standard text channel.", ephemeral=True)

        embed = await self._setup_channel(
            guild=interaction.guild,
            channel=target_channel,
            persona=persona,
            user_id=interaction.user.id,
            mention_only=mention_only,
            send_gifs=send_gifs,
        )
        await interaction.response.send_message(embed=embed)

    @companion_group.command(name="status", description="Check automatic AI configuration in this channel.")
    async def slash_status(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message("Target must be a text channel.", ephemeral=True)
        embed = await self._status_channel(interaction.guild, target)
        await interaction.response.send_message(embed=embed)

    @companion_group.command(name="disable", description="Admin: Disable automatic AI companion in this channel.")
    async def slash_disable(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        if not interaction.guild or not self._is_admin_or_owner(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message("Target must be a text channel.", ephemeral=True)
        embed = await self._disable_channel(interaction.guild, target)
        await interaction.response.send_message(embed=embed)

    @companion_group.command(name="remove", description="Admin: Permanently remove automatic AI companion from this channel.")
    async def slash_remove(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        if not interaction.guild or not self._is_admin_or_owner(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message("Target must be a text channel.", ephemeral=True)
        embed = await self._remove_channel(interaction.guild, target)
        await interaction.response.send_message(embed=embed)

    # ─── PREFIX COMMAND GROUPS: +aigf, +aibaddie, +aispecial ──────────────────

    @commands.group(
        name="aigf",
        aliases=["girlfriend", "gf"],
        invoke_without_command=True,
        help="Chat with AI Girlfriend, or configure automatic girlfriend channels.",
    )
    async def aigf(self, ctx: CustomContext, *, message: str = "") -> None:
        """Chat directly with AI Girlfriend, or use subcommands (setup, disable, remove, status)."""
        if ctx.invoked_subcommand is None:
            if not message.strip():
                embed = discord.Embed(
                    title="🌸 AI Girlfriend — Commands & Setup",
                    description=(
                        f"**Direct Chat:**\n"
                        f"`{ctx.prefix}aigf <message>` — Chat with your warm, affectionate AI companion.\n\n"
                        f"**Automatic Channel Setup (Admin):**\n"
                        f"`{ctx.prefix}aigf setup [#channel]` — Activate automatic girlfriend chat in a channel.\n"
                        f"`{ctx.prefix}aigf status` — Check configuration for this channel.\n"
                        f"`{ctx.prefix}aigf disable` — Pause automatic replies in this channel.\n"
                        f"`{ctx.prefix}aigf remove` — Remove configuration from this channel.\n"
                        f"`{ctx.prefix}aigf settings [mention_only=on/off] [gifs=on/off]` — Update settings.\n\n"
                        f"**Memory Management:**\n"
                        f"`{ctx.prefix}aiclearcompanion` — Reset your personal conversation history."
                    ),
                    color=PINK,
                )
                await ctx.send(embed=embed)
                return

            await self._handle_companion_response(
                ctx=ctx,
                persona_key="aigf",
                prompt=message,
                embed_color=PINK,
                title="🌸 Kyoka — AI Girlfriend",
                gif_category="romance",
            )

    @aigf.command(name="setup")
    @commands.guild_only()
    async def aigf_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Configure automatic AI Girlfriend in a channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required to configure AI channels.")
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            return await ctx.send("❌ Target must be a standard text channel.")
        embed = await self._setup_channel(ctx.guild, target, persona="aigf", user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aigf.command(name="disable")
    @commands.guild_only()
    async def aigf_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Disable automatic AI Girlfriend in this channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aigf.command(name="remove")
    @commands.guild_only()
    async def aigf_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Permanently remove automatic AI Girlfriend from this channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aigf.command(name="status")
    @commands.guild_only()
    async def aigf_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Check automatic AI Girlfriend configuration in this channel."""
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @commands.group(
        name="aibaddie",
        aliases=["baddie"],
        invoke_without_command=True,
        help="Chat with AI Baddie, or configure automatic baddie channels.",
    )
    async def aibaddie(self, ctx: CustomContext, *, message: str = "") -> None:
        """Chat directly with AI Baddie, or use subcommands (setup, disable, remove, status)."""
        if ctx.invoked_subcommand is None:
            if not message.strip():
                embed = discord.Embed(
                    title="💅 AI Baddie — Commands & Setup",
                    description=(
                        f"**Direct Chat:**\n"
                        f"`{ctx.prefix}aibaddie <message>` — Chat with your bold, witty, sassy AI companion.\n\n"
                        f"**Automatic Channel Setup (Admin):**\n"
                        f"`{ctx.prefix}aibaddie setup [#channel]` — Activate automatic baddie chat in a channel.\n"
                        f"`{ctx.prefix}aibaddie status` — Check configuration for this channel.\n"
                        f"`{ctx.prefix}aibaddie disable` — Pause automatic replies in this channel.\n"
                        f"`{ctx.prefix}aibaddie remove` — Remove configuration from this channel.\n\n"
                        f"**Memory Management:**\n"
                        f"`{ctx.prefix}aiclearcompanion` — Reset your personal conversation history."
                    ),
                    color=PURPLE,
                )
                await ctx.send(embed=embed)
                return

            await self._handle_companion_response(
                ctx=ctx,
                persona_key="aibaddie",
                prompt=message,
                embed_color=PURPLE,
                title="💅 Kyoka — AI Baddie",
                gif_category="flex",
            )

    @aibaddie.command(name="setup")
    @commands.guild_only()
    async def aibaddie_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Configure automatic AI Baddie in a channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required to configure AI channels.")
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            return await ctx.send("❌ Target must be a standard text channel.")
        embed = await self._setup_channel(ctx.guild, target, persona="aibaddie", user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aibaddie.command(name="disable")
    @commands.guild_only()
    async def aibaddie_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Disable automatic AI Baddie in this channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aibaddie.command(name="remove")
    @commands.guild_only()
    async def aibaddie_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Permanently remove automatic AI Baddie from this channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aibaddie.command(name="status")
    @commands.guild_only()
    async def aibaddie_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Check automatic AI Baddie configuration in this channel."""
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @commands.group(
        name="aispecial",
        aliases=["specialai", "spicyai"],
        invoke_without_command=True,
        help="Chat with the cheeky, adult-humor AI companion [Restricted].",
    )
    async def aispecial(self, ctx: CustomContext, *, message: str = "") -> None:
        """Cheeky adult-humor AI companion (Strictly Restricted by ADULT_COMMAND_ALLOWLIST)."""
        authorized = await authorize_adult(ctx, action_name="aispecial")
        if not authorized:
            return

        if ctx.invoked_subcommand is None:
            if not message.strip():
                embed = discord.Embed(
                    title="😈 Special Adult Companion — Commands & Setup",
                    description=(
                        f"**Direct Chat:**\n"
                        f"`{ctx.prefix}aispecial <message>` — Playful, suggestive adult-humor chat.\n\n"
                        f"**Automatic Channel Setup (Admin + Authorized):**\n"
                        f"`{ctx.prefix}aispecial setup [#channel]` — Activate automatic special chat in a channel.\n"
                        f"`{ctx.prefix}aispecial status` — Check configuration for this channel.\n"
                        f"`{ctx.prefix}aispecial disable` — Pause automatic replies in this channel.\n"
                        f"`{ctx.prefix}aispecial remove` — Remove configuration from this channel.\n\n"
                        f"**Security Note:**\n"
                        f"This persona and its automatic channels are strictly restricted to authorized Discord IDs."
                    ),
                    color=ROSE,
                )
                await ctx.send(embed=embed)
                return

            await self._handle_companion_response(
                ctx=ctx,
                persona_key="aispecial",
                prompt=message,
                embed_color=ROSE,
                title="😈 Kyoka — Special Adult Companion [Restricted]",
                gif_category="adultreaction",
            )

    @aispecial.command(name="setup")
    @commands.guild_only()
    async def aispecial_setup(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin + Authorized: Configure automatic Special AI Companion in a channel."""
        authorized = await authorize_adult(ctx, action_name="aispecial_setup")
        if not authorized:
            return
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required to configure AI channels.")
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            return await ctx.send("❌ Target must be a standard text channel.")
        embed = await self._setup_channel(ctx.guild, target, persona="aispecial", user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aispecial.command(name="disable")
    @commands.guild_only()
    async def aispecial_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin + Authorized: Disable automatic Special AI Companion in this channel."""
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
        """Admin + Authorized: Permanently remove automatic Special AI Companion from this channel."""
        authorized = await authorize_adult(ctx, action_name="aispecial_remove")
        if not authorized:
            return
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aispecial.command(name="status")
    @commands.guild_only()
    async def aispecial_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Check automatic Special AI Companion configuration in this channel."""
        authorized = await authorize_adult(ctx, action_name="aispecial_status")
        if not authorized:
            return
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    # ─── GENERAL AI CHANNEL MANAGEMENT COMMAND: +aichannel ──────────────────

    @commands.group(
        name="aichannel",
        aliases=["setcompanionchannel", "aichatsetup"],
        invoke_without_command=True,
        help="Configure and manage automatic AI conversation channels.",
    )
    @commands.guild_only()
    async def aichannel(self, ctx: CustomContext) -> None:
        """Manage automatic AI channels for this server."""
        embed = discord.Embed(
            title="⛩️ Automatic AI Channel Management",
            description=(
                f"**Setup Channel:**\n"
                f"`{ctx.prefix}aichannel setup <aigf|aibaddie|aispecial> [#channel]`\n\n"
                f"**Status & Settings:**\n"
                f"`{ctx.prefix}aichannel status [#channel]` — Check status of an AI channel.\n"
                f"`{ctx.prefix}aichannel disable [#channel]` — Temporarily disable an AI channel.\n"
                f"`{ctx.prefix}aichannel remove [#channel]` — Remove AI channel configuration.\n\n"
                f"**Direct Persona Shortcuts:**\n"
                f"`{ctx.prefix}aigf setup [#channel]`\n"
                f"`{ctx.prefix}aibaddie setup [#channel]`\n"
                f"`{ctx.prefix}aispecial setup [#channel]`"
            ),
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed)

    @aichannel.command(name="setup")
    @commands.guild_only()
    async def aichannel_setup(
        self,
        ctx: CustomContext,
        persona: str = "aigf",
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Admin: Setup an AI channel with a specific persona."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required to configure AI channels.")
        p = persona.lower().strip()
        if p not in PERSONA_METADATA:
            valid_list = ", ".join(f"`{k}`" for k in PERSONA_METADATA.keys())
            return await ctx.send(f"❌ Unknown persona `{persona}`. Valid personas: {valid_list}")

        if p == "aispecial":
            authorized = await authorize_adult(ctx, action_name="aispecial_setup")
            if not authorized:
                return

        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            return await ctx.send("❌ Target must be a standard text channel.")
        embed = await self._setup_channel(ctx.guild, target, persona=p, user_id=ctx.author.id)
        await ctx.send(embed=embed)

    @aichannel.command(name="status")
    @commands.guild_only()
    async def aichannel_status(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Check status of an AI channel."""
        target = channel or ctx.channel
        embed = await self._status_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aichannel.command(name="disable")
    @commands.guild_only()
    async def aichannel_disable(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Disable automatic AI in a channel."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._disable_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    @aichannel.command(name="remove")
    @commands.guild_only()
    async def aichannel_remove(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Admin: Remove AI channel configuration."""
        if not self._is_admin_or_owner(ctx.author, ctx.guild):
            return await ctx.send("❌ Administrator permissions are required.")
        target = channel or ctx.channel
        embed = await self._remove_channel(ctx.guild, target)
        await ctx.send(embed=embed)

    # ─── MEMORY RESET: +aiclearcompanion ─────────────────────────────────────

    @commands.command(
        name="aiclearcompanion",
        aliases=["clearcompanion", "resetcompanion", "aiclear"],
        help="Clear your conversation memory across all AI companion personas.",
    )
    async def aiclearcompanion(self, ctx: CustomContext) -> None:
        """Reset conversation memory for all companion personas (aigf, aibaddie, aispecial)."""
        guild_id = ctx.guild.id if ctx.guild else 0
        user_id = ctx.author.id

        if hasattr(self.bot, "ai_mgr"):
            self.bot.ai_mgr.clear_user_history(guild_id, user_id)

        embed = discord.Embed(
            title="✨ Memory Cleared",
            description="Your conversation history for all AI companions (**AI Girlfriend**, **AI Baddie**, and **Special Companion**) has been reset.",
            color=AIZEN_PURPLE,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ─── AI DIAGNOSTICS: +aidiag ─────────────────────────────────────────────

    @commands.command(
        name="aidiag",
        aliases=["aistatus", "aimodel", "aidebug"],
        help="Owner/Admin diagnostic: test Gemini API model connectivity and latency.",
    )
    async def aidiag(self, ctx: CustomContext) -> None:
        """Test and verify Gemini API connectivity without exposing secret tokens."""
        session = getattr(self.bot, "session", None)
        if not session or session.closed:
            return await ctx.send("❌ Bot HTTP session is not active.")

        async with ctx.typing():
            res = await self.bot.ai_mgr.test_connectivity(session)

        embed = discord.Embed(
            title="⛩️ Kyoka 3.0 — AI System Diagnostics",
            color=discord.Color.green() if res.get("ok") else discord.Color.red(),
        )
        embed.add_field(name="Provider", value=f"`{res.get('provider', 'Google Gemini API')}`", inline=True)
        embed.add_field(name="Configured Model", value=f"`{res.get('configured_model', 'Default')}`", inline=True)
        embed.add_field(name="Active Model", value=f"`{res.get('model', 'None')}`", inline=True)

        if res.get("ok"):
            embed.add_field(name="Status", value="`🟢 200 OK (Healthy)`", inline=True)
            embed.add_field(name="Latency", value=f"`{res.get('latency_ms', 0)} ms`", inline=True)
            embed.add_field(name="Automatic Channels", value=f"`{len(self._channel_configs)} active`", inline=True)
        else:
            embed.add_field(name="Status", value=f"`🔴 Error ({res.get('status', 'Failed')})`", inline=True)
            embed.add_field(name="Diagnostic", value=f"```{res.get('error', 'Unknown issue')}```", inline=False)

        embed.set_footer(text="Aizen Edition • Safe Diagnostics (Keys Redacted)")
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(CompanionAI(bot))
