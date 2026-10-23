from __future__ import annotations

import asyncio
import io
import logging
import urllib.parse
from typing import TYPE_CHECKING, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.General.Imagine")


class Imagine(commands.Cog, name="General-Imagine"):
    """AI Image Generation Suite."""
    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="imagine",
        aliases=["aiimage", "generate", "imagegen", "draw"],
        description="Generate high-resolution AI artwork from a descriptive prompt.",
    )
    @app_commands.describe(prompt="Detailed description of the image you want to create")
    async def imagine(self, ctx: CustomContext, *, prompt: str) -> None:
        """Generate high-fidelity AI artwork from a prompt."""
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return await ctx.send_warning("Please provide a prompt. Example: `/imagine futuristic cyberpunk city in neon rain`")

        if len(clean_prompt) > 500:
            return await ctx.send_warning("Prompt is too long (maximum 500 characters).")

        # Defer interaction or start typing
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.defer()
        else:
            await ctx.channel.typing()

        session = getattr(self.bot, "session", None)
        if not session or session.closed:
            return await ctx.send_error("HTTP network session is currently unavailable.")

        encoded_prompt = urllib.parse.quote(clean_prompt)
        # High-performance, fast HTTPS image synthesis endpoint
        api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&enhance=true"

        img_bytes: bytes | None = None
        error_msg: str | None = None

        try:
            timeout = aiohttp.ClientTimeout(total=25.0)
            async with session.get(api_url, timeout=timeout) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
                else:
                    error_msg = f"Provider returned HTTP {resp.status}."
        except asyncio.TimeoutError:
            error_msg = "Image generation request timed out after 25s. The model may be under heavy load."
        except aiohttp.ClientError as ce:
            error_msg = f"Network connection error to image provider: {type(ce).__name__}."
        except Exception as e:
            logger.debug(f"Image generation error: {e}")
            error_msg = "An unexpected error occurred while generating the image."

        if not img_bytes:
            container = KyokaContainer()
            container.add_section(
                content=(
                    f"**Image Generation Failed**\n"
                    f"> {error_msg or 'The image synthesis service was unable to generate an image for this prompt.'}\n"
                    f"-# Please try again with a revised or simpler prompt."
                )
            )
            return await send_container_response(ctx, container)

        # Build Discord File & Container
        buf = io.BytesIO(img_bytes)
        buf.seek(0)
        file = discord.File(fp=buf, filename="kyoka_artwork.png")

        container = KyokaContainer(accent_color=8140525)  # Purple
        container.add_section(
            content=(
                f"# **AI Artwork Generation**\n"
                f"> **Prompt:** *{clean_prompt[:350]}*\n"
                f"-# Generated for {ctx.author.display_name} • 1024x1024 HD"
            )
        )
        container.add_media("attachment://kyoka_artwork.png")
        await send_container_response(ctx, container, file=file)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Imagine(bot))
