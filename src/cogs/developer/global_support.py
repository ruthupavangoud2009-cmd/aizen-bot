from __future__ import annotations

from urllib.parse import urlsplit

from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner


class GlobalSupport(commands.Cog):
    """Set KYOKA's persisted global support-server invitation."""

    category = "Owner"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="globalsupport",
        aliases=["setsupport"],
        description="Show or update KYOKA's global support-server invite. Owner only.",
    )
    async def global_support(self, ctx: CustomContext, url: str | None = None) -> None:
        if not is_primary_owner(ctx.author.id):
            message = "Only the primary bot owner can update the global support server."
            if ctx.interaction:
                await ctx.interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx.send(message)
            return

        if url is None:
            await ctx.send(f"Current global support invite: {Config.SUPPORT_URL or 'Not configured'}")
            return

        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        valid_invite = (
            parsed.scheme == "https"
            and host in {"discord.gg", "discord.com", "www.discord.com"}
            and (
                host == "discord.gg" and len(parsed.path.strip("/")) > 0
                or host in {"discord.com", "www.discord.com"}
                and parsed.path.startswith("/invite/")
                and len(parsed.path.removeprefix("/invite/").strip("/")) > 0
            )
            and not parsed.username
            and not parsed.password
        )
        if not valid_invite:
            message = "Provide a Discord invitation URL such as `https://discord.gg/example` or `https://discord.com/invite/example`."
            if ctx.interaction:
                await ctx.interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx.send(message)
            return

        invite = url.strip()
        await self.bot.db.execute(
            """INSERT INTO system_state (key, value) VALUES ('support_url', ?)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            invite,
        )
        Config.SUPPORT_URL = invite
        message = f"KYOKA's global support invite is now {invite}. This change is saved and applies immediately."
        if ctx.interaction:
            await ctx.interaction.response.send_message(message, ephemeral=True)
        else:
            await ctx.send(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GlobalSupport(bot))
