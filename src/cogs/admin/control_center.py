"""
KYOKA — Control Center & Smart Server Setup Wizard
Provides an interactive Greed-inspired control panel and guided setup wizard
(+control, +setup, +modules) allowing server administrators to inspect, toggle,
and configure core bot modules safely from Discord or mobile.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import is_owner_or_staff
from src.ui.response import KyokaResponse, send_response
from src.utils.containers import KyokaContainer, edit_container_response, send_container_response
from src.utils.emojis import resolve_emoji, resolve_select_emoji

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Admin.ControlCenter")

MODULE_DEFINITIONS: list[tuple[str, str, str]] = [
    ("moderation", "Moderation & Cases", "Kick, ban, timeout, warn, purge, and sequential Case IDs"),
    ("automod", "AutoMod & Chat Guard", "Native Discord AutoMod spam, mention, and harmful-link rules"),
    ("antinuke", "Anti-Nuke & Security", "Mass ban, kick, channel, role, and webhook raid protection"),
    ("welcome", "Welcome & Goodbye", "Join/leave greeting cards, autoroles, and onboarding"),
    ("tickets", "Tickets & Support", "Interactive ticket panels, claiming, transcripts, and feedback"),
    ("music", "Music & Audio", "High-fidelity playback, queues, filters, and voice recovery"),
    ("ai", "KYOKA AI Assistant", "Server AI chat channels, personas, and FAQ assistance"),
    ("leveling", "Leveling & XP (Opt-In)", "Server XP progression & rank cards (disabled by default)"),
    ("suggestions", "Suggestions & Utility", "Suggestions, persistent reminders, polls, and custom commands"),
]


class SetupSectionSelect(discord.ui.Select):
    """Dropdown selector for navigating KYOKA Control Center & Setup Wizard sections."""

    def __init__(self, view: ControlCenterView, current_section: str = "overview") -> None:
        self.cc_view = view
        mod_emoji_keys = {
            "moderation": "MODERATION",
            "automod": "SECURITY",
            "antinuke": "ANTI_NUKE",
            "welcome": "WELCOMER",
            "tickets": "TICKET",
            "music": "MUSIC",
            "ai": "AI",
            "leveling": "LEVEL",
            "suggestions": "UTILITY",
        }
        options = [
            discord.SelectOption(
                label="Control Center Overview",
                value="overview",
                description="Live module status, prefix, and server health summary",
                emoji=resolve_select_emoji(view.bot, "SETTINGS", fallback="🎛️"),
                default=(current_section == "overview"),
            )
        ]
        for mod_id, label, desc in MODULE_DEFINITIONS:
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=mod_id,
                    description=desc[:100],
                    emoji=resolve_select_emoji(view.bot, mod_emoji_keys.get(mod_id, "MODULES")),
                    default=(current_section == mod_id),
                )
            )
        super().__init__(
            placeholder="Select a module or setup guide...",
            min_values=1,
            max_values=1,
            options=options[:25],
            custom_id="kyoka:cc:section",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.cc_view.current_section = self.values[0]
        self.cc_view._rebuild()
        await edit_container_response(interaction, self.cc_view.build_container(), view=self.cc_view)


class ControlCenterView(discord.ui.View):
    """Interactive author-locked view for KYOKA Control Center & Smart Server Setup."""

    def __init__(self, cog: ControlCenterCog, ctx: CustomContext) -> None:
        super().__init__(timeout=180.0)
        self.cog = cog
        self.bot = cog.bot
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.current_section: str = "overview"
        self.message: discord.Message | None = None
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        self.add_item(SetupSectionSelect(self, self.current_section))

        if self.current_section != "overview":
            is_enabled = self.cog.is_module_enabled(self.ctx.guild.id, self.current_section)
            toggle_btn = discord.ui.Button(
                label=f"{'Disable' if is_enabled else 'Enable'} {self.current_section.title()}",
                style=discord.ButtonStyle.danger if is_enabled else discord.ButtonStyle.success,
                custom_id="kyoka:cc:toggle",
                row=1,
            )
            toggle_btn.callback = self._on_toggle
            self.add_item(toggle_btn)

            home_btn = discord.ui.Button(
                label="Back to Overview",
                style=discord.ButtonStyle.secondary,
                custom_id="kyoka:cc:home",
                row=1,
            )
            home_btn.callback = self._on_home
            self.add_item(home_btn)

        refresh_btn = discord.ui.Button(
            label="Refresh",
            emoji=resolve_select_emoji(self.bot, "REFRESH", fallback="🔄"),
            style=discord.ButtonStyle.primary,
            custom_id="kyoka:cc:refresh",
            row=1,
        )
        refresh_btn.callback = self._on_refresh
        self.add_item(refresh_btn)

        close_btn = discord.ui.Button(
            label="Close",
            emoji=resolve_select_emoji(self.bot, "DELETE", fallback="🗑️"),
            style=discord.ButtonStyle.secondary,
            custom_id="kyoka:cc:close",
            row=1,
        )
        close_btn.callback = self._on_close
        self.add_item(close_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not is_owner_or_staff(interaction.user.id):
            await interaction.response.send_message(
                "Only the administrator who opened this Control Center can modify it.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_toggle(self, interaction: discord.Interaction) -> None:
        guild = self.ctx.guild
        mod_id = self.current_section
        new_state = not self.cog.is_module_enabled(guild.id, mod_id)
        await self.cog.set_module_enabled(guild.id, mod_id, new_state, interaction.user.id)

        # Keep LevelingManager opt-in state synchronized if toggling leveling
        if mod_id == "leveling" and hasattr(self.bot, "leveling_mgr"):
            try:
                await self.bot.leveling_mgr.set_enabled(guild.id, new_state)
            except Exception:
                pass

        self._rebuild()
        await edit_container_response(interaction, self.build_container(), view=self)

    async def _on_home(self, interaction: discord.Interaction) -> None:
        self.current_section = "overview"
        self._rebuild()
        await edit_container_response(interaction, self.build_container(), view=self)

    async def _on_refresh(self, interaction: discord.Interaction) -> None:
        self._rebuild()
        await edit_container_response(interaction, self.build_container(), view=self)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        self.stop()
        container = KyokaContainer(accent_color=None)
        container.add_text("**KYOKA Control Center Closed**\n> Configuration changes remain saved.")
        await edit_container_response(interaction, container, view=self)

    def build_container(self) -> KyokaContainer:
        guild = self.ctx.guild
        dot = resolve_emoji(self.bot, "ARROW", fallback="•")
        admin_em = resolve_emoji(self.bot, "ADMIN")
        prefix = self.bot.guild_mgr.get_prefix(guild.id) if hasattr(self.bot, "guild_mgr") else "+"

        container = KyokaContainer(accent_color=None)

        if self.current_section == "overview":
            container.add_section(
                content=(
                    f"**{admin_em} KYOKA Control Center — {guild.name}**\n"
                    "> Unified module toggles, live configuration health, and guided server setup."
                ),
                accessory={"type": 11, "media": {"url": guild.icon.url}} if guild.icon else None,
            )
            container.add_separator(divider=True)

            lines = [f"{dot} **Prefix:** `{prefix}` | **Slash:** `/`"]
            for mod_id, label, _ in MODULE_DEFINITIONS:
                enabled = self.cog.is_module_enabled(guild.id, mod_id)
                badge = "`ON`" if enabled else "`OFF`"
                lines.append(f"{dot} **{label}:** {badge}")

            container.add_text("\n".join(lines))
            container.add_separator(divider=True)
            container.add_text(
                f"-# Select a module below to configure or toggle it • Requested by {self.ctx.author.display_name}"
            )
            return container

        # Guided setup detail for selected module
        mod_meta = next((m for m in MODULE_DEFINITIONS if m[0] == self.current_section), None)
        label = mod_meta[1] if mod_meta else self.current_section.title()
        desc = mod_meta[2] if mod_meta else "Module setup and configuration."
        enabled = self.cog.is_module_enabled(guild.id, self.current_section)

        guides = {
            "moderation": (
                f"{dot} **Set Mod Log Channel:** `{prefix}modlog #channel`\n"
                f"{dot} **Case Lookup & Editing:** `{prefix}case <id>` • `{prefix}cases [@user]` • `{prefix}reason <id> <text>`\n"
                f"{dot} **Enforcement:** `{prefix}ban`, `{prefix}kick`, `{prefix}timeout`, `{prefix}warn`, `{prefix}jail`, `{prefix}purge`"
            ),
            "automod": (
                f"{dot} **Install Discord Native Rules:** `{prefix}automod setup`\n"
                f"{dot} **Toggle Rules:** `{prefix}automod enable` / `{prefix}automod disable`\n"
                f"{dot} **Inspect Rules:** `{prefix}automod config`"
            ),
            "antinuke": (
                f"{dot} **Open Antinuke Panel:** `{prefix}antinuke`\n"
                f"{dot} **Whitelist Trusted Admins:** `{prefix}whitelist add @user`\n"
                f"{dot} **Extra Owners:** `{prefix}extraowner add @user`"
            ),
            "welcome": (
                f"{dot} **Onboarding & Welcome Setup:** `{prefix}setwelcome` / `{prefix}welcome`\n"
                f"{dot} **Autoroles:** `{prefix}autorole` • **Voice Welcome:** `{prefix}voicewelcome`"
            ),
            "tickets": (
                f"{dot} **Deploy Ticket Panel:** `{prefix}ticket setup` or `/ticket`\n"
                f"{dot} **Ticket Controls:** Claim, close, reopen, transcript, and custom topics"
            ),
            "music": (
                f"{dot} **Play Audio:** `{prefix}play <song or link>`\n"
                f"{dot} **Player Card & Queue:** `{prefix}np` • `{prefix}queue` • `{prefix}loop` • `{prefix}247`"
            ),
            "ai": (
                f"{dot} **AI Chat & Personas:** `{prefix}ai <prompt>` • `/ai setup` • `/ai personality`\n"
                f"{dot} **Blox Fruits Companion:** `{prefix}bloxai <question>`"
            ),
            "leveling": (
                f"{dot} **Opt-In Status:** Leveling starts **OFF** by default for every server.\n"
                f"{dot} **Commands:** `{prefix}rank` • `{prefix}levels` • Use the toggle button below to enable/disable."
            ),
            "suggestions": (
                f"{dot} **Persistent Reminders:** `{prefix}remind 10m <text>` • `{prefix}reminders`\n"
                f"{dot} **Custom Commands:** `{prefix}cc create <name> <response>` • `{prefix}cc list`\n"
                f"{dot} **Suggestions & Polls:** `{prefix}suggest` • `{prefix}poll`"
            ),
        }

        container.add_section(
            content=(
                f"**Setup Guide — {label}** (`{'ENABLED' if enabled else 'DISABLED'}`)\n"
                f"> {desc}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(guides.get(self.current_section, f"{dot} Use `{prefix}help` to explore commands."))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.display_name}")
        return container


class ControlCenterCog(commands.Cog, name="ControlCenter"):
    """KYOKA Control Center & Smart Server Setup Wizard."""
    category: str = "Configuration"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._module_cache: dict[int, dict[str, bool]] = {}

    async def cog_load(self) -> None:
        await self.load_cache()

    def _has_db(self) -> bool:
        db = getattr(self.bot, "db", None)
        return bool(db and getattr(db, "_connected_once", False))

    async def load_cache(self) -> None:
        if not self._has_db():
            return
        try:
            rows = await self.bot.db.fetch_all("SELECT guild_id, module_id, enabled FROM guild_module_states;")
            self._module_cache.clear()
            for r in rows:
                gid = int(r["guild_id"])
                self._module_cache.setdefault(gid, {})[str(r["module_id"]).lower()] = bool(r["enabled"])
        except Exception as exc:
            logger.debug("Module state cache load notice: %s", exc)

    def is_module_enabled(self, guild_id: int, module_id: str) -> bool:
        """Check whether a module is enabled in the guild (leveling defaults to False)."""
        mod = module_id.lower()
        guild_map = self._module_cache.get(guild_id, {})
        if mod in guild_map:
            return guild_map[mod]
        if mod == "leveling":
            if hasattr(self.bot, "leveling_mgr"):
                return bool(self.bot.leveling_mgr.is_enabled(guild_id))
            return False
        return True

    async def set_module_enabled(
        self,
        guild_id: int,
        module_id: str,
        enabled: bool,
        actor_id: int | None = None,
    ) -> None:
        """Persist a module toggle for a guild."""
        mod = module_id.lower()
        self._module_cache.setdefault(guild_id, {})[mod] = bool(enabled)
        if self._has_db():
            await self.bot.db.execute(
                """
                INSERT INTO guild_module_states (guild_id, module_id, enabled, updated_by, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id, module_id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                mod,
                bool(enabled),
                actor_id,
            )

    @commands.command(
        name="control",
        aliases=["controlcenter", "wizard", "kyokasetup", "modulecontrol"],
        description="Open KYOKA's interactive Control Center & Smart Server Setup Wizard.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_cmd(self, ctx: CustomContext) -> None:
        """Launch the interactive Control Center and module setup wizard."""
        view = ControlCenterView(self, ctx)
        msg = await send_container_response(ctx, view.build_container(), view=view)
        if isinstance(msg, discord.Message):
            view.message = msg


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(ControlCenterCog(bot))
