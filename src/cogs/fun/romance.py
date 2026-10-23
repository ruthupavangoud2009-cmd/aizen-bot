from __future__ import annotations

import asyncio
import logging
import random
import datetime as dt
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.gif_manager import GIFManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Romance")
PINK = 0xEC4899
ROSE = 0xF43F5E
PURPLE = 0x7C3AED


class ProposalView(discord.ui.View):
    """Interactive proposal view with Accept and Decline buttons."""

    def __init__(self, bot: KyokaBot, proposer: discord.Member, target: discord.Member) -> None:
        super().__init__(timeout=120.0)
        self.bot = bot
        self.proposer = proposer
        self.target = target
        self.value: bool | None = None
        self.gif_mgr = GIFManager()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                f"❌ Only {self.target.mention} can respond to this marriage proposal!",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Accept 💍", style=discord.ButtonStyle.success, custom_id="propose:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        guild_id = interaction.guild_id or 0

        # Save reciprocal marriage in database
        try:
            await self.bot.db.execute(
                "INSERT INTO user_marriages (guild_id, user_id, spouse_id) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, user_id) DO UPDATE SET spouse_id = EXCLUDED.spouse_id, married_at = CURRENT_TIMESTAMP;",
                guild_id, self.proposer.id, self.target.id,
            )
            await self.bot.db.execute(
                "INSERT INTO user_marriages (guild_id, user_id, spouse_id) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, user_id) DO UPDATE SET spouse_id = EXCLUDED.spouse_id, married_at = CURRENT_TIMESTAMP;",
                guild_id, self.target.id, self.proposer.id,
            )
        except Exception as e:
            logger.error(f"Error persisting marriage: {e}")

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif("romance", session=session)

        embed = discord.Embed(
            title="💍 Married in Holy Discord Matrimony!",
            description=(
                f"🎉 **{self.target.mention} said YES to {self.proposer.mention}'s proposal!**\n\n"
                f"May your anime watchlists align, your memes be top-tier, and your ping remain low! 💖"
            ),
            color=PINK,
        )
        if gif_url:
            embed.set_image(url=gif_url)
        embed.set_footer(text="Virtual in-bot marriage • Does not constitute a real-world legal union.")

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Decline 💔", style=discord.ButtonStyle.danger, custom_id="propose:decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif("heartbreak", session=session)

        embed = discord.Embed(
            title="💔 Proposal Declined",
            description=f"**{self.target.mention}** has declined {self.proposer.mention}'s marriage proposal. There are plenty of anime characters in the sea!",
            color=ROSE,
        )
        if gif_url:
            embed.set_image(url=gif_url)

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class Romance(commands.Cog):
    """Wholesome romance, marriage system, virtual dating, flirting, and social relationship actions."""
    category = "Romance & Relationships"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_mgr = GIFManager()

    async def _action_embed(
        self,
        ctx: CustomContext,
        member: discord.Member | None,
        action_key: str,
        verb: str,
        emoji: str,
        phrase: str,
        color: int = PINK,
    ) -> None:
        if member is None:
            await ctx.send(f"Please mention someone. Example: `{ctx.prefix}{ctx.invoked_with} @user`")
            return
        if member.bot:
            await ctx.send("Keep romantic roleplay between human members.")
            return
        if member.id == ctx.author.id:
            await ctx.send("Choose another member for this romantic action.")
            return

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif(action_key, session=session)

        embed = discord.Embed(
            description=f"{emoji} **{ctx.author.mention} {verb} {member.mention}** {phrase}",
            color=color,
        )
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False),
        )

    # ─── 1. MARRIAGE & PROPOSAL ───────────────────────────────────────────────

    @commands.command(
        name="propose",
        aliases=["marry"],
        help="Propose to a server member with an interactive in-bot marriage proposal.",
    )
    @commands.guild_only()
    async def propose(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        """Propose marriage to someone in the server with interactive Accept/Decline buttons."""
        if member is None:
            await ctx.send(f"💍 Mention someone to propose to! Example: `{ctx.prefix}propose @user`")
            return
        if member.bot:
            await ctx.send("🤖 You cannot marry a bot!")
            return
        if member.id == ctx.author.id:
            await ctx.send("Self-love is important, but you cannot marry yourself in the bot!")
            return

        guild_id = ctx.guild.id

        # Check existing marriage for proposer
        author_marriage = await self.bot.db.fetch_one(
            "SELECT spouse_id FROM user_marriages WHERE guild_id = ? AND user_id = ?;",
            guild_id, ctx.author.id,
        )
        if author_marriage and author_marriage.get("spouse_id"):
            spouse_id = author_marriage["spouse_id"]
            return await ctx.send(f"⚠️ You are already married to <@{spouse_id}>! Use `{ctx.prefix}divorce` first.")

        # Check existing marriage for target
        target_marriage = await self.bot.db.fetch_one(
            "SELECT spouse_id FROM user_marriages WHERE guild_id = ? AND user_id = ?;",
            guild_id, member.id,
        )
        if target_marriage and target_marriage.get("spouse_id"):
            spouse_id = target_marriage["spouse_id"]
            return await ctx.send(f"⚠️ {member.mention} is already married to <@{spouse_id}>!")

        view = ProposalView(self.bot, ctx.author, member)
        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif("romance", session=session)

        embed = discord.Embed(
            title="💍 A Romantic Marriage Proposal!",
            description=(
                f"✨ **{ctx.author.mention} got down on one knee and asked {member.mention} to marry them!**\n\n"
                f"{member.mention}, do you take {ctx.author.mention} as your lawfully wedded Discord spouse?"
            ),
            color=PINK,
        )
        if gif_url:
            embed.set_image(url=gif_url)
        embed.set_footer(text="Click Accept or Decline below (expires in 2 minutes)")

        msg = await ctx.send(
            content=f"{member.mention}, you have a marriage proposal!",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False),
        )
        await view.wait()
        if view.value is None:
            try:
                timeout_embed = discord.Embed(
                    title="⌛ Proposal Timed Out",
                    description=f"The marriage proposal from {ctx.author.mention} to {member.mention} received no response.",
                    color=PURPLE,
                )
                await msg.edit(embed=timeout_embed, view=view)
            except Exception:
                pass

    # ─── 2. DIVORCE & BREAKUP ─────────────────────────────────────────────────

    @commands.command(
        name="divorce",
        aliases=["breakup"],
        help="Divorce your current in-bot Discord spouse.",
    )
    @commands.guild_only()
    async def divorce(self, ctx: CustomContext) -> None:
        """Divorce your current Discord spouse and clear your marriage record."""
        guild_id = ctx.guild.id
        marriage = await self.bot.db.fetch_one(
            "SELECT spouse_id FROM user_marriages WHERE guild_id = ? AND user_id = ?;",
            guild_id, ctx.author.id,
        )
        if not marriage or not marriage.get("spouse_id"):
            return await ctx.send("💔 You are not currently married to anyone in this server.")

        spouse_id = int(marriage["spouse_id"])
        await self.bot.db.execute(
            "DELETE FROM user_marriages WHERE guild_id = ? AND (user_id = ? OR user_id = ?);",
            guild_id, ctx.author.id, spouse_id,
        )

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif("heartbreak", session=session)

        embed = discord.Embed(
            title="💔 Divorce Finalized",
            description=f"**{ctx.author.mention} and <@{spouse_id}> are now officially divorced.** The virtual rings have been returned.",
            color=ROSE,
        )
        if gif_url:
            embed.set_image(url=gif_url)
        await ctx.send(embed=embed)

    # ─── 3. RELATIONSHIP / COUPLE STATUS ──────────────────────────────────────

    @commands.command(
        name="relationship",
        aliases=["couple", "marriage"],
        help="Check who you or another member are married to.",
    )
    @commands.guild_only()
    async def relationship(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        """View marriage standing and anniversary duration."""
        target = member or ctx.author
        guild_id = ctx.guild.id

        row = await self.bot.db.fetch_one(
            "SELECT spouse_id, married_at FROM user_marriages WHERE guild_id = ? AND user_id = ?;",
            guild_id, target.id,
        )
        if not row or not row.get("spouse_id"):
            return await ctx.send(f"👤 **{target.display_name}** is currently single and ready to mingle!")

        spouse_id = int(row["spouse_id"])
        married_at = row.get("married_at")
        since_str = f"<t:{int(married_at.timestamp())}:R>" if married_at else "recently"

        embed = discord.Embed(
            title=f"💖 Relationship Status • {target.display_name}",
            description=f"**{target.mention}** is happily married to **<@{spouse_id}>**!\n\n📅 **Married:** {since_str} 💍",
            color=PINK,
        )
        await ctx.send(embed=embed)

    # ─── 4. ROMANCE ACTIONS ───────────────────────────────────────────────────

    @commands.command(name="kiss", help="Send someone a playful anime kiss.")
    async def kiss(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "kissed", "kissed", "💋", "with sweet affection! 💖")

    @commands.command(name="makeout", help="Passionately make out with someone in anime roleplay.")
    async def makeout(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "makeout", "is passionately making out with", "🔥", "— get a room! 💋")

    @commands.command(name="love", help="Express heartfelt anime love to someone.")
    async def love(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "love", "sends boundless love to", "💖", "with all their heart! 🥰")

    @commands.command(name="crush", help="Check your crush or confess playfully.")
    async def crush(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        if member is None:
            pct = random.randint(10, 100)
            return await ctx.send(f"💘 Your current server crush-meter is at **{pct}%**! Keep your eyes open. 👀")
        await self._action_embed(ctx, member, "crush", "has a massive crush on", "😳", "— their heart is racing! 💓")

    @commands.command(name="date", help="Take someone on a dreamy anime date.")
    async def date(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        dates = ["to a rooftop stargazing dinner", "to a lovely seaside ramen shop", "to an arcade fun park", "on an enchanting sunset walk"]
        await self._action_embed(ctx, member, "date", "takes", "🕯️", f"{random.choice(dates)}! 🌸")

    @commands.command(name="jealous", help="Show playful anime jealousy.")
    async def jealous(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "jealous", "is pouting with jealousy at", "😤", "— pay attention to them! 💢")

    @commands.command(name="flirt", help="Send a charming flirt to someone.")
    async def flirt(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        flirts = [
            "Are you a magician? Because whenever I look at you, everyone else disappears. ✨",
            "Do you have a map? I keep getting lost in your eyes. 💫",
            "If being cute was a crime, you'd be serving a life sentence. 💖",
            "Is your name Wi-Fi? Because I'm feeling an undeniable connection. 📶",
        ]
        if member is None:
            return await ctx.send(f"😏 **Flirt line:** {random.choice(flirts)}")
        await ctx.send(f"😏 **{ctx.author.mention} whispers to {member.mention}:**\n> *\"{random.choice(flirts)}\"*")

    @commands.command(name="pickup", help="Drop a smooth anime pickup line.")
    async def pickup(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        lines = [
            "Are you from the Soul Society? Because you just purified my heart. 🌸",
            "Are you a Zanpakuto? Because hearing your name releases my ultimate bankai. ⚔️",
            "Are you an S-tier devil fruit? Because you've completely enchanted my world. 🍇",
            "Did Kyōka Suigetsu cast a spell, or are you genuinely this mesmerizing? 🌙",
        ]
        if member is None:
            return await ctx.send(f"✨ **Pickup line:** {random.choice(lines)}")
        await ctx.send(f"✨ **{ctx.author.mention} drops a line for {member.mention}:**\n> *\"{random.choice(lines)}\"*")

    @commands.command(name="compliment", help="Send someone a heartfelt, wholesome compliment.")
    async def compliment(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        compliments = [
            "You radiate incredible main-character energy.",
            "Your kindness brightens every server you join.",
            "Your taste and humor are unmatched.",
            "Talking to you is always the highlight of the day.",
        ]
        if member is None:
            return await ctx.send(f"Please mention someone. Example: `{ctx.prefix}compliment @user`")
        await ctx.send(f"🌸 **{ctx.author.mention} compliments {member.mention}:** {random.choice(compliments)}")

    @commands.command(name="cuddle", help="Warmly cuddle someone in anime roleplay.")
    async def cuddle(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "cuddled", "cuddles", "🫂", "snug and warm! 🤍")

    @commands.command(name="hug", help="Send someone a comforting, warm anime hug.")
    async def hug(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "hugged", "wraps", "💜", "in a warm, friendly hug! ✨")

    @commands.command(name="romance", help="Set a romantic mood with an anime couple reaction.")
    async def romance(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "romance", "shares a romantic anime moment with", "🌹", "under the twilight sky. ✨")

    @commands.command(name="heartbreak", help="Express dramatic anime heartbreak.")
    async def heartbreak(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        if member:
            await self._action_embed(ctx, member, "heartbreak", "suffered intense heartbreak from", "💔", "— cue the dramatic rain! 🌧️")
        else:
            session = getattr(self.bot, "session", None)
            gif_url = await self.gif_mgr.get_action_gif("heartbreak", session=session)
            embed = discord.Embed(description=f"💔 **{ctx.author.mention}'s heart just shattered!** Cue the sorrowful violin...", color=ROSE)
            if gif_url:
                embed.set_image(url=gif_url)
            await ctx.send(embed=embed)

    @commands.command(name="reject", help="Playfully reject a romantic advance.")
    async def reject(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "reject", "coldly rejected", "🙅‍♀️", "with a swift anime dodge! 💨")

    @commands.command(name="confess", help="Confess your true feelings in dramatic anime fashion.")
    async def confess(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._action_embed(ctx, member, "confess", "confesses their deepest feelings to", "💌", "while blushing furiously! 🌸")

    @commands.command(name="rizz", help="Unleash or test your ultimate anime rizz.")
    async def rizz(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        score = random.randint(50, 100)
        if member:
            await ctx.send(f"🔥 **{ctx.author.mention} deployed their Rizz on {member.mention}!**\n> Impact Rating: **{score}/100 W Rizz** 😏")
        else:
            await ctx.send(f"🔥 **{ctx.author.display_name}'s Natural Rizz Level:** **{score}/100** Unstoppable charisma!")

    @commands.command(name="ship", aliases=["compatibility"], help="Calculate two members' scientific romance compatibility.")
    async def ship(self, ctx: CustomContext, first: discord.Member, second: discord.Member | None = None) -> None:
        second = second or ctx.author
        score = random.randint(5, 100)
        bar = "💖" * (score // 10) + "🖤" * (10 - score // 10)
        verdict = "Soulmates written in the stars! ✨" if score > 80 else ("Pretty good chemistry! 💕" if score > 50 else "Friendzone territory! 🤝")

        embed = discord.Embed(
            title="💘 Romance Compatibility Scan",
            description=f"**{first.display_name}** × **{second.display_name}**\n\n{bar} **{score}%**\n\n> {verdict}",
            color=PINK,
        )
        await ctx.send(embed=embed)

    @commands.command(name="soulmate", help="Find out who your cosmic soulmate could be.")
    async def soulmate(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        members = [m for m in ctx.guild.members if not m.bot and m.id != target.id] if ctx.guild else []
        matched = random.choice(members) if members else target
        pct = random.randint(85, 100)
        await ctx.send(f"🔮 **Cosmic Soulmate Match:** {target.mention} is {pct}% destined to be with {matched.mention}! ✨")

    @commands.command(name="loveletter", help="Compose a whimsical anime love letter to someone.")
    async def loveletter(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        if member is None:
            return await ctx.send(f"Please mention someone to send a love letter to. Example: `{ctx.prefix}loveletter @user`")
        letters = [
            f"Dear {member.display_name},\nEvery second without your messages feels like a filler episode. You're my favorite canon plot. Forever yours, {ctx.author.display_name}. 💌",
            f"Dear {member.display_name},\nEven if the server goes offline and discord servers collapse, my affinity for you stays 100%. Signed, {ctx.author.display_name}. 🌸",
        ]
        embed = discord.Embed(
            title="💌 A Handwritten Anime Love Letter",
            description=random.choice(letters),
            color=PINK,
        )
        embed.set_footer(text=f"Sent with love from {ctx.author.display_name}")
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Romance(bot))
