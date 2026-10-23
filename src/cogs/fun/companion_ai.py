from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.gif_manager import GIFManager
from src.security.adult_guard import authorize_adult

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.CompanionAI")
PURPLE = 0x7C3AED
PINK = 0xEC4899
ROSE = 0xF43F5E


class CompanionAI(commands.Cog):
    """Interactive AI Companion personas: AI Girlfriend, AI Baddie, and Special Adult-Humor companion."""
    category = "AI Companions"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_mgr = GIFManager()

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

        # Show typing indicator while generating response
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
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"Error generating {persona_key} reply: {e}", exc_info=True)
            await ctx.send("💔 I had a little trouble thinking of what to say. Please try asking again shortly!")
            return

        # Relevant optional GIF inclusion (~35% chance or if keywords present)
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

    # ─── SLASH COMMAND GROUP (4 SUBCOMMANDS) ────────────────────────────────

    companion_group = app_commands.Group(
        name="companion",
        description="KYOKA AI Companion Personas",
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
            color=PURPLE,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─── PREFIX COMMANDS ─────────────────────────────────────────────────────

    @commands.command(
        name="aigf",
        aliases=["girlfriend", "gf"],
        help="Chat with your warm, affectionate, caring AI Girlfriend companion.",
    )
    async def aigf(self, ctx: CustomContext, *, message: str) -> None:
        """Chat with your loving, supportive fictional AI Girlfriend companion."""
        await self._handle_companion_response(
            ctx=ctx,
            persona_key="aigf",
            prompt=message,
            embed_color=PINK,
            title="🌸 Kyoka — AI Girlfriend",
            gif_category="romance",
        )

    @commands.command(
        name="aibaddie",
        aliases=["baddie"],
        help="Chat with your witty, sassy, stylish, and confident AI Baddie companion.",
    )
    async def aibaddie(self, ctx: CustomContext, *, message: str) -> None:
        """Chat with your bold, clever, confident AI Baddie companion."""
        await self._handle_companion_response(
            ctx=ctx,
            persona_key="aibaddie",
            prompt=message,
            embed_color=PURPLE,
            title="💅 Kyoka — AI Baddie",
            gif_category="flex",
        )

    @commands.command(
        name="aispecial",
        aliases=["specialai", "spicyai"],
        help="Chat with the cheeky, adult-humor AI companion (Restricted to Authorized Users).",
    )
    async def aispecial(self, ctx: CustomContext, *, message: str) -> None:
        """Cheeky adult-humor AI companion (Strictly Restricted by ADULT_COMMAND_ALLOWLIST)."""
        authorized = await authorize_adult(ctx, action_name="aispecial")
        if not authorized:
            return

        await self._handle_companion_response(
            ctx=ctx,
            persona_key="aispecial",
            prompt=message,
            embed_color=ROSE,
            title="😈 Kyoka — Special Adult Companion [Restricted]",
            gif_category="adultreaction",
        )

    @commands.command(
        name="aiclearcompanion",
        aliases=["clearcompanion", "resetcompanion"],
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
            color=PURPLE,
        )
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(CompanionAI(bot))
