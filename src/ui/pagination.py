"""
Kyoka 3.0 - UI Pagination View
Interactive, mobile-friendly paginated view supporting custom embeds, 5-15 items per page,
author locking, timeout cleanup, and Aizen aesthetics.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional
import discord

from src.security.owner import is_primary_owner
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.UI.Pagination")


class KyokaPaginatorView(discord.ui.View):
    """Reusable paginator view for embeds or list data."""

    def __init__(
        self,
        embeds: List[discord.Embed],
        author_id: int,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.author_id = author_id
        self.current_page: int = 0
        self.message: Optional[discord.Message] = None

        self._update_button_states()

    def _update_button_states(self) -> None:
        total = len(self.embeds)
        self.first_page_btn.disabled = self.current_page <= 0
        self.prev_page_btn.disabled = self.current_page <= 0
        self.page_indicator_btn.label = f"{self.current_page + 1} / {max(1, total)}"
        self.next_page_btn.disabled = self.current_page >= total - 1
        self.last_page_btn.disabled = self.current_page >= total - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Lock paginator controls to command author or primary bot owner."""
        if interaction.user.id == self.author_id or is_primary_owner(interaction.user.id):
            return True
        await interaction.response.send_message(
            "⛔ This navigation menu is locked to the original user.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="pag_first")
    async def first_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = 0
        self._update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary, custom_id="pag_prev")
    async def prev_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
        self._update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="pag_indicator")
    async def page_indicator_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, custom_id="pag_next")
    async def next_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
        self._update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="pag_last")
    async def last_page_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = len(self.embeds) - 1
        self._update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger, custom_id="pag_stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self) -> None:
        """Disable buttons upon interaction timeout."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


def paginate_items(
    items: List[str],
    per_page: int = 10,
    title: str = "Command Directory",
    color: int = KyokaTheme.PRIMARY,
    prefix_line: str = "• ",
) -> List[discord.Embed]:
    """Helper to partition strings into pages of 5-15 items per embed."""
    per_page = max(5, min(15, per_page))
    if not items:
        embed = discord.Embed(
            title=title,
            description="*No items found in this section.*",
            color=color,
        )
        embed.set_footer(text=KyokaTheme.FOOTER_TEXT)
        return [embed]

    embeds: List[discord.Embed] = []
    total_pages = (len(items) + per_page - 1) // per_page

    for i in range(0, len(items), per_page):
        chunk = items[i : i + per_page]
        desc = "\n".join(f"{prefix_line}{item}" for item in chunk)
        page_num = (i // per_page) + 1
        embed = discord.Embed(
            title=title,
            description=desc,
            color=color,
        )
        embed.set_footer(text=f"Page {page_num} of {total_pages} • {KyokaTheme.FOOTER_TEXT}")
        embeds.append(embed)

    return embeds
