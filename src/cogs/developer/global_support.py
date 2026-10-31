from __future__ import annotations

import re
from urllib.parse import urlsplit
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner, is_bot_staff, is_owner_or_staff
from src.utils.containers import KyokaContainer, send_container_response


def normalize_discord_invite(raw: str) -> Optional[str]:
    """Normalize any Discord invite URL or vanity code into a canonical https://discord.gg/<code> URL."""
    clean = raw.strip()
    if not clean:
        return None

    # Handle full URL
    if not clean.startswith(("http://", "https://")):
        if clean.startswith(("discord.gg/", "discord.com/invite/")):
            clean = f"https://{clean}"
        else:
            # Assume it's an invite code / vanity
            clean = f"https://discord.gg/{clean}"

    parsed = urlsplit(clean)
    host = (parsed.hostname or "").lower()

    if host in {"discord.gg", "www.discord.gg"}:
        code = parsed.path.strip("/")
        if code and len(code) >= 2:
            return f"https://discord.gg/{code}"
    elif host in {"discord.com", "www.discord.com", "discordapp.com"}:
        if parsed.path.startswith("/invite/"):
            code = parsed.path.removeprefix("/invite/").strip("/")
            if code and len(code) >= 2:
                return f"https://discord.gg/{code}"

    # Match raw invite regex pattern
    match = re.search(r"(?:discord\.gg|discord(?:app)?\.com/invite)/([a-zA-Z0-9\-_]+)", raw)
    if match:
        return f"https://discord.gg/{match.group(1)}"

    return None


class GlobalSupport(commands.Cog):
    """Dynamic configuration cog to change the support server invitation directly from Discord."""

    category = "Owner"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _is_authorized(self, ctx: CustomContext) -> bool:
        """Check if author is bot owner, registered staff, or application owner."""
        author_id = ctx.author.id
        if is_owner_or_staff(author_id):
            return True
        try:
            if await self.bot.is_owner(ctx.author):
                return True
        except Exception:
            pass
        return False

    @commands.hybrid_command(
        name="globalsupport",
        aliases=["setsupport", "supportserver", "supportlink", "setsupportserver"],
        description="View or change KYOKA's official support server invite directly from Discord.",
    )
    @app_commands.describe(url="The new Discord invite URL (e.g. discord.gg/example or invite code)")
    async def global_support(self, ctx: CustomContext, *, url: str | None = None) -> None:
        """Display or update KYOKA's global support-server invite URL."""
        current_url = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"

        # If no URL is provided, display the current support server information
        if url is None:
            container = KyokaContainer(accent_color=None)
            container.add_section(content="**Official Support Server**")
            container.add_separator(divider=True)
            container.add_text(
                f"**Current Link:** {current_url}\n\n"
                f"> Need help or want to report an issue? Join our official community server!"
            )
            # Add interactive button linking to the support server
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label="Join Support Server",
                    style=discord.ButtonStyle.link,
                    url=current_url,
                    emoji="💜",
                )
            )
            is_auth = await self._is_authorized(ctx)
            if is_auth:
                p = ctx.prefix
                container.add_text(
                    f"\n-# *Authorized: Use `{p}setsupport <invite>` or `/setsupport [url]` to change this link.*"
                )
            await send_container_response(ctx, container, view=view)
            return

        # Verification: check authorization
        if not await self._is_authorized(ctx):
            container = KyokaContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Unauthorized**\n"
                    "> Only the bot owner or registered staff can change the global support server link."
                )
            )
            if ctx.interaction:
                await ctx.interaction.response.send_message(
                    "You are not authorized to update the global support server link.",
                    ephemeral=True,
                )
            else:
                await send_container_response(ctx, container)
            return

        # Validate and normalize invite URL
        normalized = normalize_discord_invite(url.strip())
        if not normalized:
            container = KyokaContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Discord Invite URL**\n"
                    "> Please supply a valid Discord invite format, such as:\n"
                    "> • `discord.gg/yourinvite`\n"
                    "> • `https://discord.gg/yourinvite`\n"
                    "> • `https://discord.com/invite/yourinvite`\n"
                    "> • `yourinvite` (vanity or code)"
                )
            )
            if ctx.interaction:
                await ctx.interaction.response.send_message(
                    "Please provide a valid Discord invite URL.", ephemeral=True
                )
            else:
                await send_container_response(ctx, container)
            return

        # Persist new support URL into Supabase / PostgreSQL system_state
        try:
            await self.bot.db.execute(
                """INSERT INTO system_state (key, value) VALUES ('support_url', ?)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                normalized,
            )
        except Exception as e:
            logger.error("Failed persisting support_url into system_state: %s", e)

        # Update in-memory configuration
        Config.SUPPORT_URL = normalized

        # Render modern success response with interactive button
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Visit New Support Server",
                style=discord.ButtonStyle.link,
                url=normalized,
                emoji="💜",
            )
        )

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Official Support Server Updated**")
        container.add_separator(divider=True)
        container.add_text(
            f"KYOKA's official support server has been successfully updated!\n\n"
            f"• **New Support Invite:** {normalized}\n"
            f"• **Persisted:** Database & Runtime configuration updated\n"
            f"• **Applies To:** All help menus, info embeds, greeting cards, and bot profiles immediately."
        )

        if ctx.interaction:
            await ctx.interaction.response.send_message(
                f"KYOKA's global support invite is now updated to: {normalized}",
                ephemeral=True,
            )
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GlobalSupport(bot))
