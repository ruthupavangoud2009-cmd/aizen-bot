from __future__ import annotations

import logging
import traceback
import uuid
import discord
from discord import app_commands
from discord.ext import commands

from src.utils.containers import KyokaContainer, send_container_response
from src.utils.emojis import sanitize_emoji_string
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.ErrorHandler")


def _error_emoji(bot: commands.Bot, *names: str, fallback: str = "❌") -> str:
    """Resolve an emoji defensively; ensure it is usable so unrendered <:id:> never leaks."""
    registry = getattr(bot, "custom_emojis", None)
    if registry is None:
        return fallback
    for name in names:
        try:
            emoji = registry.get_emoji_obj(name)
            if emoji is not None:
                if isinstance(emoji, discord.Emoji):
                    if not getattr(emoji, "is_usable", lambda: True)():
                        continue
                    return str(emoji)
                elif isinstance(emoji, discord.PartialEmoji):
                    if hasattr(bot, "emojis"):
                        matched = discord.utils.get(bot.emojis, id=emoji.id)
                        if matched and not getattr(matched, "is_usable", lambda: True)():
                            continue
                    return str(emoji)
        except Exception:
            continue
    return fallback


class ErrorHandler(commands.Cog, name="ErrorHandler"):
    """Global listener for prefix, hybrid, and slash command errors with signature Kyoka Sovereign embeds."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._old_tree_error = None

    async def cog_load(self) -> None:
        """Register application command tree error handler."""
        if hasattr(self.bot, "tree"):
            self._old_tree_error = self.bot.tree.on_error
            self.bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self) -> None:
        """Restore original application command tree error handler."""
        if hasattr(self.bot, "tree") and self._old_tree_error:
            self.bot.tree.on_error = self._old_tree_error

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Handle errors occurring during command execution."""
        if getattr(ctx.command, "on_error", None) is not None:
            return

        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            attempted = (getattr(ctx, "invoked_with", "") or "").lower()
            if attempted in {"vouch", "vouchhelp", "rephelp", "vouchremove", "vouchchannel", "vouchregister", "vouchscan"}:
                logger.error(
                    "Vouch command '%s' was invoked but is not registered. Vouches cog loaded=%s; failed extension=%s",
                    attempted,
                    bool(self.bot.get_cog("Vouches")),
                    getattr(self.bot, "failed_extensions", {}).get("src.cogs.general.vouches"),
                )
                try:
                    await ctx.reply(
                        "The vouch module is currently synchronizing with server cache. Please check latest logs.",
                        mention_author=False,
                    )
                except Exception:
                    pass
            return

        err_icon = _error_emoji(self.bot, "ERROR", "icons_wrong", "icon_x", fallback="❌")
        warn_icon = _error_emoji(self.bot, "WARNING", "icons_warning", "icon_warning", fallback="⚠️")
        clock_icon = _error_emoji(self.bot, "TIME", "icons_clock", "loading", fallback="⏳")
        lock_icon = _error_emoji(self.bot, "LOCK", "icons_locked", "icon_lock", fallback="🔒")

        # Color and header states
        color = KyokaTheme.ERROR
        title = "Command Error"
        body = "An error occurred while executing this command."
        author_badge = "Command Alert"

        if isinstance(error, commands.MissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            title = f"{lock_icon} Permission Denied"
            body = f"> You need the following permission(s) to execute `{ctx.prefix}{ctx.command.qualified_name}`:\n> {missing_perms}"
            author_badge = "Access Denied"

        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            title = f"{lock_icon} KYOKA Missing Permissions"
            body = f"> I need the following permission(s) in this channel to perform that action:\n> {missing_perms}"
            author_badge = "Bot Permission Required"

        elif isinstance(error, discord.Forbidden):
            title = f"{lock_icon} Action Forbidden (Discord 403)"
            body = (
                "> Discord rejected this operation because KYOKA lacks the necessary server permissions, "
                "or the target user/role is higher than or equal to KYOKA in the role hierarchy.\n\n"
                "> 💜 **Resolution:** Move KYOKA's highest role higher in `Server Settings > Roles` "
                "and ensure KYOKA has administrative or moderation rights."
            )
            author_badge = "Hierarchy Constraint"

        elif isinstance(error, commands.CommandOnCooldown):
            color = KyokaTheme.WARNING
            title = f"{clock_icon} Cooldown Active"
            body = (
                f"> This command is currently cooling down to preserve rate limits.\n"
                f"> Please wait `{error.retry_after:.1f}s` before trying `{ctx.prefix}{ctx.command.qualified_name}` again."
            )
            author_badge = "Rate Limited"

        elif type(error).__name__ == "PremiumRequiredError":
            color = 0xA855F7
            title = "👑 KYOKA Prime Feature"
            body = (
                "> This command requires an active KYOKA Prime subscription.\n\n"
                "> 💜 **Tiers:** Pro ($4.99/mo) or Ultimate ($9.99/mo)\n"
                "> 💜 **Activate:** Use `+license activate <key>` or check bot settings."
            )
            author_badge = "Prime Exclusive"

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            title = f"{lock_icon} Access Denied"
            body = f"> {str(error) or 'You do not have permission to execute this command in this server or channel.'}"
            author_badge = "Authorization Failure"

        elif isinstance(error, commands.MissingRequiredArgument):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Invalid Command Usage"
            body = (
                f"> Missing required parameter: `{error.param.name}`\n\n"
                f"> 💜 **Usage:** `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`\n"
                f"> 💜 **Example:** `{ctx.prefix}{ctx.command.qualified_name} <{error.param.name}>`"
            )
            author_badge = "Invalid Usage"

        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} User Not Found"
            arg_clean = discord.utils.escape_markdown(str(getattr(error, "argument", "Unknown")))
            body = (
                f"> Could not find a member matching `{arg_clean}`.\n\n"
                f"> 💜 **Tip: Try mentioning the user** (`@User`) or provide their 17–19 digit Discord snowflake ID."
            )
            author_badge = "Target Unresolved"

        elif isinstance(error, commands.ChannelNotFound):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Channel Not Found"
            arg_clean = discord.utils.escape_markdown(str(getattr(error, "argument", "Unknown")))
            body = f"> Could not find channel matching `{arg_clean}`."
            author_badge = "Channel Unresolved"

        elif isinstance(error, commands.RoleNotFound):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Role Not Found"
            arg_clean = discord.utils.escape_markdown(str(getattr(error, "argument", "Unknown")))
            body = f"> Could not find role matching `{arg_clean}`."
            author_badge = "Role Unresolved"

        elif isinstance(error, commands.BadUnionArgument):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Invalid Argument"
            body = f"> Could not resolve `{error.param.name}`. Please mention a valid user, channel, or role, or provide an ID."
            author_badge = "Argument Mismatch"

        elif isinstance(error, commands.BadLiteralArgument):
            color = KyokaTheme.WARNING
            options = ", ".join(f"`{opt}`" for opt in error.literals)
            title = f"{warn_icon} Invalid Selection"
            body = f"> Valid choices for `{error.param.name}` are: {options}"
            author_badge = "Choice Mismatch"

        elif isinstance(error, commands.RangeError):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Value Out of Range"
            body = f"> Value `{error.value}` is out of range. Must be between `{error.minimum}` and `{error.maximum}`."
            author_badge = "Range Limit"

        elif isinstance(error, commands.TooManyArguments):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Too Many Arguments"
            body = (
                f"> Too many arguments were provided for `{ctx.command.qualified_name}`.\n\n"
                f"> 💜 **Usage:** `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
            )
            author_badge = "Syntax Error"

        elif isinstance(error, commands.BadArgument):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Invalid Command Argument"
            body = (
                f"> {str(error)}\n\n"
                f"> 💜 **Usage:** `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
            )
            author_badge = "Syntax Error"

        elif isinstance(error, commands.DisabledCommand):
            title = f"{lock_icon} Command Disabled"
            body = f"> `{ctx.prefix}{ctx.command.qualified_name}` is currently disabled by administrators."
            author_badge = "Disabled"

        elif isinstance(error, commands.NoPrivateMessage):
            title = "⛩️ Server Channel Required"
            body = "> This command can only be used inside a Discord server channel, not in Direct Messages."
            author_badge = "Guild Only"

        elif isinstance(error, commands.PrivateMessageOnly):
            title = "📩 Direct Message Required"
            body = "> This command is designed to be executed only inside Direct Messages with KYOKA."
            author_badge = "DM Only"

        elif isinstance(error, commands.NSFWChannelRequired):
            title = "🔞 Age-Restricted Channel Required"
            body = "> This command contains mature content and can only be used in Age-Restricted (NSFW) channels."
            author_badge = "NSFW Enforced"

        elif isinstance(error, commands.MaxConcurrencyReached):
            color = KyokaTheme.WARNING
            title = f"{clock_icon} Concurrency Limit Reached"
            body = "> This command is already actively running another request in this channel. Please wait for it to complete."
            author_badge = "Busy"

        elif "wavelink" in type(error).__module__ or any(k in type(error).__name__ for k in ("NoNodeAvailable", "Lavalink", "NodeException", "TrackLoadError")):
            color = 0xEC4899  # Music Pink
            title = "🎵 Audio Engine Synchronizing"
            body = (
                "> The audio streaming node is currently synchronizing with Discord voice servers.\n\n"
                f"> 💜 **Resolution:** Please verify you are in an active voice channel and retry `{ctx.prefix}{ctx.command.qualified_name}` in a few seconds."
            )
            author_badge = "Audio Protocol"

        elif isinstance(error, discord.NotFound):
            color = KyokaTheme.WARNING
            title = f"{warn_icon} Resource Not Found"
            body = "> The target Discord message, channel, or interaction has expired or was removed."
            author_badge = "Expired"

        elif isinstance(error, discord.HTTPException) and getattr(error, "status", 0) == 429:
            logger.error(
                f"Discord REST API 429 Rate Limit active during '{ctx.command}': {error}."
            )
            return

        else:
            # Genuine unexpected failure: generate unique incident ID
            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            logger.error(f"[Incident {incident_id}] Unhandled error in '{ctx.command}': {error}\n{tb}")

            title = f"{err_icon} Internal Error"
            body = (
                f"> An unexpected internal exception interrupted `{ctx.command.qualified_name}`.\n\n"
                f"> 💜 **Diagnostic Incident ID:** `{incident_id}`\n"
                f"> 💜 **Status:** Telemetry securely recorded on host server.\n\n"
                f"> *Please report this Incident ID to bot administrators if the issue persists.*"
            )
            author_badge = "Diagnostic Trace"

        # Apply custom guild UI color if available
        guild = getattr(ctx, "guild", None)
        if guild and hasattr(self.bot, "guild_mgr"):
            custom_color = self.bot.guild_mgr.get_ui_color(guild.id, default=None)
            if isinstance(custom_color, int) and not isinstance(custom_color, bool) and color != KyokaTheme.ERROR:
                color = custom_color

        clean_title = sanitize_emoji_string(title, bot=self.bot)
        clean_body = sanitize_emoji_string(body, bot=self.bot)
        author = getattr(ctx, "author", None)
        cmd_name = getattr(ctx.command, "qualified_name", "unknown")

        container = KyokaContainer(accent_color=color)
        container.add_section(content=f"**{clean_title}**\n{clean_body}")
        container.add_separator(divider=True)
        req_name = getattr(author, "display_name", "User") if author else "User"
        container.add_text(f"-# Requested by {req_name} • ✧ KYOKA Suigetsu Protocol • {ctx.prefix}{cmd_name}")

        try:
            await send_container_response(ctx, container, ephemeral=True)
            return
        except Exception:
            pass

        # Fallback to rich Embed when Components V2 dispatch is unavailable
        embed = discord.Embed(
            title=clean_title[:256],
            description=clean_body[:4000],
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        if author:
            embed.set_author(
                name=f"{author.display_name} • {author_badge}",
                icon_url=author.display_avatar.url,
            )
        footer_icon = self.bot.user.display_avatar.url if getattr(self.bot, "user", None) else None
        embed.set_footer(
            text=f"✧ KYOKA Suigetsu Protocol • {ctx.prefix}{cmd_name}",
            icon_url=footer_icon,
        )

        try:
            inter = getattr(ctx, "interaction", None)
            if inter:
                if inter.response.is_done():
                    await inter.followup.send(embed=embed, ephemeral=True)
                else:
                    await inter.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.reply(embed=embed, mention_author=False)
        except Exception:
            try:
                await ctx.send(embed=embed)
            except Exception as send_err:
                logger.warning(f"Failed to deliver command error embed: {send_err}")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors occurring during slash command execution with signature Kyoka Sovereign embeds."""
        error = getattr(error, "original", error)

        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        command_name = getattr(interaction.command, "qualified_name", None) or "unknown"
        guild_id = interaction.guild_id
        user_id = interaction.user.id if interaction.user else None

        color = KyokaTheme.ERROR
        title = "❌ Slash Command Interrupted"
        author_badge = "Command Alert"

        if isinstance(error, app_commands.CommandOnCooldown):
            color = KyokaTheme.WARNING
            title = "⏳ Cooldown Active"
            body = (
                f"> This command is cooling down to preserve rate limits.\n"
                f"> Please wait `{error.retry_after:.1f}s` before trying `/{command_name}` again."
            )
            author_badge = "Rate Limited"

        elif isinstance(error, (app_commands.MissingPermissions, app_commands.BotMissingPermissions, app_commands.CheckFailure)):
            title = "🔒 Access Denied"
            body = f"> {str(error) or 'You do not have permission to execute this slash command in this channel.'}"
            author_badge = "Access Denied"

        elif isinstance(error, discord.Forbidden):
            title = "🔒 Action Forbidden (Discord 403)"
            body = (
                "> Discord rejected this operation because KYOKA lacks the necessary server permissions, "
                "or the target user/role is higher than or equal to KYOKA in the role hierarchy."
            )
            author_badge = "Hierarchy Constraint"

        elif "wavelink" in type(error).__module__ or any(k in type(error).__name__ for k in ("NoNodeAvailable", "Lavalink", "NodeException")):
            color = 0xEC4899
            title = "🎵 Audio Protocol Synchronizing"
            body = (
                "> The audio streaming node is currently synchronizing with Discord voice servers.\n"
                "> Please verify you are in a voice channel and retry in a few moments."
            )
            author_badge = "Audio Protocol"

        else:
            logger.error(
                "[Slash Incident %s] command=%s guild_id=%s user_id=%s "
                "interaction_id=%s error_type=%s error=%s\n%s",
                incident_id,
                command_name,
                guild_id,
                user_id,
                interaction.id,
                type(error).__name__,
                str(error),
                tb,
            )
            title = "❌ Internal Error"
            body = (
                f"> An unexpected internal exception interrupted `/{command_name}`.\n\n"
                f"> 💜 **Diagnostic Incident ID:** `{incident_id}`\n"
                f"> 💜 **Status:** Telemetry securely recorded on host server.\n\n"
                f"> *Please report this Incident ID to bot administrators if the issue persists.*"
            )
            author_badge = "Diagnostic Trace"

        embed = discord.Embed(
            title=sanitize_emoji_string(title, bot=self.bot)[:256],
            description=sanitize_emoji_string(body, bot=self.bot)[:4000],
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        user = interaction.user
        if user:
            embed.set_author(
                name=f"{user.display_name} • {author_badge}",
                icon_url=user.display_avatar.url,
            )

        footer_icon = self.bot.user.display_avatar.url if self.bot.user else None
        embed.set_footer(
            text=f"✧ KYOKA Suigetsu Protocol • /{command_name}",
            icon_url=footer_icon,
        )

        msg = f"❌ **{title}** — `{incident_id}`" if "Internal" in title else f"⚠️ **{title}**"
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(msg, embed=embed, ephemeral=True)
        except (discord.NotFound, discord.InteractionResponded):
            if interaction.channel and hasattr(interaction.channel, "send"):
                try:
                    await interaction.channel.send(msg, embed=embed)
                except Exception:
                    pass
        except Exception as send_err:
            logger.exception("Slash error response failed", exc_info=send_err)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
