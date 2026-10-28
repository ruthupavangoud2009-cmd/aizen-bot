"""
KYOKA 3.0 - Modular AI Voice Engine.
Provides high-fidelity conversational Text-to-Speech (TTS), voice channel connectivity,
AI speech responses, multi-voice switching, and comprehensive diagnostics.
Coexists cleanly with Music: never disconnects or interrupts active music sessions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import io
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import static_ffmpeg
import wavelink
from src.ui.asset_manager import AssetManager
from gtts import gTTS

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False

from src.core.context import CustomContext
from src.managers.blox_fruits_web_manager import BloxFruitsWebManager
from src.managers.voice_summary_manager import (
    VoiceSummaryManager,
    VoiceListeningControlView,
    VoiceMeetingSink,
    VoiceListeningSession,
)
from src.managers.voice_conversation_manager import (
    VoiceConversationManager,
    VoiceConversationSession,
    VoiceConversationControlView,
    VoiceConversationSink,
    SoundboardControlView,
    CONVERSATIONAL_VIBES,
    HUMAN_VOICES,
)

logger = logging.getLogger("Kyoka.AIVoice")
PURPLE = 0x6F43BE

# Ensure static FFmpeg path is loaded
try:
    static_ffmpeg.add_paths()
except Exception:
    pass


def _is_vc_connected(vc: Any) -> bool:
    """Safe connection check that supports both discord.VoiceClient and wavelink.Player."""
    if not vc:
        return False
    if hasattr(vc, "is_connected") and callable(vc.is_connected):
        try:
            return vc.is_connected()
        except Exception:
            pass
    return bool(getattr(vc, "connected", False))


# Ensure Discord Opus is loaded on Windows
if not discord.opus.is_loaded():
    candidates = [
        Path(sys.prefix) / "Lib/site-packages/discord/bin/libopus-0.x64.dll",
        Path(sys.prefix) / "Lib/site-packages/discord/bin/libopus-0.x86.dll",
        "libopus-0.x64.dll",
        "opus",
    ]
    for c in candidates:
        try:
            if isinstance(c, Path) and not c.exists():
                continue
            discord.opus.load_opus(str(c))
            if discord.opus.is_loaded():
                break
        except Exception:
            pass

AVAILABLE_VOICES: Dict[str, Dict[str, str]] = {
    "ava": {
        "id": "en-US-AvaNeural",
        "name": "Ava",
        "style": "Ultra-realistic, expressive human conversational female",
        "gender": "Female (Human)",
    },
    "andrew": {
        "id": "en-US-AndrewNeural",
        "name": "Andrew",
        "style": "Ultra-realistic, natural warm conversational male",
        "gender": "Male (Human)",
    },
    "aizen": {
        "id": "en-GB-RyanNeural",
        "name": "Sosuke Aizen",
        "style": "Deep, authoritative British male anime cadence",
        "gender": "Male",
    },
    "kyoka": {
        "id": "en-US-JennyNeural",
        "name": "Kyoka",
        "style": "Expressive, melodic female anime voice",
        "gender": "Female",
    },
    "guy": {
        "id": "en-US-GuyNeural",
        "name": "Guy",
        "style": "Neutral, clean modern American male",
        "gender": "Male",
    },
    "christopher": {
        "id": "en-US-ChristopherNeural",
        "name": "Christopher",
        "style": "Warm, confident conversational male",
        "gender": "Male",
    },
    "aria": {
        "id": "en-US-AriaNeural",
        "name": "Aria",
        "style": "Crisp, professional studio female",
        "gender": "Female",
    },
    "keita": {
        "id": "ja-JP-KeitaNeural",
        "name": "Keita",
        "style": "Authentic Japanese male anime voice",
        "gender": "Male (Japanese)",
    },
    "nanami": {
        "id": "ja-JP-NanamiNeural",
        "name": "Nanami",
        "style": "Authentic Japanese female anime voice",
        "gender": "Female (Japanese)",
    },
}


class AIVoice(commands.Cog, name="AIVoice"):
    """Modular AI Voice Assistant with neural TTS and voice channel interactions."""
    category = "🤖・ARTIFICIAL INTELLIGENCE"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.web_mgr = BloxFruitsWebManager()
        self.summary_mgr = VoiceSummaryManager(bot=bot)
        self.conv_mgr = VoiceConversationManager(bot=bot)
        self._guild_voices: Dict[int, str] = {}
        self._voice_locks: Dict[int, asyncio.Lock] = {}
        self._speech_queues: Dict[int, asyncio.Queue] = {}
        self._active_tasks: Dict[int, asyncio.Task] = {}
        self._http_session: Optional[aiohttp.ClientSession] = None

    def get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._voice_locks:
            self._voice_locks[guild_id] = asyncio.Lock()
        return self._voice_locks[guild_id]

    def _get_queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self._speech_queues:
            self._speech_queues[guild_id] = asyncio.Queue()
        return self._speech_queues[guild_id]

    def _get_voice_id(self, guild_id: int) -> str:
        key = self._guild_voices.get(guild_id, "aizen")
        return AVAILABLE_VOICES.get(key, AVAILABLE_VOICES["aizen"])["id"]

    def _is_music_active(self, guild: discord.Guild) -> bool:
        """Check if guild voice client is owned or actively used by Music subsystem."""
        vc = guild.voice_client
        if not vc:
            return False
        if isinstance(vc, wavelink.Player):
            return True
        music_ctrl = getattr(self.bot, "_music_controller", None)
        if music_ctrl and hasattr(music_ctrl, "get_player"):
            player = music_ctrl.get_player(guild.id)
            if player and (player.is_playing or player.queue or getattr(player, "is_247", False)):
                return True
        return False

    async def _synthesize_audio(self, text: str, voice_id: str, output_path: str) -> bool:
        """Synthesize text to mp3 using Edge-TTS or gTTS fallback."""
        if HAS_EDGE_TTS:
            try:
                comm = edge_tts.Communicate(text, voice_id)
                await comm.save(output_path)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
            except Exception as e:
                logger.debug(f"Edge-TTS failed, falling back to gTTS: {e}")

        # Fallback to gTTS
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: gTTS(text=text, lang="en").save(output_path))
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.error(f"TTS synthesis failure: {e}")
            return False

    async def _play_audio_file(self, voice_client: discord.VoiceClient, file_path: str) -> None:
        """Play local audio file through VoiceClient with completion await and safe error recovery."""
        if not isinstance(voice_client, discord.VoiceClient):
            logger.warning("Attempted to play audio file on non-discord.VoiceClient instance.")
            return

        try:
            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.08)
        except Exception:
            pass

        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        source = discord.FFmpegPCMAudio(file_path, executable=ffmpeg_bin)
        done_event = asyncio.Event()

        def after_play(err: Optional[Exception]) -> None:
            if err:
                logger.error(f"Error during audio playback: {err}")
            done_event.set()

        try:
            voice_client.play(source, after=after_play)
            try:
                await asyncio.wait_for(done_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Audio playback wait timed out after 30s.")
        except Exception as e:
            logger.error(f"Error starting audio playback on voice client: {e}")
            done_event.set()

    async def _connect_voice(self, channel: discord.VoiceChannel | discord.StageChannel) -> Any:
        """Connect to voice channel using VoiceRecvClient when available."""
        if HAS_VOICE_RECV:
            return await channel.connect(cls=voice_recv.VoiceRecvClient)
        return await channel.connect()

    # ─── VOICE COMMANDS ──────────────────────────────────────────────────────

    @commands.group(
        name="aivoice",
        aliases=["voiceai", "aiv"],
        invoke_without_command=True,
        description="Interact with the KYOKA AI Voice Assistant in voice channels.",
    )
    async def aivoice_group(self, ctx: CustomContext) -> None:
        """Display AI Voice commands and status."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        active_voice = self._guild_voices.get(ctx.guild.id if ctx.guild else 0, "aizen")
        voice_meta = AVAILABLE_VOICES.get(active_voice, AVAILABLE_VOICES["aizen"])

        embed = discord.Embed(
            title="🎙️ KYOKA AI Voice & Meeting Intelligence Hub",
            description=(
                "> Natural-sounding neural voice synthesis, 7 conversational vibes, live soundboard, and meeting intelligence.\n\n"
                f"• `{p}aivoice talk [vibe]` — Live 2-way human voice conversation with Cyberpunk HUD\n"
                f"• `{p}aivoice vibe [name]` — Switch conversational vibe (Aizen, Gamer, Chill, Tsundere, Cyber AI)\n"
                f"• `{p}aivoice sfx [name]` — Live soundboard with boom, airhorn, level up, rimshot, and laser\n"
                f"• `{p}aivoice roast [@user]` — Deliver a hilarious verbal roast in VC with dramatic bass drop\n"
                f"• `{p}aivoice beatbox` — Drop a vocal beatbox routine into the voice channel\n"
                f"• `{p}aivoice trivia` — Host a live spoken trivia challenge with countdown chimes\n"
                f"• `{p}aivoice talkmode` — Toggle between Open Mic and Wake Word ('Kyoka')\n"
                f"• `{p}aivoice endtalk` — Conclude live conversation and get dialogue log\n"
                f"• `{p}aivoice listen [mins]` — AI joins VC, listens to conversation, and takes meeting notes\n"
                f"• `{p}aivoice summary` — Conclude voice session and generate AI meeting report\n"
                f"• `{p}aivoice speak <text>` — Synthesize speech with selected voice\n"
                f"• `{p}aivoice voice [name]` — Switch voice persona (e.g. `ava`, `andrew`, `aizen`, `kyoka`)\n\n"
                f"**Active Voice Persona:** `{voice_meta['name']}` *({voice_meta['style']})*"
            ),
            color=PURPLE,
        )
        banner_file = AssetManager.attach_feature_banner(embed, "ai_banner")
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Neural AI Voice")
        if banner_file:
            await ctx.send(embed=embed, file=banner_file)
        else:
            await ctx.send(embed=embed)

    @aivoice_group.command(name="join", aliases=["connect"], description="Connect KYOKA to your current voice channel.")
    async def voice_join(self, ctx: CustomContext) -> None:
        """Join user's voice channel."""
        if not ctx.guild:
            return await ctx.send_error("This command can only be used in a server.")

        author_voice = getattr(ctx.author, "voice", None)
        target_channel = getattr(author_voice, "channel", None) if author_voice else None
        if not author_voice or not target_channel or not getattr(target_channel, "id", None):
            return await ctx.send_error("You must be connected to a voice channel first!")

        me = ctx.guild.me or (ctx.guild.get_member(self.bot.user.id) if (self.bot and self.bot.user) else None)
        if me:
            perms = target_channel.permissions_for(me)
            if not perms.connect or not perms.speak:
                return await ctx.send_error(f"I need **Connect** and **Speak** permissions in {target_channel.mention}!")

        # Check if voice client exists
        if self._is_music_active(ctx.guild):
            return await ctx.send_error(
                "A Music session is currently active in this server. "
                "Stop music with `+stop` before connecting AI Voice."
            )

        vc = ctx.guild.voice_client
        if _is_vc_connected(vc):
            if isinstance(vc, wavelink.Player):
                return await ctx.send_error(
                    "A Music player is currently in voice. Use `+stop` or `+leave` before using AI Voice."
                )
            vc_ch = getattr(vc, "channel", None)
            if vc_ch and getattr(vc_ch, "id", None) == target_channel.id:
                return await ctx.send_success(f"Already connected to {target_channel.mention}!")
            await vc.move_to(target_channel)
            return await ctx.send_success(f"Moved to {target_channel.mention}!")

        try:
            await self._connect_voice(target_channel)
            await ctx.send_success(f"Connected to **{target_channel.name}**! Type `{ctx.prefix}aivoice speak <text>` or `{ctx.prefix}aivoice listen` to begin.")
        except Exception as e:
            logger.error(f"Failed to connect to voice in {ctx.guild.id}: {e}")
            await ctx.send_error(f"Failed to connect to voice channel: `{e}`")

    @aivoice_group.command(name="leave", aliases=["disconnect", "dc"], description="Disconnect KYOKA from the voice channel.")
    async def voice_leave(self, ctx: CustomContext) -> None:
        """Disconnect from voice channel."""
        if not ctx.guild:
            return
        vc = ctx.guild.voice_client
        if not _is_vc_connected(vc):
            return await ctx.send_error("I am not connected to any voice channel in this server.")

        # Guard: never disconnect or crash a Music wavelink player
        if isinstance(vc, wavelink.Player):
            return await ctx.send_error(
                "KYOKA is connected to a Music session. Use `+leave` or `+stop` to disconnect music."
            )

        # Stop playback and cleanup
        if hasattr(vc, "is_playing") and vc.is_playing():
            vc.stop()
        await vc.disconnect(force=True)
        await ctx.send_success("Disconnected from voice channel.")

    @aivoice_group.command(name="speak", aliases=["say", "tts"], description="Speak text aloud in the voice channel.")
    @app_commands.describe(text="The message you want KYOKA to speak")
    async def voice_speak(self, ctx: CustomContext, *, text: str) -> None:
        """Synthesize and speak text."""
        if not ctx.guild:
            return
        if not text or len(text.strip()) == 0:
            return await ctx.send_error("Please provide text to speak!")

        if len(text) > 400:
            text = text[:400] + "..."

        if self._is_music_active(ctx.guild):
            return await ctx.send_error(
                "Music is currently active in this server. Please pause or stop music before using AI Voice TTS."
            )

        vc = ctx.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return await ctx.send_error(
                "Cannot speak while Music player is connected. Use `+stop` first."
            )

        if not _is_vc_connected(vc):
            # Auto-join if author is in voice
            if ctx.author.voice and ctx.author.voice.channel:
                try:
                    vc = await self._connect_voice(ctx.author.voice.channel)
                except Exception as e:
                    return await ctx.send_error(f"Could not connect to voice channel: {e}")
            else:
                return await ctx.send_error(f"I am not in a voice channel. Connect first with `{ctx.prefix}aivoice join`!")

        voice_id = self._get_voice_id(ctx.guild.id)
        lock = self._get_lock(ctx.guild.id)

        async with ctx.typing():
            temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(temp_fd)

            success = await self._synthesize_audio(text, voice_id, temp_path)
            if not success or not os.path.exists(temp_path):
                return await ctx.send_error("Audio synthesis failed. Please try again.")

        async def _speak_task() -> None:
            async with lock:
                try:
                    if _is_vc_connected(vc) and isinstance(vc, discord.VoiceClient):
                        await self._play_audio_file(vc, temp_path)
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

        asyncio.create_task(_speak_task())
        embed = discord.Embed(
            description=f"🎙️ **Speaking:** *\"{text}\"*",
            color=PURPLE,
        )
        await ctx.send(embed=embed)

    @aivoice_group.command(name="ask", aliases=["chat", "q"], description="Ask AI a question and hear the spoken answer in voice.")
    @app_commands.describe(question="Your question for the AI")
    async def voice_ask(self, ctx: CustomContext, *, question: str) -> None:
        """Ask question, generate AI answer, and speak it aloud."""
        if not ctx.guild:
            return
        if not question.strip():
            return await ctx.send_error("Please ask a question!")

        if self._is_music_active(ctx.guild):
            return await ctx.send_error(
                "Music is currently active in this server. Please pause or stop music before using AI Voice TTS."
            )

        vc = ctx.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return await ctx.send_error(
                "Cannot speak while Music player is connected. Use `+stop` first."
            )

        if not _is_vc_connected(vc):
            if ctx.author.voice and ctx.author.voice.channel:
                try:
                    vc = await self._connect_voice(ctx.author.voice.channel)
                except Exception as e:
                    return await ctx.send_error(f"Could not connect to voice channel: {e}")
            else:
                return await ctx.send_error(f"Please join a voice channel or type `{ctx.prefix}aivoice join` first!")

        clean_q = question.lower()
        answer = ""

        # Check Blox Fruits intelligence
        if any(w in clean_q for w in ("fruit", "blox", "sea", "grind", "trade", "buddha", "kitsune", "dragon", "dough")):
            data = await self.web_mgr.get_fruit_value(clean_q)
            if data:
                answer = (
                    f"Regarding the {data['name']} fruit. Its physical price is {data.get('beli')}, "
                    f"with a trading market value of roughly {data.get('trade_value', 0):,} beli. "
                    f"Current demand is rated {data.get('demand')}. {data.get('tip')}"
                )
            else:
                answer = "In Blox Fruits, progression across the Three Seas requires prioritizing Buddha or Magma for grinding and Portal or Kitsune for PvP."
        else:
            answer = (
                f"You asked: {question}. As Sosuke Aizen, remember that no one stood on the top from the beginning. "
                f"True power lies in patience, strategy, and shattering illusions."
            )

        # Synthesize and speak
        voice_id = self._get_voice_id(ctx.guild.id)
        lock = self._get_lock(ctx.guild.id)

        async with ctx.typing():
            temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(temp_fd)

            spoken_text = answer[:350]
            success = await self._synthesize_audio(spoken_text, voice_id, temp_path)
            if not success:
                return await ctx.send_error("Voice synthesis failed. Check `+aivoice diag` for audio engine health.")

        async def _speak_task() -> None:
            async with lock:
                try:
                    if _is_vc_connected(vc) and isinstance(vc, discord.VoiceClient):
                        await self._play_audio_file(vc, temp_path)
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

        asyncio.create_task(_speak_task())

        embed = discord.Embed(
            title="🎙️ AI Voice Response",
            description=f"**Q:** *{question}*\n\n**A:** {answer}",
            color=PURPLE,
        )
        embed.set_footer(text=f"Spoken via {self._guild_voices.get(ctx.guild.id, 'aizen').title()} • KYOKA AI")
        await ctx.send(embed=embed)

    @aivoice_group.command(name="voice", aliases=["switch", "personas"], description="Select or list available AI voice personas.")
    @app_commands.describe(voice_name="Voice persona (aizen, kyoka, guy, christopher, aria, keita, nanami)")
    async def voice_select(self, ctx: CustomContext, voice_name: Optional[str] = None) -> None:
        """List or switch voices."""
        if not voice_name:
            lines = []
            current = self._guild_voices.get(ctx.guild.id if ctx.guild else 0, "aizen")
            for key, meta in AVAILABLE_VOICES.items():
                cur_marker = " `[ACTIVE]`" if key == current else ""
                lines.append(f"• **`{key}`** — **{meta['name']}** *({meta['gender']})*{cur_marker}\n  > {meta['style']}")

            embed = discord.Embed(
                title="🎭 Available AI Voice Personas",
                description=(
                    "> High-definition neural voices powered by Microsoft Edge-TTS.\n\n"
                    + "\n\n".join(lines)
                    + f"\n\n*Type `{ctx.prefix}aivoice voice <name>` to switch voice persona.*"
                ),
                color=PURPLE,
            )
            return await ctx.send(embed=embed)

        key = voice_name.lower().strip()
        if key not in AVAILABLE_VOICES:
            valid_keys = ", ".join(f"`{k}`" for k in AVAILABLE_VOICES.keys())
            return await ctx.send_error(f"Unknown voice persona. Choose from: {valid_keys}")

        if ctx.guild:
            self._guild_voices[ctx.guild.id] = key

        meta = AVAILABLE_VOICES[key]
        embed = discord.Embed(
            title="✅ AI Voice Persona Selected",
            description=(
                f"> Successfully switched server voice persona to **{meta['name']}**.\n"
                f"> **Cadence:** *{meta['style']}*\n"
                f"> **Engine ID:** `{meta['id']}`"
            ),
            color=0x2ECC71,
        )
        await ctx.send(embed=embed)

    @aivoice_group.command(name="stop", description="Stop current audio playback in the voice channel.")
    async def voice_stop(self, ctx: CustomContext) -> None:
        """Stop current speech."""
        if not ctx.guild:
            return
        vc = ctx.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send_success("Stopped voice speech playback.")
        else:
            await ctx.send_warning("No active audio playback to stop.")

    @aivoice_group.command(name="diag", aliases=["diagnostics", "health"], description="Inspect voice engine, FFmpeg, Opus, and connection health.")
    async def voice_diag(self, ctx: CustomContext) -> None:
        """Diagnostic panel for voice system."""
        ffmpeg_bin = shutil.which("ffmpeg")
        opus_loaded = discord.opus.is_loaded()
        vc = ctx.guild.voice_client if ctx.guild else None
        connected = _is_vc_connected(vc)
        channel_name = vc.channel.name if (vc and vc.channel) else "None"
        ping = round(vc.latency * 1000) if (vc and hasattr(vc, "latency") and vc.latency) else "N/A"
        is_listening = self.summary_mgr.is_listening(ctx.guild.id) if ctx.guild else False

        embed = discord.Embed(
            title="🩺 AI Voice Engine Diagnostics",
            color=0x2ECC71 if (ffmpeg_bin and opus_loaded) else 0xED4245,
        )

        embed.add_field(
            name="🎵 Audio Binaries & Packages",
            value=(
                f"• **FFmpeg:** `{'✅ Found' if ffmpeg_bin else '❌ Missing'}` ({ffmpeg_bin or 'None'})\n"
                f"• **Opus:** `{'✅ Loaded' if opus_loaded else '❌ Not Loaded'}`\n"
                f"• **Edge-TTS:** `{'✅ Installed (Primary)' if HAS_EDGE_TTS else '⚠️ Missing'}`\n"
                f"• **Voice Receiver:** `{'✅ Active (discord-ext-voice-recv)' if HAS_VOICE_RECV else '⚠️ Not Loaded'}`\n"
                f"• **gTTS Fallback:** `✅ Ready`"
            ),
            inline=False,
        )

        embed.add_field(
            name="📡 Connection & Listening State",
            value=(
                f"• **Connected:** `{'✅ Yes' if connected else '⚪ Disconnected'}`\n"
                f"• **Active Channel:** `{channel_name}`\n"
                f"• **Voice Ping:** `{ping}ms`\n"
                f"• **VC Listening Active:** `{'🟢 Yes' if is_listening else '⚪ No'}`\n"
                f"• **Music Isolation:** `✅ Safe (Separate Handlers)`"
            ),
            inline=False,
        )

        embed.set_footer(text=f"Requested by {ctx.author.display_name} • KYOKA 3.0 Diagnostics")
        await ctx.send(embed=embed)

    # ─── REAL-TIME CONVERSATIONAL VOICE (LISTEN & TALK LIKE A HUMAN) ─────────

    @aivoice_group.command(
        name="talk",
        aliases=["converse", "chatvc", "livevc"],
        description="Start real-time 2-way voice conversation where AI listens and talks back like a real human.",
    )
    async def voice_talk(self, ctx: CustomContext, mode: str = "open") -> None:
        """Start real-time voice conversation where AI listens and talks like a real human."""
        if not ctx.guild:
            return await ctx.send_error("This command can only be used in a server.")

        author_voice = getattr(ctx.author, "voice", None)
        target_channel = getattr(author_voice, "channel", None) if author_voice else None
        if not author_voice or not target_channel:
            return await ctx.send_error("You must be connected to a voice channel first!")

        # Permissions check
        me = ctx.guild.me or (ctx.guild.get_member(self.bot.user.id) if (self.bot and self.bot.user) else None)
        if me:
            perms = target_channel.permissions_for(me)
            if not perms.connect or not perms.speak:
                return await ctx.send_error(f"I need **Connect** and **Speak** permissions in {target_channel.mention}!")

        # Music coexistence check
        if self._is_music_active(ctx.guild):
            return await ctx.send_error("A Music session is currently active in this server. Stop music with `+stop` first.")

        # Check if meeting summary is active
        if self.summary_mgr.is_listening(ctx.guild.id):
            return await ctx.send_warning(
                f"A voice meeting listening session is currently active. "
                f"Use `{ctx.prefix}aivoice summary` to conclude it before starting real-time conversation."
            )

        # Check if already talking
        if self.conv_mgr.is_active(ctx.guild.id):
            session = self.conv_mgr.get_session(ctx.guild.id)
            return await ctx.send_warning(
                f"Already conversing in **#{session.channel_name}**! "
                f"Use `{ctx.prefix}aivoice talkmode` to change mode or `{ctx.prefix}aivoice endtalk` to conclude."
            )

        vibe_key = "mastermind"
        clean_mode = "open"
        if mode.lower() in CONVERSATIONAL_VIBES:
            vibe_key = mode.lower()
            clean_mode = "open"
        else:
            clean_mode = "wakeword" if mode.lower() in ("wake", "wakeword", "call") else "open"

        # Determine voice persona: prioritize server voice, else vibe default
        vibe_meta = CONVERSATIONAL_VIBES[vibe_key]
        guild_v = self._guild_voices.get(ctx.guild.id)
        voice_key = guild_v if guild_v in HUMAN_VOICES else vibe_meta.get("voice", "aizen")

        vc = ctx.guild.voice_client
        if _is_vc_connected(vc):
            if isinstance(vc, wavelink.Player):
                return await ctx.send_error("A Music player is currently in voice. Use `+stop` first.")
            if HAS_VOICE_RECV and not isinstance(vc, voice_recv.VoiceRecvClient):
                await vc.disconnect(force=True)
                vc = await self._connect_voice(target_channel)
            else:
                vc_ch = getattr(vc, "channel", None)
                if vc_ch and getattr(vc_ch, "id", None) != target_channel.id:
                    await vc.move_to(target_channel)
        else:
            try:
                vc = await self._connect_voice(target_channel)
            except Exception as e:
                return await ctx.send_error(f"Failed to connect to voice channel: `{e}`")

        # Start conversation session in manager
        session = self.conv_mgr.start_session(
            guild_id=ctx.guild.id,
            channel_id=target_channel.id,
            channel_name=target_channel.name,
            text_channel_id=ctx.channel.id,
            started_by_id=ctx.author.id,
            started_by_name=ctx.author.display_name,
            voice_key=voice_key,
            mode=clean_mode,
            vibe=vibe_key,
        )
        session.voice_client = vc

        # Attach voice_recv sink
        if HAS_VOICE_RECV and isinstance(vc, voice_recv.VoiceRecvClient):
            try:
                sink = VoiceConversationSink(session)
                vc.listen(sink)
            except Exception as e:
                logger.warning(f"Voice conversation sink attach notice: {e}")

        # Start utterance monitoring task
        self.conv_mgr.start_monitoring_task(session, self)

        # Spoken warm human greeting via neural TTS tailored to vibe
        voice_meta = session.get_voice_meta()
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        greeting = vibe_meta["greeting"]

        success = await self._synthesize_audio(greeting, voice_meta["id"], temp_path)
        if success and os.path.exists(temp_path):
            async def _announce_greeting() -> None:
                session.is_bot_speaking = True
                lock = self._get_lock(ctx.guild.id)
                async with lock:
                    try:
                        if _is_vc_connected(vc) and isinstance(vc, discord.VoiceClient):
                            await self._play_audio_file(vc, temp_path)
                    finally:
                        session.is_bot_speaking = False
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
            asyncio.create_task(_announce_greeting())

        view = VoiceConversationControlView(self.conv_mgr, session, self.bot)
        embed = self.conv_mgr.render_voice_hud(session)
        banner_file = AssetManager.attach_feature_banner(embed, "ai_banner")
        if banner_file:
            msg = await ctx.send(embed=embed, file=banner_file, view=view)
        else:
            msg = await ctx.send(embed=embed, view=view)
        session.panel_message = msg

    @aivoice_group.command(name="vibe", aliases=["persona", "mood"], description="Switch KYOKA's conversational personality and vibe in VC.")
    async def voice_vibe(self, ctx: CustomContext, vibe_name: Optional[str] = None) -> None:
        """Switch or view active conversational vibes."""
        if not ctx.guild:
            return

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not vibe_name:
            lines = []
            for v_id, meta in CONVERSATIONAL_VIBES.items():
                lines.append(f"• **{meta['emoji']} `{v_id}`** — **{meta['name']}**\n  > *{meta['description']}*")
            embed = discord.Embed(
                title="🎭 Conversational Voice Vibes & Personalities",
                description=(
                    f"> Switch KYOKA's persona during live voice chat using `{p}aivoice vibe <name>` "
                    f"or using the interactive dropdown menu on the voice HUD.\n\n" + "\n\n".join(lines)
                ),
                color=PURPLE,
            )
            banner = AssetManager.attach_feature_banner(embed, "ai_banner")
            if banner:
                return await ctx.send(embed=embed, file=banner)
            return await ctx.send(embed=embed)

        clean_v = vibe_name.lower().strip()
        if clean_v not in CONVERSATIONAL_VIBES:
            valid_list = ", ".join(f"`{k}`" for k in CONVERSATIONAL_VIBES.keys())
            return await ctx.send_error(f"Invalid vibe `{vibe_name}`. Choose from: {valid_list}")

        vibe_meta = CONVERSATIONAL_VIBES[clean_v]
        session = self.conv_mgr.get_session(ctx.guild.id)
        if session and session.active:
            session.vibe = clean_v
            if vibe_meta.get("voice") in HUMAN_VOICES:
                session.voice_key = vibe_meta["voice"]

            if session.voice_client:
                voice_id = session.get_voice_meta()["id"]
                asyncio.create_task(
                    self.conv_mgr.play_custom_announcement(session, self, vibe_meta["greeting"], voice_id)
                )

            if session.panel_message:
                try:
                    await session.panel_message.edit(embed=self.conv_mgr.render_voice_hud(session))
                except Exception:
                    pass

        embed = discord.Embed(
            title=f"{vibe_meta['emoji']} Conversational Vibe Set • {vibe_meta['name']}",
            description=f"> *\"{vibe_meta['description']}\"*\n\nKYOKA is now speaking with the **{vibe_meta['name']}** cadence in voice calls.",
            color=vibe_meta["color"],
        )
        await ctx.send(embed=embed)

    @aivoice_group.command(name="sfx", aliases=["sound", "soundboard"], description="Play instant audio sound effects in VC.")
    async def voice_sfx(self, ctx: CustomContext, sound_name: Optional[str] = None) -> None:
        """Trigger instant soundboard effects into your voice channel."""
        if not ctx.guild:
            return

        if not sound_name:
            view = SoundboardControlView(self, ctx.guild.id, self.conv_mgr.sfx_engine)
            embed = discord.Embed(
                title="🔊 KYOKA 3.0 Live Voice Soundboard",
                description=(
                    "> Click any button below to immediately fire sound effects into your voice channel!\n\n"
                    "• `💥 Boom` — Deep 808 sub-bass drop\n"
                    "• `🎺 Airhorn` — Hype triple-harmonic MLG airhorn\n"
                    "• `✨ Level Up` — 8-bit retro victory chime\n"
                    "• `🥁 Rimshot` — Ba-dum-tss comedy drum hit\n"
                    "• `🔫 Laser` — Retro sci-fi blaster\n"
                    "• `🪘 Drumroll` — Suspense snare drum roll\n"
                    "• `👏 Applause` — Cheering crowd applause\n"
                    "• `🔔 Chime` — Crystal bell notification\n\n"
                    "💡 *Pro-Tip:* You can also say these words out loud on your mic while in voice call!"
                ),
                color=0xF39C12,
            )
            banner = AssetManager.attach_feature_banner(embed, "ai_banner")
            if banner:
                return await ctx.send(embed=embed, file=banner, view=view)
            return await ctx.send(embed=embed, view=view)

        sfx_path = self.conv_mgr.sfx_engine.get_sfx_path(sound_name)
        if not sfx_path:
            avail = ", ".join(f"`{k}`" for k in self.conv_mgr.sfx_engine.RECIPES.keys())
            return await ctx.send_error(f"Sound effect `{sound_name}` not found. Available SFX: {avail}")

        vc = ctx.guild.voice_client
        if not _is_vc_connected(vc):
            return await ctx.send_error("I am not connected to any voice channel. Connect first with `+aivoice join` or `+vctalk`!")

        lock = self._get_lock(ctx.guild.id)
        async with lock:
            try:
                await self._play_audio_file(vc, sfx_path)
                await ctx.send_success(f"🔊 Played sound effect **{sound_name.upper()}**!")
            except Exception as e:
                await ctx.send_error(f"Failed to play SFX: `{e}`")

    @aivoice_group.command(name="roast", aliases=["burn", "diss"], description="Deliver a savage, hilarious verbal roast in voice channel.")
    async def voice_roast(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        """Deliver a custom, witty verbal roast aloud in voice chat."""
        if not ctx.guild:
            return
        target = member or ctx.author
        vc = ctx.guild.voice_client
        if not _is_vc_connected(vc):
            return await ctx.send_error("KYOKA must be in a voice channel first! Use `+vctalk` or `+aivoice join`.")

        roasts = [
            f"{target.display_name}, your gameplay is like a broken pencil. Completely pointless, but everyone still has to watch you struggle with it.",
            f"Hold on everyone, quiet down! {target.display_name} is about to make another tactical decision that wipes out the entire squad.",
            f"I asked artificial intelligence to calculate {target.display_name}'s win rate, and the server overheated from dividing by zero.",
            f"{target.display_name}, you're living proof that even in an era of advanced artificial intelligence, human error remains completely undefeated.",
            f"Look at {target.display_name} over there, looking like an NPC that forgot its dialogue tree halfway through the cutscene.",
        ]
        chosen_roast = random.choice(roasts)
        voice_id = self._get_voice_id(ctx.guild.id)

        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        async with ctx.typing():
            success = await self._synthesize_audio(chosen_roast, voice_id, temp_path)
            if not success or not os.path.exists(temp_path):
                return await ctx.send_error("Could not synthesize voice roast.")

        sfx_path = self.conv_mgr.sfx_engine.get_sfx_path("badumtss")
        lock = self._get_lock(ctx.guild.id)
        async with lock:
            try:
                await self._play_audio_file(vc, temp_path)
                if sfx_path and os.path.exists(sfx_path):
                    await asyncio.sleep(0.1)
                    await self._play_audio_file(vc, sfx_path)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        embed = discord.Embed(
            description=f"🔥 **Voice Roast Delivered to {target.mention}:**\n> *\"{chosen_roast}\"*",
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)

    @aivoice_group.command(name="beatbox", aliases=["spitbars"], description="KYOKA drops a sick vocal beatbox routine into the voice channel.")
    async def voice_beatbox(self, ctx: CustomContext) -> None:
        """Drop a rhythmically synthesized vocal beatbox pattern into VC."""
        if not ctx.guild:
            return
        vc = ctx.guild.voice_client
        if not _is_vc_connected(vc):
            return await ctx.send_error("KYOKA must be connected to voice. Use `+vctalk` or `+aivoice join` first!")

        beatbox_lyrics = (
            "Boots and cats and boots and cats. "
            "Pffft-chhh-kuh-tah! B-b-boom, ticka-ticka, b-b-boom! "
            "Drop the bass! Chhh-kah, chhh-kah! Wub-wub-wub... yeah, that is how Kyoka rolls on the mic!"
        )

        voice_id = self._get_voice_id(ctx.guild.id)
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        async with ctx.typing():
            success = await self._synthesize_audio(beatbox_lyrics, voice_id, temp_path)
            if not success or not os.path.exists(temp_path):
                return await ctx.send_error("Beatbox synthesis failed.")

        drum_sfx = self.conv_mgr.sfx_engine.get_sfx_path("drumroll")
        boom_sfx = self.conv_mgr.sfx_engine.get_sfx_path("boom")

        lock = self._get_lock(ctx.guild.id)
        async with lock:
            try:
                if drum_sfx:
                    await self._play_audio_file(vc, drum_sfx)
                await self._play_audio_file(vc, temp_path)
                if boom_sfx:
                    await self._play_audio_file(vc, boom_sfx)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        embed = discord.Embed(
            title="🎤 Beatbox Dropped in Voice!",
            description="> *\"Boots and cats and boots and cats! Pffft-chhh-kuh-tah! Wub-wub-wub...\"*\n\n🔥 KYOKA just laid down a fresh vocal beat in your voice channel!",
            color=0xF1C40F,
        )
        await ctx.send(embed=embed)

    @aivoice_group.command(name="trivia", aliases=["quiz"], description="Host a live voice trivia challenge in the voice channel.")
    async def voice_trivia(self, ctx: CustomContext) -> None:
        """Read a trivia question aloud in voice with sound effects."""
        if not ctx.guild:
            return
        vc = ctx.guild.voice_client
        if not _is_vc_connected(vc):
            return await ctx.send_error("KYOKA must be in voice! Use `+vctalk` or `+aivoice join`.")

        questions = [
            ("In Bleach, what is the name of Sosuke Aizen's Zanpakuto?", "Kyoka Suigetsu"),
            ("In Dragon Ball Z, who was the first Super Saiyan shown on screen?", "Goku"),
            ("In Minecraft, what ore is required to craft Netherite ingots?", "Ancient Debris"),
            ("In Naruto, who taught Naruto the Rasengan technique?", "Jiraiya"),
            ("What is the highest bounty in One Piece history?", "Gol D. Roger"),
        ]
        q, a = random.choice(questions)
        spoken_text = f"Voice Trivia Challenge! Listen carefully: {q}. Shout your answer into your mic now!"

        voice_id = self._get_voice_id(ctx.guild.id)
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        async with ctx.typing():
            success = await self._synthesize_audio(spoken_text, voice_id, temp_path)
            if not success or not os.path.exists(temp_path):
                return await ctx.send_error("Could not synthesize trivia audio.")

        chime_sfx = self.conv_mgr.sfx_engine.get_sfx_path("chime")
        lock = self._get_lock(ctx.guild.id)
        async with lock:
            try:
                if chime_sfx:
                    await self._play_audio_file(vc, chime_sfx)
                await self._play_audio_file(vc, temp_path)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        embed = discord.Embed(
            title="🧠 Live Voice Channel Trivia!",
            description=f"### ❓ Question:\n> **{q}**\n\n*Shout the answer into your microphone or discuss in VC!*",
            color=0x3498DB,
        )
        embed.set_footer(text="Answer will be revealed when someone shouts it on mic or in chat!")
        await ctx.send(embed=embed)

    @aivoice_group.command(name="talkmode", aliases=["vcmode"], description="Switch between Open Mic and Wake Word conversation mode.")
    async def voice_talkmode(self, ctx: CustomContext, mode: Optional[str] = None) -> None:
        """Switch between Open Mic and Wake Word conversation mode."""
        if not ctx.guild:
            return
        session = self.conv_mgr.get_session(ctx.guild.id)
        if not session or not session.active:
            return await ctx.send_warning(f"No active voice conversation session. Start one with `{ctx.prefix}aivoice talk`!")

        if mode:
            session.mode = "wakeword" if mode.lower() in ("wake", "wakeword", "call") else "open"
        else:
            session.mode = "wakeword" if session.mode == "open" else "open"

        mode_name = "Wake Word ('Kyoka' or 'Aizen')" if session.mode == "wakeword" else "Open Mic (Replies to speech)"
        await ctx.send_success(f"Conversational voice mode changed to: **{mode_name}**.")

    @aivoice_group.command(name="endtalk", aliases=["stoptalk", "conclude"], description="End active voice conversation session.")
    async def voice_endtalk(self, ctx: CustomContext) -> None:
        """Conclude active voice conversation and generate dialogue recap."""
        if not ctx.guild:
            return
        if not self.conv_mgr.is_active(ctx.guild.id):
            return await ctx.send_warning("No active voice conversation in this server.")
        await self.end_conversation_session(ctx.guild, ctx.channel, trigger_user=ctx.author, summarize=True)

    async def end_conversation_session(
        self,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        trigger_user: Optional[discord.User | discord.Member] = None,
        summarize: bool = True,
    ) -> None:
        """Conclude conversational voice session, detach audio receiver, deliver dialogue report, and disconnect."""
        session = self.conv_mgr.stop_session(guild.id)
        if not session:
            return

        vc = guild.voice_client
        if vc and hasattr(vc, "stop_listening"):
            try:
                vc.stop_listening()
            except Exception:
                pass

        if summarize and session.full_transcript:
            summary_md = self.conv_mgr.generate_conversation_summary(session)
            dur = session.ended_at or datetime.datetime.now(datetime.timezone.utc)
            dur_str = f"{int((dur - session.started_at).total_seconds()) // 60}m {int((dur - session.started_at).total_seconds()) % 60}s"

            embed_desc = summary_md
            if len(embed_desc) > 3800:
                embed_desc = embed_desc[:3750] + "\n\n*(Full dialogue continues in attached file...)*"

            embed = discord.Embed(
                title=f"💬 Voice Conversation Summary • #{session.channel_name}",
                description=embed_desc,
                color=0x2ECC71,
            )
            embed.add_field(
                name="📊 Session Details",
                value=(
                    f"• **Duration:** `{dur_str}`\n"
                    f"• **Exchanges:** `{len(session.full_transcript)} turns`\n"
                    f"• **Voice Persona:** `{session.get_voice_meta()['name']}`\n"
                    f"• **Mode:** `{session.mode.capitalize()}`"
                ),
                inline=False,
            )
            banner_file = AssetManager.attach_feature_banner(embed, "ai_banner")
            embed.set_footer(text=f"Ended by {trigger_user.display_name if trigger_user else 'Host'} • KYOKA 3.0")

            doc_text = (
                f"# KYOKA 3.0 Real-Time Voice Conversation Log\n"
                f"- **Voice Channel:** #{session.channel_name}\n"
                f"- **Date:** {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"- **Duration:** {dur_str}\n"
                f"- **Persona:** {session.get_voice_meta()['name']}\n\n"
                f"---\n\n"
                f"{summary_md}\n"
            )
            file_bytes = io.BytesIO(doc_text.encode("utf-8"))
            summary_file = discord.File(file_bytes, filename=f"voice_chat_{session.channel_name}_{int(time.time())}.md")

            files_to_send = [summary_file]
            if banner_file:
                files_to_send.insert(0, banner_file)

            await channel.send(embed=embed, files=files_to_send)
        else:
            await channel.send(f"👋 Voice conversation in **#{session.channel_name}** ended.")

        # Disconnect cleanly if not music
        if _is_vc_connected(vc) and not self._is_music_active(guild):
            try:
                await asyncio.sleep(0.5)
                await vc.disconnect(force=True)
            except Exception:
                pass

    # ─── VC LISTENING & MEETING SUMMARIZATION ────────────────────────────────

    @aivoice_group.command(
        name="listen",
        aliases=["record", "transcribe", "meeting", "startlisten"],
        description="AI joins your voice channel, listens to conversation, and compiles meeting notes.",
    )
    async def voice_listen(self, ctx: CustomContext, duration: int = 30) -> None:
        """Join voice, listen to audio and discussions, and prepare for meeting summary."""
        if not ctx.guild:
            return await ctx.send_error("This command can only be used in a server.")

        author_voice = getattr(ctx.author, "voice", None)
        target_channel = getattr(author_voice, "channel", None) if author_voice else None
        if not author_voice or not target_channel:
            return await ctx.send_error("You must be connected to a voice channel first!")

        # Check permissions
        me = ctx.guild.me or (ctx.guild.get_member(self.bot.user.id) if (self.bot and self.bot.user) else None)
        if me:
            perms = target_channel.permissions_for(me)
            if not perms.connect or not perms.speak:
                return await ctx.send_error(f"I need **Connect** and **Speak** permissions in {target_channel.mention}!")

        # Music coexistence check
        if self._is_music_active(ctx.guild):
            return await ctx.send_error("A Music session is currently active in this server. Stop music with `+stop` first.")

        # Check if already listening in this guild
        if self.summary_mgr.is_listening(ctx.guild.id):
            session = self.summary_mgr.get_session(ctx.guild.id)
            return await ctx.send_warning(
                f"Already listening in **#{session.channel_name}**! "
                f"Use `{ctx.prefix}aivoice summary` to finish and generate the summary, or `{ctx.prefix}aivoice note <text>` to add notes."
            )

        duration = max(2, min(duration, 120))  # bounded 2-120 minutes

        vc = ctx.guild.voice_client
        # Reconnect with VoiceRecvClient if not already receiving capable
        if _is_vc_connected(vc):
            if isinstance(vc, wavelink.Player):
                return await ctx.send_error("A Music player is currently in voice. Use `+stop` first.")
            if HAS_VOICE_RECV and not isinstance(vc, voice_recv.VoiceRecvClient):
                await vc.disconnect(force=True)
                vc = await self._connect_voice(target_channel)
            else:
                vc_ch = getattr(vc, "channel", None)
                if vc_ch and getattr(vc_ch, "id", None) != target_channel.id:
                    await vc.move_to(target_channel)
        else:
            try:
                vc = await self._connect_voice(target_channel)
            except Exception as e:
                return await ctx.send_error(f"Failed to connect to voice channel: `{e}`")

        # Start listening session in manager
        session = self.summary_mgr.start_session(
            guild_id=ctx.guild.id,
            channel_id=target_channel.id,
            channel_name=target_channel.name,
            started_by_id=ctx.author.id,
            started_by_name=ctx.author.display_name,
            text_channel_id=ctx.channel.id,
            duration_minutes=duration,
        )
        session.voice_client = vc

        # Attach VoiceRecvClient AudioSink
        if HAS_VOICE_RECV and isinstance(vc, voice_recv.VoiceRecvClient):
            try:
                sink = VoiceMeetingSink(session)
                vc.listen(sink)
            except Exception as e:
                logger.warning(f"Voice sink attach notice: {e}")

        # Schedule automatic timeout
        async def _auto_timeout() -> None:
            await asyncio.sleep(duration * 60)
            if self.summary_mgr.is_listening(ctx.guild.id):
                await self.process_session_summary(ctx.guild, ctx.channel, auto_timeout=True)

        session.timeout_task = asyncio.create_task(_auto_timeout())

        # Spoken greeting announcement via TTS
        voice_id = self._get_voice_id(ctx.guild.id)
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        greeting = (
            "Kyoka AI voice listening activated. I am now monitoring this voice session and recording meeting notes."
        )

        success = await self._synthesize_audio(greeting, voice_id, temp_path)
        if success and os.path.exists(temp_path):
            async def _announce():
                lock = self._get_lock(ctx.guild.id)
                async with lock:
                    try:
                        if _is_vc_connected(vc) and isinstance(vc, discord.VoiceClient):
                            await self._play_audio_file(vc, temp_path)
                    finally:
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
            asyncio.create_task(_announce())

        view = VoiceListeningControlView(self.summary_mgr, session, self.bot)
        embed = discord.Embed(
            title=f"🎙️ AI Voice Listening Session Started • #{target_channel.name}",
            description=(
                f"> Kyoka is now in **{target_channel.name}**, listening to the conversation, tracking speaker "
                f"activity, and recording meeting context.\n\n"
                f"• **Host:** {ctx.author.mention}\n"
                f"• **Target Duration:** `{duration} minutes` *(auto-summarizes upon completion)*\n"
                f"• **Audio Receiving:** `{'🟢 Active (discord-ext-voice-recv)' if HAS_VOICE_RECV else '🟡 Context Mode'}`\n"
                f"• **VC Chat Logging:** `🟢 Enabled (text messages in VC will be included)`\n\n"
                f"**Controls:**\n"
                f"• Click **End & Summarize** or use `{ctx.prefix}aivoice summary` to generate notes\n"
                f"• Click **Add Note** or use `{ctx.prefix}aivoice note <text>` to log agenda items\n"
                f"• Click **Cancel** or use `{ctx.prefix}aivoice stoplisten` to abort"
            ),
            color=PURPLE,
        )
        banner_file = AssetManager.attach_feature_banner(embed, "ai_banner")
        embed.set_footer(text="KYOKA 3.0 Multimodal Meeting Intelligence • Powered by Gemini AI")
        if banner_file:
            msg = await ctx.send(embed=embed, file=banner_file, view=view)
        else:
            msg = await ctx.send(embed=embed, view=view)
        session.panel_message = msg

    @aivoice_group.command(name="summary", aliases=["recap", "summarize", "notes"], description="Conclude active voice session and generate AI meeting summary.")
    async def voice_summary(self, ctx: CustomContext) -> None:
        """End voice listening session and generate AI meeting summary."""
        if not ctx.guild:
            return

        if self.summary_mgr.is_listening(ctx.guild.id):
            await self.process_session_summary(ctx.guild, ctx.channel, trigger_user=ctx.author)
            return

        # If no active session, show the most recent past summary
        recents = await self.summary_mgr.get_recent_summaries(ctx.guild.id, limit=1)
        if not recents:
            return await ctx.send_warning(
                f"No active or previous voice listening session found. "
                f"Start one with `{ctx.prefix}aivoice listen` while in a voice channel!"
            )

        last = recents[0]
        embed = discord.Embed(
            title=f"📋 Latest Voice Meeting Summary • #{last['channel_name']}",
            description=last["summary"][:3800],
            color=PURPLE,
        )
        embed.set_footer(text=f"Session #{last['id']} • {last['duration']} • {last['created_at']}")
        await ctx.send(embed=embed)

    @aivoice_group.command(name="stoplisten", aliases=["endlisten", "cancelmeeting"], description="Stop listening session without waiting.")
    async def voice_stoplisten(self, ctx: CustomContext) -> None:
        """Stop current listening session and generate summary."""
        if not ctx.guild:
            return
        if not self.summary_mgr.is_listening(ctx.guild.id):
            return await ctx.send_warning("No active voice listening session in this server.")
        await self.process_session_summary(ctx.guild, ctx.channel, trigger_user=ctx.author)

    @aivoice_group.command(name="note", aliases=["addnote", "task"], description="Add a note or action item to the active voice session.")
    async def voice_note(self, ctx: CustomContext, *, text: str) -> None:
        """Add manual note to live listening session."""
        if not ctx.guild:
            return
        session = self.summary_mgr.get_session(ctx.guild.id)
        if not session or session.status != "listening":
            return await ctx.send_warning(
                f"No voice listening session currently active. Start one with `{ctx.prefix}aivoice listen`!"
            )

        session.add_note(ctx.author.display_name, text)
        await ctx.send_success(f"Added note to voice session: *\"{text}\"*")

    @aivoice_group.command(name="sessions", aliases=["history", "pastsummaries"], description="Browse recent voice meeting summaries.")
    async def voice_sessions(self, ctx: CustomContext) -> None:
        """List historical meeting summaries."""
        if not ctx.guild:
            return
        recents = await self.summary_mgr.get_recent_summaries(ctx.guild.id, limit=8)
        if not recents:
            return await ctx.send_info(
                f"No voice session summaries recorded yet for **{ctx.guild.name}**. "
                f"Use `{ctx.prefix}aivoice listen` to begin!"
            )

        lines = []
        for r in recents:
            lines.append(
                f"• **Session `#{r['id']}`** — **#{r['channel_name']}** ({r['duration']}, {r['speaker_count']} speakers)\n"
                f"  > Host: `{r['started_by']}` • Date: `{r['created_at']}`\n"
                f"  > View: `{ctx.prefix}aivoice session {r['id']}`"
            )

        embed = discord.Embed(
            title=f"📚 Voice Meeting History • {ctx.guild.name}",
            description="\n\n".join(lines),
            color=PURPLE,
        )
        await ctx.send(embed=embed)

    @aivoice_group.command(name="session", description="View a specific historical voice meeting summary.")
    async def voice_session_view(self, ctx: CustomContext, session_id: int) -> None:
        """View past session by ID."""
        if not ctx.guild:
            return
        recents = await self.summary_mgr.get_recent_summaries(ctx.guild.id, limit=25)
        found = next((r for r in recents if r["id"] == session_id), None)
        if not found:
            return await ctx.send_error(f"Meeting session `#{session_id}` not found.")

        embed = discord.Embed(
            title=f"📋 Voice Meeting Summary • #{found['channel_name']} (Session #{found['id']})",
            description=found["summary"][:3800],
            color=PURPLE,
        )
        embed.set_footer(text=f"Host: {found['started_by']} • Duration: {found['duration']} • {found['created_at']}")
        await ctx.send(embed=embed)

    async def process_session_summary(
        self,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        trigger_user: Optional[discord.User | discord.Member] = None,
        auto_timeout: bool = False,
    ) -> None:
        """Complete listening session, stop receiver, call Gemini for structured summary, and deliver report."""
        session = self.summary_mgr.stop_session(guild.id)
        if not session:
            return

        session.status = "processing"
        vc = guild.voice_client

        # Stop listening sink if active
        if vc and hasattr(vc, "stop_listening"):
            try:
                vc.stop_listening()
            except Exception:
                pass

        # Send loading/processing message
        status_embed = discord.Embed(
            title="🧠 Analyzing Voice Meeting Recording...",
            description=(
                f"> **Channel:** `#{session.channel_name}`\n"
                f"> **Duration:** `{session.get_duration_str()}`\n"
                f"> **Speakers:** `{len(session.speakers)} tracked`\n\n"
                f"Kyoka AI is transcribing audio, identifying key decisions, and compiling action items. "
                f"Please wait a moment..."
            ),
            color=PURPLE,
        )
        status_msg = await channel.send(embed=status_embed)

        # Call Gemini AI
        http_session = self.get_http_session()
        summary_data = await self.summary_mgr.generate_summary(session, http_session)

        # Save to database
        row_id = await self.summary_mgr.save_summary_to_db(session, summary_data)

        # Format presentation Embed
        full_md = summary_data["summary_markdown"]
        dur_str = summary_data["duration_str"]
        spk_count = summary_data["speaker_count"]

        embed_desc = full_md
        if len(embed_desc) > 3800:
            embed_desc = embed_desc[:3750] + "\n\n*(Full report continues in attached document...)*"

        summary_embed = discord.Embed(
            title=f"📋 AI Voice Meeting Summary • #{session.channel_name}",
            description=embed_desc,
            color=0x2ECC71,
        )
        summary_embed.add_field(
            name="📊 Meeting Statistics",
            value=(
                f"• **Duration:** `{dur_str}`\n"
                f"• **Participants:** `{spk_count}`\n"
                f"• **Host:** `{session.started_by_name}`\n"
                f"• **Session ID:** `#{row_id or 1}`\n"
                f"• **Audio Stream:** `{'✅ Transcribed from Audio' if summary_data.get('audio_captured') else '📝 Compiled from Session Notes'}`"
            ),
            inline=False,
        )

        banner_file = AssetManager.attach_feature_banner(summary_embed, "ai_banner")
        summary_embed.set_footer(text=f"Concluded by {trigger_user.display_name if trigger_user else 'Auto-Timer'} • KYOKA 3.0")

        # Create downloadable Markdown document
        doc_content = (
            f"# KYOKA 3.0 AI Voice Meeting Minutes\n"
            f"- **Voice Channel:** #{session.channel_name}\n"
            f"- **Date:** {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"- **Duration:** {dur_str}\n"
            f"- **Host:** {session.started_by_name}\n\n"
            f"---\n\n"
            f"{full_md}\n\n"
            f"---\n"
            f"Generated automatically by Kyoka 3.0 AI Voice Intelligence.\n"
        )
        file_bytes = io.BytesIO(doc_content.encode("utf-8"))
        summary_file = discord.File(file_bytes, filename=f"meeting_summary_{session.channel_name}_{int(time.time())}.md")

        files_to_send = [summary_file]
        if banner_file:
            files_to_send.insert(0, banner_file)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await channel.send(embed=summary_embed, files=files_to_send)

        # Spoken verbal recap in voice channel via TTS
        recap_text = summary_data.get("verbal_recap", "")
        if recap_text and _is_vc_connected(vc):
            voice_id = self._get_voice_id(guild.id)
            temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(temp_fd)

            success = await self._synthesize_audio(recap_text, voice_id, temp_path)
            if success and os.path.exists(temp_path):
                lock = self._get_lock(guild.id)
                async with lock:
                    try:
                        if _is_vc_connected(vc) and isinstance(vc, discord.VoiceClient):
                            await self._play_audio_file(vc, temp_path)
                    finally:
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass

        # Disconnect cleanly after finishing summary
        if _is_vc_connected(vc) and not self._is_music_active(guild):
            try:
                await asyncio.sleep(1.0)
                await vc.disconnect(force=True)
            except Exception:
                pass

    # ─── STANDALONE PREFIX SHORTCUTS ─────────────────────────────────────────

    @commands.command(name="vctalk", aliases=["talkvc", "chatinvc", "conversevc"], help="AI joins voice channel to listen and converse in real-time like a human.")
    async def cmd_vctalk(self, ctx: CustomContext, mode: str = "open") -> None:
        await self.voice_talk(ctx, mode=mode)

    @commands.command(name="endvctalk", aliases=["stopvctalk", "vctalkend"], help="End real-time voice conversation session.")
    async def cmd_endvctalk(self, ctx: CustomContext) -> None:
        await self.voice_endtalk(ctx)

    @commands.command(name="vcsfx", aliases=["soundboard", "vcsound", "playsfx"], help="Trigger soundboard effects into voice channel.")
    async def cmd_vcsfx(self, ctx: CustomContext, sound_name: Optional[str] = None) -> None:
        await self.voice_sfx(ctx, sound_name=sound_name)

    @commands.command(name="vcvibe", aliases=["voicevibe", "moodvc", "vibecheck"], help="Switch KYOKA's conversational vibe in voice calls.")
    async def cmd_vcvibe(self, ctx: CustomContext, vibe_name: Optional[str] = None) -> None:
        await self.voice_vibe(ctx, vibe_name=vibe_name)

    @commands.command(name="vcroast", aliases=["roastvc", "vcburn"], help="Deliver a savage verbal roast into voice channel.")
    async def cmd_vcroast(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        await self.voice_roast(ctx, member=member)

    @commands.command(name="vcbeatbox", aliases=["beatboxvc", "spitbarsvc"], help="Drop a vocal beatbox routine in voice channel.")
    async def cmd_vcbeatbox(self, ctx: CustomContext) -> None:
        await self.voice_beatbox(ctx)

    @commands.command(name="vctrivia", aliases=["triviavc", "quizvc"], help="Host a live voice trivia challenge in voice channel.")
    async def cmd_vctrivia(self, ctx: CustomContext) -> None:
        await self.voice_trivia(ctx)

    @commands.command(name="vclisten", aliases=["startlisten", "recordvc"], help="AI joins voice channel to listen and record meeting notes.")
    async def cmd_vclisten(self, ctx: CustomContext, duration: int = 30) -> None:
        await self.voice_listen(ctx, duration=duration)

    @commands.command(name="vcsummary", aliases=["vcrecap", "meetingsummary", "vcnotes"], help="End voice listening session and generate AI meeting summary.")
    async def cmd_vcsummary(self, ctx: CustomContext) -> None:
        await self.voice_summary(ctx)

    @commands.command(name="vcnote", aliases=["vctask", "meetingnote"], help="Add a note or action item to the active voice listening session.")
    async def cmd_vcnote(self, ctx: CustomContext, *, text: str) -> None:
        await self.voice_note(ctx, text=text)

    @commands.command(name="vcsessions", aliases=["vchistory"], help="Browse recent voice meeting summaries.")
    async def cmd_vcsessions(self, ctx: CustomContext) -> None:
        await self.voice_sessions(ctx)

    # ─── LISTENERS & CLEANUP ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Capture text messages sent in VC text channel during active listening or conversation sessions."""
        if message.author.bot or not message.guild:
            return
        session = self.summary_mgr.get_session(message.guild.id)
        if session and session.status == "listening":
            if message.channel.id in (session.channel_id, session.text_channel_id):
                session.add_chat_message(message.author.display_name, message.content)

        conv_session = self.conv_mgr.get_session(message.guild.id)
        if conv_session and conv_session.active:
            if message.channel.id in (conv_session.channel_id, conv_session.text_channel_id):
                conv_session.history.append({
                    "speaker": message.author.display_name,
                    "text": message.content,
                    "reply": "(noted from chat)",
                })

    async def cog_unload(self) -> None:
        """Clean up HTTP session and cancel active voice listening and conversation sessions."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        for session in list(self.summary_mgr.active_sessions.values()):
            if session.timeout_task and not session.timeout_task.done():
                session.timeout_task.cancel()
            if session.voice_client and hasattr(session.voice_client, "stop_listening"):
                try:
                    session.voice_client.stop_listening()
                except Exception:
                    pass
        for conv_session in list(self.conv_mgr.sessions.values()):
            if conv_session.monitor_task and not conv_session.monitor_task.done():
                conv_session.monitor_task.cancel()
            if conv_session.voice_client and hasattr(conv_session.voice_client, "stop_listening"):
                try:
                    conv_session.voice_client.stop_listening()
                except Exception:
                    pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIVoice(bot))
    logger.info("🎙️ [KYOKA] Modular AI Voice Engine Cog loaded.")
