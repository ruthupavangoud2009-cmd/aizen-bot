from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.gif_manager import GIFManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.AnimeActions")
PURPLE = 0x7C3AED
CYAN = 0x06B6D4


class AnimeActions(commands.Cog):
    """Expressive anime roleplay actions, comedic reactions, and social interactions."""
    category = "Anime Actions"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_mgr = GIFManager()

    async def _action(
        self,
        ctx: CustomContext,
        member: discord.Member | None,
        action_key: str,
        verb_targeted: str,
        verb_solo: str,
        emoji: str,
        tail: str = "",
        allow_solo: bool = True,
    ) -> None:
        if member is None and not allow_solo:
            await ctx.send(f"Please mention someone. Example: `{ctx.prefix}{ctx.invoked_with} @user`")
            return
        if member and member.bot:
            await ctx.send("Keep anime roleplay interactions between human members.")
            return
        if member and member.id == ctx.author.id and not allow_solo:
            await ctx.send("Choose another member for this playful interaction.")
            return

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif(action_key, session=session)

        if member:
            desc = f"{emoji} **{ctx.author.mention} {verb_targeted} {member.mention}!** {tail}".strip()
            targets = [ctx.author, member]
        else:
            desc = f"{emoji} **{ctx.author.mention} {verb_solo}!** {tail}".strip()
            targets = [ctx.author]

        embed = discord.Embed(description=desc, color=PURPLE)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=targets, roles=False, everyone=False),
        )

    # ─── PREFIX ANIME ACTIONS ────────────────────────────────────────────────

    @commands.command(name="act", help="Perform an expressive anime reaction or action with high-quality GIFs. Usage: ?act <action> [@member]")
    async def act(
        self,
        ctx: CustomContext,
        action: str,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Prefix command gateway to anime actions."""
        action_val = action.lower().strip()
        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif(action_val, session=session)

        if member:
            desc = f"✨ **{ctx.author.mention} performed {action_val} on {member.mention}!**"
            targets = [ctx.author, member]
        else:
            desc = f"✨ **{ctx.author.mention} performed {action_val}!**"
            targets = [ctx.author]

        embed = discord.Embed(description=desc, color=PURPLE)
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=targets, roles=False, everyone=False),
        )

    @commands.command(name="kill", help="Defeat someone in a fictional anime roleplay duel.")
    async def kill(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "kill", "defeated", "defeated themselves in a training duel", "⚔️", "in an epic fictional anime duel. Respawn and try again! 🌟", allow_solo=False)

    @commands.command(name="punch", help="Punch someone in dramatic anime roleplay.")
    async def punch(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "punch", "lands a serious anime punch on", "throws a rapid combination of air punches", "👊", "Oof! 💥", allow_solo=False)

    @commands.command(name="blast", help="Unleash an anime ki/reiatsu blast.")
    async def blast(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "blast", "unleashes a colossal reiatsu blast at", "powers up a massive kinetic blast", "⚡", "Total obliteration! 🌌")

    @commands.command(name="animekick", aliases=["akick", "kickanime"], help="Fictional anime-style martial arts kick (not moderation).")
    async def animekick(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "kick", "lands a spinning anime roundhouse kick on", "executes a high martial arts kick", "🥋", "Direct hit! 💥", allow_solo=False)

    @commands.command(name="slap", help="Give someone a comedic anime slap.")
    async def slap(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "slapped", "slapped", "winds up a theatrical anime slap", "🪭", "A flawless illusion! ✨", allow_solo=False)

    @commands.command(name="bonk", help="Give someone a harmless cartoon bonk.")
    async def bonk(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "bonked", "bonked", "bonks the air", "🔨", "with a harmless cartoon bonk!", allow_solo=False)

    @commands.command(name="pat", help="Give someone a gentle anime headpat.")
    async def pat(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "patted", "pats", "pats their own head", "✨", "gently on the head. Good job! 🌸", allow_solo=False)

    @commands.command(name="poke", help="Poke someone to get their attention.")
    async def poke(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "poked", "pokes", "pokes the screen", "👉", "Boop! 💫", allow_solo=False)

    @commands.command(name="bite", help="Playfully bite someone in anime fashion.")
    async def bite(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "bite", "took a playful bite out of", "chomps playfully", "🦷", "Nom nom nom! 🐱", allow_solo=False)

    @commands.command(name="yeet", help="Yeet someone across the server horizon.")
    async def yeet(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "yeet", "yeeted", "yeeted themselves into orbit", "🚀", "into the stratosphere! Begone! 💨", allow_solo=False)

    @commands.command(name="highfive", help="Give someone a high five.")
    async def highfive(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "high-fived", "gives a crisp high-five to", "high-fives the mirror", "🙌", "Teamwork makes the dream work! ⭐", allow_solo=False)

    @commands.command(name="stare", help="Stare intensely at someone.")
    async def stare(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "stare", "is staring intensely at", "is staring blankly into the abyss", "👁️", "— not blinking once. 😶")

    @commands.command(name="scare", help="Jump out and scare someone.")
    async def scare(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "scare", "jumped out and scared", "is trembling with fright", "👻", "BOO! Jump-scare delivered! 😱", allow_solo=False)

    @commands.command(name="laugh", help="Burst out into anime laughter.")
    async def laugh(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "laugh", "is laughing hysterically at", "is laughing uncontrollably", "🤣", "Bahaha! That's hilarious! 💀")

    @commands.command(name="dance", help="Break into an energetic anime dance.")
    async def dance(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "dance", "is dancing happily with", "is busting incredible dance moves", "💃", "Look at those rhythm skills! 🎶")

    @commands.command(name="cry", help="Weep anime tears of sorrow or joy.")
    async def cry(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "cry", "is crying on the shoulder of", "is crying anime waterfalls", "😭", "The sorrow is real! 🌧️")

    @commands.command(name="rage", help="Fly into an all-out anime rage.")
    async def rage(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "rage", "is raging furiously at", "is powering up in sheer blind rage", "💢", "Their power level is skyrocketing! 🌋")

    @commands.command(name="wave", help="Wave hello or goodbye with an anime GIF.")
    async def wave(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "wave", "waves enthusiastically at", "waves hello to everyone in the channel", "👋", "Hello there! ✨")

    @commands.command(name="wink", help="Wink at someone with a charming anime GIF.")
    async def wink(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "wink", "winks playfully at", "gives a charming wink", "😉", "Aizen knows something you don't. ✨")

    @commands.command(name="embarrass", help="Act completely flustered and embarrassed.")
    async def embarrass(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "embarrass", "got intensely flustered by", "is mortified and hiding their face", "😳", "Steam is rising from their ears! 💨")

    @commands.command(name="dramatic", help="Perform a dramatic anime pose or scene.")
    async def dramatic(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "dramatic", "strikes a dramatic anime pose confronting", "strikes an ultra-dramatic main-character pose", "🎭", "Cue the cinematic lighting! 🎬")

    @commands.command(name="angry", help="Pout or storm off in anime anger.")
    async def angry(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "angry", "is furious with", "is pouting angrily", "😠", "Hmph! Don't talk to them right now! 💢")

    @commands.command(name="shy", help="Act adorably shy and timid.")
    async def shy(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "shy", "fidgets shyly around", "is feeling super shy", "👉👈", "Can barely look you in the eyes... 🌸")

    @commands.command(name="facepalm", help="Do a dramatic anime facepalm.")
    async def facepalm(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "facepalm", "facepalms at the actions of", "facepalms in utter disbelief", "🤦", "Why are we like this? 💀")

    @commands.command(name="laughat", help="Point and laugh playfully at someone.")
    async def laughat(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "laugh", "points and laughs hysterically at", "laughs at the absurdity of it all", "👉😆", "Classic moment! 👏", allow_solo=False)

    @commands.command(name="crywith", help="Cry together with a fellow member.")
    async def crywith(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "cry", "is weeping in solidarity with", "sheds a tear for the world", "🫂😭", "Stay strong, comrades! 🤍", allow_solo=False)

    @commands.command(name="comfort", help="Comfort and reassure someone.")
    async def comfort(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "comfort", "comforts and reassures", "finds comfort in calm thoughts", "🤍", "Everything is going to be okay. ✨", allow_solo=False)

    @commands.command(name="cheer", help="Cheer someone on with maximum enthusiasm.")
    async def cheer(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "cheer", "cheers loudly for", "cheers enthusiastically", "📣", "You've got this! Gambatte! 🌟")

    @commands.command(name="celebrate", help="Celebrate a big win or milestone.")
    async def celebrate(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "celebrate", "celebrates victory together with", "is throwing a massive celebration party", "🎉", "Pop the confetti! 🥳")

    @commands.command(name="mock", help="Playfully mock someone.")
    async def mock(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "mock", "is playfully mocking", "mocks the situation", "🤪", "“Oh look at me, I'm so cool!” 🙃", allow_solo=False)

    @commands.command(name="explode", help="Completely explode in dramatic fashion.")
    async def explode(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "explode", "causes a massive explosion around", "spontaneously explodes into sparks", "💥", "BOOOOOM! 💣")

    @commands.command(name="dodge", help="Smoothly dodge an attack or awkward question.")
    async def dodge(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "dodge", "effortlessly dodged the attack from", "matrix-dodges through the room", "💨", "Too slow! Can't touch this! ⚡")

    @commands.command(name="flex", help="Flex your anime muscles or achievements.")
    async def flex(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "flex", "flexes their superiority over", "flexes their undeniable dominance", "💪", "Witness peak performance! 👑")

    @commands.command(name="scream", help="Scream at the top of your lungs.")
    async def scream(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "scream", "screams directly at", "screams into the endless void", "😱", "AAAAAAAHHHHHHH! 🔊")

    @commands.command(name="sleep", help="Fall asleep peacefully.")
    async def sleep(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "sleep", "falls asleep peacefully next to", "drifts into a deep slumber", "💤", "Goodnight, world! 🌙")

    @commands.command(name="wake", help="Wake someone up or shake off sleep.")
    async def wake(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "wake", "shakes and wakes up", "wakes up bright and early", "⏰", "Rise and shine, sleeping beauty! ☀️")

    @commands.command(name="vibe", help="Vibe and chill to anime beats.")
    async def vibe(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "vibe", "vibes to lo-fi anime beats with", "is chilling and vibing to the rhythm", "🎧", "Immaculate vibes only. 🎵")

    @commands.command(name="reaction", help="Share a random dramatic anime reaction GIF.")
    async def reaction(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "reaction", "drops an epic reaction for", "drops a timeless anime reaction", "✨", "Pure cinema. 🎬")

    @commands.command(name="blush", help="Show a blushing anime reaction.")
    async def blush(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "shy", "blushes adorably at", "blushes warmly", "🌸", "So cute! 🥺")

    @commands.command(name="happy", help="Show a happy anime reaction.")
    async def happy(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "celebrate", "beams happily with", "is overflowing with happiness", "✨", "Pure joy! 🌟")

    @commands.command(name="sleepy", help="Show a sleepy anime reaction.")
    async def sleepy(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "sleep", "yawns sleepily next to", "is getting super sleepy", "🥱", "Time for a nap... 💤")

    @commands.command(name="thumbsup", help="Give an encouraging thumbs-up reaction.")
    async def thumbsup(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "cheer", "gives a proud thumbs-up to", "gives an enthusiastic thumbs-up", "👍", "Approved! ⭐")

    @commands.command(name="shrug", help="Show an anime shrug reaction.")
    async def shrug(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "vibe", "shrugs casually at", "shrugs indifference", "🤷", "Who knows? ¯\\_(ツ)_/¯")

    @commands.command(name="killme", help="Comedic dramatic collapse anime reaction (comedy only).")
    async def killme(self, ctx: CustomContext, member: discord.Member | None = None):
        await self._action(ctx, member, "dramatic", "collapses from dramatic embarrassment at", "collapses dramatically onto the floor", "😵", "The comedy is too strong! 💀")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(AnimeActions(bot))
