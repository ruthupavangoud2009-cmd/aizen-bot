"""
Kyoka Discord Bot - Voice Welcome System
Per-server configurable Text-To-Speech (TTS) voice greetings with music coexistence.
Never interrupts, moves, or disconnects active music playback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Cogs.VoiceWelcome")


class VoiceWelcome(commands.Cog):
    """Per-server Voice Welcome Manager with dynamic TTS and zero-music-interruption design."""
    category: str = "Utility"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    # ─── LISTENERS ────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Trigger voice greeting when member joins guild if configured for server_join/both."""
        if not member.guild:
            return
        await self.bot.voice_welcome_mgr.handle_member_event(member, "server_join")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Trigger voice greeting when member connects to configured voice channel."""
        if not member.guild:
            return

        # Check if member just joined a voice channel or changed channels
        if after.channel and (not before.channel or before.channel.id != after.channel.id):
            await self.bot.voice_welcome_mgr.handle_member_event(member, "voice_join")

    # ─── ADMIN COMMANDS ───────────────────────────────────────────────────────

    @commands.group(
        name="voicewelcome",
        aliases=["vw", "vwelcome"],
        invoke_without_command=True,
        description="Configure voice welcome TTS greetings for your server.",
    )
    @commands.has_permissions(administrator=True)
    async def voicewelcome_group(self, ctx: CustomContext) -> None:
        """Show Voice Welcome overview and current server configuration."""
        if not ctx.guild:
            return
        config = await self.bot.voice_welcome_mgr.get_config(ctx.guild.id)
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        ch_id = config.get("channel_id")
        ch_mention = f"<#{ch_id}>" if ch_id else "*None configured*"
        status_badge = "🟢 **Enabled**" if config.get("enabled") else "🔴 **Disabled**"

        is_music = self.bot.voice_welcome_mgr.is_music_active(ctx.guild)
        music_status = "🎵 Active (Greetings will safely queue)" if is_music else "⚪ Idle"

        embed = discord.Embed(
            title="🎙️ Voice Welcome System",
            description=(
                f"Status: {status_badge}\n\n"
                f"**Configuration:**\n"
                f"• **Channel:** {ch_mention}\n"
                f"• **Trigger:** `{config.get('trigger', 'both')}` (`server_join`, `voice_join`, or `both`)\n"
                f"• **Language:** `{config.get('language', 'en')}`\n"
                f"• **Cooldown:** `{config.get('cooldown_seconds', 30)}s` per user\n"
                f"• **Queue Expiry:** `{config.get('queue_expiration_seconds', 120)}s`\n"
                f"• **Allow Bots:** `{'Yes' if config.get('allow_bots') else 'No'}`\n"
                f"• **Music Coexistence:** {music_status}\n\n"
                f"**Greeting Message:**\n"
                f"> {config.get('greeting_text')}\n\n"
                f"**Commands:**\n"
                f"• `{p}vw enable` / `{p}vw disable` — Toggle system\n"
                f"• `{p}vw channel <#channel>` — Set target voice channel\n"
                f"• `{p}vw message <text>` — Set custom spoken greeting\n"
                f"• `{p}vw trigger <server_join|voice_join|both>` — Set event trigger\n"
                f"• `{p}vw lang <code>` — Set TTS language (`en`, `es`, `fr`, etc.)\n"
                f"• `{p}vw preview` — Test play greeting in your voice channel\n"
                f"• `{p}vw reset` — Reset to default configuration"
            ),
            color=0x2B0938,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • KYOKA 3.0")
        await ctx.send(embed=embed)

    @voicewelcome_group.command(name="enable", description="Enable voice welcome greetings.")
    @commands.has_permissions(administrator=True)
    async def vw_enable(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        config = await self.bot.voice_welcome_mgr.get_config(ctx.guild.id)
        if not config.get("channel_id"):
            return await ctx.send_warning("Please set a voice channel first using `voicewelcome channel <#channel>`.")

        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, enabled=True)
        await ctx.send_success("Voice welcome greetings have been **enabled**.")

    @voicewelcome_group.command(name="disable", description="Disable voice welcome greetings.")
    @commands.has_permissions(administrator=True)
    async def vw_disable(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, enabled=False)
        await ctx.send_success("Voice welcome greetings have been **disabled**.")

    @voicewelcome_group.command(name="channel", description="Set the target voice channel for greetings.")
    @commands.has_permissions(administrator=True)
    async def vw_channel(self, ctx: CustomContext, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        if not ctx.guild:
            return
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, channel_id=channel.id)
        await ctx.send_success(f"Voice welcome target channel set to {channel.mention}.")

    @voicewelcome_group.command(name="message", description="Set custom spoken greeting.")
    @commands.has_permissions(administrator=True)
    async def vw_message(self, ctx: CustomContext, *, message: str) -> None:
        if not ctx.guild:
            return
        clean_msg = message.strip()[:300]
        if not clean_msg:
            return await ctx.send_error("Greeting message cannot be empty.")
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, greeting_text=clean_msg)
        await ctx.send_success(f"Voice greeting updated to:\n> {clean_msg}")

    @voicewelcome_group.command(name="trigger", description="Set trigger condition (server_join, voice_join, or both).")
    @commands.has_permissions(administrator=True)
    async def vw_trigger(self, ctx: CustomContext, trigger: str) -> None:
        if not ctx.guild:
            return
        clean_trig = trigger.lower().strip()
        if clean_trig not in ("server_join", "voice_join", "both"):
            return await ctx.send_error("Trigger must be one of: `server_join`, `voice_join`, or `both`.")
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, trigger=clean_trig)
        await ctx.send_success(f"Voice welcome trigger set to `{clean_trig}`.")

    @voicewelcome_group.command(name="lang", description="Set TTS language code (e.g. en, es, fr, de, ja).")
    @commands.has_permissions(administrator=True)
    async def vw_lang(self, ctx: CustomContext, language_code: str) -> None:
        if not ctx.guild:
            return
        clean_lang = language_code.lower().strip()[:10]
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, language=clean_lang)
        await ctx.send_success(f"Voice welcome TTS language set to `{clean_lang}`.")

    @voicewelcome_group.command(name="cooldown", description="Set per-user greeting cooldown in seconds.")
    @commands.has_permissions(administrator=True)
    async def vw_cooldown(self, ctx: CustomContext, seconds: int) -> None:
        if not ctx.guild:
            return
        safe_sec = max(5, min(seconds, 3600))
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, cooldown_seconds=safe_sec)
        await ctx.send_success(f"Voice welcome cooldown set to `{safe_sec}s`.")

    @voicewelcome_group.command(name="allowbots", description="Configure whether bot accounts receive voice greetings.")
    @commands.has_permissions(administrator=True)
    async def vw_allowbots(self, ctx: CustomContext, enable: bool) -> None:
        if not ctx.guild:
            return
        await self.bot.voice_welcome_mgr.update_config(ctx.guild.id, allow_bots=enable)
        status = "enabled" if enable else "disabled"
        await ctx.send_success(f"Voice welcome greetings for bot accounts have been **{status}**.")

    @voicewelcome_group.command(name="preview", description="Preview and play greeting in your current voice channel.")
    @commands.has_permissions(administrator=True)
    async def vw_preview(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        config = await self.bot.voice_welcome_mgr.get_config(ctx.guild.id)
        template = config.get("greeting_text") or "Welcome {member} to {server}!"
        spoken = self.bot.voice_welcome_mgr.format_greeting(template, ctx.author)

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send_info(
                f"**Spoken Greeting Text:**\n> {spoken}\n\n*Join a voice channel and re-run to hear audio playback.*",
                title="Voice Greeting Preview",
            )

        if self.bot.voice_welcome_mgr.is_music_active(ctx.guild):
            return await ctx.send_warning("Cannot play preview: Music is currently playing in a voice channel.")

        await ctx.send_info(f"🎙️ Playing voice preview in {ctx.author.voice.channel.mention}...\n> {spoken}")
        await self.bot.voice_welcome_mgr.play_greeting(ctx.guild, ctx.author.voice.channel, ctx.author, config)

    @voicewelcome_group.command(name="reset", description="Reset voice welcome settings to factory defaults.")
    @commands.has_permissions(administrator=True)
    async def vw_reset(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        await self.bot.voice_welcome_mgr.reset_config(ctx.guild.id)
        await ctx.send_success("Voice welcome configuration has been reset to defaults.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(VoiceWelcome(bot))
