from __future__ import annotations

import logging
import traceback
import uuid
import discord
from discord import app_commands
from discord.ext import commands

from src.utils.containers import KyokaContainer, send_container_response
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.ErrorHandler")


def _error_emoji(bot: commands.Bot, *names: str, fallback: str = "") -> str:
    """Resolve an emoji defensively; prefer animated custom application emojis."""
    registry = getattr(bot, "custom_emojis", None)
    if registry is None:
        return fallback
    for name in names:
        try:
            emoji = registry.get_emoji_obj(name)
            if emoji is not None and getattr(emoji, "animated", False):
                return str(emoji)
        except Exception:
            continue
    for name in names:
        try:
            emoji = registry.get_emoji_obj(name)
            if emoji is not None:
                return str(emoji)
        except Exception:
            continue
    return fallback


class ErrorHandler(commands.Cog, name="ErrorHandler"):
    """Global listener for prefix, hybrid, and slash command errors with secure diagnostic incident tracking."""

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
            # Do not silently swallow a missing vouch command: that made a
            # failed Vouches extension look like the bot ignored the message.
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
                        "The vouch module is not loaded right now. The bot has logged the extension failure; "
                        "please check the latest Render startup logs.",
                        mention_author=False,
                    )
                except Exception:
                    pass
            return

        err_icon = _error_emoji(self.bot, "ERROR", "icons_wrong", "icon_x", fallback="")
        warn_icon = _error_emoji(self.bot, "WARNING", "icons_warning", "icon_warning", fallback="")
        clock_icon = _error_emoji(self.bot, "TIME", "icons_clock", "loading", fallback="")
        lock_icon = _error_emoji(self.bot, "LOCK", "icons_locked", "icon_lock", fallback="")

        err_sp = f"{err_icon} " if err_icon else ""
        warn_sp = f"{warn_icon} " if warn_icon else ""
        clock_sp = f"{clock_icon} " if clock_icon else ""
        lock_sp = f"{lock_icon} " if lock_icon else ""

        container = KyokaContainer(accent_color=None)

        if isinstance(error, commands.MissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_sp}Permission Denied**\n"
                    f"> You need the following permissions to execute this command:\n> {missing_perms}"
                )
            )

        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_sp}Bot Missing Permissions**\n"
                    f"> I need the following permissions in this channel:\n> {missing_perms}"
                )
            )

        elif isinstance(error, commands.CommandOnCooldown):
            container.add_section(
                content=(
                    f"**{clock_sp}Cooldown Active**\n"
                    f"> This command is currently on cooldown. Try again in `{error.retry_after:.1f}s`."
                )
            )

        elif type(error).__name__ == "PremiumRequiredError":
            return

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            container.add_section(
                content=(
                    f"**{lock_sp}Access Denied**\n"
                    f"> {str(error) or 'You do not have permission to use this command.'}"
                )
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            container.add_section(
                content=(
                    f"**{warn_sp}Invalid Command Usage**\n"
                    f"> Missing required parameter: `{error.param.name}`\n"
                    f"> Usage: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
                )
            )

        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            container.add_section(
                content=(
                    f"**{warn_sp}User Not Found**\n"
                    f"> Could not find a member or user matching `{discord.utils.escape_markdown(str(error.argument))}`.\n"
                    f"> *Tip: Try mentioning the user (@User) or providing their 17–19 digit Discord ID.*"
                )
            )

        elif isinstance(error, commands.ChannelNotFound):
            container.add_section(
                content=(
                    f"**{warn_sp}Channel Not Found**\n"
                    f"> Could not find channel `{discord.utils.escape_markdown(str(error.argument))}`."
                )
            )

        elif isinstance(error, commands.RoleNotFound):
            container.add_section(
                content=(
                    f"**{warn_sp}Role Not Found**\n"
                    f"> Could not find role `{discord.utils.escape_markdown(str(error.argument))}`."
                )
            )

        elif isinstance(error, commands.BadUnionArgument):
            container.add_section(
                content=(
                    f"**{warn_sp}Invalid Argument**\n"
                    f"> Could not resolve `{error.param.name}`. Please mention a valid user/role or provide an ID."
                )
            )

        elif isinstance(error, commands.BadLiteralArgument):
            options = ", ".join(f"`{opt}`" for opt in error.literals)
            container.add_section(
                content=(
                    f"**{warn_sp}Invalid Choice**\n"
                    f"> Valid options for `{error.param.name}` are: {options}"
                )
            )

        elif isinstance(error, commands.RangeError):
            container.add_section(
                content=(
                    f"**{warn_sp}Value Out of Range**\n"
                    f"> `{error.value}` is out of range. Must be between `{error.minimum}` and `{error.maximum}`."
                )
            )

        elif isinstance(error, commands.TooManyArguments):
            container.add_section(
                content=(
                    f"**{warn_sp}Too Many Arguments**\n"
                    f"> Too many arguments were passed to `{ctx.command.qualified_name}`.\n"
                    f"> Usage: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
                )
            )

        elif isinstance(error, commands.BadArgument):
            container.add_section(
                content=(
                    f"**{warn_sp}Invalid Command Argument**\n"
                    f"> {str(error)}\n"
                    f"> Usage: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
                )
            )

        elif isinstance(error, discord.HTTPException) and error.status == 429:
            logger.error(
                f"Discord REST API 429 Rate Limit active during '{ctx.command}': {error}. "
                "Suppressing error message response to avoid extending rate limit window."
            )
            return

        else:
            # Genuine unexpected failure: generate unique incident ID
            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            logger.error(f"[Incident {incident_id}] Unhandled error in '{ctx.command}': {error}\n{tb}")

            container.add_section(
                content=(
                    f"**{err_icon}Internal Error**\n"
                    f"> An unexpected error occurred while executing this command.\n"
                    f"> **Diagnostic Incident ID:** `{incident_id}`\n"
                    f"> *The incident has been securely recorded on the server. Please report this Incident ID to bot administrators.*"
                )
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        try:
            await send_container_response(ctx, container, ephemeral=True)
        except Exception as send_error:
            logger.warning("Failed to deliver error container; attempting plain-text fallback: %s", type(send_error).__name__)
            try:
                await ctx.reply("KYOKA encountered an error while handling this command. Please try again.", mention_author=False)
            except Exception as fallback_error:
                logger.debug("Plain-text command error fallback also failed: %s", type(fallback_error).__name__)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors occurring during slash command execution."""
        error = getattr(error, "original", error)

        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        # Include safe identifiers so an incident can be traced from the user's
        # Discord error card to Render logs without logging message content or tokens.
        command_name = getattr(interaction.command, "qualified_name", None) or "unknown"
        guild_id = interaction.guild_id
        user_id = interaction.user.id if interaction.user else None
        logger.error(
            "[Slash Incident %s] command=%s guild_id=%s user_id=%s "
            "interaction_id=%s error_type=%s error=%s\\n%s",
            incident_id,
            command_name,
            guild_id,
            user_id,
            interaction.id,
            type(error).__name__,
            str(error),
            tb,
        )

        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ **Cooldown Active:** Please wait `{error.retry_after:.1f}s` before trying again."
        elif isinstance(error, (app_commands.MissingPermissions, app_commands.BotMissingPermissions, app_commands.CheckFailure)):
            msg = f"🔒 **Access Denied:** {str(error) or 'You do not have permission to execute this slash command.'}"
        else:
            msg = (
                f"❌ **Internal Error:** An unexpected error occurred while processing this interaction.\n"
                f"> **Diagnostic Incident ID:** `{incident_id}`\n"
                f"> *Please report this Incident ID to bot administrators.*"
            )

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except (discord.NotFound, discord.InteractionResponded) as send_err:
            # The interaction token may have expired or already been acknowledged.
            logger.warning(
                "Could not deliver slash error card (incident_id=%s command=%s): %s",
                incident_id, command_name, type(send_err).__name__,
            )
            if interaction.channel and hasattr(interaction.channel, "send"):
                try:
                    await interaction.channel.send(msg)
                except Exception:
                    pass
        except Exception as send_err:
            logger.exception(
                "Slash error response failed (incident_id=%s command=%s); "
                "the original callback error is logged above.",
                incident_id, command_name, exc_info=send_err,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
