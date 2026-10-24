"""
Kyoka 3.0 - Reusable UI Components
Confirmation dialogs, selection dropdowns, status displays, and interactive modals.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional
import discord

from src.security.owner import is_primary_owner
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.UI.Components")


class ConfirmCancelView(discord.ui.View):
    """Reusable two-button confirmation view (Confirm / Cancel)."""

    def __init__(
        self,
        author_id: int,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None

        self.confirm_btn.label = confirm_label
        self.cancel_btn.label = cancel_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id or is_primary_owner(interaction.user.id):
            return True
        await interaction.response.send_message("⛔ You are not authorized to respond to this dialog.", ephemeral=True)
        return False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_confirm")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌", custom_id="btn_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class DropdownSelect(discord.ui.Select):
    """Generic styled select dropdown."""

    def __init__(
        self,
        placeholder: str,
        options: List[discord.SelectOption],
        callback_handler: Callable[[discord.Interaction, List[str]], Any],
        custom_id: str = "kyoka_dropdown_select",
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            options=options,
            custom_id=custom_id,
            min_values=1,
            max_values=1,
        )
        self.callback_handler = callback_handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.callback_handler(interaction, self.values)


class DropdownSelectorView(discord.ui.View):
    """View wrapping a generic dropdown select."""

    def __init__(
        self,
        author_id: int,
        placeholder: str,
        options: List[discord.SelectOption],
        on_select: Callable[[discord.Interaction, List[str]], Any],
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.select_menu = DropdownSelect(placeholder, options, on_select)
        self.add_item(self.select_menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id or is_primary_owner(interaction.user.id):
            return True
        await interaction.response.send_message("⛔ You are not authorized to use this selection menu.", ephemeral=True)
        return False
