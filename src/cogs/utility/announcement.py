"""
Kyoka Discord Bot - Announcement Command
Provides reliable broadcast tools for server staff and bot owners.
Sends exact plain-text messages or optional styled embeds to target channels with safe mention handling.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import is_owner_or_staff

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Cogs.Announcement")


class Announcement(commands.Cog):
    """Reliable announcement and broadcast delivery system."""
    category: str = "Utility"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.command(
        name="send",
        description="Send a message to a channel and delete the command message.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def send_message(
        self,
        ctx: CustomContext,
        channel: discord.TextChannel,
        *,
        message: str,
    ) -> None:
        """Send a plain-text message, then remove the invoking command."""
        if not ctx.guild or channel.guild.id != ctx.guild.id:
            return await ctx.send_error("Choose a text channel in this server.")

        content = message.strip()
        if not content:
            return await ctx.send_error("Message cannot be empty.")

        bot_member = ctx.guild.me
        if not bot_member:
            return await ctx.send_error("I could not verify my permissions in this server.")
        command_permissions = ctx.channel.permissions_for(bot_member)
        if not command_permissions.manage_messages:
            return await ctx.send_error("I need Manage Messages here to delete your command message.")
        channel_permissions = channel.permissions_for(bot_member)
        if not channel_permissions.view_channel or not channel_permissions.send_messages:
            return await ctx.send_error(f"I cannot send messages in {channel.mention}.")

        author = ctx.author
        is_staff = is_owner_or_staff(author.id)
        allowed_mentions = discord.AllowedMentions(
            everyone=author.guild_permissions.mention_everyone or is_staff,
            roles=author.guild_permissions.mention_everyone or is_staff,
            users=True,
            replied_user=False,
        )

        try:
            await channel.send(content, allowed_mentions=allowed_mentions)
        except discord.Forbidden:
            return await ctx.send_error(f"I do not have permission to send messages in {channel.mention}.")
        except discord.HTTPException:
            logger.exception("Could not send message to channel %s in guild %s", channel.id, ctx.guild.id)
            return await ctx.send_error(f"Discord could not deliver the message to {channel.mention}.")

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send_error(
                f"Message sent to {channel.mention}, but I need Manage Messages here to delete your command."
            )
        except discord.HTTPException:
            logger.exception("Could not delete send command in guild %s", ctx.guild.id)
            await ctx.send_error(
                f"Message sent to {channel.mention}, but Discord would not let me delete your command."
            )

    @commands.command(
        name="announce",
        description="Broadcast an announcement to a target channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def announce(
        self,
        ctx: CustomContext,
        channel: discord.TextChannel | discord.Thread | discord.VoiceChannel,
        *,
        message: str,
    ) -> None:
        """Send an announcement to the selected channel.
        Usage:
            announce #announcements hi -> sends 'hi'
            announce #announcements --embed Special Announcement! | Details here -> sends embed
        """
        if not ctx.guild:
            return

        # Authorization check: primary owner or staff with manage_messages / administrator
        author = ctx.author
        is_staff = is_owner_or_staff(author.id)
        has_perm = author.guild_permissions.manage_messages or author.guild_permissions.administrator
        if not (is_staff or has_perm):
            return await ctx.send_error("You do not have permission to use the announce command.")

        # Validate target channel permissions
        bot_member = ctx.guild.me
        perms = channel.permissions_for(bot_member)
        if not (perms.send_messages and perms.view_channel):
            return await ctx.send_error(f"I do not have permission to send messages in {channel.mention}.")

        clean_content = message.strip()
        if not clean_content:
            return await ctx.send_error("Announcement message cannot be empty.")

        # Safe mention controls: prevent accidental mass mentions unless authorized
        can_mass_mention = author.guild_permissions.mention_everyone or is_staff
        allowed_mentions = discord.AllowedMentions(
            everyone=can_mass_mention,
            roles=can_mass_mention,
            users=True,
            replied_user=False,
        )

        try:
            # Check if embed mode is requested via --embed flag
            if clean_content.startswith("--embed"):
                embed_text = clean_content[7:].strip()
                title = "📢 Server Announcement"
                body = embed_text

                if "|" in embed_text:
                    parts = embed_text.split("|", 1)
                    title = parts[0].strip() or title
                    body = parts[1].strip()

                embed = discord.Embed(
                    title=title,
                    description=body,
                    color=0x2B0938,
                )
                embed.set_footer(
                    text=f"Posted by {author.display_name} • {ctx.guild.name}",
                    icon_url=author.display_avatar.url if author.display_avatar else None,
                )
                sent_msg = await channel.send(embed=embed, allowed_mentions=allowed_mentions)
            else:
                # Send exact plain text message (e.g. 'announce #announcements hi' -> sends 'hi')
                sent_msg = await channel.send(clean_content, allowed_mentions=allowed_mentions)

            # Response to caller
            conf_text = f"✅ Announcement successfully sent to {channel.mention} ([Jump to Message]({sent_msg.jump_url}))"
            if getattr(ctx, "interaction", None):
                await ctx.send(conf_text, ephemeral=True)
            else:
                await ctx.send(conf_text, delete_after=6)

        except discord.Forbidden:
            await ctx.send_error(f"Failed to post: Missing permissions in {channel.mention}.")
        except Exception as e:
            logger.error(f"Error in announce command: {e}")
            await ctx.send_error(f"An unexpected error occurred while sending the announcement: {e}")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Announcement(bot))
