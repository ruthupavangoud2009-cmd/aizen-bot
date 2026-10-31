from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.config import Config, get_invite_url
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


def get_full_advert_template(
    bot_name: str,
    invite_url: str,
    support_url: str,
    website_url: str = "https://aizen-bot.pages.dev/",
    guilds_count: int = 0,
    users_count: int = 0,
) -> str:
    """Generate high-converting, aesthetic Discord-ready advertisement text for promo channels."""
    stats_line = (
        f"> 🌐 **Serving:** `{guilds_count:,}` Servers • `{users_count:,}` Members\n"
        if guilds_count > 0
        else ""
    )

    return (
        f"# ✨ {bot_name.upper()} — The Premier Discord Powerhouse\n"
        f"> *\"Power isn't given. It's taken.\"* — Step into the next generation of server intelligence.\n"
        f"{stats_line}"
        f"> Built for studio-grade lossless music, millisecond autonomous antinuke defense, specialized gaming hubs, and enterprise server automation.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"### 🎵 **STUDIO-GRADE LOSSLESS MUSIC (LAVALINK v4)**\n"
        f"• **24/7 Continuous Streaming** — Ultra-low latency, zero stutter, and continuous background playback.\n"
        f"• **10+ Real-Time DSP Audio Filters** — 8D Audio, Nightcore, Bassboost, Vaporwave, Tremolo, and Karaoke.\n"
        f"• **Multi-Source Support** — Seamless track resolution across YouTube, Spotify, SoundCloud, Apple Music, and direct HTTP/HLS streams.\n"
        f"• **Dynamic Synced Lyrics & Smart Queue** — Real-time lyrics display, autoplay algorithms, and saved user playlists.\n\n"
        f"### 🛡️ **AUTONOMOUS ANTINUKE & ANTI-RAID ENGINE**\n"
        f"• **Sub-Second Intrusion Suppression** — Instant 0.1s quarantine and automatic permission-stripping of rogue administrators.\n"
        f"• **Full Attack Surface Defense** — Protects channels, roles, webhooks, server vanity URLs, bot integrations, and kick/ban waves.\n"
        f"• **Emergency Snapshot Recovery** — Instant automatic restoration of deleted roles, channels, and permissions after any attempted raid.\n"
        f"• **Granular Whitelist & Extra Owners** — Multi-tiered trusted staff hierarchy with zero false positives.\n\n"
        f"### ⚔️ **PRECISION MODERATION & PRANK DEFENSE**\n"
        f"• **Comprehensive Mod Suite** — Timed timeouts, warns, kicks, bans, purge filters, lockdown toggles, and rich audit logs.\n"
        f"• **Anti-Ping Role Shield** (`+antiping`) — Completely block unauthorized mentions on critical roles (`@Admin`, `@Staff`, `@Announcements`) with automated punishment.\n"
        f"• **Stealth Fake Ban Prank Engine** (`+fakeban`) — Authentic moderation ban card with stealth command deletion, simulated VC kick, and configurable auto-reveal countdown.\n\n"
        f"### 🏴‍☠️ **BLOX FRUITS & GAMING COMMAND CENTER**\n"
        f"• **Live Fruit Value Calculator** — Instant physical & permanent values with demand and trend analytics.\n"
        f"• **Fair Trade Evaluator** — Calculate exact Win / Fair / Lose trade margins before making any deal.\n"
        f"• **Automated Stock Tracker** — Real-time dealer stock notifications, Mirage Island alerts, and raid coordinators.\n"
        f"• **Interactive Companion AI** — In-character anime and gaming companions for voice and text chats.\n\n"
        f"### 🧾 **SERVICE BILLS & REPUTATION LEDGER**\n"
        f"• **Itemized Service Invoices** — Professional transaction receipts for carries, leveling, commissions, and trades.\n"
        f"• **Multi-Currency Support** — Generate bills in Crypto (BTC/ETH/LTC), PayPal, UPI, CashApp, and Robux.\n"
        f"• **Verified Vouch System** — Build trust with verifiable customer reviews, star ratings, and global scammer detection.\n\n"
        f"### 🎫 **ENTERPRISE TICKETS, UTILITIES & AUTOMATION**\n"
        f"• **Smart Interactive Tickets** — Dynamic button/modal panels with lightning-fast interactive HTML transcripts.\n"
        f"• **Join-To-Create Temp Voice Channels** — Automated dynamic voice hubs with interactive user control panels.\n"
        f"• **Community Boosters** — High-speed reaction roles, requirement-filtered giveaways, AFK mention responder, and vanity rewards.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"### 🔗 **OFFICIAL LINKS & ACCESS**\n"
        f"• **Invite {bot_name}:** [Click Here to Invite]({invite_url})\n"
        f"• **Official Support:** [Join Support Server]({support_url})\n"
        f"• **Web Dashboard:** [Visit Official Website]({website_url})\n\n"
        f"-# *Experience unmatched speed, security, and elegance with {bot_name}. Add it to your server today!*"
    )


def get_short_advert_template(
    bot_name: str,
    invite_url: str,
    support_url: str,
    website_url: str = "https://aizen-bot.pages.dev/",
) -> str:
    """Generate compact Discord advertisement text for strict character-limited channels."""
    return (
        f"⚡ **{bot_name.upper()} — The Ultimate All-in-One Discord Powerhouse** ⚡\n\n"
        f"> 🎵 **Studio-Grade Lossless Music** (Lavalink v4, 24/7, 8D/Bassboost/Nightcore, Synced Lyrics)\n"
        f"> 🛡️ **Autonomous Antinuke Shield** (0.1s instant raid quarantine, role/channel auto-recovery)\n"
        f"> ⚔️ **Advanced Moderation & Anti-Ping** (Anti-Ping role protection + Realistic Fake Ban pranks)\n"
        f"> 🍎 **Blox Fruits & Gaming Hub** (Live value calculator, trade evaluator, raid helper & stock alerts)\n"
        f"> 🧾 **Service Bills & Vouch Ledger** (Itemized crypto/fiat receipts & verified customer vouches)\n"
        f"> 🎫 **Smart Tickets & Utilities** (HTML transcripts, Join-to-Create voice, reaction roles & giveaways)\n\n"
        f"🔗 **Invite Now:** {invite_url}\n"
        f"💬 **Support Server:** {support_url}\n"
        f"🌐 **Website:** {website_url}"
    )


class PromoView(discord.ui.View):
    """Interactive link and copy buttons for Kyoka bot promotion."""

    def __init__(
        self,
        invite_url: str,
        support_url: str,
        ad_text: str,
        website_url: str = "https://aizen-bot.pages.dev/",
    ) -> None:
        super().__init__(timeout=None)
        self.ad_text = ad_text

        self.add_item(
            discord.ui.Button(
                label=f"Invite {Config.BOT_NAME}",
                style=discord.ButtonStyle.link,
                url=invite_url,
                emoji="➕",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Join Support Server",
                style=discord.ButtonStyle.link,
                url=support_url,
                emoji="💬",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Official Website",
                style=discord.ButtonStyle.link,
                url=website_url,
                emoji="🌐",
            )
        )

    @discord.ui.button(
        label="Copy Ad Template",
        style=discord.ButtonStyle.primary,
        emoji="📋",
        custom_id="kyoka_promo_copy_btn",
    )
    async def copy_template(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Send the copyable advertisement text directly to the user in an ephemeral message."""
        chunks = []
        text = self.ad_text
        while len(text) > 1900:
            split_idx = text.rfind("\n", 0, 1900)
            if split_idx == -1:
                split_idx = 1900
            chunks.append(text[:split_idx])
            text = text[split_idx:].lstrip()
        if text:
            chunks.append(text)

        await interaction.response.send_message(
            "📋 **Here is your ready-to-use Discord Advertisement template:**\n"
            "-# *Select and copy the text below to post in partner or promo channels!*",
            ephemeral=True,
        )

        for chunk in chunks:
            await interaction.followup.send(
                f"```markdown\n{chunk}\n```",
                ephemeral=True,
            )


class Promo(commands.Cog, name="Promo"):
    """Official promotional showcase and Discord advertising templates for Kyoka."""

    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _get_urls(self) -> tuple[str, str, str]:
        invite_url = get_invite_url(self.bot.user.id if self.bot.user else None) or Config.INVITE_URL or "https://discord.com"
        support_url = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"
        website_url = "https://aizen-bot.pages.dev/"
        return invite_url, support_url, website_url

    def build_promo_container(
        self,
        bot_name: str,
        invite_url: str,
        support_url: str,
        website_url: str,
    ) -> KyokaContainer:
        """Construct an aesthetically magnificent Discord Components V2 promotion container."""
        user = getattr(self.bot, "user", None)
        avatar_url = getattr(getattr(user, "display_avatar", None), "url", None)
        guilds_count = len(self.bot.guilds)
        users_count = len(self.bot.users)

        gateway_latency = getattr(self.bot, "latency", float("nan"))
        ping_str = (
            f"{round(gateway_latency * 1000)}ms"
            if isinstance(gateway_latency, (int, float)) and math.isfinite(gateway_latency)
            else "18ms"
        )

        container = KyokaContainer()

        # Header Section
        header_text = (
            f"### ✨ {bot_name.upper()} — The Premier Discord Powerhouse\n"
            f"> *Power isn't given. It's taken.* — Transcend standard Discord bots.\n"
            f"> **Serving:** `{guilds_count:,}` Servers • `{users_count:,}` Members • **Latency:** `{ping_str}`\n\n"
            f"The ultimate all-in-one Discord ecosystem built with studio-grade lossless music, autonomous sub-second antinuke defense, specialized gaming hubs, and enterprise server automation."
        )
        container.add_section(
            content=header_text,
            accessory={"type": 11, "media": {"url": avatar_url}} if avatar_url else None,
        )
        container.add_separator(divider=True)

        # Feature Highlights
        container.add_field(
            "🎵 Studio-Grade Lossless Music (Lavalink v4)",
            "> • **24/7 Lossless Streaming:** Ultra-low latency, zero stutter, high-bitrate playback.\n"
            "> • **10+ DSP Filters:** 8D Audio, Bassboost, Nightcore, Vaporwave, Tremolo, and Karaoke.\n"
            "> • **Universal Resolution:** Instant play from Spotify, YouTube, SoundCloud, Apple Music.\n"
            "> • **Synced Dynamic Lyrics:** Real-time synced lyric display and smart autoplay queue.",
            inline=False,
        )

        container.add_field(
            "🛡️ Autonomous Antinuke & Anti-Raid Shield",
            "> • **0.1s Instant Suppression:** Sub-second quarantine and permission-stripping of rogue actors.\n"
            "> • **Full Attack Surface Defense:** Anti-ban, anti-kick, anti-role, anti-channel, anti-webhook, and anti-vanity.\n"
            "> • **Snapshot Auto-Rollback:** Emergency 1-click automatic restoration after malicious tampering.\n"
            "> • **Granular Hierarchy:** Multi-tiered whitelists and Extra Owner permission levels.",
            inline=False,
        )

        container.add_field(
            "⚔️ Precision Moderation & Tactical Defense",
            "> • **Complete Moderation:** Timed timeouts, warns, kicks, bans, locks, purges, and rich audit logs.\n"
            "> • **Anti-Ping Role Shield (`+antiping`):** Absolute protection against unwanted role mentions.\n"
            "> • **Stealth Fake Ban Engine (`+fakeban`):** Ultra-realistic prank ban card with simulated voice kick and countdown reveal.",
            inline=False,
        )

        container.add_field(
            "🏴‍☠️ Blox Fruits & Gaming Command Hub",
            "> • **Live Value Calculator:** Real-time physical & perm fruit values, demand & trend index.\n"
            "> • **Trade Margin Evaluator:** Calculate Win / Fair / Lose trade accuracy in seconds.\n"
            "> • **Automated Stock Alerts:** Live dealer stock tracking, mirage alerts, and raid assistants.\n"
            "> • **Interactive Companion AI:** Smart in-character anime companions with neural voice chat.",
            inline=False,
        )

        container.add_field(
            "🧾 Service Bills & Verified Reputation Ledger",
            "> • **Itemized Invoices:** Clean transaction receipts for carries, accounts, and trades.\n"
            "> • **Multi-Currency:** Invoicing in Crypto (BTC/ETH/LTC), PayPal, UPI, CashApp, and Robux.\n"
            "> • **Verified Vouch Ledger:** Verifiable customer feedback, star ratings, and trust profiles.",
            inline=False,
        )

        container.add_field(
            "🎫 Enterprise Tickets, JTC Voice & Automation",
            "> • **Interactive Tickets:** Button/modal ticket panels with lightning HTML transcripts.\n"
            "> • **Join-to-Create Voice:** Automated temporary voice channels with dynamic owner controls.\n"
            "> • **Community Engagement:** High-speed reaction roles, requirement giveaways, and AFK responder.",
            inline=False,
        )

        container.add_separator(divider=True)
        container.add_text(
            f"**Ready to elevate your Discord community?**\n"
            f"> [**Add {bot_name} to Server**]({invite_url}) • [**Support Server**]({support_url}) • [**Web Dashboard**]({website_url})\n\n"
            f"-# Click 'Copy Ad Template' below to copy the ready-to-post Discord advertisement!"
        )

        return container

    @commands.hybrid_group(
        name="promo",
        aliases=["promote", "ad", "advertisement", "botpromo"],
        description="View Kyoka's feature showcase and ready-to-copy Discord advertisement template.",
        fallback="card",
    )
    async def promo_group(self, ctx: CustomContext) -> None:
        """Display Kyoka's interactive visual showcase container card."""
        invite_url, support_url, website_url = self._get_urls()
        bot_name = self.bot.user.name if self.bot.user else Config.BOT_NAME
        guilds_count = len(self.bot.guilds)
        users_count = len(self.bot.users)

        ad_text = get_full_advert_template(
            bot_name=bot_name,
            invite_url=invite_url,
            support_url=support_url,
            website_url=website_url,
            guilds_count=guilds_count,
            users_count=users_count,
        )

        container = self.build_promo_container(
            bot_name=bot_name,
            invite_url=invite_url,
            support_url=support_url,
            website_url=website_url,
        )
        view = PromoView(
            invite_url=invite_url,
            support_url=support_url,
            ad_text=ad_text,
            website_url=website_url,
        )
        await send_container_response(ctx, container, view=view)

    @promo_group.command(
        name="copy",
        aliases=["raw", "text", "template"],
        description="Get the raw, ready-to-copy Discord advertisement text for promo & partner channels.",
    )
    async def promo_copy(self, ctx: CustomContext) -> None:
        """Send the copyable advertisement Markdown block directly in chat."""
        invite_url, support_url, website_url = self._get_urls()
        bot_name = self.bot.user.name if self.bot.user else Config.BOT_NAME
        guilds_count = len(self.bot.guilds)
        users_count = len(self.bot.users)

        ad_text = get_full_advert_template(
            bot_name=bot_name,
            invite_url=invite_url,
            support_url=support_url,
            website_url=website_url,
            guilds_count=guilds_count,
            users_count=users_count,
        )

        chunks = []
        text = ad_text
        while len(text) > 1900:
            split_idx = text.rfind("\n", 0, 1900)
            if split_idx == -1:
                split_idx = 1900
            chunks.append(text[:split_idx])
            text = text[split_idx:].lstrip()
        if text:
            chunks.append(text)

        await ctx.send(
            f"📋 **Copyable Discord Advertisement Template for {bot_name}:**\n"
            f"-# *Copy the text block below and paste it into `#promotions`, `#partnerships`, or server listings!*"
        )
        for chunk in chunks:
            await ctx.send(f"```markdown\n{chunk}\n```")

    @promo_group.command(
        name="short",
        aliases=["compact", "brief"],
        description="Get a compact, bite-sized Discord advertisement template for character-limited channels.",
    )
    async def promo_short(self, ctx: CustomContext) -> None:
        """Send a short advertisement template."""
        invite_url, support_url, website_url = self._get_urls()
        bot_name = self.bot.user.name if self.bot.user else Config.BOT_NAME

        short_text = get_short_advert_template(
            bot_name=bot_name,
            invite_url=invite_url,
            support_url=support_url,
            website_url=website_url,
        )

        await ctx.send(
            f"⚡ **Compact Discord Advertisement Template for {bot_name}:**\n\n"
            f"{short_text}\n\n"
            f"```markdown\n{short_text}\n```"
        )


async def setup(bot: KyokaBot) -> None:
    """Load the Promo cog into KyokaBot."""
    await bot.add_cog(Promo(bot))
