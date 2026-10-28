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
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        err_icon = f"{e_reg.get('icons_wrong', e_reg.get('icon_x', '❌'))} " if e_reg else "❌ "
        warn_icon = f"{e_reg.get('icons_warning', '⚠️')} " if e_reg else "⚠️ "
        clock_icon = f"{e_reg.get('icons_clock', '⏳')} " if e_reg else "⏳ "
        lock_icon = f"{e_reg.get('icons_locked', e_reg.get('icon_lock', '🔒'))} " if e_reg else "🔒 "

        container = KyokaContainer(accent_color=None)

        if isinstance(error, commands.MissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_icon}Permission Denied**\n"
                    f"> You need the following permissions to execute this command:\n> {missing_perms}"
                )
            )

        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_icon}Bot Missing Permissions**\n"
                    f"> I need the following permissions in this channel:\n> {missing_perms}"
                )
            )

        elif isinstance(error, commands.CommandOnCooldown):
            container.add_section(
                content=(
                    f"**{clock_icon}Cooldown Active**\n"
                    f"> This command is currently on cooldown. Try again in `{error.retry_after:.1f}s`."
                )
            )

        elif type(error).__name__ == "PremiumRequiredError":
            return

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            container.add_section(
                content=(
                    f"**{lock_icon}Access Denied**\n"
                    f"> {str(error) or 'You do not have permission to use this command.'}"
                )
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Command Usage**\n"
                    f"> Missing required parameter: `{error.param.name}`\n"
                    f"> Usage: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
                )
            )

        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            container.add_section(
                content=(
                    f"**{warn_icon}User Not Found**\n"
                    f"> Could not find a member or user matching `{discord.utils.escape_markdown(str(error.argument))}`.\n"
                    f"> *Tip: Try mentioning the user (@User) or providing their 17–19 digit Discord ID.*"
                )
            )

        elif isinstance(error, commands.ChannelNotFound):
            container.add_section(
                content=(
                    f"**{warn_icon}Channel Not Found**\n"
                    f"> Could not find channel `{discord.utils.escape_markdown(str(error.argument))}`."
                )
            )

        elif isinstance(error, commands.RoleNotFound):
            container.add_section(
                content=(
                    f"**{warn_icon}Role Not Found**\n"
                    f"> Could not find role `{discord.utils.escape_markdown(str(error.argument))}`."
                )
            )

        elif isinstance(error, commands.BadUnionArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Argument**\n"
                    f"> Could not resolve `{error.param.name}`. Please mention a valid user/role or provide an ID."
                )
            )

        elif isinstance(error, commands.BadLiteralArgument):
            options = ", ".join(f"`{opt}`" for opt in error.literals)
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Choice**\n"
                    f"> Valid options for `{error.param.name}` are: {options}"
                )
            )

        elif isinstance(error, commands.RangeError):
            container.add_section(
                content=(
                    f"**{warn_icon}Value Out of Range**\n"
                    f"> `{error.value}` is out of range. Must be between `{error.minimum}` and `{error.maximum}`."
                )
            )

        elif isinstance(error, commands.TooManyArguments):
            container.add_section(
                content=(
                    f"**{warn_icon}Too Many Arguments**\n"
                    f"> Too many arguments were passed to `{ctx.command.qualified_name}`.\n"
                    f"> Usage: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
                )
            )

        elif isinstance(error, commands.BadArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Command Argument**\n"
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
        except Exception as e:
            logger.debug(f"Failed to deliver error response container: {e}")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors occurring during slash command execution."""
        error = getattr(error, "original", error)

        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        logger.error(f"[Slash Incident {incident_id}] Error in slash command '{interaction.command}': {error}\n{tb}")

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
        except Exception as send_err:
            logger.debug(f"Failed to send slash error response: {send_err}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
