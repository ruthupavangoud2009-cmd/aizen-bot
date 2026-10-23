"""
Kyoka Discord Bot - Enterprise SaaS Help & Module Console
Dynamic permission-aware help menu powered by Discord Components V2 Container Cards.
Organized into 17 clean, intuitive command categories with interactive dropdown navigation.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response
from src.security.owner import is_primary_owner
from src.security.adult_guard import is_adult_authorized

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class Help(commands.Cog):
    """Enterprise SaaS Help & Module Console with dynamic 17-category permission filtering."""
    category: str = "General"

    CATEGORY_ORDER = [
        "General",
        "Fun",
        "Anime Actions",
        "Romance & Relationships",
        "Adult Humor — Restricted",
        "AI Companions",
        "AI Chat",
        "Games",
        "Social & Profiles",
        "Community & XP",
        "Moderation",
        "Tickets",
        "Giveaways",
        "Images & GIFs",
        "Premium",
        "Administration",
        "Utility",
    ]

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _resolve_category(self, cmd: commands.Command) -> str:
        """Resolve a command into one of the 17 standard KYOKA 3.0 help categories."""
        name = cmd.name.lower()
        cog_cat = getattr(cmd.cog, "category", "").strip()

        # 1. Adult Humor — Restricted
        if cog_cat == "Adult Humor — Restricted" or name in (
            "goon", "goonreaction", "fuck", "smash", "thirst", "downbad", "downbadcheck",
            "hornybonk", "seduce", "spank", "wildreaction", "adultreaction", "simp",
            "obsessed", "fantasize", "tease", "bedroomeyes", "caughtlacking", "rateattraction",
        ):
            return "Adult Humor — Restricted"

        # 2. AI Companions
        if cog_cat == "AI Companions" or name in ("aigf", "aibaddie", "aispecial", "aiclearcompanion", "girlfriend", "baddie", "specialai", "clearcompanion"):
            return "AI Companions"

        # 3. AI Chat
        if cog_cat in ("AI & Chat", "AIInteractions") and name in ("ai", "chat", "askai", "aizenai", "aisetup", "aipersonality", "aiconfig", "aitest", "aiclear", "aistatus"):
            return "AI Chat"

        # 4. Romance & Relationships
        if cog_cat == "Romance & Relationships" or name in (
            "propose", "marry", "divorce", "breakup", "relationship", "couple", "marriage",
            "kiss", "makeout", "love", "crush", "date", "jealous", "flirt", "pickup",
            "compliment", "cuddle", "hug", "romance", "heartbreak", "reject", "confess",
            "rizz", "ship", "compatibility", "soulmate", "loveletter",
        ):
            return "Romance & Relationships"

        # 5. Anime Actions
        if cog_cat == "Anime Actions" or name in (
            "punch", "blast", "animekick", "akick", "kickanime", "slap", "bonk", "pat", "poke",
            "bite", "yeet", "highfive", "stare", "scare", "laugh", "dance", "cry", "rage",
            "wave", "wink", "embarrass", "dramatic", "angry", "shy", "facepalm", "laughat",
            "crywith", "comfort", "cheer", "celebrate", "mock", "explode", "dodge", "flex",
            "scream", "sleep", "wake", "vibe", "reaction", "blush", "happy", "sleepy",
            "thumbsup", "shrug", "killme", "kill", "act",
        ):
            return "Anime Actions"

        # 6. Games
        if cog_cat == "Games" or name in (
            "bloxfruits", "bf", "bloxtrivia", "tod", "truthordare", "poll", "wordguess",
            "wordgame", "dailychallenge", "dailyquest", "challenge", "rps", "trivia",
            "guessanumber", "guessnumber", "guess", "guessstatus", "guesscancel", "guesshelp",
        ):
            return "Games"

        # 7. Fun
        if cog_cat == "Fun" or name in (
            "8ball", "eightball", "coinflip", "flip", "dice", "roll", "choose", "rate",
            "joke", "fact", "quote", "wyr", "truth", "dare", "roast", "funhelp",
        ):
            return "Fun"

        # 8. Images & GIFs
        if name in ("gif", "meme", "randomgif", "imagine", "steal", "emojis", "expressions", "stickers", "delemoji"):
            return "Images & GIFs"

        # 9. Social & Profiles
        if name in ("avatar", "banner", "profile", "serveravatar", "serverbanner", "userinfo", "membercount"):
            return "Social & Profiles"

        # 10. Community & XP
        if name in ("levels", "rank", "levelconfig", "activity", "leaderboard", "privacy", "diagnostics"):
            return "Community & XP"

        # 11. Moderation
        if cog_cat.lower() in ("moderation", "mod") or name in (
            "ban", "unban", "kick", "timeout", "mute", "unmute", "warn", "warnings", "delwarn",
            "purge", "lock", "unlock", "slowmode", "snipe", "snipeall", "clearsnipe", "clearsnipeall",
            "modlog", "admins", "mods", "bots",
        ):
            return "Moderation"

        # 12. Tickets
        if cog_cat.lower() in ("ticket", "tickets") or name.startswith("ticket"):
            return "Tickets"

        # 13. Giveaways
        if cog_cat.lower() in ("giveaway", "giveaways") or name in ("giveaway", "gstart", "gend", "greroll", "glist", "requirements"):
            return "Giveaways"

        # 14. Premium
        if name in ("premium", "redeem", "tier", "license"):
            return "Premium"

        # 15. Administration
        if cog_cat.lower() in ("admin", "administration", "security", "antinuke", "config", "settings") or name in (
            "prefix", "setprefix", "resetprefix", "autorole", "welcome", "boost", "media",
            "sticky", "antinuke", "whitelist", "extraowner", "logs", "config",
        ):
            return "Administration"

        # 16. Utility
        if cog_cat.lower() in ("utility", "util") or name in (
            "afk", "voice", "tempvoice", "translate", "translator", "verify", "verification",
            "reactionroles", "role", "roleall", "roleinfo", "listroles", "channelinfo",
            "serverinfo", "server", "tech", "dev", "clear",
        ):
            return "Utility"

        # 17. General
        return "General"

    @staticmethod
    def _can_run_command(cmd: Any, ctx: CustomContext | None = None) -> bool:
        """Hide hidden commands, owner-restricted commands, and adult-restricted commands from unauthorized users."""
        if getattr(cmd, "hidden", False):
            return False

        # OwnerSystem sends its dedicated help response privately; never list developer internals.
        cog = getattr(cmd, "cog", None)
        cog_cat = str(getattr(cog, "category", "")).strip().lower()
        if cog_cat in {"owner", "developer"}:
            return False

        cmd_name = str(getattr(cmd, "name", "")).strip().lower()
        owner_only = {"spam", "spamcancel", "guesshostadd", "guesshostremove", "guesshosts"}
        if cmd_name in owner_only and (ctx is None or not is_primary_owner(getattr(ctx.author, "id", None))):
            return False

        # Adult-humor allowlist restriction check
        if cog_cat in ("adult humor — restricted", "adult humor - restricted", "adulthumor"):
            author_id = getattr(ctx.author, "id", None) if ctx else None
            if not is_adult_authorized(author_id):
                return False

        return True

    def _get_badge(self, cmd: commands.Command) -> str:
        """Return a visual permission/status tag for a command."""
        name = cmd.qualified_name.lower()
        resolved_cat = self._resolve_category(cmd)

        if resolved_cat == "Adult Humor — Restricted":
            return " `[Restricted]`"
        if name in ("spam", "spamcancel", "guesshostadd", "guesshostremove", "guesshosts"):
            return " `[Owner]`"
        if name in ("ban", "unban", "kick", "timeout", "mute", "unmute", "warn", "delwarn", "lock", "unlock", "slowmode", "purge", "clear", "modlog"):
            return " `[Mod]`"
        if name in ("imagine", "tier", "license"):
            return " `[Prime]`"
        return ""

    async def _get_visible_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Group commands that the current user has permission to view and execute into the 17 categories."""
        categories: dict[str, list[commands.Command]] = {cat: [] for cat in self.CATEGORY_ORDER}

        def _collect_all(cmd_obj: commands.Command) -> list[commands.Command]:
            cmd_list = [cmd_obj]
            if isinstance(cmd_obj, commands.Group):
                for sub_cmd in sorted(cmd_obj.commands, key=lambda s: s.qualified_name):
                    cmd_list.extend(_collect_all(sub_cmd))
            return cmd_list

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler"]:
                continue

            for cmd in cog.get_commands():
                for c in _collect_all(cmd):
                    if self._can_run_command(c, ctx):
                        target_cat = self._resolve_category(c)
                        if target_cat not in categories:
                            categories[target_cat] = []
                        if c not in categories[target_cat]:
                            categories[target_cat].append(c)

        # Retain only non-empty categories following exact priority order
        ordered_categories: dict[str, list[commands.Command]] = {}
        for cat in self.CATEGORY_ORDER:
            if cat in categories and categories[cat]:
                ordered_categories[cat] = categories[cat]

        for cat, cmds in categories.items():
            if cat not in ordered_categories and cmds:
                ordered_categories[cat] = cmds

        return ordered_categories

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji for category header."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return "•"
        mapping = {
            "General": e_reg.get("icon_info", "ℹ️"),
            "Fun": e_reg.get("icon_sparkles", "🎭"),
            "Anime Actions": e_reg.get("icon_sparkles", "⚔️"),
            "Romance & Relationships": e_reg.get("icon_heart", "💖"),
            "Adult Humor — Restricted": e_reg.get("icon_fire", "🔞"),
            "AI Companions": e_reg.get("icon_sparkles", "🤖"),
            "AI Chat": e_reg.get("icon_sparkles", "💬"),
            "Games": e_reg.get("icon_games", "🎮"),
            "Social & Profiles": e_reg.get("icon_profile", "👤"),
            "Community & XP": e_reg.get("icon_chart", "📈"),
            "Moderation": e_reg.get("icon_moderation", "🔨"),
            "Tickets": e_reg.get("icon_ticket", "🎫"),
            "Giveaways": e_reg.get("discord_giveaway", "🎉"),
            "Images & GIFs": e_reg.get("icon_image", "🖼️"),
            "Premium": e_reg.get("verified_premium", "💎"),
            "Administration": e_reg.get("icon_settings", "⚙️"),
            "Utility": e_reg.get("icon_wrench", "🛠️"),
        }
        return mapping.get(cat_name, e_reg.get("icon_moderation", "•"))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any] | None:
        """Resolve emoji dict for Select Menu options."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return None
        mapping = {
            "General": "icon_info",
            "Fun": "icon_sparkles",
            "Anime Actions": "icon_sparkles",
            "Romance & Relationships": "icon_heart",
            "Adult Humor — Restricted": "icon_fire",
            "AI Companions": "icon_sparkles",
            "AI Chat": "icon_sparkles",
            "Games": "icon_games",
            "Social & Profiles": "icon_profile",
            "Community & XP": "icon_chart",
            "Moderation": "icon_moderation",
            "Tickets": "icon_ticket",
            "Giveaways": "discord_giveaway",
            "Images & GIFs": "icon_image",
            "Premium": "verified_premium",
            "Administration": "icon_settings",
            "Utility": "icon_wrench",
        }
        emoji_name = mapping.get(cat_name, "icon_moderation")
        return e_reg.get_select_emoji(emoji_name, fallback_unicode=None)

    def _build_home_container(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
        selected_val: str = "home",
    ) -> KyokaContainer:
        """Construct the Signature Kyoka SaaS Overview Card with Default Accent."""
        guild = ctx.guild
        author = ctx.author
        current_prefix = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        e_reg = self.bot.custom_emojis

        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Hey, I'm {Config.BOT_NAME}**\n"
                f"> Built for our community — keeping your server safe, active, and effortlessly connected."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Latency:** `{ws_ping}ms`\n"
            f"{dot} **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
            f"{dot} **Categories:** `{len(visible_categories)}` | **Available Commands:** `{total_commands}`"
        )
        container.add_separator(divider=True)

        # Dropdown Options
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None)
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": selected_val == "home",
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for cat_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": f"{cat_name} ({len(cmds)})",
                "value": cat_name.lower(),
                "default": selected_val == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(cat_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a category to view commands...",
                "options": options[:25],
            }
        ])

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {author.display_name} • Type {current_prefix}help <command> for details**")
        container.add_separator(divider=True)

        buttons = []
        if Config.INVITE_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Invite Kyoka",
                "url": Config.INVITE_URL,
            })
        if Config.SUPPORT_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": Config.SUPPORT_URL,
            })
        if buttons:
            container.add_action_row(buttons)

        return container

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
    ) -> KyokaContainer:
        """Construct category command card with permission badges and clean layout."""
        cat_icon = self._get_category_emoji(cat_name)
        e_reg = self.bot.custom_emojis

        container = KyokaContainer(accent_color=None)
        cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
        container.add_section(
            content=(
                f"**{cat_icon_prefix}{cat_name} Commands**\n"
                f"> Listing `{len(commands_list)}` accessible command(s) for your role in this server."
            )
        )
        container.add_separator(divider=True)

        # Sort commands alphabetically
        sorted_cmds = sorted(commands_list, key=lambda c: c.qualified_name.lower())
        formatted_cmds = ", ".join([f"`{cmd.qualified_name}`{self._get_badge(cmd)}" for cmd in sorted_cmds])
        container.add_text(formatted_cmds)
        container.add_separator(divider=True)

        # Dropdown options
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None)
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": False,
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for c_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": f"{c_name} ({len(cmds)})",
                "value": c_name.lower(),
                "default": c_name.lower() == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(c_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a category to view commands...",
                "options": options[:25],
            }
        ])

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name} • Type {self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)}help <command> for details**")
        container.add_separator(divider=True)

        buttons = []
        if Config.INVITE_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Invite Kyoka",
                "url": Config.INVITE_URL,
            })
        if Config.SUPPORT_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": Config.SUPPORT_URL,
            })
        if buttons:
            container.add_action_row(buttons)

        return container

    @commands.hybrid_command(
        name="help",
        aliases=["commands", "modules", "h"],
        description="Display the Kyoka command directory tailored to your permissions.",
    )
    async def help_command(self, ctx: CustomContext, *, command_or_module: str | None = None) -> None:
        """Interactive help menu filtered by user permissions and organized into 17 categories."""
        visible_categories = await self._get_visible_categories(ctx)

        # Direct command or module lookup
        if command_or_module:
            query = command_or_module.lower().strip()

            target_cmd = self.bot.get_command(query)
            if target_cmd and self._can_run_command(target_cmd, ctx):
                current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
                cat = self._resolve_category(target_cmd)
                cat_icon = self._get_category_emoji(cat)
                desc = target_cmd.description or target_cmd.help or "No detailed description available."
                aliases = ", ".join([f"`{a}`" for a in target_cmd.aliases]) if target_cmd.aliases else "`None`"
                sig = f" {target_cmd.signature}" if target_cmd.signature else ""
                usage = f"`{current_prefix}{target_cmd.qualified_name}{sig}`"
                example = f"`{current_prefix}{target_cmd.qualified_name}`"

                badge = self._get_badge(target_cmd)
                status_str = badge.strip(" `[]") if badge else "Public"

                # Check slash command support
                slash_info = f"`/{target_cmd.name}`" if getattr(target_cmd, "app_command", None) else "Prefix command"
                if cat == "AI Companions":
                    slash_info = f"`/companion {target_cmd.name}` or `{current_prefix}{target_cmd.name}`"
                elif cat == "Anime Actions":
                    slash_info = f"`/act` or `{current_prefix}{target_cmd.name} @user`"

                e_reg = self.bot.custom_emojis
                dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

                container = KyokaContainer(accent_color=None)
                cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
                container.add_section(
                    content=(
                        f"**{cat_icon_prefix}Command: `{target_cmd.name}`**\n"
                        f"> {desc}"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"{dot} **Usage:** {usage}\n"
                    f"{dot} **Example:** {example} | **Slash:** {slash_info}\n"
                    f"{dot} **Category:** `{cat}` | **Access:** `{status_str}`\n"
                    f"{dot} **Aliases:** {aliases}"
                )
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

            # Direct module / category lookup
            category_aliases = {
                "general": "General",
                "fun": "Fun",
                "anime": "Anime Actions",
                "actions": "Anime Actions",
                "anime actions": "Anime Actions",
                "romance": "Romance & Relationships",
                "relationships": "Romance & Relationships",
                "marriage": "Romance & Relationships",
                "adult": "Adult Humor — Restricted",
                "adulthumor": "Adult Humor — Restricted",
                "restricted": "Adult Humor — Restricted",
                "companion": "AI Companions",
                "companions": "AI Companions",
                "aicompanions": "AI Companions",
                "aichat": "AI Chat",
                "chat": "AI Chat",
                "games": "Games",
                "game": "Games",
                "social": "Social & Profiles",
                "profile": "Social & Profiles",
                "profiles": "Social & Profiles",
                "community": "Community & XP",
                "xp": "Community & XP",
                "levels": "Community & XP",
                "mod": "Moderation",
                "moderation": "Moderation",
                "ticket": "Tickets",
                "tickets": "Tickets",
                "gw": "Giveaways",
                "giveaway": "Giveaways",
                "giveaways": "Giveaways",
                "images": "Images & GIFs",
                "gifs": "Images & GIFs",
                "image": "Images & GIFs",
                "gif": "Images & GIFs",
                "prime": "Premium",
                "premium": "Premium",
                "admin": "Administration",
                "administration": "Administration",
                "util": "Utility",
                "utility": "Utility",
            }
            target_cat_name = category_aliases.get(query)
            if not target_cat_name:
                target_cat_name = next((c for c in visible_categories.keys() if c.lower() == query), None)

            if target_cat_name:
                matched_cat = next((c for c in visible_categories.keys() if c.lower() == target_cat_name.lower()), None)
                if matched_cat:
                    custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
                    container = self._build_category_container(
                        ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                    )
                    await send_container_response(ctx, container)
                    return

        # Main Help Console (Home Overview)
        custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
        container = self._build_home_container(ctx, visible_categories, custom_id_prefix)
        await send_container_response(ctx, container)

        def check(interaction: discord.Interaction) -> bool:
            if not interaction.data:
                return False
            custom_id = interaction.data.get("custom_id", "")
            return (
                custom_id.startswith(f"{custom_id_prefix}:")
                and interaction.user.id == ctx.author.id
            )

        while True:
            try:
                interaction: discord.Interaction = await self.bot.wait_for(
                    "interaction", check=check, timeout=120.0
                )
                custom_id = interaction.data.get("custom_id", "")
                action = custom_id.split(":")[-1]

                # Select Menu Navigation
                if action == "select_category":
                    selected = interaction.data.get("values", ["home"])[0]
                    if selected == "home":
                        new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    else:
                        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected), None)
                        if matched_cat:
                            new_container = self._build_category_container(
                                ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                            )
                        else:
                            new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")

                    await edit_container_response(interaction, new_container)

            except asyncio.TimeoutError:
                break


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Help(bot))
