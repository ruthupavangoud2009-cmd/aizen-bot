"""
KYOKA 3.0 — Community Suggestions Cog with Interactive Voting.
Allows community members to submit feedback and feature ideas.
Integrates with the +setup wizard for easy channel configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Set
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.Suggestions")


class SuggestionVoteView(discord.ui.View):
    """Interactive voting buttons for community suggestions with double-vote prevention."""

    def __init__(self, suggestion_id: int, upvotes: int = 0, downvotes: int = 0) -> None:
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id
        self.upvotes = upvotes
        self.downvotes = downvotes
        self.upvoters: Set[int] = set()
        self.downvoters: Set[int] = set()

    @discord.ui.button(label="Upvote (0)", style=discord.ButtonStyle.success, emoji="👍", custom_id="sug:upvote")
    async def btn_upvote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user_id = interaction.user.id
        if user_id in self.upvoters:
            self.upvoters.remove(user_id)
            self.upvotes = max(0, self.upvotes - 1)
            msg = "Removed your upvote."
        else:
            self.upvoters.add(user_id)
            self.upvotes += 1
            if user_id in self.downvoters:
                self.downvoters.remove(user_id)
                self.downvotes = max(0, self.downvotes - 1)
            msg = "Registered your upvote!"

        # Update button labels
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "sug:upvote":
                    child.label = f"Upvote ({self.upvotes})"
                elif child.custom_id == "sug:downvote":
                    child.label = f"Downvote ({self.downvotes})"

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="Downvote (0)", style=discord.ButtonStyle.danger, emoji="👎", custom_id="sug:downvote")
    async def btn_downvote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user_id = interaction.user.id
        if user_id in self.downvoters:
            self.downvoters.remove(user_id)
            self.downvotes = max(0, self.downvotes - 1)
            msg = "Removed your downvote."
        else:
            self.downvoters.add(user_id)
            self.downvotes += 1
            if user_id in self.upvoters:
                self.upvoters.remove(user_id)
                self.upvotes = max(0, self.upvotes - 1)
            msg = "Registered your downvote!"

        # Update button labels
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "sug:upvote":
                    child.label = f"Upvote ({self.upvotes})"
                elif child.custom_id == "sug:downvote":
                    child.label = f"Downvote ({self.downvotes})"

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(msg, ephemeral=True)


class Suggestions(commands.Cog):
    """Community feedback, suggestions, and voting system."""

    category = "⭐・LEVELS & COMMUNITY"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.command(
        name="suggest",
        aliases=["suggestion"],
        description="Submit a community suggestion or idea for server feedback.",
    )
    @commands.guild_only()
    async def suggest(self, ctx: CustomContext, *, idea: str) -> None:
        """Submit a community suggestion with interactive voting."""
        if not ctx.guild:
            return

        # Check configured channel
        row = await self.bot.db.fetch_one(
            "SELECT channel_id, is_enabled FROM guild_suggestions_settings WHERE guild_id = ?;",
            ctx.guild.id,
        )
        if not row or not row.get("channel_id") or not row.get("is_enabled", True):
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            return await ctx.send(
                "❌ **Suggestions are not configured in this server.**\n"
                f"> Administrators can run `{prefix}setup suggestions #channel` to activate the suggestions channel."
            )

        channel_id = int(row["channel_id"])
        target_channel = ctx.guild.get_channel(channel_id)
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            return await ctx.send(
                f"⚠️ The configured suggestions channel (`#{channel_id}`) was not found.\n"
                f"> An admin can reconfigure it with `{prefix}setup suggestions #channel`."
            )

        # Insert suggestion into database
        insert_row = await self.bot.db.fetch_one(
            """
            INSERT INTO guild_suggestions (guild_id, user_id, channel_id, content, status)
            VALUES (?, ?, ?, ?, 'pending')
            RETURNING id;
            """,
            ctx.guild.id,
            ctx.author.id,
            channel_id,
            idea,
        )
        sug_id = insert_row["id"] if insert_row else 1

        # Build Suggestion Card
        embed = discord.Embed(
            title=f"💡 Suggestion #{sug_id}",
            description=idea,
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=f"{ctx.author.display_name} ({ctx.author})",
            icon_url=ctx.author.display_avatar.url,
        )
        embed.add_field(name="Status", value="`⏳ Under Review`", inline=True)
        embed.set_footer(text=f"Submitted by {ctx.author.id} • Kyoka Suggestions")

        view = SuggestionVoteView(suggestion_id=sug_id)

        try:
            msg = await target_channel.send(embed=embed, view=view)
            await self.bot.db.execute(
                "UPDATE guild_suggestions SET message_id = ? WHERE id = ?;",
                msg.id,
                sug_id,
            )
            await ctx.send(
                f"✅ **Your suggestion has been submitted!**\n> View it in {target_channel.mention}."
            )
        except discord.Forbidden:
            await ctx.send(
                f"⚠️ I don't have permission to send messages in {target_channel.mention}. "
                "Please notify a server administrator."
            )


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Suggestions(bot))
