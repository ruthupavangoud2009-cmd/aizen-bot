from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import aiohttp
import discord
from discord.ext import commands, tasks

from src.core.config import Config
from src.security.owner import is_primary_owner
from src.core.context import CustomContext
from src.database.base import BaseDatabase
from src.database.postgres import PostgresDatabase
from src.managers.guild_manager import GuildManager
from src.managers.permission_manager import PermissionManager
from src.managers.blacklist_manager import BlacklistManager
from src.managers.system_manager import SystemManager
from src.managers.log_manager import LogManager
from src.managers.premium_manager import PremiumManager
from src.managers.embed_manager import EmbedManager
from src.managers.event_manager import EventManager
from src.managers.ticket_manager import TicketManager
from src.managers.tech_manager import TechNewsManager
from src.managers.dev_pulse_manager import DevPulseManager
from src.managers.tech_realtime_manager import TechRealtimeManager
from src.managers.temp_voice_manager import TempVoiceManager
from src.managers.translator_manager import TranslatorManager
from src.managers.sticky_manager import StickyManager
from src.managers.antinuke_manager import AntinukeManager
from src.managers.media_manager import MediaManager
from src.managers.giveaway_manager import GiveawayManager
from src.managers.activity_manager import ActivityManager
from src.managers.ai_manager import AIManager
from src.utils.emojis import EmojiRegistry

logger = logging.getLogger("Kyoka.Core")


async def get_prefix(bot: KyokaBot, message: discord.Message) -> list[str]:
    """
    Dynamic prefix resolver:
    - Supports configured guild prefix, default prefix ('+'), and legacy prefix ('?').
    - Supports bot mentions (<@id>, <@!id>).
    - Bot Owner, Developers & No-Prefix Authorized Users can also use commands with NO prefix.
    """
    guild_id = message.guild.id if message.guild else None
    guild_prefix = bot.guild_mgr.get_prefix(guild_id) if hasattr(bot, "guild_mgr") else Config.DEFAULT_PREFIX

    # Collect all valid prefixes: guild-specific, default (+), and legacy (?)
    prefixes: list[str] = []
    for p in (guild_prefix, Config.DEFAULT_PREFIX, "+", "?"):
        if p and p not in prefixes:
            prefixes.append(p)

    # Check if author has No-Prefix authorization or is Owner/Developer
    is_no_prefix = False
    if message.author:
        author_id = message.author.id
        from src.security.owner import is_primary_owner
        if is_primary_owner(author_id) or author_id in getattr(bot, "no_prefix_users", set()):
            is_no_prefix = True
        elif hasattr(bot, "perm_mgr") and bot.perm_mgr.is_developer_sync(author_id):
            is_no_prefix = True

    if is_no_prefix and "" not in prefixes:
        prefixes.append("")

    if bot.user:
        return commands.when_mentioned_or(*prefixes)(bot, message)
    return prefixes


class KyokaBot(commands.Bot):
    """Production-grade custom Discord bot class for Kyoka."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True

        proxy_url = Config.DISCORD_PROXY or os.getenv("DISCORD_PROXY", "").strip() or None
        if proxy_url:
            # Mask credentials if present for security in logs
            import urllib.parse
            parsed_proxy = urllib.parse.urlparse(proxy_url)
            masked_host = f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}" if parsed_proxy.hostname else "configured proxy"
            logger.info(f"Outbound proxy configured: {masked_host}")

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
            status=discord.Status.dnd,
            proxy=proxy_url,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                roles=False,
                users=True,
                replied_user=True,
            ),
            activity=discord.CustomActivity(
                name=f"Listening to {Config.DEFAULT_PREFIX}help",
            ),
        )

        if Config.CLIENT_ID:
            self._connection.application_id = Config.CLIENT_ID

        # Sole Database Driver (Supabase PostgreSQL)
        from src.database.postgres import PostgresDatabase
        self.db: PostgresDatabase = PostgresDatabase(Config.DATABASE_URL)

        from src.core.cache import MicrosecondCache
        self.cache: MicrosecondCache = MicrosecondCache()

        self.session: aiohttp.ClientSession | None = None
        self.start_time: discord.datetime = discord.utils.utcnow()

        # Core Managers & Emoji Registry
        self.guild_mgr: GuildManager = GuildManager(self.db, cache=self.cache)
        self.perm_mgr: PermissionManager = PermissionManager(self, self.db)
        self.blacklist_mgr: BlacklistManager = BlacklistManager(self.db)
        self.sys_mgr: SystemManager = SystemManager(self.db)
        self.log_mgr: LogManager = LogManager(self.db)
        self.premium_mgr: PremiumManager = PremiumManager(self.db)
        self.embed_mgr: EmbedManager = EmbedManager(self.db)
        self.event_mgr: EventManager = EventManager(self.db)
        self.ticket_mgr: TicketManager = TicketManager(self.db)
        self.tech_mgr: TechNewsManager = TechNewsManager(self.db)
        self.dev_mgr: DevPulseManager = DevPulseManager(self.db)
        self.tech_realtime_mgr: TechRealtimeManager = TechRealtimeManager(self.db)
        self.temp_voice_mgr: TempVoiceManager = TempVoiceManager(self.db)
        self.translator_mgr: TranslatorManager = TranslatorManager(self.db)
        self.sticky_mgr: StickyManager = StickyManager(self.db)
        self.antinuke_mgr: AntinukeManager = AntinukeManager(self.db)
        self.media_mgr: MediaManager = MediaManager(self.db)
        self.giveaway_mgr: GiveawayManager = GiveawayManager(self.db)
        self.activity_mgr: ActivityManager = ActivityManager(self.db)
        self.ai_mgr: AIManager = AIManager(self.db)
        from src.managers.leveling_manager import LevelingManager
        self.leveling_mgr: LevelingManager = LevelingManager(self.db)
        from src.managers.reaction_role_manager import ReactionRoleManager
        self.reaction_role_mgr: ReactionRoleManager = ReactionRoleManager(self.db)
        self.custom_emojis: EmojiRegistry = EmojiRegistry(self)
        self.no_prefix_users: set[int] = set()
        self.custom_status: str | None = None
        self.failed_extensions: dict[str, str] = {}

        # Attach Global Command Guard
        self.add_check(self._global_command_check)

    async def get_context(
        self, origin: discord.Message | discord.Interaction, *, cls: type[CustomContext] = CustomContext
    ) -> CustomContext:
        """Inject our CustomContext into all commands."""
        return await super().get_context(origin, cls=cls)

    async def _global_command_check(self, ctx: commands.Context) -> bool:
        """Global guard: blocks blacklisted users/guilds and handles maintenance mode."""
        # blacklist Check
        if self.blacklist_mgr.is_user_blacklisted(ctx.author.id):
            reason = self.blacklist_mgr.get_blacklist_reason(ctx.author.id)
            raise commands.CheckFailure(f"You are globally blacklisted from using this bot.\n> Reason: `{reason}`")

        if ctx.guild and self.blacklist_mgr.is_guild_blacklisted(ctx.guild.id):
            reason = self.blacklist_mgr.get_blacklist_reason(ctx.guild.id)
            raise commands.CheckFailure(f"This server is blacklisted from using this bot.\n> Reason: `{reason}`")

        # maintenance Mode Check
        if self.sys_mgr.maintenance_mode:
            if not is_primary_owner(ctx.author.id):
                raise commands.CheckFailure(
                    f"Bot is currently in Maintenance Mode.\n> Reason: `{self.sys_mgr.maintenance_reason}`"
                )

        # disabled Command Check
        cmd_name = ctx.command.qualified_name if ctx.command else ""
        if self.sys_mgr.is_command_disabled(cmd_name):
            if not is_primary_owner(ctx.author.id):
                raise commands.CheckFailure(f"Command `{cmd_name}` is temporarily disabled by administrators.")

        if ctx.guild and self.guild_mgr.is_command_disabled(ctx.guild.id, cmd_name):
            raise commands.CheckFailure(f"Command `{cmd_name}` is disabled in this server.")

        return True

    async def on_message(self, message: discord.Message) -> None:
        """Handle standalone bot mentions and process prefix/mention commands."""
        if message.author.bot:
            return

        # Check if message is purely mentioning the bot (with optional spaces)
        clean_content = message.content.strip()
        if self.user and clean_content in [f"<@{self.user.id}>", f"<@!{self.user.id}>"]:
            from src.core.greetings import send_bot_mention_card
            await send_bot_mention_card(self, message)
            return

        # Record qualifying message activity & progression in background (non-blocking & fail-safe)
        if message.guild:
            if hasattr(self, "activity_mgr"):
                try:
                    asyncio.create_task(
                        self.activity_mgr.record_message(
                            message.guild.id,
                            message.author.id,
                            message.channel.id,
                            len(message.content),
                        )
                    )
                except Exception as e:
                    logger.debug(f"Activity logging notice: {e}")

            if hasattr(self, "leveling_mgr"):
                try:
                    asyncio.create_task(self._process_message_xp(message))
                except Exception as e:
                    logger.debug(f"Leveling XP notice: {e}")

        # Dispatch prefix & no-prefix commands with complete safety
        await self.process_commands(message)

    async def _process_message_xp(self, message: discord.Message) -> None:
        """Process XP gain and optional level-up alerts safely in the background."""
        try:
            is_opt = self.activity_mgr.is_opted_out(message.author.id) if hasattr(self, "activity_mgr") else False
            awarded, new_xp, new_lvl, leveled_up = await self.leveling_mgr.award_message_xp(
                message.guild.id, message.author.id, is_opted_out=is_opt
            )
            if leveled_up and message.guild:
                cfg = self.leveling_mgr.get_guild_settings(message.guild.id)
                if cfg.get("announce", True):
                    ch = message.guild.get_channel(cfg.get("channel_id") or message.channel.id)
                    if ch:
                        await ch.send(f"🎉 Congratulations {message.author.mention}, you leveled up to **Level {new_lvl}**!")
        except Exception as e:
            logger.debug(f"Background XP processing notice: {e}")

    async def on_command(self, ctx: commands.Context) -> None:
        """Log command execution details safely (never logging sensitive credentials)."""
        guild_info = f"Guild {ctx.guild.id}" if ctx.guild else "Direct Message"
        logger.info(
            f"Command Executed: '{ctx.command.qualified_name}' by {ctx.author} (ID: {ctx.author.id}) "
            f"in {guild_info} | Prefix: '{ctx.prefix}'"
        )

    async def setup_hook(self) -> None:
        """Asynchronous initialization before websocket login."""
        logger.info("Initializing async subsystems and managers...")

        # start HTTP Client Session
        self.session = aiohttp.ClientSession()

        # connect to Database Pool
        await self.db.connect()

        # load all Manager Caches & Custom Emojis
        await self.guild_mgr.load_cache()
        await self.perm_mgr.load_cache()
        await self.blacklist_mgr.load_cache()
        await self.sys_mgr.load_cache()
        await self.log_mgr.load_cache()
        await self.premium_mgr.load_cache()
        await self.ticket_mgr.load_cache()
        await self.tech_mgr.load_cache()
        await self.dev_mgr.load_cache()
        await self.tech_realtime_mgr.initialize()
        await self.temp_voice_mgr.load_cache()
        await self.translator_mgr.load_cache()
        await self.sticky_mgr.load_cache()
        await self.antinuke_mgr.load_cache()
        await self.media_mgr.load_cache()
        await self.giveaway_mgr.load_cache()
        await self.activity_mgr.load_cache()
        await self.ai_mgr.load_cache()
        await self.leveling_mgr.load_cache()
        await self.reaction_role_mgr.load_cache()
        await self.custom_emojis.load()

        # Load No-Prefix authorized users into memory
        from src.security.owner import OWNER_ID
        self.no_prefix_users.add(OWNER_ID)
        try:
            np_rows = await self.db.fetch_all("SELECT user_id FROM system_no_prefix;")
            for r in np_rows:
                self.no_prefix_users.add(int(r["user_id"]))
            logger.info(f"Loaded {len(self.no_prefix_users)} No-Prefix authorized user(s) into memory cache.")
        except Exception as e:
            logger.debug(f"Notice loading No-Prefix users: {e}")

        # Load persistent custom bot status into memory
        try:
            status_row = await self.db.fetch_one("SELECT value FROM system_state WHERE key = 'bot_status';")
            if status_row and status_row.get("value"):
                self.custom_status = status_row["value"]
                logger.info(f"Loaded persistent custom bot status: {self.custom_status}")
        except Exception as e:
            logger.debug(f"Notice loading custom status: {e}")

        # load Error Handler
        await self.load_extension("src.errors.handler")

        # dynamically Load all Cogs
        await self._load_all_extensions()

        # Slash Command Synchronization Strategy
        if Config.DEV_GUILD_ID:
            try:
                dev_guild = discord.Object(id=Config.DEV_GUILD_ID)
                self.tree.copy_global_to(guild=dev_guild)
                synced_dev = await self.tree.sync(guild=dev_guild)
                logger.info(
                    f"Instant Dev Sync: Synced {len(synced_dev)} slash commands to DEV_GUILD_ID ({Config.DEV_GUILD_ID})."
                )
            except Exception as e:
                logger.warning(f"DEV_GUILD_ID slash command sync failed: {e}")

        if Config.SYNC_COMMANDS_ON_STARTUP:
            try:
                synced = await self.tree.sync()
                logger.info(
                    f"Global Slash Sync: Successfully synced {len(synced)} application/slash commands globally to Discord API."
                )
            except Exception as e:
                logger.warning(f"Automatic global slash command sync failed: {e}")
        else:
            logger.info("Automatic global slash command sync on startup is disabled (set SYNC_COMMANDS_ON_STARTUP=true or use '+sync').")

        logger.info("Setup hook completed successfully.")

    async def _load_all_extensions(self) -> None:
        """Walk through src/cogs and load every python module."""
        cogs_dir = Path(__file__).resolve().parent.parent / "cogs"

        for file in cogs_dir.rglob("*.py"):
            # Skip any file that starts with '_' or is inside a directory starting with '_'
            if any(part.startswith("_") for part in file.relative_to(cogs_dir).parts):
                continue

            relative = file.relative_to(cogs_dir.parent.parent)
            module_name = ".".join(relative.with_suffix("").parts)

            try:
                await self.load_extension(module_name)
                logger.info(f"Loaded extension: {module_name}")
            except Exception as e:
                self.failed_extensions[module_name] = type(e).__name__
                logger.error(f"Failed to load extension {module_name}: {type(e).__name__}", exc_info=e)

    async def close(self) -> None:
        """Gracefully release database pools and network sessions."""
        logger.info("Shutting down Kyoka Bot gracefully...")

        if self.session:
            await self.session.close()

        if self.db:
            await self.db.close()

        await super().close()

    @tasks.loop(seconds=60)
    async def _rotate_presence(self) -> None:
        """Maintain persistent bot presence and DND status."""
        try:
            status_text = self.custom_status or f"Listening to {Config.DEFAULT_PREFIX}help"
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=status_text),
            )
        except Exception:
            pass


    @_rotate_presence.before_loop
    async def _before_rotate_presence(self) -> None:
        await self.wait_until_ready()


    async def on_ready(self) -> None:
        """Fired when Discord client has finished caching guilds."""
        logger.info(
            f"Logged in as {self.user} (ID: {self.user.id}) across {len(self.guilds)} guilds."
        )

        # Never infer privileged identities from Discord team/application ownership.
        # The security policy has one immutable primary owner ID.
        from src.security.owner import OWNER_ID
        self.owner_id = OWNER_ID
        self.owner_ids = {OWNER_ID}

        # Snapshot guild states for zero-latency antinuke self-healing
        for g in self.guilds:
            try:
                self.antinuke_mgr.snapshot_guild_state(g)
            except Exception as e:
                logger.debug(f"Notice snapshotting guild {g.id}: {e}")

        # Immediately lock presence to DND with persistent custom status
        try:
            status_text = self.custom_status or f"Listening to {Config.DEFAULT_PREFIX}help"
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=status_text),
            )
        except Exception as e:
            logger.warning(f"Could not enforce DND presence: {e}")
        if not self._rotate_presence.is_running():
            self._rotate_presence.start()

        # Startup Diagnostics Log
        prefix_count = len(self.commands)
        slash_count = len(self.tree.get_commands())
        cogs_count = len(self.cogs)
        msg_intent = self.intents.message_content
        logger.info(
            f"=== KYOKA 3.0 STARTUP DIAGNOSTICS ===\n"
            f"> Cogs Loaded: {cogs_count}\n"
            f"> Registered Prefix Commands: {prefix_count}\n"
            f"> Registered Slash Commands: {slash_count}\n"
            f"> Default Prefix: '{Config.DEFAULT_PREFIX}' (Also accepts: '+', '?', mentions, and No-Prefix for owner)\n"
            f"> Gateway Message Content Intent: {'ENABLED (OK)' if msg_intent else 'DISABLED (CRITICAL)'}\n"
            f"======================================"
        )

        logger.info("Presence locked to DND. Slash command tree initialized.")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Fired when Kyoka is invited to a new server."""
        from src.core.greetings import send_guild_welcome_card
        await send_guild_welcome_card(self, guild)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Fired when Kyoka is removed from a server."""
        logger.info(f"Removed from guild: {guild.name} ({guild.id}).")
        # Clean up any active music player for this guild
        music_cog = self.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            player = music_cog.controller.get_player(guild.id)
            if player:
                try:
                    await player.stop()
                except Exception:
                    pass
                music_cog.controller._players.pop(guild.id, None)


# Backward Compatibility Alias
KyroBot = KyokaBot
