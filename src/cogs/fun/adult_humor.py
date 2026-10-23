from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.gif_manager import GIFManager
from src.security.adult_guard import authorize_adult, is_adult_authorized

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.AdultHumor")
ROSE = 0xF43F5E
DARK_PINK = 0xBE185D


class AdultHumor(commands.Cog):
    """Playful, non-explicit adult-oriented comedy, suggestive anime reactions, and thirst humor.
    STRICTLY RESTRICTED: Requires explicit authorization in ADULT_COMMAND_ALLOWLIST.
    """
    category = "Adult Humor — Restricted"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_mgr = GIFManager()

    async def cog_check(self, ctx: CustomContext) -> bool:
        """Cog-wide security check: Fail closed if author is not in ADULT_COMMAND_ALLOWLIST."""
        return await authorize_adult(ctx, action_name=ctx.command.name if ctx.command else "adult_humor")

    async def _adult_action(
        self,
        ctx: CustomContext,
        member: discord.Member | None,
        action_key: str,
        verb: str,
        emoji: str,
        tail: str,
        allow_self: bool = False,
    ) -> None:
        if member is None and not allow_self:
            await ctx.send(f"Please mention someone. Example: `{ctx.prefix}{ctx.invoked_with} @user`")
            return
        if member and member.bot:
            await ctx.send("Keep playful interactions between human members.")
            return
        if member and member.id == ctx.author.id and not allow_self:
            await ctx.send("Choose another member for this playful interaction.")
            return

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif(action_key, session=session)

        target_text = member.mention if member else "the whole room"
        embed = discord.Embed(
            description=f"{emoji} **{ctx.author.mention} {verb} {target_text}!** {tail}",
            color=ROSE,
        )
        if gif_url:
            embed.set_image(url=gif_url)
        embed.set_footer(text="Adult Humor [Restricted] • Consenting fictional anime roleplay")

        targets = [ctx.author]
        if member:
            targets.append(member)

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=targets, roles=False, everyone=False),
        )

    # ─── 1. GOON & GOONREACTION ───────────────────────────────────────────────

    @commands.command(name="goon", help="Drop an unhinged, comedic goon-mode anime reaction.")
    async def goon(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "goon", "is in full unhinged goon mode over", "🌀", "— someone confiscate their device! 💀", allow_self=True)

    @commands.command(name="goonreaction", help="Share a dramatic anime goon reaction GIF.")
    async def goonreaction(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "goon", "dropped an unhinged goon reaction at", "👀", "— eyes glued to the screen! 😵‍💫", allow_self=True)

    # ─── 2. SMASH ─────────────────────────────────────────────────────────────

    @commands.command(name="smash", help="Smash or pass? Deliver an enthusiastic fictional smash verdict.")
    async def smash(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "smash", "confidently declared SMASH on", "💥", "— without a single second of hesitation! 🔥")

    # ─── 3. THIRST & DOWNBAD ──────────────────────────────────────────────────

    @commands.command(name="thirst", help="Express unquenchable comedic thirst.")
    async def thirst(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "thirst", "is dangerously thirsting over", "🥤", "— get this person a glass of water ASAP! 💦", allow_self=True)

    @commands.command(name="downbad", help="Call out astronomical levels of being down bad.")
    async def downbad(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "downbad", "caught someone being astronomically down bad for", "📉", "— down catastrophic! 💀", allow_self=True)

    @commands.command(name="downbadcheck", help="Check someone's astronomical down-bad percentage.")
    async def downbadcheck(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        score = random.randint(40, 100)
        bar = "🚨" * (score // 10) + "⬛" * (10 - score // 10)
        diagnosis = "Needs an emergency cold shower! 🚿" if score > 80 else ("Dangerously close to the edge! ⚠️" if score > 60 else "Manageable condition. 👍")

        embed = discord.Embed(
            title="📉 Down-Bad Diagnostic Scanner [Restricted]",
            description=f"**Target:** {target.mention}\n\n{bar} **{score}% Down Bad**\n\n> **Diagnosis:** {diagnosis}",
            color=DARK_PINK,
        )
        await ctx.send(embed=embed)

    # ─── 4. HORNYBONK ─────────────────────────────────────────────────────────

    @commands.command(name="hornybonk", help="Send someone straight to horny jail with a giant anime bonk.")
    async def hornybonk(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "hornybonk", "swung the mega titanium bat and sent", "🔨", "straight to horny jail! BONK! 🚨")

    # ─── 5. SEDUCE ───────────────────────────────────────────────────────────

    @commands.command(name="seduce", help="Attempt a playful anime seduction maneuver.")
    async def seduce(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "seduce", "deploys a sultry seduction pose towards", "🌹", "— the room temperature just spiked! 💋")

    # ─── 6. SPANK ─────────────────────────────────────────────────────────────

    @commands.command(name="spank", help="Deliver a playful cartoon anime spank.")
    async def spank(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "spank", "playfully spanks", "👋", "for behaving badly! Naughty! 💢")

    # ─── 7. WILDREACTION & ADULTREACTION ──────────────────────────────────────

    @commands.command(name="wildreaction", help="Send a wild suggestive anime reaction.")
    async def wildreaction(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "wildreaction", "is having a wildly flustered reaction because of", "🌶️", "— too spicy to handle! 🔥", allow_self=True)

    @commands.command(name="adultreaction", help="Send an adult anime reaction GIF.")
    async def adultreaction(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "adultreaction", "shared a suggestive mature reaction with", "😏", "— iykyk! ✨", allow_self=True)

    # ─── 8. SIMP & OBSESSED ───────────────────────────────────────────────────

    @commands.command(name="simp", help="Bow down and simp shamelessly.")
    async def simp(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "simp", "is shamelessly simping on main for", "🛐", "— crown them the head of the fan club! 👑")

    @commands.command(name="obsessed", help="Completely lose your mind with an obsession reaction.")
    async def obsessed(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "obsessed", "is uncontrollably obsessed with", "😵", "— thinking about them 24/7! 💫", allow_self=True)

    # ─── 9. FANTASIZE & TEASE ─────────────────────────────────────────────────

    @commands.command(name="fantasize", help="Daydream and fantasize about spicy anime scenarios.")
    async def fantasize(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "fantasize", "is daydreaming spicy scenarios starring", "💭", "— blushing from ear to ear! 🌸")

    @commands.command(name="tease", help="Playfully tease someone with cheeky anime banter.")
    async def tease(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "tease", "cheekily teases", "😜", "— don't get all flustered now! 😏")

    # ─── 10. BEDROOMEYES & CAUGHTLACKING ───────────────────────────────────────

    @commands.command(name="bedroomeyes", help="Give someone seductive anime bedroom eyes.")
    async def bedroomeyes(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "bedroomeyes", "gives captivating bedroom eyes to", "🫦", "— the tension is palpable. ✨")

    @commands.command(name="caughtlacking", help="Expose someone for getting caught lacking.")
    async def caughtlacking(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        await self._adult_action(ctx, member, "caughtlacking", "caught", "📸", "lacking in 4K UHD 60FPS! Caught red-handed! 🚨")

    # ─── 11. RATEATTRACTION ───────────────────────────────────────────────────

    @commands.command(name="rateattraction", help="Give someone a spicy attraction score out of 100.")
    async def rateattraction(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        score = random.randint(70, 100)
        verdict = "Drop-dead gorgeous anime protagonist! 🔥" if score > 90 else "Absolute smoke-show! 💅"

        embed = discord.Embed(
            title="✨ Attraction Rating Scanner [Restricted]",
            description=f"**Target:** {target.mention}\n\nRating: **{score}/100**\n\n> {verdict}",
            color=ROSE,
        )
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(AdultHumor(bot))
