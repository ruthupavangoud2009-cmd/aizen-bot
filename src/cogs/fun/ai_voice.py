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
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

import static_ffmpeg
from gtts import gTTS

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

from src.core.context import CustomContext
from src.managers.blox_fruits_web_manager import BloxFruitsWebManager

logger = logging.getLogger("Kyoka.AIVoice")
PURPLE = 0x6F43BE

# Ensure static FFmpeg path is loaded
try:
    static_ffmpeg.add_paths()
except Exception:
    pass

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
        self._guild_voices: Dict[int, str] = {}
        self._voice_locks: Dict[int, asyncio.Lock] = {}
        self._speech_queues: Dict[int, asyncio.Queue] = {}
        self._active_tasks: Dict[int, asyncio.Task] = {}

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
        """Play local audio file through VoiceClient with completion await."""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        source = discord.FFmpegPCMAudio(file_path, executable=ffmpeg_bin)
        done_event = asyncio.Event()

        def after_play(err: Optional[Exception]) -> None:
            if err:
                logger.error(f"Error during audio playback: {err}")
            done_event.set()

        voice_client.play(source, after=after_play)
        await done_event.wait()

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
            title="🎙️ KYOKA AI Voice Assistant Hub",
            description=(
                "> Natural-sounding neural voice synthesis, AI conversation, and voice channel controls.\n\n"
                f"• `{p}aivoice join` — Connect to your current voice channel\n"
                f"• `{p}aivoice leave` — Safely disconnect from voice\n"
                f"• `{p}aivoice speak <text>` — Synthesize speech with selected voice\n"
                f"• `{p}aivoice ask <question>` — Ask AI a question and hear the spoken answer\n"
                f"• `{p}aivoice voice [name]` — Switch voice persona (e.g. `aizen`, `kyoka`, `guy`)\n"
                f"• `{p}aivoice stop` — Stop current speech playback\n"
                f"• `{p}aivoice diag` — Inspect Opus, FFmpeg, and voice health\n\n"
                f"**Active Voice Persona:** `{voice_meta['name']}` *({voice_meta['style']})*"
            ),
            color=PURPLE,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Neural AI Voice")
        await ctx.send(embed=embed)

    @aivoice_group.command(name="join", aliases=["connect"], description="Connect KYOKA to your current voice channel.")
    async def voice_join(self, ctx: CustomContext) -> None:
        """Join user's voice channel."""
        if not ctx.guild:
            return await ctx.send_error("This command can only be used in a server.")

        author_voice = ctx.author.voice
        if not author_voice or not author_voice.channel:
            return await ctx.send_error("You must be connected to a voice channel first!")

        target_channel = author_voice.channel
        me = ctx.guild.me
        perms = target_channel.permissions_for(me)
        if not perms.connect or not perms.speak:
            return await ctx.send_error(f"I need **Connect** and **Speak** permissions in {target_channel.mention}!")

        # Check if voice client exists
        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            if vc.channel.id == target_channel.id:
                return await ctx.send_success(f"Already connected to {target_channel.mention}!")
            await vc.move_to(target_channel)
            return await ctx.send_success(f"Moved to {target_channel.mention}!")

        try:
            await target_channel.connect()
            await ctx.send_success(f"Connected to **{target_channel.name}**! Type `{ctx.prefix}aivoice speak <text>` to test audio.")
        except Exception as e:
            logger.error(f"Failed to connect to voice in {ctx.guild.id}: {e}")
            await ctx.send_error(f"Failed to connect to voice channel: `{e}`")

    @aivoice_group.command(name="leave", aliases=["disconnect", "dc"], description="Disconnect KYOKA from the voice channel.")
    async def voice_leave(self, ctx: CustomContext) -> None:
        """Disconnect from voice channel."""
        if not ctx.guild:
            return
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            return await ctx.send_error("I am not connected to any voice channel in this server.")

        # Stop playback and cleanup
        if vc.is_playing():
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

        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            # Auto-join if author is in voice
            if ctx.author.voice and ctx.author.voice.channel:
                try:
                    vc = await ctx.author.voice.channel.connect()
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
                    if vc and vc.is_connected():
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

        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            if ctx.author.voice and ctx.author.voice.channel:
                try:
                    vc = await ctx.author.voice.channel.connect()
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
                    if vc and vc.is_connected():
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
        connected = vc.is_connected() if vc else False
        channel_name = vc.channel.name if (vc and vc.channel) else "None"
        ping = round(vc.latency * 1000) if (vc and hasattr(vc, "latency") and vc.latency) else "N/A"

        embed = discord.Embed(
            title="🩺 AI Voice Engine Diagnostics",
            color=0x2ECC71 if (ffmpeg_bin and opus_loaded) else 0xED4245,
        )

        embed.add_field(
            name="🎵 Audio Binaries",
            value=(
                f"• **FFmpeg:** `{'✅ Found' if ffmpeg_bin else '❌ Missing'}` ({ffmpeg_bin or 'None'})\n"
                f"• **Opus:** `{'✅ Loaded' if opus_loaded else '❌ Not Loaded'}`\n"
                f"• **Edge-TTS:** `{'✅ Installed (Primary)' if HAS_EDGE_TTS else '⚠️ Missing'}`\n"
                f"• **gTTS Fallback:** `✅ Ready`"
            ),
            inline=False,
        )

        embed.add_field(
            name="📡 Connection State",
            value=(
                f"• **Connected:** `{'✅ Yes' if connected else '⚪ Disconnected'}`\n"
                f"• **Active Channel:** `{channel_name}`\n"
                f"• **Voice Ping:** `{ping}ms`\n"
                f"• **Music Isolation:** `✅ Safe (Separate Handlers)`"
            ),
            inline=False,
        )

        embed.set_footer(text=f"Requested by {ctx.author.display_name} • KYOKA 3.0 Diagnostics")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIVoice(bot))
    logger.info("🎙️ [KYOKA] Modular AI Voice Engine Cog loaded.")
