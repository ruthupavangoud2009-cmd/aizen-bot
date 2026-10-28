"""
Kyoka Discord Bot - Server-Specific Bot Branding Cog
Provides:
- setbot avatar <image URL or attachment>
- setbot bio <text>
- setbot banner <image URL or attachment>
- setbot name <name>
- setbot reset
- setbot view
Strict per-guild isolation, permissions verification, Discord API limitation handling,
and graceful fallback to default KYOKA branding.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Optional
import aiohttp
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner, is_owner_or_staff, audit

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Admin.Branding")


class Branding(commands.Cog, name="Admin-Branding"):
    """Server-Specific KYOKA Identity & Branding Management."""

    category: str = "⚙️・SERVER ADMINISTRATION"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _can_manage_branding(self, ctx: CustomContext) -> bool:
        """Verify user is Server Owner, Administrator, Manage Server, or Bot Primary Owner."""
        if not ctx.guild:
            return False
        if is_primary_owner(ctx.author.id):
            return True
        if ctx.author.id == ctx.guild.owner_id:
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True
        return False

    @staticmethod
    def _is_valid_image_url(url: str) -> bool:
        """Validate if a URL is a legitimate image resource."""
        if not url or not isinstance(url, str):
            return False
        clean = url.lower().split("?")[0].strip()
        if not clean.startswith("https://"):
            return False
        allowed_extensions = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        if any(clean.endswith(ext) for ext in allowed_extensions):
            return True
        if "cdn.discordapp.com/avatars" in clean or "cdn.discordapp.com/icons" in clean or "cdn.discordapp.com/attachments" in clean:
            return True
        return False

    @commands.hybrid_group(
        name="setbot",
        aliases=["botedit", "botbrand", "serverbot"],
        invoke_without_command=True,
        description="Configure KYOKA's server-specific identity and visual branding.",
    )
    @commands.guild_only()
    async def setbot(self, ctx: CustomContext) -> None:
        """Root command for server branding customization."""
        if ctx.invoked_subcommand is None:
            p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            embed = discord.Embed(
                title="⛩️ KYOKA 3.0 — Server Branding Suite",
                description=(
                    f"Customize KYOKA's appearance and identity specifically for **{ctx.guild.name}**.\n\n"
                    f"**Available Commands:**\n"
                    f"• `{p}botedit name <name>` — Set server display name & bot nickname\n"
                    f"• `{p}botedit avatar <url or attachment>` — Set server bot avatar (only for this server)\n"
                    f"• `{p}botedit banner <url or attachment>` — Set server bot banner (only for this server)\n"
                    f"• `{p}botedit bio <text>` — Set server bot bio (only people in this server see it)\n"
                    f"• `{p}botedit view` — View this server's current branding configuration\n"
                    f"• `{p}botedit reset` — Reset server branding back to default KYOKA branding\n\n"
                    f"🛡️ *Requires Manage Server or Administrator permissions.*\n"
                    f"🔒 *Strict Server Isolation: All changes apply ONLY to this server. Other servers and DMs always see normal KYOKA branding.*"
                ),
                color=0x7C3AED,
            )
            embed.set_footer(text=f"{ctx.guild.name} • Server Branding Engine")
            await ctx.send(embed=embed)

    @setbot.command(
        name="name",
        aliases=["nick", "nickname", "displayname"],
        description="Set KYOKA's server-specific display name and bot nickname.",
    )
    @commands.guild_only()
    async def setbot_name(self, ctx: CustomContext, *, name: Optional[str] = None) -> None:
        if name is not None and not name.strip():
            await ctx.send_warning("❌ Name cannot be empty.")
            return

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if name is None:
            branding = await self.bot.branding_mgr.get_branding(ctx.guild.id)
            current_name = branding.get("display_name")
            embed = discord.Embed(
                title=f"⛩️ KYOKA 3.0 • SERVER BOT NAME • {ctx.guild.name}",
                description=(
                    f"**Current Server Display Name for `{ctx.guild.name}`:**\n"
                    f"> `{current_name}`\n\n"
                    f"🔒 **Strict Server Isolation:**\n"
                    f"> This name applies **ONLY** to `{ctx.guild.name}`. Members in other servers or DMs will not see this name.\n\n"
                    f"**How to Change:**\n"
                    f"• `{p}botedit name <new name>`\n"
                    f"• To restore default name: `{p}botedit reset`"
                ),
                color=0x7C3AED,
            )
            embed.set_footer(text=f"Server Isolation Active • {ctx.guild.name}")
            await ctx.send(embed=embed)
            return

        if not self._can_manage_branding(ctx):
            await ctx.send_warning("❌ You need **Manage Server** or **Administrator** permissions to modify KYOKA's branding.")
            return

        clean_name = name.strip()
        if len(clean_name) > 32:
            await ctx.send_warning("❌ Name cannot exceed 32 characters (Discord nickname limit).")
            return

        applied_nickname = False
        try:
            guild_me = ctx.guild.me
            await guild_me.edit(
                nick=clean_name,
                reason=f"KYOKA server branding updated by {ctx.author} ({ctx.author.id})",
            )
            applied_nickname = True
        except Exception:
            applied_nickname = False

        # Persist to database
        try:
            await self.bot.branding_mgr.set_field(
                ctx.guild.id,
                "display_name",
                clean_name,
                ctx.author.id,
                {"applied_nickname": applied_nickname},
            )
        except Exception as dbe:
            logger.error("Failed to save branding display_name: %s", dbe)
            await ctx.send_warning(f"❌ Failed to persist branding to database: {dbe}")
            return

        # Audit log
        await audit(self.bot, ctx.author.id, "set-bot-name", ctx.guild.id, "success", f"name={clean_name[:50]}")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • SERVER BOT NAME CONFIGURED",
            description=(
                f"✅ **KYOKA's server display name for `{ctx.guild.name}` is now set to `{clean_name}`!**\n\n"
                f"• **Target Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                f"• **Configured By:** {ctx.author.mention}\n"
                f"• **Live Discord Nickname:** `{'Updated Successfully' if applied_nickname else 'Preserved (Embeds Only)'}`\n"
                f"• **Strict Isolation:** This name applies exclusively to `{ctx.guild.name}` and will not affect any other server."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Server Branding • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @setbot.command(
        name="avatar",
        aliases=["avater", "icon", "pfp", "pic"],
        description="Set KYOKA's server-specific bot avatar (only changes in this server).",
    )
    @commands.guild_only()
    async def setbot_avatar(
        self,
        ctx: CustomContext,
        image: Optional[discord.Attachment] = None,
        *,
        image_url: Optional[str] = None,
    ) -> None:
        """Set server-specific bot avatar from attachment or URL. Changes ONLY for this server."""
        target_url = None
        if image:
            target_url = image.url
        elif ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url:
            target_url = image_url.strip()

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not target_url:
            branding = await self.bot.branding_mgr.get_branding(ctx.guild.id)
            av_url = branding.get("avatar_url")
            is_custom = bool(branding.get("is_custom"))
            embed = discord.Embed(
                title=f"⛩️ KYOKA 3.0 • SERVER BOT AVATAR • {ctx.guild.name}",
                description=(
                    f"**Current Server Avatar for `{ctx.guild.name}`:**\n"
                    f"> {'🎨 Custom Server Avatar Active' if is_custom else '⛩️ Default Global Avatar Active'}\n\n"
                    f"🔒 **Strict Server Isolation:**\n"
                    f"> This avatar applies **ONLY** to `{ctx.guild.name}`. Members in other servers or DMs will not see this avatar.\n\n"
                    f"**How to Change:**\n"
                    f"• `{p}botedit avatar <image URL>` (or `{p}botedit avater <image URL>`)\n"
                    f"• Upload an image file with comment `{p}botedit avatar`\n"
                    f"• To restore default avatar: `{p}botedit reset`"
                ),
                color=0x7C3AED,
            )
            if av_url:
                embed.set_thumbnail(url=av_url)
            embed.set_footer(text=f"Server Isolation Active • {ctx.guild.name}")
            await ctx.send(embed=embed)
            return

        if not self._can_manage_branding(ctx):
            await ctx.send_warning("❌ You need **Manage Server** or **Administrator** permissions to modify KYOKA's branding.")
            return

        if not self._is_valid_image_url(target_url):
            await ctx.send_warning("❌ Invalid image URL. Must be an HTTPS link ending with `.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`.")
            return

        # Download & validate image bytes
        session = getattr(self.bot, "session", None)
        close_session = False
        if session is None or (isinstance(getattr(session, "closed", None), bool) and session.closed):
            session = aiohttp.ClientSession()
            close_session = True
        try:
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    await ctx.send_warning(f"❌ Failed to download image (HTTP {resp.status}). Please check URL.")
                    return
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(t in content_type for t in ("image/png", "image/jpeg", "image/webp", "image/gif")):
                    await ctx.send_warning("❌ Unsupported image format. Please use PNG, JPEG, WebP, or GIF.")
                    return
                avatar_bytes = await resp.read()
                if len(avatar_bytes) > 10 * 1024 * 1024:
                    await ctx.send_warning("❌ Image file size exceeds 10MB limit.")
                    return
        except Exception as e:
            logger.warning("Error fetching avatar image: %s", e)
            await ctx.send_warning(f"❌ Could not retrieve image: {e}")
            return
        finally:
            if close_session:
                await session.close()

        # Attempt Discord Per-Guild Bot Member Avatar API
        applied_discord_api = False
        try:
            guild_me = ctx.guild.me
            await guild_me.edit(
                avatar=avatar_bytes,
                reason=f"KYOKA server branding updated by {ctx.author} ({ctx.author.id})",
            )
            applied_discord_api = True
        except Exception:
            applied_discord_api = False

        # Persist to database
        try:
            await self.bot.branding_mgr.set_field(
                ctx.guild.id,
                "avatar_url",
                target_url,
                ctx.author.id,
                {"applied_discord_avatar": applied_discord_api},
            )
            # Sync with legacy guild_custom_avatars table for backwards compatibility
            if self.bot.db:
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
        except Exception as dbe:
            logger.error("Failed to persist avatar to DB: %s", dbe)
            await ctx.send_warning(f"❌ Failed to persist branding to database: {dbe}")
            return

        # Audit log
        await audit(self.bot, ctx.author.id, "set-bot-avatar", ctx.guild.id, "success", f"applied_api={applied_discord_api}")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • SERVER BOT AVATAR CONFIGURED",
            description=(
                f"✅ **KYOKA's server avatar for `{ctx.guild.name}` has been successfully updated!**\n\n"
                f"• **Target Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                f"• **Configured By:** {ctx.author.mention}\n"
                f"• **Discord Profile API Applied:** `{'Yes (Live Member Avatar)' if applied_discord_api else 'Kyoka Visual Branding Engine'}`\n\n"
                f"🔒 **Strict Server Isolation:**\n"
                f"> **Only members in `{ctx.guild.name}` will see this avatar.**\n"
                f"> Other servers and DMs will never see this avatar.\n\n"
                f"• **Reset Anytime:** Type `{p}botedit reset` to restore default KYOKA branding."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=target_url)
        embed.set_footer(text=f"Server Branding • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @setbot.command(
        name="banner",
        aliases=["header", "splash", "background"],
        description="Set KYOKA's server-specific bot banner (only changes in this server).",
    )
    @commands.guild_only()
    async def setbot_banner(
        self,
        ctx: CustomContext,
        image: Optional[discord.Attachment] = None,
        *,
        image_url: Optional[str] = None,
    ) -> None:
        """Set server-specific bot banner from attachment or URL. Changes ONLY for this server."""
        target_url = None
        if image:
            target_url = image.url
        elif ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url:
            target_url = image_url.strip()

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not target_url:
            branding = await self.bot.branding_mgr.get_branding(ctx.guild.id)
            banner_url = branding.get("banner_url")
            is_custom = bool(branding.get("is_custom"))
            embed = discord.Embed(
                title=f"⛩️ KYOKA 3.0 • SERVER BOT BANNER • {ctx.guild.name}",
                description=(
                    f"**Current Server Banner for `{ctx.guild.name}`:**\n"
                    f"> {'🎨 Custom Server Banner Active' if is_custom and banner_url else '⛩️ Default Global Banner Active'}\n\n"
                    f"🔒 **Strict Server Isolation:**\n"
                    f"> This banner applies **ONLY** to `{ctx.guild.name}`. Members in other servers or DMs will not see this banner.\n\n"
                    f"**How to Change:**\n"
                    f"• `{p}botedit banner <image URL>`\n"
                    f"• Upload an image file with comment `{p}botedit banner`\n"
                    f"• To restore default: `{p}botedit reset`"
                ),
                color=0x7C3AED,
            )
            if banner_url:
                embed.set_image(url=banner_url)
            embed.set_footer(text=f"Server Isolation Active • {ctx.guild.name}")
            await ctx.send(embed=embed)
            return

        if not self._can_manage_branding(ctx):
            await ctx.send_warning("❌ You need **Manage Server** or **Administrator** permissions to modify KYOKA's branding.")
            return

        if not self._is_valid_image_url(target_url):
            await ctx.send_warning("❌ Invalid image URL. Must be an HTTPS link ending with `.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`.")
            return

        # Download & validate image
        session = getattr(self.bot, "session", None)
        close_session = False
        if session is None or (isinstance(getattr(session, "closed", None), bool) and session.closed):
            session = aiohttp.ClientSession()
            close_session = True
        try:
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    await ctx.send_warning(f"❌ Failed to download banner image (HTTP {resp.status}).")
                    return
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(t in content_type for t in ("image/png", "image/jpeg", "image/webp", "image/gif")):
                    await ctx.send_warning("❌ Unsupported image format. Please use PNG, JPEG, WebP, or GIF.")
                    return
                banner_bytes = await resp.read()
                if len(banner_bytes) > 10 * 1024 * 1024:
                    await ctx.send_warning("❌ Banner image file size exceeds 10MB limit.")
                    return
        except Exception as e:
            logger.warning("Error fetching banner image: %s", e)
            await ctx.send_warning(f"❌ Could not retrieve image: {e}")
            return
        finally:
            if close_session:
                await session.close()

        # Persist to database
        try:
            await self.bot.branding_mgr.set_field(
                ctx.guild.id,
                "banner_url",
                target_url,
                ctx.author.id,
            )
        except Exception as dbe:
            logger.error("Failed to save branding banner: %s", dbe)
            await ctx.send_warning(f"❌ Failed to persist branding to database: {dbe}")
            return

        # Audit log
        await audit(self.bot, ctx.author.id, "set-bot-banner", ctx.guild.id, "success", f"url={target_url[:100]}")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • SERVER BOT BANNER CONFIGURED",
            description=(
                f"✅ **KYOKA's server banner for `{ctx.guild.name}` has been successfully configured!**\n\n"
                f"• **Target Server:** `{ctx.guild.name}` (`{ctx.guild.id}`)\n"
                f"• **Configured By:** {ctx.author.mention}\n\n"
                f"🔒 **Strict Server Isolation:**\n"
                f"> **This banner applies exclusively to `{ctx.guild.name}`.**\n"
                f"> All other servers and DMs will never see this banner.\n\n"
                f"• **Reset Anytime:** Type `{p}botedit reset` to restore default KYOKA branding."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_image(url=target_url)
        embed.set_footer(text=f"Server Branding • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @setbot.command(
        name="bio",
        aliases=["about", "desc", "description"],
        description="Set KYOKA's server-specific bio (only people in this server can see it).",
    )
    @commands.guild_only()
    async def setbot_bio(self, ctx: CustomContext, *, text: Optional[str] = None) -> None:
        """Set server-specific bot bio description. Only people in this server can see it."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not text or not text.strip():
            branding = await self.bot.branding_mgr.get_branding(ctx.guild.id)
            current_bio = branding.get("bio")
            embed = discord.Embed(
                title=f"⛩️ KYOKA 3.0 • SERVER BOT BIO • {ctx.guild.name}",
                description=(
                    f"**Active Bio for `{ctx.guild.name}`:**\n"
                    f"> {current_bio}\n\n"
                    f"🔒 **Strict Server Isolation:**\n"
                    f"> **Only people in this server can see this bio** in `{p}help`, `{p}botinfo`, and bot profile cards.\n"
                    f"> Any other people who view KYOKA from other servers or DMs will see the **normal global bio**.\n\n"
                    f"**How to Update:**\n"
                    f"• `{p}botedit bio <new bio text>`\n"
                    f"• To restore default bio: `{p}botedit reset`"
                ),
                color=0x7C3AED,
            )
            embed.set_footer(text=f"Server Isolation Active • {ctx.guild.name}")
            await ctx.send(embed=embed)
            return

        if not self._can_manage_branding(ctx):
            await ctx.send_warning("❌ You need **Manage Server** or **Administrator** permissions to modify KYOKA's branding.")
            return

        clean_bio = text.strip()
        if len(clean_bio) > 300:
            await ctx.send_warning("❌ Bio cannot exceed 300 characters.")
            return

        # Persist to database
        try:
            await self.bot.branding_mgr.set_field(
                ctx.guild.id,
                "bio",
                clean_bio,
                ctx.author.id,
            )
        except Exception as dbe:
            logger.error("Failed to save branding bio: %s", dbe)
            await ctx.send_warning(f"❌ Failed to persist branding to database: {dbe}")
            return

        # Audit log
        await audit(self.bot, ctx.author.id, "set-bot-bio", ctx.guild.id, "success", f"bio={clean_bio[:60]}")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • SERVER BOT BIO CONFIGURED",
            description=(
                f"✅ **KYOKA's server bio for `{ctx.guild.name}` has been successfully configured!**\n\n"
                f"• **Active Server Bio:**\n> {clean_bio}\n\n"
                f"🔒 **Strict Server Isolation Guaranteed:**\n"
                f"> **Only members in `{ctx.guild.name}` will see this bio** (visible in `{p}help`, `{p}botinfo`, and bot profile cards in this server).\n"
                f"> **Any other people trying to see it from other servers or DMs will see the normal global bio.**\n\n"
                f"• **Configured By:** {ctx.author.mention}\n"
                f"• **Reset Anytime:** `{p}botedit reset`"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Server Branding • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @setbot.command(
        name="reset",
        aliases=["clear", "default"],
        description="Reset KYOKA's branding for this server back to default KYOKA branding.",
    )
    @commands.guild_only()
    async def setbot_reset(self, ctx: CustomContext) -> None:
        """Reset all server-specific branding for this guild."""
        if not self._can_manage_branding(ctx):
            await ctx.send_warning("❌ You need **Manage Server** or **Administrator** permissions to modify KYOKA's branding.")
            return

        # 1. Reset Discord API nickname if modified
        try:
            await ctx.guild.me.edit(
                nick=None,
                reason=f"KYOKA server branding reset by {ctx.author} ({ctx.author.id})",
            )
        except Exception as e:
            logger.debug("Notice resetting guild nickname: %s", e)

        # 2. Reset Discord API avatar if modified
        try:
            await ctx.guild.me.edit(
                avatar=None,
                reason=f"KYOKA server branding reset by {ctx.author} ({ctx.author.id})",
            )
        except Exception as e:
            logger.debug("Notice resetting guild avatar: %s", e)

        # 3. Clear database entries
        try:
            await self.bot.branding_mgr.reset_branding(ctx.guild.id)
            if self.bot.db:
                await self.bot.db.execute("DELETE FROM guild_custom_avatars WHERE guild_id = ?;", ctx.guild.id)
        except Exception as dbe:
            logger.error("Failed to reset branding in DB: %s", dbe)
            await ctx.send_warning(f"❌ Failed to reset branding in database: {dbe}")
            return

        # 4. Audit log
        await audit(self.bot, ctx.author.id, "reset-server-branding", ctx.guild.id, "success")

        defaults = self.bot.branding_mgr.get_default_branding()
        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • DEFAULT BRANDING RESTORED",
            description=(
                f"✅ **KYOKA's branding for `{ctx.guild.name}` has been successfully reset!**\n\n"
                f"• **Actioned By:** {ctx.author.mention}\n"
                f"• **Active Branding:** Sōsuke Aizen Sovereign Edition (Default)\n"
                f"• **Display Name:** `{defaults['display_name']}`\n"
                f"• **Server Isolation:** All server-specific branding overrides have been removed."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        if defaults.get("avatar_url"):
            embed.set_thumbnail(url=defaults["avatar_url"])
        embed.set_footer(text=f"Default Global Branding Active • {ctx.guild.name}")
        await ctx.send(embed=embed)

    @setbot.command(
        name="view",
        aliases=["show", "info", "status", "profile"],
        description="Display KYOKA's current branding configured for this server.",
    )
    @commands.guild_only()
    async def setbot_view(self, ctx: CustomContext) -> None:
        """View current server branding configuration."""
        branding = await self.bot.branding_mgr.get_branding(ctx.guild.id)
        is_custom = branding.get("is_custom", False)
        status_badge = "🎨 Custom Server Branding Active" if is_custom else "⛩️ Default KYOKA Branding (Global)"

        embed = discord.Embed(
            title=f"⛩️ Server Branding Overview • {ctx.guild.name}",
            description=f"Status: **{status_badge}**\n*All settings are isolated strictly to this server.*",
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )

        nick_status = " (Live Discord Nickname)" if branding.get("applied_nickname") else ""
        embed.add_field(
            name="🏷️ Display Name",
            value=f"`{branding['display_name']}`{nick_status}",
            inline=True,
        )

        embed.add_field(
            name="📝 Bio",
            value=f"{branding['bio'][:200]}",
            inline=False,
        )

        avatar_status = " (Live Member Avatar)" if branding.get("applied_discord_avatar") else " (Visual Engine)"
        av_url = branding.get("avatar_url")
        if av_url:
            embed.add_field(
                name="🖼️ Avatar",
                value=f"[Download / View]({av_url}){avatar_status}",
                inline=True,
            )
            embed.set_thumbnail(url=av_url)

        banner_url = branding.get("banner_url")
        if banner_url:
            embed.add_field(
                name="🚩 Banner",
                value=f"[Download / View]({banner_url})",
                inline=True,
            )
            embed.set_image(url=banner_url)

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed.set_footer(
            text=f"Use {p}setbot to customize • Kyoka 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Branding(bot))
