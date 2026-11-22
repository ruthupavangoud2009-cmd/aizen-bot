"""
Kyoka Discord Bot - Discord Components V2 (Container Layout) Utility
Implements Discord's new Container (type: 17) layout with embedded TextDisplays,
Sections, Separators, and integrated Action Rows (Dropdowns/Buttons inside the card).
"""

from __future__ import annotations

import logging
from typing import Any
import discord
from discord.ext import commands

from src.utils.emojis import sanitize_emoji_string

logger = logging.getLogger("Kyoka.Containers")


class KyokaContainer:
    """Builder for Discord Components V2 Container cards with a shared KYŌKA accent."""

    DEFAULT_ACCENT_COLOR = 0x7C3AED  # Royal Violet

    def __init__(self, accent_color: int | None = None) -> None:
        self.components: list[dict[str, Any]] = []
        self._accent_color: int | None = (
            accent_color if accent_color is not None else self.DEFAULT_ACCENT_COLOR
        )
        self.author_name: str | None = None
        self.author_icon_url: str | None = None
        self.footer_text: str | None = None
        self.footer_icon_url: str | None = None

    def set_author(self, name: str, icon_url: str | None = None) -> KyokaContainer:
        """Set author header for embed conversion."""
        self.author_name = name
        self.author_icon_url = icon_url
        return self

    def set_footer(self, text: str, icon_url: str | None = None) -> KyokaContainer:
        """Set footer text and icon for embed conversion."""
        self.footer_text = text
        self.footer_icon_url = icon_url
        return self

    @property
    def accent_color(self) -> int | None:
        return self._accent_color

    @accent_color.setter
    def accent_color(self, value: int | None) -> None:
        self._accent_color = value

    def add_text(self, content: str) -> KyokaContainer:
        """Add a TextDisplay component (type: 10) inside the container."""
        self.components.append({
            "type": 10,
            "content": content,
        })
        return self

    def add_section(
        self,
        content: str,
        accessory: dict[str, Any] | None = None,
    ) -> KyokaContainer:
        """Add a Section component (type: 9) if accessory is present, otherwise TextDisplay (type: 10)."""
        if not accessory:
            return self.add_text(content)

        section_data: dict[str, Any] = {
            "type": 9,
            "components": [
                {
                    "type": 10,
                    "content": content,
                }
            ],
            "accessory": accessory,
        }
        self.components.append(section_data)
        return self

    def add_separator(self, divider: bool = True) -> KyokaContainer:
        """Add a visual Separator component (type: 14)."""
        self.components.append({
            "type": 14,
            "divider": divider,
        })
        return self

    def add_footer(self, text: str, icon_url: str | None = None) -> KyokaContainer:
        """Add a footer."""
        self.add_text(f"{text}")
        return self

    def add_field(self, name: str, value: str, inline: bool = False) -> KyokaContainer:
        """Add a formatted field to the container."""
        return self.add_text(f"**{name}**\n{value}")

    def add_media(self, url: str) -> KyokaContainer:
        """Add a full-width Media Gallery component (type: 12) inside the container."""
        if not url or not str(url).strip():
            return self
        self.components.append({
            "type": 12,
            "items": [
                {
                    "media": {
                        "url": str(url).strip()
                    }
                }
            ]
        })
        return self

    def add_image(self, url: str) -> KyokaContainer:
        """Alias for add_media."""
        return self.add_media(url)

    def add_thumbnail(self, url: str) -> KyokaContainer:
        """Add a thumbnail accessory or media."""
        if not url or not str(url).strip():
            return self
        clean_url = str(url).strip()
        # If there's an existing section/text component without accessory, attach to it
        for comp in reversed(self.components):
            if comp.get("type") == 10:  # upgrade TextDisplay to Section with accessory
                content = comp.get("content", "")
                idx = self.components.index(comp)
                self.components[idx] = {
                    "type": 9,
                    "components": [{"type": 10, "content": content}],
                    "accessory": {
                        "type": 11,
                        "media": {"url": clean_url}
                    }
                }
                return self
            elif comp.get("type") == 9 and "accessory" not in comp:
                comp["accessory"] = {
                    "type": 11,
                    "media": {"url": clean_url}
                }
                return self

        # Fallback: add a section with thumbnail
        self.components.append({
            "type": 9,
            "components": [{"type": 10, "content": " "}],
            "accessory": {
                "type": 11,
                "media": {"url": clean_url}
            }
        })
        return self

    def add_action_row(self, items: list[dict[str, Any]]) -> KyokaContainer:
        """Add an Action Row (type: 1) containing Select Menus or Buttons inside the container."""
        self.components.append({
            "type": 1,
            "components": items,
        })
        return self

    def to_embed(self, content: str | None = None) -> discord.Embed:
        """Convert container components into a standard signature discord.Embed."""
        if hasattr(self, "_fallback_embed") and self._fallback_embed is not None:
            return self._fallback_embed

        color = self.accent_color if self.accent_color is not None else self.DEFAULT_ACCENT_COLOR
        embed = discord.Embed(
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        desc_parts: list[str] = []
        if content and str(content).strip():
            desc_parts.append(str(content).strip())

        footer_text: str | None = getattr(self, "footer_text", None)

        for comp in self.components:
            ctype = comp.get("type")
            if ctype == 10:  # TextDisplay
                text = str(comp.get("content", ""))
                if text.startswith("-# "):
                    footer_text = text.replace("-# ", "").strip()
                elif text.startswith("## ") and not embed.title:
                    embed.title = text.replace("## ", "").strip()
                elif text.strip():
                    desc_parts.append(text.strip())

            elif ctype == 9:  # Section
                sub_comps = comp.get("components", [])
                for sc in sub_comps:
                    text = str(sc.get("content", ""))
                    if text.startswith("-# "):
                        footer_text = text.replace("-# ", "").strip()
                    elif text.startswith("## ") and not embed.title:
                        embed.title = text.replace("## ", "").strip()
                    elif text.strip():
                        desc_parts.append(text.strip())

                acc = comp.get("accessory", {})
                if acc.get("type") == 11 and "media" in acc:
                    embed.set_thumbnail(url=acc["media"].get("url", ""))

            elif ctype == 12:  # Media Gallery
                items = comp.get("items", [])
                if items and "media" in items[0]:
                    embed.set_image(url=items[0]["media"].get("url", ""))

        if desc_parts:
            raw_desc = "\n\n".join(desc_parts)
            embed.description = sanitize_emoji_string(raw_desc)[:4000]

        if embed.title:
            embed.title = sanitize_emoji_string(embed.title)[:256]

        if footer_text:
            embed.set_footer(
                text=footer_text[:2048],
                icon_url=getattr(self, "footer_icon_url", None),
            )
        elif not embed.footer or not embed.footer.text:
            embed.set_footer(
                text="✧ KYOKA Suigetsu Protocol",
                icon_url=getattr(self, "footer_icon_url", None),
            )

        if getattr(self, "author_name", None):
            embed.set_author(
                name=self.author_name[:256],
                icon_url=getattr(self, "author_icon_url", None),
            )

        return embed

    def build(self) -> discord.Embed:
        """Compatibility method returning a discord.Embed representation."""
        return self.to_embed()

    def to_dict(self) -> dict[str, Any]:
        """Serialize container to Discord API component structure."""
        comps = list(self.components)
        if not comps:
            comps.append({"type": 10, "content": " "})
        data: dict[str, Any] = {
            "type": 17,
            "components": comps,
        }
        if self.accent_color is not None:
            data["accent_color"] = self.accent_color
        return data

def build_container_payload(
    container: KyokaContainer | list[KyokaContainer],
    view: discord.ui.View | None = None,
    content: str | None = None,
    allowed_mentions: discord.AllowedMentions | dict[str, Any] | None = None,
    is_edit: bool = False,
) -> dict[str, Any]:
    """Generate the full Discord REST payload supporting single or multiple stacked containers with root-level controls."""
    if isinstance(container, list):
        container_list = container
    else:
        container_list = [container]

    root_comps = []

    # In Components V2 (flag 32768), traditional top-level 'content' is forbidden by Discord API.
    # Any outer text / mention ping must be placed as a top-level TextDisplay component (type 10).
    if content and str(content).strip():
        root_comps.append({
            "type": 10,
            "content": str(content).strip(),
        })

    for c in container_list:
        c_dict: dict[str, Any] = {
            "type": 17,
            "components": list(c.components),
        }
        if c.accent_color is not None:
            c_dict["accent_color"] = c.accent_color

        if not c_dict["components"]:
            c_dict["components"] = [{"type": 10, "content": "\u200b"}]
        else:
            for comp in c_dict["components"]:
                if comp.get("type") == 10 and (not comp.get("content") or not str(comp.get("content")).strip()):
                    comp["content"] = "\u200b"
                elif comp.get("type") == 9:
                    for sub in comp.get("components", []):
                        if sub.get("type") == 10 and (not sub.get("content") or not str(sub.get("content")).strip()):
                            sub["content"] = "\u200b"

        root_comps.append(c_dict)

    # Place view action rows (builder buttons and dropdowns) directly INSIDE the container
    if view is not None:
        if hasattr(view, "to_container_components"):
            view_comps = view.to_container_components()
        else:
            view_comps = view.to_components()
        if view_comps:
            if root_comps and root_comps[-1].get("type") == 17:
                root_comps[-1]["components"].extend(view_comps)
            else:
                root_comps.extend(view_comps)

    if allowed_mentions is not None:
        if isinstance(allowed_mentions, discord.AllowedMentions):
            mentions_payload = allowed_mentions.to_dict()
        else:
            mentions_payload = allowed_mentions
    else:
        # Default: allow parsing user mentions and replied user; suppress mass everyone/role pings
        mentions_payload = {
            "parse": ["users"],
            "replied_user": True,
        }

    payload: dict[str, Any] = {
        "components": root_comps[:5],  # Discord allows maximum 5 top-level items
        "allowed_mentions": mentions_payload,
    }
    if not is_edit:
        payload["flags"] = 32768  # IS_COMPONENTS_V2 (1 << 15) only valid on new message creation

    return payload


def _prepare_multipart_form(
    payload: dict[str, Any],
    file_list: list[discord.File],
    wrapper: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Constructs compliant multipart form fields for Discord REST API file uploads.
    Injects attachments metadata array into payload and attaches binary streams as files[i].
    """
    for f in file_list:
        try:
            f.reset()
        except Exception:
            pass

    payload["attachments"] = [
        {"id": i, "filename": f.filename}
        for i, f in enumerate(file_list)
    ]

    top_json = wrapper if wrapper is not None else payload
    if wrapper is not None and "data" in wrapper:
        wrapper["data"] = payload

    form: list[dict[str, Any]] = [
        {"name": "payload_json", "value": discord.utils._to_json(top_json)}
    ]
    for i, f in enumerate(file_list):
        form.append({
            "name": f"files[{i}]",
            "value": f.fp,
            "filename": f.filename,
            "content_type": "application/octet-stream",
        })
    return form


async def send_container_response(
    interaction_or_ctx: discord.Interaction | commands.Context | discord.abc.Messageable | discord.User | discord.Member,
    container: KyokaContainer | list[KyokaContainer],
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    content: str | None = None,
    file: discord.File | None = None,
    files: list[discord.File] | None = None,
    allowed_mentions: discord.AllowedMentions | dict[str, Any] | None = None,
) -> Any:
    """Send a message using standard, high-definition Discord Rich Embeds with custom Kyoka Sovereign aesthetics."""
    interaction = getattr(interaction_or_ctx, "interaction", None)
    target = interaction if interaction is not None else interaction_or_ctx

    container_list = container if isinstance(container, list) else [container]
    primary = container_list[0]

    # Resolve fallback link view if buttons are embedded inside container components
    actual_view = view
    if actual_view is None:
        link_view = discord.ui.View(timeout=None)
        has_links = False
        for c in container_list:
            for comp in getattr(c, "components", []):
                if comp.get("type") == 1:
                    for item in comp.get("components", []):
                        if item.get("type") == 2 and item.get("style") == 5:
                            lbl = item.get("label", "Link")
                            u = item.get("url", "https://discord.com")
                            if u and u.startswith("http"):
                                link_view.add_item(discord.ui.Button(label=lbl, url=u, style=discord.ButtonStyle.link))
                                has_links = True
        if has_links:
            actual_view = link_view

    file_list = [file] if file is not None else (files or None)

    guild = getattr(target, "guild", None)
    bot = getattr(target, "client", getattr(target, "bot", None))
    if not bot and hasattr(target, "_state"):
        bot = getattr(target._state, "_parent", getattr(target._state, "bot", None))

    custom_ui_color = None
    if guild and bot and hasattr(bot, "guild_mgr"):
        custom_ui_color = bot.guild_mgr.get_ui_color(guild.id, default=None)

    embeds = []
    for i, c in enumerate(container_list):
        emb = c.to_embed(content=content if i == 0 else None)
        if custom_ui_color is not None:
            emb.color = discord.Color(custom_ui_color)
        elif emb.color is None or emb.color.value == 0:
            emb.color = discord.Color(KyokaContainer.DEFAULT_ACCENT_COLOR)
        embeds.append(emb)

    single_embed = embeds[0] if len(embeds) == 1 else None

    # 1. Interaction or Hybrid Interaction
    if isinstance(target, discord.Interaction):
        try:
            if target.response.is_done():
                if single_embed:
                    return await target.followup.send(
                        embed=single_embed,
                        view=actual_view or discord.utils.MISSING,
                        ephemeral=ephemeral,
                        files=file_list or discord.utils.MISSING,
                    )
                else:
                    return await target.followup.send(
                        embeds=embeds,
                        view=actual_view or discord.utils.MISSING,
                        ephemeral=ephemeral,
                        files=file_list or discord.utils.MISSING,
                    )
            else:
                if single_embed:
                    await target.response.send_message(
                        embed=single_embed,
                        view=actual_view or discord.utils.MISSING,
                        ephemeral=ephemeral,
                        files=file_list or discord.utils.MISSING,
                    )
                else:
                    await target.response.send_message(
                        embeds=embeds,
                        view=actual_view or discord.utils.MISSING,
                        ephemeral=ephemeral,
                        files=file_list or discord.utils.MISSING,
                    )
                try:
                    return await target.original_response()
                except Exception:
                    return None
        except (discord.NotFound, discord.HTTPException):
            channel = getattr(target, "channel", None)
            if channel and hasattr(channel, "send"):
                if single_embed:
                    return await channel.send(
                        embed=single_embed,
                        view=actual_view or discord.utils.MISSING,
                        files=file_list or discord.utils.MISSING,
                    )
                return await channel.send(
                    embeds=embeds,
                    view=actual_view or discord.utils.MISSING,
                    files=file_list or discord.utils.MISSING,
                )
            raise

    # 2. Context
    if isinstance(target, commands.Context):
        try:
            if single_embed:
                return await target.reply(
                    embed=single_embed,
                    view=actual_view or discord.utils.MISSING,
                    files=file_list or discord.utils.MISSING,
                    mention_author=False,
                )
            return await target.reply(
                embeds=embeds,
                view=actual_view or discord.utils.MISSING,
                files=file_list or discord.utils.MISSING,
                mention_author=False,
            )
        except Exception:
            if single_embed:
                return await target.send(
                    embed=single_embed,
                    view=actual_view or discord.utils.MISSING,
                    files=file_list or discord.utils.MISSING,
                )
            return await target.send(
                embeds=embeds,
                view=actual_view or discord.utils.MISSING,
                files=file_list or discord.utils.MISSING,
            )

    # 3. Direct Messageable Channel / Thread
    if hasattr(target, "send") and callable(target.send):
        if single_embed:
            return await target.send(
                embed=single_embed,
                view=actual_view or discord.utils.MISSING,
                files=file_list or discord.utils.MISSING,
            )
        return await target.send(
            embeds=embeds,
            view=actual_view or discord.utils.MISSING,
            files=file_list or discord.utils.MISSING,
        )

    # 4. User or Member DM
    if isinstance(target, (discord.User, discord.Member)):
        dm = await target.create_dm()
        if single_embed:
            return await dm.send(
                embed=single_embed,
                view=actual_view or discord.utils.MISSING,
                files=file_list or discord.utils.MISSING,
            )
        return await dm.send(
            embeds=embeds,
            view=actual_view or discord.utils.MISSING,
            files=file_list or discord.utils.MISSING,
        )

    raise ValueError(f"Unsupported target for send_container_response: {type(target)}")


async def edit_container_response(
    interaction_or_msg: discord.Interaction | discord.Message,
    container: KyokaContainer | list[KyokaContainer],
    view: discord.ui.View | None = None,
    file: discord.File | None = None,
    files: list[discord.File] | None = None,
    content: str | None = None,
) -> Any:
    """Edit an existing message or interaction safely using Discord Rich Embeds."""
    container_list = container if isinstance(container, list) else [container]
    embeds = [c.to_embed(content=content if i == 0 else None) for i, c in enumerate(container_list)]
    single_embed = embeds[0] if len(embeds) == 1 else None

    if isinstance(interaction_or_msg, discord.Message):
        if single_embed:
            return await interaction_or_msg.edit(
                embed=single_embed,
                view=view or discord.utils.MISSING,
            )
        return await interaction_or_msg.edit(
            embeds=embeds,
            view=view or discord.utils.MISSING,
        )

    if isinstance(interaction_or_msg, discord.Interaction):
        if not interaction_or_msg.response.is_done():
            if single_embed:
                return await interaction_or_msg.response.edit_message(
                    embed=single_embed,
                    view=view or discord.utils.MISSING,
                )
            return await interaction_or_msg.response.edit_message(
                embeds=embeds,
                view=view or discord.utils.MISSING,
            )
        else:
            if single_embed:
                return await interaction_or_msg.edit_original_response(
                    embed=single_embed,
                    view=view or discord.utils.MISSING,
                )
            return await interaction_or_msg.edit_original_response(
                embeds=embeds,
                view=view or discord.utils.MISSING,
            )


# Backward Compatibility Alias
KyroContainer = KyokaContainer

