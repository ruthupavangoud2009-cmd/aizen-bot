"""
Kyoka 3.0 - Eclipse Interface Feature Renderers
Provides dedicated, high-end, responsive layouts for every major bot subsystem:
Music, AI & Voice, Blox Fruits AI, Service Bills, Vouches, Tickets, Verification,
Welcome & Goodbye, Moderation, Giveaways, Reaction Roles, AFK, Leveling, and Premium.
Adheres strictly to the KYOKA: Eclipse Interface design language.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional
import discord

from src.ui.theme import KyokaTheme
from src.ui.asset_manager import AssetManager
from src.ui.help_renderer import KyokaHelpEmbed
from src.utils.emojis import em


class FeatureRenderer:
    """Centralized renderer for all KYOKA 3.0 Eclipse Interface feature panels and cards."""

    # ── 1. MUSIC NOW PLAYING CARD ─────────────────────────────────────────────
    @staticmethod
    def render_music_card(
        title: str,
        artist: str,
        duration: str,
        requester: str,
        current_pos_ms: int = 0,
        total_duration_ms: int = 0,
        volume: int = 100,
        loop_mode: str = "off",
        queue_count: int = 0,
        track_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render the sleek Eclipse Interface Now Playing card."""
        e_music = em(bot, "MUSIC", animated=True)
        embed = KyokaHelpEmbed(
            title=f"{e_music} {title[:60]}",
            url=track_url if track_url else None,
            color=KyokaTheme.PRIMARY,
        )

        # Calculate progress bar
        prog_bar = ""
        if total_duration_ms > 0:
            prog_bar = f"\n`{KyokaTheme.progress_bar(current_pos_ms, total_duration_ms, length=12)}`"

        embed.description = (
            f"> **Artist:** `{artist}`\n"
            f"> **Duration:** `{duration}`{prog_bar}\n"
            f"> **Status:** Vol: `{volume}%` · Loop: `{loop_mode.upper()}` · Queue: `{queue_count} tracks`"
        )

        banner_file = AssetManager.attach_feature_banner(embed, "music")
        embed.banner_file = banner_file

        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        embed.set_footer(text=f"Requested by {requester} • {KyokaTheme.MUSIC_FOOTER}")
        return embed

    # ── 2. AI CHAT RESPONSE CARD ───────────────────────────────────────────────
    @staticmethod
    def render_ai_chat_card(
        query: str,
        response: str,
        personality: str = "aizen",
        latency_ms: Optional[int] = None,
        user_name: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render conversational Aizen Gemini AI interaction card."""
        pers_clean = personality.title()
        e_ai = em(bot, "SPARKLE", animated=True)
        embed = KyokaHelpEmbed(
            title=f"{e_ai} Kyoka AI · {pers_clean} Mind",
            description=response[:4000],
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "ai")
        embed.banner_file = banner_file

        footer_parts = [f"Persona: {pers_clean}"]
        if latency_ms is not None:
            footer_parts.append(f"{latency_ms}ms")
        if user_name:
            footer_parts.append(f"Prompt by {user_name}")
        footer_parts.append(KyokaTheme.FOOTER_TEXT)

        embed.set_footer(text=" • ".join(footer_parts))
        return embed

    # ── 3. AI VOICE CONTROL CARD ───────────────────────────────────────────────
    @staticmethod
    def render_ai_voice_card(
        channel_name: str,
        personality: str,
        status: str = "Active",
        latency_ms: Optional[int] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render neural AI Voice channel control & TTS dashboard."""
        e_voice = em(bot, "VOICE")
        e_sparkle = em(bot, "SPARKLE", animated=True)
        e_arrow = em(bot, "ARROW")
        embed = KyokaHelpEmbed(
            title=f"{e_voice} Neural Voice Matrix · Kyoka Suigetsu {e_sparkle}",
            description=(
                f"> **Voice Channel:** `{channel_name}`\n"
                f"> **Personality Core:** `{personality.title()}`\n"
                f"> **Synthesizer Status:** `{status}`\n\n"
                f"{e_arrow} Speak naturally with `@Kyoka` or use `+aivoice speak <text>`\n"
                f"{e_arrow} Use `+aivoice stop` to silence or `+aivoice leave` to disconnect."
            ),
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "ai")
        embed.banner_file = banner_file
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Latency: {latency_ms or 0}ms")
        return embed

    # ── 4. BLOX FRUITS AI ADVISOR ─────────────────────────────────────────────
    @staticmethod
    def render_blox_fruits_card(
        topic: str,
        advice: str,
        fruit_name: Optional[str] = None,
        market_value: Optional[str] = None,
        trade_demand: Optional[str] = None,
        requester: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render Blox Fruits game analysis, fruit values, and carry guides."""
        e_bf = em(bot, "BLOXFRUITS")
        e_stats = em(bot, "STATS")
        e_arrow = em(bot, "ARROW")
        embed = KyokaHelpEmbed(
            title=f"{e_bf} Blox Fruits Companion • {topic.title()}",
            description=f"> {advice[:2000]}",
            color=KyokaTheme.PRIMARY,
        )

        if fruit_name and (market_value or trade_demand):
            embed.add_field(
                name=f"{e_stats} Market Valuation: {fruit_name}",
                value=(
                    f"{e_arrow} **Value:** `{market_value or 'N/A'}`\n"
                    f"{e_arrow} **Trade Demand:** `{trade_demand or 'Stable'}`"
                ),
                inline=False,
            )

        banner_file = AssetManager.attach_feature_banner(embed, "blox_fruits")
        embed.banner_file = banner_file
        embed.set_footer(text=f"Requested by {requester or 'Player'} • KYOKA Blox Fruits AI")
        return embed

    # ── 5. BLOX FRUITS SERVICE INVOICE ─────────────────────────────────────────
    @staticmethod
    def render_service_invoice(
        invoice_id: str,
        customer_id: int,
        creator_id: int,
        service_item: str,
        agreed_payment: str,
        category: str = "Raids & Carries",
        status: str = "PENDING",
        subtotal: float = 0.0,
        tax: float = 0.0,
        total: float = 0.0,
        currency: str = "USD",
        notes: str = "",
        created_timestamp: int = 0,
        guild_name: str = "KYŌKA SERVICES",
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render official itemized Blox Fruits service receipt and ledger card."""
        is_paid = status.upper() == "PAID"
        status_icon = em(bot, "ONLINE") if is_paid else em(bot, "IDLE")
        status_label = "PAID & VERIFIED" if is_paid else "PENDING PAYMENT"
        color = KyokaTheme.SUCCESS if is_paid else KyokaTheme.PRIMARY

        e_bills = em(bot, "BILLS")
        e_arrow = em(bot, "ARROW")
        e_user = em(bot, "USER")
        e_shield = em(bot, "MODERATION")
        e_tag = em(bot, "ROLES")
        e_box = em(bot, "ARCHIVE")
        e_coin = em(bot, "ECONOMY", animated=True)
        e_stats = em(bot, "STATS")
        e_edit = em(bot, "EDIT")

        created_str = f"<t:{created_timestamp}:f> (<t:{created_timestamp}:R>)" if created_timestamp else "Recent"

        embed = KyokaHelpEmbed(
            title=f"{e_bills} {guild_name} • INVOICE `{invoice_id}`",
            description=(
                f"**Official Blox Fruits Service Receipt & Payment Ledger**\n"
                f"{e_arrow} **Status:** {status_icon} **`{status_label}`**\n"
                f"{e_arrow} **Issued:** {created_str}"
            ),
            color=color,
        )

        embed.add_field(name=f"{e_user} Customer", value=f"<@{customer_id}>\n`ID: {customer_id}`", inline=True)
        embed.add_field(name=f"{e_shield} Service Provider", value=f"<@{creator_id}>", inline=True)
        embed.add_field(name=f"{e_tag} Category", value=f"`{category}`", inline=True)

        embed.add_field(
            name=f"{e_box} Service Details",
            value=f"> {discord.utils.escape_markdown(service_item)}",
            inline=False,
        )

        embed.add_field(
            name=f"{e_coin} Agreed Payment / Total Due",
            value=f"**`{agreed_payment}`**",
            inline=True,
        )

        if subtotal > 0:
            embed.add_field(
                name=f"{e_stats} Price Breakdown",
                value=f"Subtotal: `{currency} {subtotal:,.2f}`\nTax: `{currency} {tax:,.2f}`\nTotal: `**{currency} {total:,.2f}**`",
                inline=True,
            )

        if notes:
            embed.add_field(
                name=f"{e_edit} Payment Instructions & Terms",
                value=f"> {notes[:800]}",
                inline=False,
            )

        banner_file = AssetManager.attach_feature_banner(embed, "service_bills")
        embed.banner_file = banner_file
        embed.set_footer(text=f"Issued by <@{creator_id}> • KYOKA Invoicing Portal")
        return embed

    # ── 6. VOUCH & REPUTATION SUMMARY CARD ─────────────────────────────────────
    @staticmethod
    def render_vouch_profile(
        target_name: str,
        target_avatar_url: str,
        total_vouches: int,
        rating_avg: float = 5.0,
        recent_vouches: Optional[List[Dict[str, Any]]] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render member trust summary and reputation profile."""
        e_star = em(bot, "STAR")
        e_vouch = em(bot, "VOUCH")
        stars = e_star * max(1, min(5, int(round(rating_avg))))
        embed = KyokaHelpEmbed(
            title=f"{e_vouch} {target_name} • Trust & Reputation Profile",
            description=(
                f"> **Total Verified Vouches:** `{total_vouches}`\n"
                f"> **Average Rating:** {stars} (`{rating_avg:.1f}/5.0`)\n"
                f"> **Status:** Verified Community Provider\n\n"
                f"Use `+vouch @user <service> <review>` to submit a verified rating."
            ),
            color=KyokaTheme.PRIMARY,
        )

        if recent_vouches:
            for v in recent_vouches[:3]:
                stype = v.get("service_type", "General")
                v_stars = f"{e_star} `{int(v.get('rating', 5))}/5`"
                embed.add_field(
                    name=f"`#{v.get('id', 'VOUCH')}` {stype.title()} · {v_stars}",
                    value=f"> {v.get('reason', 'Great service!')}\n> *By <@{v.get('voucher_id', '0')}>*",
                    inline=False,
                )

        banner_file = AssetManager.attach_feature_banner(embed, "vouches")
        embed.banner_file = banner_file
        embed.set_thumbnail(url=target_avatar_url)
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Verified Trust System")
        return embed

    # ── 7. TICKET SYSTEM HUB PANEL ─────────────────────────────────────────────
    @staticmethod
    def render_ticket_panel(
        guild_name: str,
        panels_count: int,
        panel_names: Optional[List[str]] = None,
        prefix: str = "+",
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render the enterprise ticket system hub card."""
        e_ticket = em(bot, "TICKET")
        e_arrow = em(bot, "ARROW")
        p_list = ", ".join(f"`{name}`" for name in (panel_names or [])[:10]) or "*None configured yet*"
        embed = KyokaHelpEmbed(
            title=f"{e_ticket} Support Ticket Hub • {guild_name}",
            description=(
                f"> **Enterprise Support & Staff Claiming Engine**\n"
                f"> Deploy customizable, secure ticket panels with HTML transcripts.\n\n"
                f"{e_arrow} **Active Panels ({panels_count}):** {p_list}\n"
                f"{e_arrow} **Deploy Panel:** `{prefix}ticket setup`\n"
                f"{e_arrow} **Staff Controls:** `{prefix}ticket claim`, `{prefix}ticket close`\n"
                f"{e_arrow} **HTML Transcripts:** Automatically saved & secure"
            ),
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "tickets")
        embed.banner_file = banner_file
        embed.set_footer(text=KyokaTheme.TICKET_FOOTER)
        return embed

    # ── 8. VERIFICATION GATEKEEPER CARD ───────────────────────────────────────
    @staticmethod
    def render_verification_card(
        guild_name: str,
        instructions: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render the verification gatekeeper embed."""
        e_ver = em(bot, "VERIFICATION", animated=True)
        e_arrow = em(bot, "ARROW")
        embed = KyokaHelpEmbed(
            title=f"{e_ver} Gateway Verification • {guild_name}",
            description=(
                f"> {instructions or 'To unlock access to the server, click the Verify button below.'}\n\n"
                f"{e_arrow} **Security Policy:** Anti-raid challenge enforcement\n"
                f"{e_arrow} **Permissions:** Access granted immediately upon verification\n"
                f"{e_arrow} **Assistance:** Contact staff if you encounter difficulties."
            ),
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "verification")
        embed.banner_file = banner_file
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Server Security Gate")
        return embed

    # ── 9. WELCOME & GOODBYE CARDS ─────────────────────────────────────────────
    @staticmethod
    def render_welcome_card(
        member_name: str,
        member_mention: str,
        guild_name: str,
        member_count: int,
        avatar_url: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render stylish welcome arrival card."""
        e_welcome = em(bot, "WELCOME")
        e_sparkle = em(bot, "SPARKLE", animated=True)
        e_arrow = em(bot, "ARROW")
        embed = KyokaHelpEmbed(
            title=f"{e_welcome} Welcome to {guild_name}!",
            description=(
                f"**A new presence enters the realm.**\n"
                f"> Greetings, {member_mention}! You are member **#{member_count}**.\n\n"
                f"{e_sparkle} **Next Steps:**\n"
                f"{e_arrow} Check the server channels and rules\n"
                f"{e_arrow} Type `+help` to inspect KYOKA's command console\n"
                f"{e_arrow} Enjoy your journey!"
            ),
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "welcome")
        embed.banner_file = banner_file
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"{member_name} joined • {KyokaTheme.FOOTER_TEXT}")
        return embed

    @staticmethod
    def render_goodbye_card(
        member_name: str,
        guild_name: str,
        member_count: int,
        avatar_url: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render departure card."""
        e_leave = em(bot, "GOODBYE")
        embed = KyokaHelpEmbed(
            title=f"{e_leave} Farewell from {guild_name}",
            description=(
                f"**A presence departs the citadel.**\n"
                f"> **{member_name}** has left the server.\n"
                f"> Remaining members: **{member_count}**"
            ),
            color=KyokaTheme.SECONDARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "goodbye")
        embed.banner_file = banner_file
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT}")
        return embed

    # ── 10. MODERATION LOG CARD ────────────────────────────────────────────────
    @staticmethod
    def render_moderation_card(
        action: str,
        target_name: str,
        target_id: int,
        moderator_name: str,
        reason: str,
        case_id: Optional[int] = None,
        duration: Optional[str] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render high-contrast security audit moderation card."""
        action_upper = action.upper()
        is_danger = action_upper in ("BAN", "SOFTBAN", "NUKE")
        color = KyokaTheme.CRIMSON if is_danger else KyokaTheme.PRIMARY
        e_mod = em(bot, "BAN" if is_danger else "MODERATION")
        e_arrow = em(bot, "ARROW")

        case_tag = f"Case #{case_id:04d} • " if case_id else ""
        dur_str = f"{e_arrow} **Duration:** `{duration}`\n" if duration else ""
        embed = KyokaHelpEmbed(
            title=f"{e_mod} {case_tag}{action_upper}",
            description=(
                f"{e_arrow} **Target:** `{target_name}` (<@{target_id}>)\n"
                f"{e_arrow} **Moderator:** `{moderator_name}`\n"
                f"{dur_str}"
                f"{e_arrow} **Reason:** {discord.utils.escape_markdown(reason)}"
            ),
            color=color,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "moderation")
        embed.banner_file = banner_file
        embed.set_footer(text=f"Target ID: {target_id} • KYOKA Security Audit")
        return embed

    # ── 11. GIVEAWAYS & EVENTS CARD ───────────────────────────────────────────
    @staticmethod
    def render_giveaway_panel(
        prize: str,
        host_name: str,
        end_timestamp: int,
        winners_count: int = 1,
        entries_count: int = 0,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render giveaway countdown panel."""
        e_gw = em(bot, "GIVEAWAY")
        e_arrow = em(bot, "ARROW")
        embed = KyokaHelpEmbed(
            title=f"{e_gw} GIVEAWAY: {prize}",
            description=(
                f"> Click **{e_gw} Enter** below to participate!\n\n"
                f"{e_arrow} **Host:** `{host_name}`\n"
                f"{e_arrow} **Winners:** `{winners_count}`\n"
                f"{e_arrow} **Entries:** `{entries_count}`\n"
                f"{e_arrow} **Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:f>)"
            ),
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "giveaways")
        embed.banner_file = banner_file
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Automated Giveaways")
        return embed

    # ── 12. AFK STATUS CARD ───────────────────────────────────────────────────
    @staticmethod
    def render_afk_card(
        member_name: str,
        reason: str,
        elapsed_seconds: Optional[float] = None,
        is_return: bool = False,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render AFK status set or welcome back card."""
        if is_return:
            e_back = em(bot, "WELCOME")
            duration_str = f" after `{int(elapsed_seconds or 0)}s`" if elapsed_seconds else ""
            embed = KyokaHelpEmbed(
                title=f"{e_back} Welcome back, {member_name}!",
                description=f"> Your AFK status has been cleared{duration_str}.",
                color=KyokaTheme.SUCCESS,
            )
        else:
            e_afk = em(bot, "AFK")
            embed = KyokaHelpEmbed(
                title=f"{e_afk} {member_name} is now AFK",
                description=f"> **Reason:** {discord.utils.escape_markdown(reason)}",
                color=KyokaTheme.PRIMARY,
            )

        banner_file = AssetManager.attach_feature_banner(embed, "afk")
        embed.banner_file = banner_file
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • AFK System")
        return embed

    # ── 13. LEVELING & RANK PROGRESSION ───────────────────────────────────────
    @staticmethod
    def render_rank_card(
        member_name: str,
        level: int,
        current_xp: int,
        needed_xp: int,
        rank: int,
        total_xp: int,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render XP progress and server standing."""
        e_lvl = em(bot, "LEVELING")
        bar = KyokaTheme.progress_bar(current_xp, needed_xp, length=12)
        embed = KyokaHelpEmbed(
            title=f"{e_lvl} Rank Standing • {member_name}",
            description=(
                f"> **Server Rank:** `#{rank}`\n"
                f"> **Level:** `{level}`\n"
                f"> **XP Progress:** `{current_xp:,} / {needed_xp:,}` XP\n"
                f"`{bar}`\n"
                f"> **Total Accumulation:** `{total_xp:,}` XP"
            ),
            color=KyokaTheme.PRIMARY,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "leveling")
        embed.banner_file = banner_file
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Server Leaderboards")
        return embed

    # ── 14. PREMIUM & TIER STATUS ─────────────────────────────────────────────
    @staticmethod
    def render_premium_card(
        guild_name: str,
        is_premium: bool,
        tier: str = "Free",
        expiration: Optional[str] = None,
        features: Optional[List[str]] = None,
        bot: Any = None,
    ) -> KyokaHelpEmbed:
        """Render Kyoka Prime tier status and exclusive perks."""
        e_prem = em(bot, "PREMIUM", animated=True)
        e_lock = em(bot, "LOCK")
        e_sparkle = em(bot, "SPARKLE", animated=True)
        e_arrow = em(bot, "ARROW")
        status_tag = f"{e_prem} PRIME ACTIVE" if is_premium else f"{e_lock} FREE EDITION"
        color = KyokaTheme.PRIMARY if is_premium else KyokaTheme.SECONDARY

        feat_lines = "\n".join(
            f"{e_arrow} {f}"
            for f in (features or ["High-fidelity Audio", "Enterprise Tickets", "Blox Fruits AI"])
        )
        expires_line = f"> **Expires:** `{expiration}`\n" if expiration else ""

        embed = KyokaHelpEmbed(
            title=f"{e_prem} Kyoka Prime • {guild_name}",
            description=(
                f"> **Status:** **{status_tag}**\n"
                f"> **Current Tier:** `{tier}`\n"
                f"{expires_line}\n"
                f"{e_sparkle} **Active Privileges:**\n{feat_lines}"
            ),
            color=color,
        )

        banner_file = AssetManager.attach_feature_banner(embed, "premium")
        embed.banner_file = banner_file
        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • High-Performance Tier")
        return embed
