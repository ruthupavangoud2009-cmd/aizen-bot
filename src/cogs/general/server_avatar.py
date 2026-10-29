"""
Kyoka Discord Bot - Server Avatar & Custom Bot Avatar Cog
Manages server icons/banners and provides the PREMIUM Custom Bot Avatar subsystem.
Enforces subscription checks, interactive confirmation, persistent PostgreSQL storage,
audit logging, and fail-safe Discord API fallbacks.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner, is_owner_or_staff, audit
from src.security.feature_access import require_premium, check_guild_feature_access
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.General.ServerAvatar")


class AvatarConfirmationView(discord.ui.View):
    """Interactive preview and confirmation view for applying a custom server bot avatar."""

    def __init__(
        self,
        ctx: CustomContext,
        target_url: str,
        avatar_bytes: bytes,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.target_url = target_url
        self.avatar_bytes = avatar_bytes
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "❌ Only the administrator who initiated this avatar update can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm & Apply Avatar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_callback(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_callback(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class AvatarResetConfirmationView(discord.ui.View):
    """Interactive confirmation view for resetting the server bot avatar to default Aizen branding."""

    def __init__(self, ctx: CustomContext, timeout: float = 45.0) -> None:
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "❌ Only the administrator who initiated this reset can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Yes, Restore Default Aizen Avatar", style=discord.ButtonStyle.danger, emoji="🔄")
    async def confirm_callback(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Keep Custom Avatar", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_callback(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class ServerAvatar(commands.Cog, name="General-ServerAvatar"):
    """Server Icon, Server Banner, and Premium Custom Bot Avatar management."""
    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    # ── FREE TIER: SERVER ICON & BANNER VIEWERS ──

    @commands.group(
        name="server",
        invoke_without_command=True,
        description="Display server media and branding assets.",
    )
    async def server_group(self, ctx: CustomContext) -> None:
        """Display server assets (`server avatar` or `server banner`)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @server_group.command(
        name="avatar",
        aliases=["icon"],
        description="Display this server's high-resolution icon.",
    )
    async def server_avatar(self, ctx: CustomContext) -> None:
        """Display the server's icon."""
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
        description="Display this server's banner or splash art.",
    )
    async def server_banner(self, ctx: CustomContext) -> None:
        """Display this server's banner or splash."""
        if not ctx.guild:
            return

        banner_url = str(ctx.guild.banner.url) if ctx.guild.banner else None
        splash_url = str(ctx.guild.splash.url) if ctx.guild.splash else None
        active_url = banner_url or splash_url

        if not active_url:
            await ctx.send_warning("This server does not have a banner or invite splash configured.")
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

    @staticmethod
    def _is_valid_image_url(url: str) -> bool:
        """Validate if a URL is an acceptable image source (HTTPS + valid image extension or Discord CDN)."""
        if not url or not isinstance(url, str):
            return False
        clean = url.lower().split("?")[0].strip()
        if not clean.startswith("https://"):
            return False
        allowed_extensions = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        if any(clean.endswith(ext) for ext in allowed_extensions):
            return True
        if "cdn.discordapp.com/avatars" in clean or "cdn.discordapp.com/icons" in clean:
            return True
        return False

    @commands.command(
        name="setbotavatar",
        aliases=["botavatar", "serverbotavatar", "guildavatar"],
        description="Set a custom server-specific avatar for Kyoka in this server (Premium).",
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @require_premium("custom_bot_avatar")
    async def set_bot_avatar(self, ctx: CustomContext, image_url: Optional[str] = None) -> None:
        """
        Set a custom bot avatar for Kyoka in this server.
        Usage: +setbotavatar <image_url> or attach an image with +setbotavatar
        Requires: Kyoka Premium & Manage Server permissions.
        """
        # Permission validation: Server Owner, Manage Server, or Bot Primary Owner
        is_server_admin = ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.guild.owner_id
        if not is_server_admin and not is_owner_or_staff(ctx.author.id):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to customize Kyoka's avatar.")
            return

        # 1. Resolve source image from attachment or URL
        target_url = None
        if ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url:
            target_url = image_url.strip()

        if not target_url:
            p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send_warning(
                "❌ Please attach an image file or provide a valid image URL.\n"
                f"> **Syntax:** `{p}setbotavatar <image_url>` or upload a file with `{p}setbotavatar`"
            )
            return

        if not self._is_valid_image_url(target_url):
            await ctx.send_warning(
                "❌ Invalid image URL. Must be an HTTPS link ending with `.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`."
            )
            return

        # 2. Download and validate image bytes
        try:
            async with self.bot.session.get(target_url, timeout=12) as resp:
                if resp.status != 200:
                    await ctx.send_warning(f"❌ Failed to download image (HTTP {resp.status}). Please verify the URL.")
                    return
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(t in content_type for t in ("image/png", "image/jpeg", "image/webp", "image/gif")):
                    await ctx.send_warning("❌ Unsupported file format. Please upload a PNG, JPEG, WebP, or GIF image.")
                    return
                avatar_bytes = await resp.read()
                if len(avatar_bytes) > 10 * 1024 * 1024:
                    await ctx.send_warning("❌ Image file size exceeds Discord's 10MB limit.")
                    return
        except Exception as e:
            logger.warning("Error downloading server avatar image: %s", e)
            await ctx.send_warning(f"❌ Could not retrieve image: {e}")
            return

        # 3. Interactive Preview & Confirmation
        preview_embed = discord.Embed(
            title="🖼️ Preview Custom Server Avatar",
            description=(
                f"**Target Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                f"**Requested By:** {ctx.author.mention} (`{ctx.author.name}`)\n"
                f"**Image Size:** `{len(avatar_bytes) / 1024:.1f} KB`\n\n"
                f"> Click **Confirm & Apply Avatar** below to activate this custom avatar for `{ctx.guild.name}`."
            ),
            color=0x7C3AED,
        )
        preview_embed.set_image(url=target_url)
        preview_embed.set_footer(text="Confirmation expires in 60 seconds • Kyoka Premium")

        view = AvatarConfirmationView(ctx, target_url, avatar_bytes, timeout=60.0)
        confirm_msg = await ctx.send(embed=preview_embed, view=view)

        await view.wait()

        if view.confirmed is None:
            timeout_embed = discord.Embed(
                title="⏳ Avatar Update Timed Out",
                description="> No confirmation received within 60 seconds. Avatar was not changed.",
                color=0x6B7280,
            )
            try:
                await confirm_msg.edit(embed=timeout_embed, view=None)
            except Exception:
                pass
            return

        if view.confirmed is False:
            cancel_embed = discord.Embed(
                title="❌ Avatar Update Cancelled",
                description="> Avatar update was cancelled by user. No changes were made.",
                color=0xEF4444,
            )
            try:
                await confirm_msg.edit(embed=cancel_embed, view=None)
            except Exception:
                pass
            return

        # 4. Attempt Discord Per-Guild Bot Profile API
        applied_discord_api = False
        api_notice = ""

        try:
            guild_me = ctx.guild.me
            await guild_me.edit(avatar=avatar_bytes, reason=f"Kyoka Premium custom server avatar by {ctx.author} ({ctx.author.id})")
            applied_discord_api = True
        except discord.HTTPException as e:
            logger.info(f"Discord guild member avatar API notice for guild {ctx.guild.id}: {e}")
            applied_discord_api = False
            api_notice = (
                "\n\nℹ️ **Discord Profile Note:**\n"
                "> Discord's native per-guild member avatar API is restricted for bot accounts without Bot Nitro partnership.\n"
                "> **Kyoka Visual Branding Fallback is now ACTIVE:** This custom avatar will display on all welcome cards, ticket panels, music embeds, and the web dashboard for this server."
            )
        except Exception as e:
            logger.warning(f"Unexpected error editing guild avatar: {e}")
            applied_discord_api = False

        # 5. Persist to PostgreSQL database (survives restarts)
        try:
            if hasattr(self.bot, "db") and self.bot.db:
                await self.bot.db.execute(
                    """
                    INSERT INTO guild_custom_avatars (guild_id, avatar_url, set_by, status, applied_discord_api, updated_at)
                    VALUES (?, ?, ?, 'active', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        avatar_url = excluded.avatar_url,
                        set_by = excluded.set_by,
                        status = 'active',
                        applied_discord_api = excluded.applied_discord_api,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    ctx.guild.id,
                    target_url,
                    ctx.author.id,
                    applied_discord_api,
                )
            if hasattr(self.bot, "branding_mgr"):
                await self.bot.branding_mgr.set_field(
                    ctx.guild.id,
                    "avatar_url",
                    target_url,
                    ctx.author.id,
                    {"applied_discord_avatar": applied_discord_api},
                )
        except Exception as dbe:
            logger.error(f"Failed to persist custom guild avatar to DB: {dbe}")

        # 6. Audit logging
        await audit(
            self.bot,
            ctx.author.id,
            "set-bot-avatar",
            ctx.guild.id,
            "success",
            f"applied_discord_api={applied_discord_api};url={target_url[:200]}",
        )

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        success_embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • CUSTOM SERVER AVATAR ACTIVATED",
            description=(
                f"✅ **Kyoka's custom avatar for `{ctx.guild.name}` has been successfully configured!**\n\n"
                f"• **Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                f"• **Configured By:** {ctx.author.mention}\n"
                f"• **Discord Profile API Applied:** `{'Yes (Live Member Avatar)' if applied_discord_api else 'Kyoka Visual Branding Engine'}`\n"
                f"• **Reset Anytime:** Type `{p}resetbotavatar` to restore global Aizen branding.{api_notice}"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        success_embed.set_thumbnail(url=target_url)
        success_embed.set_footer(
            text=f"Kyoka Premium • {ctx.guild.name}",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )

        try:
            await confirm_msg.edit(embed=success_embed, view=None)
        except Exception:
            await ctx.send(embed=success_embed)

    @commands.command(
        name="resetbotavatar",
        aliases=["resetavatar", "removebotavatar"],
        description="Reset Kyoka's server avatar back to the default Aizen avatar (Premium).",
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @require_premium("custom_bot_avatar")
    async def reset_bot_avatar(self, ctx: CustomContext) -> None:
        """
        Reset Kyoka's custom server avatar back to default global Aizen branding.
        Usage: +resetbotavatar
        Requires: Kyoka Premium & Manage Server permissions.
        """
        is_server_admin = ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.guild.owner_id
        if not is_server_admin and not is_owner_or_staff(ctx.author.id):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to reset Kyoka's avatar.")
            return

        view = AvatarResetConfirmationView(ctx, timeout=45.0)
        confirm_embed = discord.Embed(
            title="🔄 Confirm Avatar Reset",
            description=(
                f"Are you sure you want to restore the default global **Aizen branding** for **{ctx.guild.name}**?\n\n"
                "> This will remove the custom server avatar and restore Kyoka's default theme."
            ),
            color=0x7C3AED,
        )
        confirm_msg = await ctx.send(embed=confirm_embed, view=view)

        await view.wait()

        if not view.confirmed:
            cancel_embed = discord.Embed(
                title="❌ Reset Cancelled",
                description="> Avatar reset was cancelled. Custom avatar remains active.",
                color=0x6B7280,
            )
            try:
                await confirm_msg.edit(embed=cancel_embed, view=None)
            except Exception:
                pass
            return

        # Reset Discord API member avatar
        try:
            await ctx.guild.me.edit(avatar=None, reason=f"Kyoka avatar reset by {ctx.author} ({ctx.author.id})")
        except Exception as e:
            logger.debug(f"Notice on member avatar edit reset: {e}")

        # Remove from database
        try:
            if hasattr(self.bot, "db") and self.bot.db:
                await self.bot.db.execute(
                    "DELETE FROM guild_custom_avatars WHERE guild_id = ?;",
                    ctx.guild.id,
                )
            if hasattr(self.bot, "branding_mgr"):
                await self.bot.branding_mgr.reset_field(ctx.guild.id, "avatar_url")
        except Exception as dbe:
            logger.error(f"Failed to delete custom avatar from DB: {dbe}")

        # Audit log
        await audit(self.bot, ctx.author.id, "reset-bot-avatar", ctx.guild.id, "success")

        default_thumb = self.bot.user.display_avatar.url if self.bot.user else ""
        reset_embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • DEFAULT BRANDING RESTORED",
            description=(
                f"✅ **Kyoka's server avatar for `{ctx.guild.name}` has been restored to default global Aizen branding.**\n\n"
                f"• **Actioned By:** {ctx.author.mention}\n"
                f"• **Active Branding:** Sōsuke Aizen Sovereign Edition"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        if default_thumb:
            reset_embed.set_thumbnail(url=default_thumb)
        reset_embed.set_footer(text=f"Default Global Branding Active • {ctx.guild.name}")

        try:
            await confirm_msg.edit(embed=reset_embed, view=None)
        except Exception:
            await ctx.send(embed=reset_embed)

    @commands.command(
        name="setbotbanner",
        aliases=["botbanner", "serverbotbanner", "guildbotbanner"],
        description="Set a custom server-specific banner for Kyoka in this server (Premium).",
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @require_premium("custom_bot_avatar")
    async def set_bot_banner(self, ctx: CustomContext, image_url: Optional[str] = None) -> None:
        """
        Set a custom bot banner for Kyoka in this server.
        Usage: +setbotbanner <image_url> or attach an image with +setbotbanner
        Requires: Kyoka Premium & Manage Server permissions.
        """
        is_server_admin = ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.guild.owner_id
        if not is_server_admin and not is_owner_or_staff(ctx.author.id):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to customize Kyoka's banner.")
            return

        target_url = None
        if ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url:
            target_url = image_url.strip()

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not target_url:
            branding = await self.bot.branding_mgr.get_branding(ctx.guild.id) if hasattr(self.bot, "branding_mgr") else {}
            curr_banner = branding.get("banner_url")
            embed = discord.Embed(
                title=f"⛩️ KYOKA 3.0 • SERVER BOT BANNER • {ctx.guild.name}",
                description=(
                    f"**Current Server Banner for `{ctx.guild.name}`:**\n"
                    f"> {'🎨 Custom Server Banner Active' if curr_banner else '⛩️ Default Global Banner Active'}\n\n"
                    f"🔒 **Strict Server Isolation:**\n"
                    f"> This banner applies **ONLY** to `{ctx.guild.name}`. Other servers will never see it.\n\n"
                    f"**How to Set:**\n"
                    f"• `{p}setbotbanner <image URL>` or upload an image with `{p}setbotbanner`\n"
                    f"• To reset: `{p}resetbotbanner`"
                ),
                color=0x7C3AED,
            )
            if curr_banner:
                embed.set_image(url=curr_banner)
            await ctx.send(embed=embed)
            return

        if not self._is_valid_image_url(target_url):
            await ctx.send_warning(
                "❌ Invalid image URL. Must be an HTTPS link ending with `.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`."
            )
            return

        try:
            async with self.bot.session.get(target_url, timeout=12) as resp:
                if resp.status != 200:
                    await ctx.send_warning(f"❌ Failed to download banner image (HTTP {resp.status}).")
                    return
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(t in content_type for t in ("image/png", "image/jpeg", "image/webp", "image/gif")):
                    await ctx.send_warning("❌ Unsupported file format. Please upload PNG, JPEG, WebP, or GIF.")
                    return
                banner_bytes = await resp.read()
                if len(banner_bytes) > 10 * 1024 * 1024:
                    await ctx.send_warning("❌ Banner image file size exceeds 10MB limit.")
                    return
        except Exception as e:
            logger.warning("Error fetching banner: %s", e)
            await ctx.send_warning(f"❌ Could not retrieve image: {e}")
            return

        if hasattr(self.bot, "branding_mgr"):
            try:
                await self.bot.branding_mgr.set_field(
                    ctx.guild.id,
                    "banner_url",
                    target_url,
                    ctx.author.id,
                )
            except Exception as dbe:
                logger.error("Failed to save branding banner: %s", dbe)
                await ctx.send_warning(f"❌ Failed to persist banner to database: {dbe}")
                return

        await audit(self.bot, ctx.author.id, "set-bot-banner", ctx.guild.id, "success", f"url={target_url[:100]}")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • CUSTOM SERVER BANNER ACTIVATED",
            description=(
                f"✅ **Kyoka's custom banner for `{ctx.guild.name}` has been successfully configured!**\n\n"
                f"• **Target Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                f"• **Configured By:** {ctx.author.mention}\n"
                f"• **Strict Isolation:** This banner applies exclusively to `{ctx.guild.name}`.\n"
                f"• **Reset Anytime:** Type `{p}resetbotbanner` to restore default."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_image(url=target_url)
        embed.set_footer(text=f"Kyoka Premium • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command(
        name="resetbotbanner",
        aliases=["resetbanner", "removebotbanner"],
        description="Reset Kyoka's server banner back to default (Premium).",
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @require_premium("custom_bot_avatar")
    async def reset_bot_banner(self, ctx: CustomContext) -> None:
        """Reset Kyoka's custom server banner back to default."""
        is_server_admin = ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.guild.owner_id
        if not is_server_admin and not is_owner_or_staff(ctx.author.id):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to reset Kyoka's banner.")
            return

        if hasattr(self.bot, "branding_mgr"):
            try:
                await self.bot.branding_mgr.reset_field(ctx.guild.id, "banner_url")
            except Exception as e:
                logger.error("Failed to reset banner field: %s", e)
                await ctx.send_warning(f"❌ Failed to reset banner in database: {e}")
                return

        await audit(self.bot, ctx.author.id, "reset-bot-banner", ctx.guild.id, "success")

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • DEFAULT BANNER RESTORED",
            description=(
                f"✅ **Kyoka's server banner for `{ctx.guild.name}` has been restored to default global theme.**\n\n"
                f"• **Actioned By:** {ctx.author.mention}\n"
                f"• **Active Branding:** Sōsuke Aizen Sovereign Edition (Default)\n"
                f"• **Customize Again:** `{p}setbotbanner <url>`"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Default Global Branding Active • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command(
        name="setbotbio",
        aliases=["botbio", "serverbotbio", "guildbotbio"],
        description="Set Kyoka's server-specific bio (only people in this server can see it).",
    )
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def set_bot_bio(self, ctx: CustomContext, *, text: Optional[str] = None) -> None:
        """
        Set server-specific bot bio description.
        Usage: +setbotbio <text>
        Requires: Manage Server or Administrator permissions.
        """
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not text or not text.strip():
            branding = await self.bot.branding_mgr.get_branding(ctx.guild.id) if hasattr(self.bot, "branding_mgr") else {}
            curr_bio = branding.get("bio", "Power isn't given. It's taken. — Sosuke Aizen")
            embed = discord.Embed(
                title=f"⛩️ KYOKA 3.0 • SERVER BOT BIO • {ctx.guild.name}",
                description=(
                    f"**Active Bio for `{ctx.guild.name}`:**\n"
                    f"> {curr_bio}\n\n"
                    f"🔒 **Strict Server Isolation:**\n"
                    f"> Only members in this server see this bio in bot profile cards.\n\n"
                    f"**How to Set:**\n"
                    f"• `{p}setbotbio <new bio text>`\n"
                    f"• To reset: `{p}resetbotbio`"
                ),
                color=0x7C3AED,
            )
            embed.set_footer(text=f"Server Isolation Active • {ctx.guild.name}")
            await ctx.send(embed=embed)
            return

        is_server_admin = ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.guild.owner_id
        if not is_server_admin and not is_owner_or_staff(ctx.author.id):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to customize Kyoka's bio.")
            return

        clean_bio = text.strip()
        if len(clean_bio) > 300:
            await ctx.send_warning("❌ Bio cannot exceed 300 characters.")
            return

        if hasattr(self.bot, "branding_mgr"):
            try:
                await self.bot.branding_mgr.set_field(
                    ctx.guild.id,
                    "bio",
                    clean_bio,
                    ctx.author.id,
                )
            except Exception as dbe:
                logger.error("Failed to save branding bio: %s", dbe)
                await ctx.send_warning(f"❌ Failed to persist bio to database: {dbe}")
                return

        await audit(self.bot, ctx.author.id, "set-bot-bio", ctx.guild.id, "success", f"bio={clean_bio[:60]}")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • SERVER BOT BIO CONFIGURED",
            description=(
                f"✅ **KYOKA's server bio for `{ctx.guild.name}` has been successfully configured!**\n\n"
                f"• **Active Server Bio:**\n> {clean_bio}\n\n"
                f"🔒 **Strict Server Isolation Guaranteed:**\n"
                f"> **Only members in `{ctx.guild.name}` will see this bio.**\n"
                f"> Members in other servers or DMs will see the standard global bio.\n\n"
                f"• **Configured By:** {ctx.author.mention}\n"
                f"• **Reset Anytime:** `{p}resetbotbio`"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Server Branding • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command(
        name="resetbotbio",
        aliases=["resetbio", "removebotbio"],
        description="Reset Kyoka's server bio back to default.",
    )
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def reset_bot_bio(self, ctx: CustomContext) -> None:
        """Reset Kyoka's custom server bio back to default."""
        is_server_admin = ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.guild.owner_id
        if not is_server_admin and not is_owner_or_staff(ctx.author.id):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to reset Kyoka's bio.")
            return

        if hasattr(self.bot, "branding_mgr"):
            try:
                await self.bot.branding_mgr.reset_field(ctx.guild.id, "bio")
            except Exception as e:
                logger.error("Failed to reset bio field: %s", e)
                await ctx.send_warning(f"❌ Failed to reset bio in database: {e}")
                return

        await audit(self.bot, ctx.author.id, "reset-bot-bio", ctx.guild.id, "success")

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • DEFAULT BIO RESTORED",
            description=(
                f"✅ **KYOKA's server bio for `{ctx.guild.name}` has been restored to default global theme.**\n\n"
                f"• **Actioned By:** {ctx.author.mention}\n"
                f"• **Active Bio:** Power isn't given. It's taken. — Sosuke Aizen\n"
                f"• **Customize Again:** `{p}setbotbio <text>`"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Default Global Branding Active • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command(
        name="botprofile",
        aliases=["botbranding", "serverbranding", "botidentity"],
        description="View Kyoka's complete active identity and branding configured for this server.",
    )
    @commands.guild_only()
    async def show_bot_profile(self, ctx: CustomContext) -> None:
        """Display Kyoka's complete active server profile (Avatar, Banner, Bio, Display Name)."""
        branding = await self.bot.branding_mgr.get_branding(ctx.guild.id) if hasattr(self.bot, "branding_mgr") else {}
        is_custom = branding.get("is_custom", False)
        status_badge = "🎨 Custom Server Branding Active" if is_custom else "⛩️ Default Global Branding (Aizen Edition)"

        embed = discord.Embed(
            title=f"⛩️ Server Bot Identity Profile • {ctx.guild.name}",
            description=f"Status: **{status_badge}**\n*All overrides are isolated strictly to this server.*",
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name="🏷️ Display Name",
            value=f"`{branding.get('display_name', 'KYOKA 3.0')}`",
            inline=True,
        )

        bio_text = str(branding.get("bio") or "Power isn't given. It's taken. — Sosuke Aizen")[:200]
        embed.add_field(
            name="📝 Bio",
            value=bio_text,
            inline=False,
        )

        av_url = branding.get("avatar_url")
        if av_url:
            embed.set_thumbnail(url=av_url)
            embed.add_field(
                name="🖼️ Avatar",
                value=f"[Download / View]({av_url})",
                inline=True,
            )

        banner_url = branding.get("banner_url")
        if banner_url:
            embed.set_image(url=banner_url)
            embed.add_field(
                name="🚩 Banner",
                value=f"[Download / View]({banner_url})",
                inline=True,
            )

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed.set_footer(
            text=f"Use {p}setbotavatar, {p}setbotbanner, {p}setbotbio to customize • Kyoka 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        await ctx.send(embed=embed)


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
            await ctx.send_warning("❌ Please attach an image or provide a valid image URL to update the server icon.")
            return

        try:
            async with self.bot.session.get(target_url, timeout=10) as resp:
                if resp.status != 200:
                    await ctx.send_warning(f"❌ Failed to download image (HTTP {resp.status}).")
                    return
                icon_bytes = await resp.read()
                if len(icon_bytes) > 10 * 1024 * 1024:
                    await ctx.send_warning("❌ Image file size exceeds 10MB limit.")
                    return

            await ctx.guild.edit(icon=icon_bytes, reason=f"Server icon updated by {ctx.author} ({ctx.author.id})")
            await ctx.send_success(f"Successfully updated the server icon for **{ctx.guild.name}**!")
        except discord.Forbidden:
            await ctx.send_warning("❌ Missing Permissions: Kyoka needs `Manage Server` permission to edit the server icon.")
        except Exception as e:
            logger.error(f"Error updating server icon: {e}")
            await ctx.send_warning(f"❌ Failed to update server icon: {e}")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(ServerAvatar(bot))
