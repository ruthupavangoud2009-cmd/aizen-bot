from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Any
import discord

from src.utils.containers import KyokaContainer, KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot, KyroBot
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyoka.Music.Views")


class MusicControlView(discord.ui.View):
    """Interactive media control row with zero unicode emojis (uses custom application emojis)."""

    def __init__(
        self,
        bot: KyokaBot | KyroBot,
        player: Optional[GuildPlayer] = None,
        guild_id: Optional[int] = None,
        track_url: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.guild_id = guild_id or (player.guild.id if player else 0)

        # Apply custom emojis from assets if available
        self._apply_custom_emojis()

    def _apply_custom_emojis(self) -> None:
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return

        def _safe_emoji(name: str) -> Optional[discord.PartialEmoji | str]:
            if not hasattr(e_reg, "get_emoji_obj"):
                return None
            try:
                res = e_reg.get_emoji_obj(name)
                if isinstance(res, (str, discord.Emoji, discord.PartialEmoji)):
                    return res
            except Exception:
                pass
            return None

        is_paused = bool(self.player and self.player.is_paused)

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                cid = child.custom_id or ""
                if "playpause" in cid:
                    if is_paused:
                        child.label = "Resume"
                        em = _safe_emoji("music") or _safe_emoji("paused")
                        if em:
                            child.emoji = em
                    else:
                        child.label = "Pause"
                        em = _safe_emoji("paused")
                        if em:
                            child.emoji = em
                elif "skip" in cid:
                    em = _safe_emoji("skip")
                    if em:
                        child.emoji = em
                elif "voldown" in cid:
                    em = _safe_emoji("volume_down") or _safe_emoji("voldown")
                    if em:
                        child.emoji = em
                elif "volup" in cid:
                    em = _safe_emoji("volume_up") or _safe_emoji("volup")
                    if em:
                        child.emoji = em
                elif "stop" in cid:
                    em = _safe_emoji("icons_stop_button") or _safe_emoji("stop")
                    if em:
                        child.emoji = em
                elif "like" in cid or "loop" in cid or "autoplay" in cid or "queue" in cid:
                    child.emoji = None

    def _get_player(self, interaction: discord.Interaction) -> Optional[GuildPlayer]:
        if interaction.guild_id:
            music_cog = self.bot.get_cog("Music")
            if music_cog and hasattr(music_cog, "controller"):
                p = music_cog.controller.get_player(interaction.guild_id)
                if p:
                    self.player = p
                    return p
        return self.player

    def _check_voice(self, interaction: discord.Interaction, player: Optional[GuildPlayer]) -> Optional[str]:
        """Verify that user is connected to the same voice channel as Kyoka."""
        if not player or not player.is_connected or not player.voice_client or not player.voice_client.channel:
            return "Player is not connected to a voice channel."

        member = interaction.user
        if not isinstance(member, discord.Member):
            return "Could not verify your voice state."

        if interaction.guild_id and player.guild.id != interaction.guild_id:
            return "Unauthorized cross-server playback control attempt."

        # Allow server administrators, manage_guild, or users with DJ role
        has_dj = any(
            role.name.lower() in ("dj", "music dj", "kyoka dj", "kyro dj")
            for role in getattr(member, "roles", [])
        )
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild or has_dj:
            return None

        voice_state = getattr(member, "voice", None)
        user_vc = getattr(voice_state, "channel", None) if voice_state else None
        if not user_vc or not getattr(user_vc, "id", None):
            return "Join a voice channel first, then try again."

        vc = getattr(player, "voice_client", None)
        bot_vc = getattr(vc, "channel", None) if vc else None
        if not bot_vc or not getattr(bot_vc, "id", None):
            return "Kyoka is not connected to a voice channel."

        if user_vc.id != bot_vc.id:
            return f"You must be in the same voice channel as Kyoka ({bot_vc.mention}) to use music controls."

        return None

    @discord.ui.button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:playpause",
    )
    async def btn_pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        if not player or not player.is_connected or not player.current:
            c = KyokaContainer()
            c.add_section(content="**Playback Notice**\n> No active track is currently playing or paused.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        if player.is_paused:
            player.resume()
            button.label = "Pause"
            if e_reg:
                button.emoji = e_reg.get_emoji_obj("paused")
        elif player.is_playing:
            player.pause()
            button.label = "Resume"
            if e_reg:
                button.emoji = e_reg.get_emoji_obj("music") or e_reg.get_emoji_obj("paused")

        await player.update_controller_message(force=True)

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:skip",
    )
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        if not player or not player.is_connected or not player.current:
            c = KyokaContainer()
            c.add_section(content="**Skip Notice**\n> Nothing is currently playing to skip.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        try:
            await player.skip()
        except Exception as e:
            logger.warning(f"Skip button failed in guild {interaction.guild_id}: {type(e).__name__}: {e}")
            c = KyokaContainer()
            c.add_section(content=f"**Skip Notice**\n> Could not skip right now: `{e}`")
            await send_container_response(interaction, c, ephemeral=True)
            return

    @discord.ui.button(
        label="Vol -",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:voldown",
    )
    async def btn_vol_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        cur_vol = int(player.volume * 100)
        player.set_volume(cur_vol - 10)
        await player.update_controller_message(force=True)

    @discord.ui.button(
        label="Vol +",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:volup",
    )
    async def btn_vol_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        cur_vol = int(player.volume * 100)
        player.set_volume(cur_vol + 10)
        await player.update_controller_message(force=True)

    @discord.ui.button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        custom_id="kyoka:music:stop",
    )
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        player._disconnect_announced = True
        await player.stop()

    @discord.ui.button(
        label="Like",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:like",
        row=1,
    )
    async def btn_like(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        if not player or not player.current:
            c = KyokaContainer()
            c.add_section(content="**Favorites Notice**\n> No track is currently playing to add to Favorites.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        if not getattr(self.bot, "db", None) or not getattr(self.bot.db, "pool", None):
            c = KyokaContainer()
            c.add_section(content="**Database Notice**\n> Database service is currently offline. Please try again later.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        current = player.current
        db = self.bot.db
        user_id = interaction.user.id

        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = 'favorites';",
            user_id,
        )
        if not pl_row:
            await db.execute(
                "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, 'Favorites') ON CONFLICT DO NOTHING;",
                user_id,
            )
            pl_row = await db.fetch_one(
                "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = 'favorites';",
                user_id,
            )

        if not pl_row:
            c = KyokaContainer()
            c.add_section(content="**Database Error**\n> Failed to access your Favorites playlist.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        playlist_id = pl_row["id"]
        save_title = (current.title or "Unknown Track")[:250].replace("[", "(").replace("]", ")")
        save_author = (current.author or "Official Artist")[:250]

        existing = await db.fetch_one(
            "SELECT id FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) = LOWER($2);",
            playlist_id,
            save_title,
        )
        if existing:
            c = KyokaContainer()
            c.add_section(content=f"**Favorites Notice**\n> `{save_title}` is already in your **Favorites**.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        track_web_url = getattr(current, "url", None) or getattr(current, "stream_url", "")
        await db.execute(
            "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
            playlist_id,
            save_title,
            save_author,
            current.duration,
            track_web_url,
        )
        c = KyokaContainer()
        c.add_section(content=f"**Favorites Added**\n> Saved **[{save_title}]({track_web_url})** to your **Favorites** playlist!")
        await send_container_response(interaction, c, ephemeral=True)

    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:loop",
        row=1,
    )
    async def btn_loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        new_mode = player.set_loop_mode()
        await player.update_controller_message(force=True)
        c = KyokaContainer()
        c.add_section(content=f"**Loop Mode**\n> Loop mode set to **{new_mode.upper()}**.")
        await send_container_response(interaction, c, ephemeral=True)

    @discord.ui.button(
        label="Autoplay",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:autoplay",
        row=1,
    )
    async def btn_autoplay(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        err = self._check_voice(interaction, player)
        if err:
            c = KyokaContainer()
            c.add_section(content=f"**Voice Error**\n> {err}")
            await send_container_response(interaction, c, ephemeral=True)
            return

        player.smart_autoplay = not player.smart_autoplay
        state = "Enabled" if player.smart_autoplay else "Disabled"
        await player.update_controller_message(force=True)
        c = KyokaContainer()
        c.add_section(content=f"**Smart Autoplay**\n> Smart Autoplay **{state}**.")
        await send_container_response(interaction, c, ephemeral=True)

    @discord.ui.button(
        label="Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:music:queue",
        row=1,
    )
    async def btn_queue(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self._get_player(interaction)
        if not player or (not player.queue and not player.current):
            c = KyokaContainer()
            c.add_section(content="**Queue Empty**\n> The playback queue is currently empty.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        curr_text = ""
        if player.current:
            safe_curr = player.current.title.replace("[", "(").replace("]", ")")
            curr_link = f"[{safe_curr}]({player.current.url})" if player.current.url else f"**{safe_curr}**"
            curr_text = f"**Now Playing:** {curr_link} `[{player.current.formatted_duration}]`\n\n"

        if not player.queue:
            c = KyokaContainer()
            c.add_section(content=f"{curr_text}**Upcoming Queue:** None\n> Use `?play <song>` to add more songs.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        q_lines = []
        for i, t in enumerate(player.queue[:10], 1):
            safe_title = t.title.replace("[", "(").replace("]", ")")
            track_link = f"[{safe_title}]({t.url})" if t.url else f"**{safe_title}**"
            q_lines.append(f"`{i:02d}.` {track_link} `[{t.formatted_duration}]` — `{t.requester}`")

        remaining = len(player.queue) - 10
        rem_text = f"\n*...and {remaining} more in queue*" if remaining > 0 else ""
        c = KyokaContainer()
        c.add_section(
            content=f"{curr_text}**Upcoming Queue ({len(player.queue)} tracks):**\n" + "\n".join(q_lines) + rem_text
        )
        await send_container_response(interaction, c, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]) -> None:
        logger.error(f"Error in music control view item {item}: {error}", exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            c = KyokaContainer()
            c.add_section(content="**Control Notice**\n> An unexpected issue occurred while executing this action.")
            await send_container_response(interaction, c, ephemeral=True)
        except Exception:
            pass
