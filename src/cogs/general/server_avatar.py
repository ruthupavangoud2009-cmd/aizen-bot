from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyokaContainer,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.General.ServerAvatar")


class ServerAvatar(commands.Cog, name="General-ServerAvatar"):
    """Server Icon and Server Banner."""
    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="server",
        invoke_without_command=True,
        description="Display server media and branding assets.",
    )
    async def server_group(self, ctx: CustomContext) -> None:
        """Display server assets (`?server avatar` or `?server banner`)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @server_group.command(
        name="avatar",
        aliases=["icon"],
        description="Display this server's high-resolution icon.",
    )
    async def server_avatar(self, ctx: CustomContext) -> None:
        """Display the server's icon (`?server avatar`)."""
        if not ctx.guild or not ctx.guild.icon:
            await ctx.send_warning("This server does not have an icon configured.")
            return

        icon_url = str(ctx.guild.icon.url)
        hd_url = f"{icon_url}?size=4096" if "?" not in icon_url else f"{icon_url}&size=4096"
        dl_str = self.bot.custom_emojis.get("icons_download", "📥")

        container = KyokaContainer(accent_color=None)
        container.add_section(content=f"**{ctx.guild.name}** • {dl_str} [Download Icon]({hd_url})")
        container.add_separator(divider=True)
        container.add_media(f"{icon_url}?size=1024" if "?" not in icon_url else icon_url)
        await send_container_response(ctx, container)

    @server_group.command(
        name="banner",
        aliases=["splash"],
        description="Display this server's high-resolution banner or invite splash.",
    )
    async def server_banner(self, ctx: CustomContext) -> None:
        """Display the server's banner or splash (`?server banner`)."""
        if not ctx.guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        banner_url = str(ctx.guild.banner.url) if ctx.guild.banner else None
        splash_url = str(ctx.guild.splash.url) if ctx.guild.splash else None

        active_url = banner_url or splash_url
        if not active_url:
            await ctx.send_warning("This server does not have a banner or splash background set.")
            return

        hd_url = f"{active_url}?size=4096" if "?" not in active_url else f"{active_url}&size=4096"
        label = "Server Banner" if banner_url else "Invite Splash"
        dl_str = self.bot.custom_emojis.get("icons_download", "📥")

        container = KyokaContainer(accent_color=None)
        container.add_section(content=f"**{ctx.guild.name}** • {dl_str} [Download {label}]({hd_url})")
        container.add_separator(divider=True)
        container.add_media(f"{active_url}?size=2048" if "?" not in active_url else active_url)
        await send_container_response(ctx, container)

    @commands.command(name="serveravatar")
    async def serveravatar_shorthand(self, ctx: CustomContext) -> None:
        await self.server_avatar(ctx)

    @commands.command(name="serverbanner")
    async def serverbanner_shorthand(self, ctx: CustomContext) -> None:
        await self.server_banner(ctx)

    @commands.command(
        name="setbotavatar",
        aliases=["botavatar", "serverbotavatar", "guildavatar"],
        description="Set a custom server-specific avatar for Kyoka in this server.",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def set_bot_avatar(self, ctx: CustomContext, image_url: Optional[str] = None) -> None:
        """Set a custom avatar for Kyoka in this server (provide image URL or attach an image)."""
        from src.security.owner import is_owner_or_staff
        if not is_owner_or_staff(ctx.author.id) and not ctx.author.guild_permissions.manage_guild:
            await ctx.send_warning("❌ You need **Manage Server** permission to change Kyoka's server avatar.")
            return

        # 1. Determine image source (attachment or URL)
        target_url = None
        if ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url:
            target_url = image_url.strip()

        if not target_url:
            await ctx.send_warning(
                "❌ Please attach an image or provide a valid image URL.\n"
                f"> **Usage:** `+setbotavatar <image_url>` or attach a PNG/JPG with `+setbotavatar`"
            )
            return

        # 2. Download and validate image bytes
        try:
            async with self.bot.session.get(target_url, timeout=10) as resp:
                if resp.status != 200:
                    await ctx.send_warning(f"❌ Failed to download image (HTTP {resp.status}). Please check the URL.")
                    return
                content_type = resp.headers.get("Content-Type", "")
                if not any(t in content_type for t in ("image/png", "image/jpeg", "image/webp", "image/gif")):
                    await ctx.send_warning("❌ The provided URL or file does not appear to be a supported image (PNG, JPEG, WebP, GIF).")
                    return
                avatar_bytes = await resp.read()
                if len(avatar_bytes) > 10 * 1024 * 1024:
                    await ctx.send_warning("❌ Image file size too large (maximum 10MB).")
                    return
        except Exception as e:
            logger.warning("Error downloading server avatar image: %s", e)
            await ctx.send_warning(f"❌ Could not retrieve image: {e}")
            return

        # 3. Apply custom avatar to guild.me
        try:
            await ctx.guild.me.edit(avatar=avatar_bytes)
            embed = discord.Embed(
                title="⛩️ KYOKA 3.0 • CUSTOM SERVER AVATAR APPLIED",
                description=(
                    f"✅ **Kyoka's server avatar for `{ctx.guild.name}` has been successfully updated!**\n\n"
                    f"• **Configured By:** {ctx.author.mention} (`{ctx.author.name}`)\n"
                    f"• **Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                    f"• **Reset Anytime:** Type `+resetbotavatar` to restore global Kyoka avatar."
                ),
                color=0x7C3AED,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=ctx.guild.me.display_avatar.url)
            embed.set_footer(text=f"Custom Guild Avatar • {ctx.guild.name} • Kyoka 3.0")
            await ctx.send(embed=embed)
        except discord.HTTPException as e:
            logger.error("Failed to edit bot server avatar: %s", e)
            if e.code == 50035:
                await ctx.send_warning(
                    "❌ Discord rejected the avatar file format or size. Please ensure it is a valid PNG or JPEG square image."
                )
            else:
                await ctx.send_warning(
                    f"❌ Could not update bot server avatar: {e.text or e}.\n"
                    "> *Note: Server-specific bot avatars may require the server to meet Discord boost/profile requirements.*"
                )

    @commands.command(
        name="resetbotavatar",
        aliases=["resetavatar"],
        description="Reset Kyoka's server avatar back to the default global avatar.",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def reset_bot_avatar(self, ctx: CustomContext) -> None:
        """Reset Kyoka's server avatar back to default."""
        from src.security.owner import is_owner_or_staff
        if not is_owner_or_staff(ctx.author.id) and not ctx.author.guild_permissions.manage_guild:
            await ctx.send_warning("❌ You need **Manage Server** permission to reset Kyoka's server avatar.")
            return

        try:
            await ctx.guild.me.edit(avatar=None)
            embed = discord.Embed(
                title="⛩️ KYOKA 3.0 • SERVER AVATAR RESET",
                description=(
                    f"✅ **Kyoka's avatar in `{ctx.guild.name}` has been reset to default global branding.**\n\n"
                    f"• **Actioned By:** {ctx.author.mention}\n"
                    f"• **Server:** `{ctx.guild.name}`"
                ),
                color=0x7C3AED,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
            embed.set_footer(text="Kyoka 3.0 • Default Global Branding Active")
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("Failed to reset bot server avatar: %s", e)
            await ctx.send_warning(f"❌ Failed to reset server avatar: {e}")

    @commands.command(
        name="setservericon",
        aliases=["seticon", "changeservericon"],
        description="Update this server's official icon (requires Manage Server).",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def set_server_icon(self, ctx: CustomContext, image_url: Optional[str] = None) -> None:
        """Update the Discord server's icon (`+setservericon <url>` or attached image)."""
        target_url = None
        if ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url:
            target_url = image_url.strip()

        if not target_url:
            await ctx.send_warning(
                "❌ Please attach an image or provide an image URL to set as server icon."
            )
            return

        try:
            async with self.bot.session.get(target_url, timeout=10) as resp:
                if resp.status != 200:
                    return await ctx.send_warning("❌ Failed to download image from the provided URL.")
                icon_bytes = await resp.read()
            await ctx.guild.edit(icon=icon_bytes)
            embed = discord.Embed(
                title="🖼️ Server Icon Updated",
                description=f"✅ Successfully updated server icon for **{ctx.guild.name}**!",
                color=0x10B981,
            )
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send_warning(f"❌ Failed to update server icon: {e}")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(ServerAvatar(bot))
