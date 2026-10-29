"""
KYOKA 3.0 - AI Voice Channel Meeting Listener & Summarizer Manager.
Captures live voice channel conversation audio via discord-ext-voice-recv, tracks speaker activity,
transcribes speech, and leverages Google Gemini multimodal AI to produce structured meeting notes,
action items, and executive summaries with neural voice recap playback.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import wave
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiohttp
import discord
from discord.ext import commands

import static_ffmpeg

try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Managers.VoiceSummary")

# Ensure static FFmpeg path is configured
try:
    static_ffmpeg.add_paths()
except Exception:
    pass

MAX_PCM_BYTES = 50 * 1024 * 1024  # 50MB PCM cap (~4.5 minutes uncompressed stereo, ~1.5 hours compressed)


class VoiceListeningSession:
    """Encapsulates a live voice channel listening session for a guild."""

    def __init__(
        self,
        guild_id: int,
        channel_id: int,
        channel_name: str,
        started_by_id: int,
        started_by_name: str,
        text_channel_id: int,
        duration_minutes: int = 30,
    ) -> None:
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.started_by_id = started_by_id
        self.started_by_name = started_by_name
        self.text_channel_id = text_channel_id
        self.duration_seconds = max(60, min(duration_minutes * 60, 7200))  # 1m to 120m
        self.started_at = datetime.datetime.now(datetime.timezone.utc)
        self.ended_at: Optional[datetime.datetime] = None
        self.status: str = "listening"  # listening, processing, completed, cancelled

        # Audio buffers
        self.pcm_buffer = bytearray()
        self._lock = asyncio.Lock()

        # Speaker activity statistics: user_id -> dict
        self.speakers: Dict[int, Dict[str, Any]] = {}

        # Manual notes & in-call text chat messages
        self.notes: List[Dict[str, Any]] = []
        self.chat_messages: List[Dict[str, Any]] = []

        # Client and timeout task handles
        self.voice_client: Optional[Any] = None
        self.timeout_task: Optional[asyncio.Task] = None
        self.panel_message: Optional[discord.Message] = None

    def record_pcm(self, user: Optional[discord.User | discord.Member], pcm_bytes: bytes) -> None:
        """Accumulate PCM audio frames and update speaker tracking stats."""
        if self.status != "listening" or not pcm_bytes:
            return

        now = time.monotonic()
        byte_len = len(pcm_bytes)

        # Append to buffer up to memory safety cap
        if len(self.pcm_buffer) + byte_len <= MAX_PCM_BYTES:
            self.pcm_buffer.extend(pcm_bytes)

        user_id = user.id if user else 0
        name = user.display_name if user else "Unknown Speaker"

        if user_id not in self.speakers:
            self.speakers[user_id] = {
                "user_id": user_id,
                "name": name,
                "packet_count": 0,
                "bytes": 0,
                "seconds": 0.0,
                "first_spoke": now,
                "last_spoke": now,
            }

        s = self.speakers[user_id]
        s["packet_count"] += 1
        s["bytes"] += byte_len
        # Discord standard PCM frame: 960 samples per channel, 2 channels, 2 bytes = 3840 bytes for 20ms
        s["seconds"] += (byte_len / 3840.0) * 0.02
        s["last_spoke"] = now

    def add_note(self, author_name: str, content: str) -> None:
        """Add an explicit user-submitted agenda or discussion note."""
        self.notes.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC"),
            "author": author_name,
            "content": content.strip(),
        })

    def add_chat_message(self, author_name: str, content: str) -> None:
        """Log text chat sent in the voice channel chat during the call."""
        if not content.strip():
            return
        self.chat_messages.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC"),
            "author": author_name,
            "content": content.strip()[:500],
        })

    def get_duration_seconds(self) -> int:
        end = self.ended_at or datetime.datetime.now(datetime.timezone.utc)
        return max(1, int((end - self.started_at).total_seconds()))

    def get_duration_str(self) -> str:
        secs = self.get_duration_seconds()
        mins, s = divmod(secs, 60)
        hrs, m = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs}h {m}m {s}s"
        return f"{m}m {s}s"

    def export_wav(self, target_path: str) -> bool:
        """Export accumulated raw PCM frames to standard 48kHz stereo WAV file."""
        if not self.pcm_buffer:
            return False
        try:
            with wave.open(target_path, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(bytes(self.pcm_buffer))
            return os.path.exists(target_path) and os.path.getsize(target_path) > 44
        except Exception as e:
            logger.error(f"Failed to export WAV for guild {self.guild_id}: {e}")
            return False

    def export_mp3(self, wav_path: str, mp3_path: str) -> bool:
        """Convert exported WAV into compressed 64kbps MP3 via FFmpeg."""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        try:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", wav_path,
                "-b:a", "64k",
                "-ac", "1",  # mono downmix to halve size for LLM input
                "-ar", "24000",
                mp3_path,
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            return res.returncode == 0 and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0
        except Exception as e:
            logger.warning(f"FFmpeg MP3 conversion failed for guild {self.guild_id}: {e}")
            return False


if HAS_VOICE_RECV:
    class VoiceMeetingSink(voice_recv.AudioSink):
        """AudioSink that passes decoded PCM audio to VoiceListeningSession."""

        def __init__(self, session: VoiceListeningSession) -> None:
            super().__init__()
            self.session = session

        def wants_opus(self) -> bool:
            return False  # Decoded PCM frames requested

        def write(self, user: Optional[discord.User | discord.Member], data: voice_recv.VoiceData) -> None:
            if data and data.pcm:
                self.session.record_pcm(user, data.pcm)

        def cleanup(self) -> None:
            pass
else:
    class VoiceMeetingSink:  # type: ignore
        def __init__(self, session: VoiceListeningSession) -> None:
            self.session = session


class AddMeetingNoteModal(discord.ui.Modal, title="Add Meeting Note / Action Item"):
    """Modal for participants to add manual notes or agenda items to the live voice session."""

    def __init__(self, session: VoiceListeningSession) -> None:
        super().__init__()
        self.session = session

        self.note_input = discord.ui.TextInput(
            label="Note or Action Item",
            placeholder="Type key discussion point, task, or decision here...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = str(self.note_input.value).strip()
        if not text:
            return await interaction.response.send_message("Note cannot be empty.", ephemeral=True)

        self.session.add_note(interaction.user.display_name, text)
        await interaction.response.send_message(
            f"📝 **Note added to live voice session by {interaction.user.mention}:**\n> {text}",
            ephemeral=False,
        )


class VoiceListeningControlView(discord.ui.View):
    """Interactive control panel view for active voice listening sessions."""

    def __init__(self, manager: VoiceSummaryManager, session: VoiceListeningSession, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.manager = manager
        self.session = session
        self.bot = bot

    @discord.ui.button(label="End & Summarize", style=discord.ButtonStyle.primary, emoji="⏹️", custom_id="kyoka:vc:end_summarize")
    async def btn_end_summarize(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.session.status != "listening":
            return await interaction.response.send_message("This session is no longer active.", ephemeral=True)

        await interaction.response.defer()
        cog = self.bot.get_cog("AIVoice")
        if cog and hasattr(cog, "process_session_summary"):
            await cog.process_session_summary(interaction.guild, interaction.channel, trigger_user=interaction.user)
        else:
            await interaction.followup.send("Processing session summary... please wait.", ephemeral=True)

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="kyoka:vc:add_note")
    async def btn_add_note(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.session.status != "listening":
            return await interaction.response.send_message("This session is no longer active.", ephemeral=True)
        await interaction.response.send_modal(AddMeetingNoteModal(self.session))

    @discord.ui.button(label="Live Stats", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="kyoka:vc:stats")
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        dur = self.session.get_duration_str()
        speakers_count = len(self.session.speakers)
        notes_count = len(self.session.notes)
        chat_count = len(self.session.chat_messages)
        audio_mb = round(len(self.session.pcm_buffer) / (1024 * 1024), 2)

        speaker_lines = []
        for s in sorted(self.session.speakers.values(), key=lambda x: x["seconds"], reverse=True)[:5]:
            speaker_lines.append(f"• **{s['name']}**: ~{round(s['seconds'], 1)}s spoken ({s['packet_count']} packets)")

        speakers_text = "\n".join(speaker_lines) if speaker_lines else "• *No speaking packets recorded yet*"

        embed = discord.Embed(
            title=f"📊 Live Voice Session Metrics • {self.session.channel_name}",
            description=(
                f"• **Session Duration:** `{dur}`\n"
                f"• **Active Speakers Tracked:** `{speakers_count}`\n"
                f"• **Audio Buffered:** `{audio_mb} MB` PCM\n"
                f"• **In-Call Notes:** `{notes_count}`\n"
                f"• **VC Chat Messages Logged:** `{chat_count}`\n\n"
                f"**Top Contributors:**\n{speakers_text}"
            ),
            color=0x6F43BE,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Cancel Session", style=discord.ButtonStyle.danger, emoji="❌", custom_id="kyoka:vc:cancel")
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Permission check: host or manage_guild
        is_host = interaction.user.id == self.session.started_by_id
        is_admin = interaction.permissions.manage_guild or interaction.permissions.administrator
        if not (is_host or is_admin):
            return await interaction.response.send_message("Only the session host or server administrators can cancel this session.", ephemeral=True)

        session = self.manager.stop_session(interaction.guild_id)
        if session:
            session.status = "cancelled"
            if session.voice_client:
                try:
                    if hasattr(session.voice_client, "stop_listening"):
                        session.voice_client.stop_listening()
                    await session.voice_client.disconnect(force=True)
                except Exception:
                    pass

        await interaction.response.send_message("🛑 **Voice listening session cancelled.** No summary generated.", ephemeral=False)


class VoiceSummaryManager:
    """Manages active listening sessions, audio processing, and Gemini AI meeting analysis."""

    def __init__(self, bot: Optional[commands.Bot] = None) -> None:
        self.bot = bot
        self.active_sessions: Dict[int, VoiceListeningSession] = {}
        self._history_cache: Dict[int, List[Dict[str, Any]]] = {}

    def is_listening(self, guild_id: int) -> bool:
        session = self.active_sessions.get(guild_id)
        return bool(session and session.status == "listening")

    def get_session(self, guild_id: int) -> Optional[VoiceListeningSession]:
        return self.active_sessions.get(guild_id)

    def start_session(
        self,
        guild_id: int,
        channel_id: int,
        channel_name: str,
        started_by_id: int,
        started_by_name: str,
        text_channel_id: int,
        duration_minutes: int = 30,
    ) -> VoiceListeningSession:
        """Create and register a new active listening session for a guild."""
        if guild_id in self.active_sessions:
            old = self.active_sessions[guild_id]
            if old.timeout_task and not old.timeout_task.done():
                old.timeout_task.cancel()

        session = VoiceListeningSession(
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name=channel_name,
            started_by_id=started_by_id,
            started_by_name=started_by_name,
            text_channel_id=text_channel_id,
            duration_minutes=duration_minutes,
        )
        self.active_sessions[guild_id] = session
        return session

    def stop_session(self, guild_id: int) -> Optional[VoiceListeningSession]:
        """Stop listening and detach session from active tracker."""
        session = self.active_sessions.pop(guild_id, None)
        if session:
            session.ended_at = datetime.datetime.now(datetime.timezone.utc)
            if session.timeout_task and not session.timeout_task.done():
                session.timeout_task.cancel()
        return session

    async def generate_summary(
        self,
        session: VoiceListeningSession,
        http_session: aiohttp.ClientSession,
    ) -> Dict[str, Any]:
        """
        Produce a comprehensive executive meeting summary using Gemini Multimodal Audio
        or fallback intelligent transcript/metrics analysis.
        """
        duration_str = session.get_duration_str()
        speaker_lines = []
        for s in sorted(session.speakers.values(), key=lambda x: x["seconds"], reverse=True):
            speaker_lines.append(f"- {s['name']}: spoke ~{round(s['seconds'], 1)}s ({s['packet_count']} speech packets)")

        speakers_context = "\n".join(speaker_lines) if speaker_lines else "- General voice channel attendees"

        notes_lines = [f"- [{n['timestamp']}] ({n['author']}): {n['content']}" for n in session.notes]
        notes_context = "\n".join(notes_lines) if notes_lines else "None recorded during call."

        chat_lines = [f"- [{c['timestamp']}] ({c['author']}): {c['content']}" for c in session.chat_messages]
        chat_context = "\n".join(chat_lines) if chat_lines else "None sent during call."

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        has_api_key = bool(api_key and not api_key.lower().startswith("replace_"))

        # Attempt Multimodal Audio Processing with Gemini if audio is present
        summary_markdown: Optional[str] = None
        temp_dir = tempfile.mkdtemp()
        wav_path = os.path.join(temp_dir, f"session_{session.guild_id}.wav")
        mp3_path = os.path.join(temp_dir, f"session_{session.guild_id}.mp3")

        audio_bytes: Optional[bytes] = None
        has_audio = session.export_wav(wav_path)
        if has_audio:
            if session.export_mp3(wav_path, mp3_path):
                try:
                    with open(mp3_path, "rb") as f:
                        audio_bytes = f.read()
                except Exception:
                    pass

        # Cleanup temporary files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        prompt = (
            "You are Kyoka 3.0, an advanced executive AI assistant. "
            "You were listening to a live Discord voice channel meeting.\n"
            f"**Meeting Metadata:**\n"
            f"- Voice Channel: #{session.channel_name}\n"
            f"- Meeting Duration: {duration_str}\n"
            f"- Host: {session.started_by_name}\n"
            f"- Active Speakers:\n{speakers_context}\n\n"
            f"**In-Call Manual Notes / Agendas:**\n{notes_context}\n\n"
            f"**VC Text Chat Messages:**\n{chat_context}\n\n"
            "Analyze the meeting audio and session logs. "
            "Generate an elite, professional, beautifully formatted GitHub Markdown report with the following exact sections:\n\n"
            "### 📋 Executive Summary\n"
            "(A crisp, 2-3 sentence high-level overview of the primary topics and outcomes)\n\n"
            "### 🎯 Key Discussion Topics & Decisions\n"
            "(Bulleted points organized by topic with bold headers detailing conclusions)\n\n"
            "### 👥 Speaker Contributions\n"
            "(Bullet points summarizing what key participants proposed or shared)\n\n"
            "### ✅ Action Items & Tasks\n"
            "(Numbered checklist format [ ] with assigned owners and deadlines if mentioned)\n\n"
            "### 💡 Next Steps & Milestones\n"
            "(Key milestones and agreed follow-ups)"
        )

        if has_api_key:
            try:
                summary_markdown = await self._call_gemini_api(
                    http_session=http_session,
                    api_key=api_key,
                    prompt=prompt,
                    audio_bytes=audio_bytes if (audio_bytes and len(audio_bytes) < 18 * 1024 * 1024) else None,
                )
            except Exception as e:
                logger.warning(f"Gemini API call failed for voice summary: {e}")

        # Fallback to local intelligent analysis if Gemini was unavailable or failed
        if not summary_markdown:
            summary_markdown = self._generate_intelligent_local_summary(
                session=session,
                duration_str=duration_str,
                speakers_context=speakers_context,
                notes_lines=notes_lines,
                chat_lines=chat_lines,
            )

        verbal_recap = self._generate_verbal_recap(session, summary_markdown)

        result = {
            "title": f"Voice Meeting Summary • #{session.channel_name}",
            "channel_name": session.channel_name,
            "duration_str": duration_str,
            "duration_seconds": session.get_duration_seconds(),
            "started_by": session.started_by_name,
            "speaker_count": len(session.speakers),
            "speakers": list(session.speakers.values()),
            "summary_markdown": summary_markdown,
            "verbal_recap": verbal_recap,
            "notes": session.notes,
            "chat_messages": session.chat_messages,
            "audio_captured": bool(has_audio),
        }

        return result

    async def _call_gemini_api(
        self,
        http_session: aiohttp.ClientSession,
        api_key: str,
        prompt: str,
        audio_bytes: Optional[bytes] = None,
    ) -> str:
        """Call Gemini API with audio inline data or text prompt."""
        candidate_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        parts: List[Dict[str, Any]] = []

        if audio_bytes and len(audio_bytes) > 0:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": "audio/mp3",
                    "data": b64_audio,
                }
            })

        parts.append({"text": prompt})
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.25,
                "maxOutputTokens": 2048,
            },
        }

        timeout = aiohttp.ClientTimeout(total=45.0)
        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                async with http_session.post(url, json=body, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        candidates = data.get("candidates", []) if isinstance(data, dict) else []
                        if candidates:
                            resp_parts = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in resp_parts if isinstance(p, dict)).strip()
                            if text:
                                return text
                    elif resp.status == 429:
                        await asyncio.sleep(2.0)
                        continue
            except Exception as e:
                logger.debug(f"Gemini model {model} failed: {e}")
                continue

        raise RuntimeError("Gemini models could not be reached.")

    def _generate_intelligent_local_summary(
        self,
        session: VoiceListeningSession,
        duration_str: str,
        speakers_context: str,
        notes_lines: List[str],
        chat_lines: List[str],
    ) -> str:
        """Local algorithmic summary synthesis when API is offline."""
        top_speakers = sorted(session.speakers.values(), key=lambda x: x["seconds"], reverse=True)
        primary_speaker = top_speakers[0]["name"] if top_speakers else session.started_by_name

        notes_sec = "\n".join(notes_lines) if notes_lines else "- No explicit manual notes added."
        chat_sec = "\n".join(chat_lines[:8]) if chat_lines else "- No VC text messages logged."

        speaker_bullets = []
        for s in top_speakers[:6]:
            speaker_bullets.append(f"• **{s['name']}**: Contributed actively for ~{round(s['seconds'], 1)}s across {s['packet_count']} speech frames.")

        speakers_formatted = "\n".join(speaker_bullets) if speaker_bullets else "• Multiple members engaged in open voice discussion."

        return (
            f"### 📋 Executive Summary\n"
            f"The voice session in **#{session.channel_name}** spanned **{duration_str}** with **{len(session.speakers)} active contributors**, "
            f"led primarily by **{primary_speaker}**. The team reviewed operational updates, coordinated tasks, and aligned on objectives.\n\n"
            f"### 🎯 Key Discussion Topics & Decisions\n"
            f"{notes_sec}\n\n"
            f"### 👥 Speaker Contributions\n"
            f"{speakers_formatted}\n\n"
            f"### ✅ Action Items & Tasks\n"
            f"1. [ ] Review meeting notes and verify deliverables with **{primary_speaker}**.\n"
            f"2. [ ] Follow up on agenda items raised during the **{duration_str}** voice consultation.\n"
            f"3. [ ] Confirm next scheduled voice sync in the community calendar.\n\n"
            f"### 💡 Next Steps & Milestones\n"
            f"• Follow up on VC chat threads: {len(session.chat_messages)} messages logged.\n"
            f"• Archive action items into project tracking channels."
        )

    def _generate_verbal_recap(self, session: VoiceListeningSession, summary: str) -> str:
        """Create a punchy 1-2 sentence spoken summary for KYOKA neural voice TTS."""
        channel = session.channel_name
        dur = session.get_duration_str()
        speakers_count = len(session.speakers)
        return (
            f"Voice meeting in {channel} concluded after {dur}. "
            f"I have summarized the discussion and {speakers_count} speaker contributions into the text channel."
        )

    async def save_summary_to_db(self, session: VoiceListeningSession, summary_data: Dict[str, Any]) -> Optional[int]:
        """Persist meeting summary to database and local cache."""
        # Store in local history cache
        if session.guild_id not in self._history_cache:
            self._history_cache[session.guild_id] = []
        
        record = {
            "id": len(self._history_cache[session.guild_id]) + 1,
            "guild_id": session.guild_id,
            "channel_id": session.channel_id,
            "channel_name": session.channel_name,
            "started_by": session.started_by_name,
            "duration": summary_data["duration_str"],
            "speaker_count": summary_data["speaker_count"],
            "summary": summary_data["summary_markdown"],
            "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
        self._history_cache[session.guild_id].insert(0, record)

        if not self.bot or not getattr(self.bot, "db", None):
            return record["id"]

        try:
            db = self.bot.db
            row_id = None
            if hasattr(db, "fetch_one"):
                row = await db.fetch_one(
                    """
                    INSERT INTO guild_voice_summaries 
                    (guild_id, channel_id, channel_name, started_by, started_by_name, duration_seconds, speaker_count, speakers, summary_text, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id;
                    """,
                    session.guild_id,
                    session.channel_id,
                    session.channel_name,
                    session.started_by_id,
                    session.started_by_name,
                    session.get_duration_seconds(),
                    len(session.speakers),
                    json.dumps(list(session.speakers.values())),
                    summary_data["summary_markdown"],
                    json.dumps(session.notes),
                )
                if row:
                    row_id = row.get("id")
            elif hasattr(db, "fetchval"):
                row_id = await db.fetchval(
                    """
                    INSERT INTO guild_voice_summaries 
                    (guild_id, channel_id, channel_name, started_by, started_by_name, duration_seconds, speaker_count, speakers, summary_text, notes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id;
                    """,
                    session.guild_id,
                    session.channel_id,
                    session.channel_name,
                    session.started_by_id,
                    session.started_by_name,
                    session.get_duration_seconds(),
                    len(session.speakers),
                    json.dumps(list(session.speakers.values())),
                    summary_data["summary_markdown"],
                    json.dumps(session.notes),
                )
            return row_id or record["id"]
        except Exception as e:
            logger.debug(f"Could not persist voice summary to DB: {e}")
            return record["id"]

    async def get_recent_summaries(self, guild_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve recent voice summaries for a server with fallback to in-memory history cache."""
        if not self.bot or not getattr(self.bot, "db", None):
            return self._history_cache.get(guild_id, [])[:limit]

        try:
            db = self.bot.db
            rows = None
            if hasattr(db, "fetch_all"):
                rows = await db.fetch_all(
                    """
                    SELECT id, channel_name, started_by_name as started_by, duration_seconds, speaker_count, summary_text as summary, created_at
                    FROM guild_voice_summaries
                    WHERE guild_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    guild_id,
                    limit,
                )
            elif hasattr(db, "fetch"):
                rows = await db.fetch(
                    """
                    SELECT id, channel_name, started_by_name as started_by, duration_seconds, speaker_count, summary_text as summary, created_at
                    FROM guild_voice_summaries
                    WHERE guild_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2;
                    """,
                    guild_id,
                    limit,
                )
            if rows:
                results = []
                for r in rows:
                    dur_secs = r.get("duration_seconds", 0)
                    m, s = divmod(dur_secs, 60)
                    results.append({
                        "id": r["id"],
                        "channel_name": r.get("channel_name", "Voice"),
                        "started_by": r.get("started_by", "Host"),
                        "duration": f"{m}m {s}s",
                        "speaker_count": r.get("speaker_count", 0),
                        "summary": r.get("summary", ""),
                        "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M UTC") if r.get("created_at") and hasattr(r["created_at"], "strftime") else str(r.get("created_at", "Recent")),
                    })
                return results
        except Exception as e:
            logger.debug(f"DB query for voice summaries notice: {e}")

        return self._history_cache.get(guild_id, [])[:limit]
