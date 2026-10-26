from __future__ import annotations

import asyncio
import logging
from typing import Any
import asyncpg

from src.database.base import BaseDatabase

logger = logging.getLogger("Kyoka.Database.Postgres")


class PostgresDatabase(BaseDatabase):
    """PostgreSQL / Supabase async database connector with self-healing connection pool."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None
        self._lock = asyncio.Lock()

    async def _heal_pool(self) -> None:
        """Self-healing connection pool reconnector with exponential backoff."""
        async with self._lock:
            if self.pool and not self.pool._closed:
                try:
                    async with self.pool.acquire(timeout=3) as conn:
                        await conn.execute("SELECT 1;")
                    return
                except Exception:
                    logger.warning("Database connection pool unhealthy. Cycling connection pool...")
                    try:
                        await self.pool.close()
                    except Exception:
                        pass
                    self.pool = None

            clean_dsn = self.dsn.replace("postgresql+asyncpg://", "postgresql://")
            delays = [0.5, 1.0, 2.0, 4.0]
            for attempt, delay in enumerate(delays, 1):
                try:
                    logger.info(f"Self-healing database pool reconnecting (attempt {attempt}/{len(delays)})...")
                    self.pool = await self._create_pool(clean_dsn)
                    logger.info("Database pool self-healed and reconnected successfully.")
                    return
                except Exception as e:
                    logger.warning(f"Reconnect attempt {attempt} failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)

            raise ConnectionError("Database pool could not be auto-healed after multiple backoff attempts.")

    async def _create_pool(self, clean_dsn: str) -> asyncpg.Pool:
        """Create pool with dual-stack address diagnosis and IPv4 fallback for Render."""
        import socket
        import urllib.parse

        try:
            return await asyncpg.create_pool(
                clean_dsn,
                min_size=2,
                max_size=10,
                command_timeout=30,
                statement_cache_size=0,
            )
        except OSError as e:
            is_unreachable = getattr(e, "errno", None) in (101, 10051) or "unreachable" in str(e).lower()
            if not is_unreachable:
                raise

            parsed = urllib.parse.urlparse(clean_dsn)
            host = parsed.hostname or "unknown"
            port = parsed.port or 5432

            ipv4_addrs = []
            ipv6_addrs = []
            try:
                loop = asyncio.get_running_loop()
                addr_infos = await loop.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                for item in addr_infos:
                    fam, _, _, _, sockaddr = item
                    ip = sockaddr[0]
                    if fam == socket.AF_INET and ip not in ipv4_addrs:
                        ipv4_addrs.append(ip)
                    elif fam == socket.AF_INET6 and ip not in ipv6_addrs:
                        ipv6_addrs.append(ip)
            except Exception as dns_err:
                logger.warning(f"DNS check for '{host}' encountered: {dns_err}")

            if ipv4_addrs:
                logger.warning(
                    f"Network unreachable connecting to '{host}:{port}' via IPv6. "
                    f"Retrying connection via resolved IPv4 address '{ipv4_addrs[0]}'..."
                )
                try:
                    userinfo = f"{parsed.username or ''}:{parsed.password or ''}@" if parsed.username else ""
                    netloc = f"{userinfo}{ipv4_addrs[0]}:{port}"
                    ipv4_dsn = parsed._replace(netloc=netloc).geturl()
                    return await asyncpg.create_pool(
                        ipv4_dsn,
                        min_size=2,
                        max_size=10,
                        command_timeout=30,
                        statement_cache_size=0,
                    )
                except Exception as ipv4_err:
                    logger.error(f"IPv4 fallback connection attempt to '{ipv4_addrs[0]}' failed: {ipv4_err}")

            if "supabase.co" in host.lower() and host.lower().startswith("db."):
                logger.critical(
                    f"CRITICAL: Database connection failed: [Errno 101] Network is unreachable to host '{host}'.\n"
                    f"DNS lookup confirmed '{host}' only provides IPv6 addresses ({ipv6_addrs}).\n"
                    "Render containers lack outbound IPv6 routing.\n"
                    "To resolve: Update DATABASE_URL in Render to use your Supabase Connection Pooler:\n"
                    "  postgresql://postgres.<project_ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres\n"
                    "  (or port 6543 for transaction mode)."
                )

            raise

    async def connect(self) -> None:
        """Create an asynchronous PostgreSQL connection pool."""
        try:
            clean_dsn = self.dsn.replace("postgresql+asyncpg://", "postgresql://")
            self.pool = await self._create_pool(clean_dsn)
            logger.info("Connected to PostgreSQL / Supabase cloud database pool.")
            await self.initialize_tables()
        except Exception as e:
            logger.critical(f"Failed to connect to PostgreSQL / Supabase: {e}", exc_info=e)
            raise

    async def close(self) -> None:
        """Close connection pool gracefully."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL database connection pool closed.")

    async def initialize_tables(self) -> None:
        """Initialize PostgreSQL schemas for Kyoka modules."""
        queries = [
            # Guild settings table
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                prefix VARCHAR(10) DEFAULT '?',
                language VARCHAR(10) DEFAULT 'en',
                log_channel_id BIGINT,
                mod_role_id BIGINT,
                disabled_commands TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # System developers table
            """
            CREATE TABLE IF NOT EXISTS system_developers (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # System global blacklists table
            """
            CREATE TABLE IF NOT EXISTS system_blacklists (
                target_id BIGINT PRIMARY KEY,
                target_type VARCHAR(20) DEFAULT 'user',
                reason TEXT DEFAULT 'Violation of bot rules',
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # System global state table
            """
            CREATE TABLE IF NOT EXISTS system_state (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT
            );
            """,
            # System No-Prefix persistent authorized dispatchers
            """
            CREATE TABLE IF NOT EXISTS system_no_prefix (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Global Blacklist persistent table
            """
            CREATE TABLE IF NOT EXISTS system_blacklists (
                target_id BIGINT PRIMARY KEY,
                target_type VARCHAR(16) DEFAULT 'user',
                reason TEXT,
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # User profiles / Economy table
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id BIGINT,
                guild_id BIGINT,
                balance BIGINT DEFAULT 0,
                bank BIGINT DEFAULT 0,
                xp BIGINT DEFAULT 0,
                level INT DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            # Server modular audit logging channels
            """
            CREATE TABLE IF NOT EXISTS guild_logs (
                guild_id BIGINT PRIMARY KEY,
                all_channel_id BIGINT,
                mod_channel_id BIGINT,
                message_channel_id BIGINT,
                member_channel_id BIGINT,
                server_channel_id BIGINT,
                voice_channel_id BIGINT
            );
            """,
            # Premium License Keys table
            """
            CREATE TABLE IF NOT EXISTS premium_keys (
                key VARCHAR(64) PRIMARY KEY,
                duration_days INT NOT NULL,
                target_type VARCHAR(20) DEFAULT 'guild',
                created_by BIGINT NOT NULL,
                is_used BOOLEAN DEFAULT FALSE,
                redeemed_by BIGINT,
                redeemed_target_id BIGINT,
                redeemed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Active Guild/Server Premium table
            """
            CREATE TABLE IF NOT EXISTS guild_premium (
                guild_id BIGINT PRIMARY KEY,
                tier VARCHAR(50) DEFAULT 'pro',
                activated_by BIGINT,
                key_used VARCHAR(64),
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Active User/Personal Premium table
            """
            CREATE TABLE IF NOT EXISTS user_premium (
                user_id BIGINT PRIMARY KEY,
                tier VARCHAR(50) DEFAULT 'pro',
                key_used VARCHAR(64),
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Customer Lifetime Analytics & Repeat Buyers table
            """
            CREATE TABLE IF NOT EXISTS premium_customers (
                target_id BIGINT PRIMARY KEY,
                target_type VARCHAR(20) DEFAULT 'user',
                total_redemptions INT DEFAULT 1,
                total_days_purchased INT DEFAULT 0,
                first_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Custom Components V2 Embed / Container Templates table
            """
            CREATE TABLE IF NOT EXISTS server_embeds (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                embed_name VARCHAR(64) NOT NULL,
                container_payload TEXT NOT NULL,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, embed_name)
            );
            """,
            # Live Interactive Messages for Dropdown Page Switchers
            """
            CREATE TABLE IF NOT EXISTS interactive_cards (
                guild_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                template_name VARCHAR(64),
                card_payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, message_id)
            );
            """,
            # Server Auto-Events (Welcome, Leave, Boost) binding table
            """
            CREATE TABLE IF NOT EXISTS server_events (
                guild_id BIGINT NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                channel_id BIGINT,
                embed_name VARCHAR(64),
                message_content TEXT,
                is_enabled BOOLEAN DEFAULT TRUE,
                dm_enabled BOOLEAN DEFAULT FALSE,
                dm_embed_name VARCHAR(64),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, event_type)
            );
            """,
            # Modular Ticket Panels configuration table
            """
            CREATE TABLE IF NOT EXISTS ticket_panels (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                panel_name VARCHAR(64) NOT NULL,
                embed_name VARCHAR(64) NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                category_id BIGINT,
                support_role_id BIGINT,
                log_channel_id BIGINT,
                naming_format VARCHAR(64) DEFAULT 'ticket-{count}',
                button_label VARCHAR(64) DEFAULT 'Create Ticket',
                button_style INT DEFAULT 1,
                button_emoji VARCHAR(64),
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, panel_name)
            );
            """,
            # Active Open/Closed Tickets tracking table
            """
            CREATE TABLE IF NOT EXISTS active_tickets (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                panel_id INT REFERENCES ticket_panels(id) ON DELETE CASCADE,
                channel_id BIGINT NOT NULL UNIQUE,
                user_id BIGINT NOT NULL,
                ticket_number INT NOT NULL,
                claimed_by BIGINT,
                status VARCHAR(20) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                closed_by BIGINT
            );
            """,
            # Guild Sequential Ticket Number Counter table
            """
            CREATE TABLE IF NOT EXISTS guild_ticket_counters (
                guild_id BIGINT PRIMARY KEY,
                total_tickets INT DEFAULT 0
            );
            """,
            # User Music Taste & Listening History table
            """
            CREATE TABLE IF NOT EXISTS user_music_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT,
                track_title VARCHAR(255) NOT NULL,
                artist VARCHAR(255) NOT NULL,
                genre VARCHAR(100) DEFAULT 'general',
                source VARCHAR(50) DEFAULT 'bot',
                play_count INT DEFAULT 1,
                last_played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, track_title, artist)
            );
            """,
            # Guild Music & Autoplay Configuration table
            """
            CREATE TABLE IF NOT EXISTS guild_music_settings (
                guild_id BIGINT PRIMARY KEY,
                autoplay BOOLEAN DEFAULT FALSE,
                autoplay_mode VARCHAR(20) DEFAULT 'smart',
                default_volume INT DEFAULT 100,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # User Custom Playlists & Liked Songs table
            """
            CREATE TABLE IF NOT EXISTS user_playlists (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                playlist_name VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, playlist_name)
            );
            """,
            # User Playlist Tracks table
            """
            CREATE TABLE IF NOT EXISTS user_playlist_tracks (
                id SERIAL PRIMARY KEY,
                playlist_id INT REFERENCES user_playlists(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                author VARCHAR(255) NOT NULL,
                duration INT DEFAULT 0,
                url TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # User Playlist Tracks index on foreign key
            """
            CREATE INDEX IF NOT EXISTS idx_user_playlist_tracks_plid ON user_playlist_tracks(playlist_id);
            """,
            # Guild Member Warnings table
            """
            CREATE TABLE IF NOT EXISTS guild_warns (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                moderator_id BIGINT NOT NULL,
                reason TEXT DEFAULT 'No reason provided',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Guild AutoMod & Chat Guard configuration table
            """
            CREATE TABLE IF NOT EXISTS guild_automod (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                anti_spam BOOLEAN DEFAULT TRUE,
                spam_threshold INT DEFAULT 5,
                anti_mentions BOOLEAN DEFAULT TRUE,
                mention_threshold INT DEFAULT 4,
                anti_invites BOOLEAN DEFAULT TRUE,
                anti_badwords BOOLEAN DEFAULT FALSE,
                badwords_list TEXT DEFAULT '',
                anti_repeated BOOLEAN DEFAULT TRUE,
                anti_caps BOOLEAN DEFAULT FALSE,
                caps_threshold INT DEFAULT 70,
                action VARCHAR(32) DEFAULT 'delete',
                timeout_duration INT DEFAULT 60,
                exempt_roles TEXT DEFAULT '',
                exempt_channels TEXT DEFAULT '',
                log_channel_id BIGINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Guild Auto-Role table
            """
            CREATE TABLE IF NOT EXISTS guild_autoroles (
                guild_id BIGINT PRIMARY KEY,
                role_id BIGINT,
                human_role_id BIGINT,
                bot_role_id BIGINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            ALTER TABLE guild_autoroles ADD COLUMN IF NOT EXISTS human_role_id BIGINT;
            """,
            """
            ALTER TABLE guild_autoroles ADD COLUMN IF NOT EXISTS bot_role_id BIGINT;
            """,
            # Guild 24/7 Voice Stay Mode table
            """
            CREATE TABLE IF NOT EXISTS guild_music_247 (
                guild_id BIGINT PRIMARY KEY,
                is_247 BOOLEAN DEFAULT FALSE
            );
            """,
            # Guild Ghost-Ping Settings table
            """
            CREATE TABLE IF NOT EXISTS guild_ghostping_settings (
                guild_id BIGINT PRIMARY KEY,
                is_enabled BOOLEAN DEFAULT TRUE,
                channel_id BIGINT
            );
            """,
            # User AFK table
            """
            CREATE TABLE IF NOT EXISTS user_afk (
                user_id BIGINT,
                guild_id BIGINT,
                reason TEXT DEFAULT 'AFK',
                nickname_changed BOOLEAN DEFAULT FALSE,
                original_nickname VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            # Guild Server Snapshots for Disaster Recovery & Nuke Rollback
            """
            CREATE TABLE IF NOT EXISTS guild_server_snapshots (
                guild_id BIGINT PRIMARY KEY,
                snapshot_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by BIGINT
            );
            """,
            # Guild Anonymous Confession Settings
            """
            CREATE TABLE IF NOT EXISTS guild_confession_settings (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT,
                counter INT DEFAULT 0,
                is_enabled BOOLEAN DEFAULT TRUE
            );
            """,
            # User AFK Voice Mail & Notes Inbox
            """
            CREATE TABLE IF NOT EXISTS user_afk_notes (
                id SERIAL PRIMARY KEY,
                target_user_id BIGINT NOT NULL,
                sender_id BIGINT NOT NULL,
                sender_name VARCHAR(64) NOT NULL,
                guild_id BIGINT NOT NULL,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Guild Tech Intelligence Feed Configuration
            """
            CREATE TABLE IF NOT EXISTS guild_tech_news (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                categories TEXT DEFAULT 'all',
                thread_enabled BOOLEAN DEFAULT FALSE,
                mode VARCHAR(20) DEFAULT 'live',
                alert_role_id BIGINT,
                last_digest_date VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            ALTER TABLE guild_tech_news ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'live';
            """,
            """
            ALTER TABLE guild_tech_news ADD COLUMN IF NOT EXISTS alert_role_id BIGINT;
            """,
            """
            ALTER TABLE guild_tech_news ADD COLUMN IF NOT EXISTS last_digest_date VARCHAR(10);
            """,
            # Dispatched Tech Intelligence Articles Registry for Deduplication
            """
            CREATE TABLE IF NOT EXISTS tech_news_history (
                article_hash VARCHAR(64) PRIMARY KEY,
                source VARCHAR(32) NOT NULL,
                category VARCHAR(32) NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                is_critical BOOLEAN DEFAULT FALSE,
                dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            ALTER TABLE tech_news_history ADD COLUMN IF NOT EXISTS is_critical BOOLEAN DEFAULT FALSE;
            """,
            """
            ALTER TABLE tech_news_history ADD COLUMN IF NOT EXISTS title_hash VARCHAR(64);
            """,
            """
            ALTER TABLE tech_news_history ADD COLUMN IF NOT EXISTS entity_hash VARCHAR(64);
            """,
            # Guild Developer Opportunities Feed Configuration
            """
            CREATE TABLE IF NOT EXISTS guild_dev_pulse (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                categories TEXT DEFAULT 'all',
                thread_enabled BOOLEAN DEFAULT FALSE,
                mode VARCHAR(20) DEFAULT 'live',
                alert_role_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Dispatched Developer Opportunities Registry for Deduplication
            """
            CREATE TABLE IF NOT EXISTS dev_pulse_history (
                item_hash VARCHAR(64) PRIMARY KEY,
                source VARCHAR(32) NOT NULL,
                category VARCHAR(32) NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                title_hash VARCHAR(64),
                entity_hash VARCHAR(64),
                dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            ALTER TABLE dev_pulse_history ADD COLUMN IF NOT EXISTS title_hash VARCHAR(64);
            """,
            """
            ALTER TABLE dev_pulse_history ADD COLUMN IF NOT EXISTS entity_hash VARCHAR(64);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tech_news_title_hash ON tech_news_history(title_hash);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tech_news_entity_hash ON tech_news_history(entity_hash);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_dev_pulse_title_hash ON dev_pulse_history(title_hash);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_dev_pulse_entity_hash ON dev_pulse_history(entity_hash);
            """,
            """
            ALTER TABLE guild_tech_news ADD COLUMN IF NOT EXISTS cadence VARCHAR(32) DEFAULT 'hourly';
            """,
            """
            ALTER TABLE guild_tech_news ADD COLUMN IF NOT EXISTS last_dispatch_ts TIMESTAMP;
            """,
            """
            ALTER TABLE guild_dev_pulse ADD COLUMN IF NOT EXISTS cadence VARCHAR(32) DEFAULT 'hourly';
            """,
            """
            ALTER TABLE guild_dev_pulse ADD COLUMN IF NOT EXISTS last_dispatch_ts TIMESTAMP;
            """,
            # Community Projects Showcase Registry
            """
            CREATE TABLE IF NOT EXISTS community_projects (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                title VARCHAR(120) NOT NULL,
                description TEXT NOT NULL,
                demo_url TEXT NOT NULL,
                image_url TEXT,
                message_id BIGINT,
                channel_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_project_upvotes (
                project_id INT REFERENCES community_projects(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_id, user_id)
            );
            """,
            # Real-Time Cloud Infrastructure Outages Tracking Registry for Self-Healing Embeds
            """
            CREATE TABLE IF NOT EXISTS active_tech_incidents (
                incident_id VARCHAR(64) NOT NULL,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                provider VARCHAR(32) NOT NULL,
                title TEXT NOT NULL,
                status VARCHAR(32) NOT NULL,
                impact VARCHAR(32) DEFAULT 'minor',
                url TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (incident_id, guild_id)
            );
            """,
            # Critical Zero-Day CVEs and Supply Chain Threat Alerts Registry
            """
            CREATE TABLE IF NOT EXISTS tech_cve_history (
                cve_id VARCHAR(64) PRIMARY KEY,
                title TEXT NOT NULL,
                severity VARCHAR(32) NOT NULL,
                cvss_score FLOAT DEFAULT 9.0,
                affected_package VARCHAR(120),
                dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Major Runtimes and Frameworks Release Radar Registry
            """
            CREATE TABLE IF NOT EXISTS tech_releases_history (
                release_id VARCHAR(120) PRIMARY KEY,
                project VARCHAR(64) NOT NULL,
                tag_name VARCHAR(64) NOT NULL,
                dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Dynamic Temp Voice Channels Configuration
            """
            CREATE TABLE IF NOT EXISTS guild_temp_voice_settings (
                guild_id BIGINT PRIMARY KEY,
                category_id BIGINT NOT NULL,
                master_channel_id BIGINT NOT NULL,
                interface_channel_id BIGINT,
                interface_message_id BIGINT,
                default_name_format VARCHAR(100) DEFAULT '{user}''s Room',
                default_user_limit INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            ALTER TABLE guild_temp_voice_settings ADD COLUMN IF NOT EXISTS interface_channel_id BIGINT;
            """,
            """
            ALTER TABLE guild_temp_voice_settings ADD COLUMN IF NOT EXISTS interface_message_id BIGINT;
            """,
            # Active Temp Voice Channels Tracking for Persistence & Cleanup
            """
            CREATE TABLE IF NOT EXISTS active_temp_voice_channels (
                channel_id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                owner_id BIGINT NOT NULL,
                control_message_id BIGINT,
                is_locked BOOLEAN DEFAULT FALSE,
                is_hidden BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Sticky Messages Configuration & State
            """
            CREATE TABLE IF NOT EXISTS guild_sticky_messages (
                channel_id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                content TEXT NOT NULL,
                embed_title VARCHAR(256),
                embed_color VARCHAR(16),
                last_message_id BIGINT,
                is_enabled BOOLEAN DEFAULT TRUE,
                created_by BIGINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Reaction Flag Translator Configuration
            """
            CREATE TABLE IF NOT EXISTS guild_translator_settings (
                guild_id BIGINT PRIMARY KEY,
                is_enabled BOOLEAN DEFAULT TRUE,
                reaction_enabled BOOLEAN DEFAULT TRUE,
                target_mode VARCHAR(16) DEFAULT 'ephemeral',
                disabled_channels BIGINT[] DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Dynamic Role Shortcuts Configuration
            """
            CREATE TABLE IF NOT EXISTS guild_role_shortcuts (
                guild_id BIGINT NOT NULL,
                shortcut_name VARCHAR(64) NOT NULL,
                role_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, shortcut_name)
            );
            """,
            # Antinuke Core Settings table
            """
            CREATE TABLE IF NOT EXISTS antinuke_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                log_channel_id BIGINT,
                punishment VARCHAR(20) DEFAULT 'strip_roles',
                vanity_protection BOOLEAN DEFAULT TRUE,
                everyone_protection BOOLEAN DEFAULT TRUE,
                role_protection BOOLEAN DEFAULT TRUE,
                channel_protection BOOLEAN DEFAULT TRUE,
                ban_protection BOOLEAN DEFAULT TRUE,
                kick_protection BOOLEAN DEFAULT TRUE,
                bot_protection BOOLEAN DEFAULT TRUE,
                webhook_protection BOOLEAN DEFAULT TRUE,
                prune_protection BOOLEAN DEFAULT TRUE,
                automod_protection BOOLEAN DEFAULT TRUE,
                integration_protection BOOLEAN DEFAULT TRUE,
                emoji_protection BOOLEAN DEFAULT TRUE,
                guild_update_protection BOOLEAN DEFAULT TRUE,
                channel_create_protection BOOLEAN DEFAULT TRUE,
                channel_delete_protection BOOLEAN DEFAULT TRUE,
                channel_update_protection BOOLEAN DEFAULT TRUE,
                role_create_protection BOOLEAN DEFAULT TRUE,
                role_delete_protection BOOLEAN DEFAULT TRUE,
                role_update_protection BOOLEAN DEFAULT TRUE,
                webhook_create_protection BOOLEAN DEFAULT TRUE,
                webhook_delete_protection BOOLEAN DEFAULT TRUE,
                member_role_protection BOOLEAN DEFAULT TRUE,
                sticker_protection BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Migrations for existing antinuke_settings table
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS channel_create_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS channel_delete_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS channel_update_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS role_create_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS role_delete_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS role_update_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS webhook_create_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS webhook_delete_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS member_role_protection BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE antinuke_settings ADD COLUMN IF NOT EXISTS sticker_protection BOOLEAN DEFAULT TRUE;",
            # Antinuke Whitelist and Extra Owners table
            """
            CREATE TABLE IF NOT EXISTS antinuke_whitelist (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                is_extra_owner BOOLEAN DEFAULT FALSE,
                is_full BOOLEAN DEFAULT TRUE,
                scope TEXT DEFAULT '',
                added_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            );
            """,
            # Antinuke Role Whitelist table (any member holding a whitelisted role is immune)
            """
            CREATE TABLE IF NOT EXISTS antinuke_role_whitelist (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                is_full BOOLEAN DEFAULT TRUE,
                scope TEXT DEFAULT '',
                added_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, role_id)
            );
            """,
            # Antinuke Incident & Attack History table
            """
            CREATE TABLE IF NOT EXISTS antinuke_incident_logs (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                action VARCHAR(100) NOT NULL,
                perpetrator_id BIGINT NOT NULL,
                perpetrator_tag VARCHAR(100) NOT NULL,
                punishment VARCHAR(50) NOT NULL,
                mitigation TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_antinuke_incident_logs_guild ON antinuke_incident_logs(guild_id, created_at DESC);",
            # Guild Media-Only Channels table
            """
            CREATE TABLE IF NOT EXISTS guild_media_channels (
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, channel_id)
            );
            """,
            # Giveaways Management tables
            """
            CREATE TABLE IF NOT EXISTS giveaways (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL UNIQUE,
                host_id BIGINT NOT NULL,
                prize VARCHAR(255) NOT NULL,
                winner_count INT DEFAULT 1,
                ends_at TIMESTAMP NOT NULL,
                required_role_id BIGINT,
                is_ended BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS giveaway_participants (
                giveaway_id INT NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (giveaway_id, user_id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_giveaways_active ON giveaways(guild_id, is_ended, ends_at);",
            # Owner security audit trail; contains IDs/actions only, never credentials.
            "CREATE TABLE IF NOT EXISTS kyoka_audit_log (id BIGSERIAL PRIMARY KEY, actor_id BIGINT NOT NULL, action VARCHAR(80) NOT NULL, target_id BIGINT, occurred_at TIMESTAMPTZ NOT NULL, outcome VARCHAR(24) NOT NULL, details VARCHAR(500) DEFAULT '')",
            "CREATE INDEX IF NOT EXISTS idx_kyoka_audit_recent ON kyoka_audit_log(occurred_at DESC)",
            # Premium lifecycle history.
            "CREATE TABLE IF NOT EXISTS kyoka_premium_history (id BIGSERIAL PRIMARY KEY, scope VARCHAR(16) NOT NULL, target_id BIGINT NOT NULL, tier VARCHAR(16) NOT NULL, action VARCHAR(24) NOT NULL, actor_id BIGINT NOT NULL, expires_at TIMESTAMPTZ, note VARCHAR(500) DEFAULT '', occurred_at TIMESTAMPTZ NOT NULL)",
            "ALTER TABLE guild_premium ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active'",
            "ALTER TABLE guild_premium ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE guild_premium ADD COLUMN IF NOT EXISTS activated_by BIGINT",
            "ALTER TABLE user_premium ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active'",
            "ALTER TABLE user_premium ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE user_premium ADD COLUMN IF NOT EXISTS activated_by BIGINT",
            # Reaction roles bindings (Carl-bot & Dyno style)
            """
            CREATE TABLE IF NOT EXISTS reaction_roles (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                emoji VARCHAR(100) NOT NULL,
                role_id BIGINT NOT NULL,
                mode VARCHAR(20) DEFAULT 'normal',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_rr_msg_emoji UNIQUE (message_id, emoji)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_rr_msg ON reaction_roles (message_id);",
            "CREATE INDEX IF NOT EXISTS idx_rr_guild ON reaction_roles (guild_id);",
            # KYOKA 3.0 Giveaway Schema Extensions
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS is_paused BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS is_cancelled BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS remaining_seconds_when_paused INT;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS claim_deadline_seconds INT DEFAULT 0;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS auto_reroll_unclaimed BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS entry_limit INT DEFAULT 0;",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS embed_color VARCHAR(10) DEFAULT '';",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS thumbnail_url TEXT DEFAULT '';",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS bonus_stacking_policy VARCHAR(20) DEFAULT 'highest';",
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS bonus_multiplier_cap DOUBLE PRECISION DEFAULT 10.0;",
            # KYOKA 3.0 Giveaway Participant Extensions
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS base_entries INT DEFAULT 1;",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS bonus_entries INT DEFAULT 0;",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS effective_weight DOUBLE PRECISION DEFAULT 1.0;",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS qualifying_roles TEXT DEFAULT '';",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS bonus_breakdown TEXT DEFAULT '';",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS exclusion_reason TEXT DEFAULT '';",
            "ALTER TABLE giveaway_participants ADD COLUMN IF NOT EXISTS excluded_by BIGINT;",
            # KYOKA 3.0 Giveaway Requirements
            """
            CREATE TABLE IF NOT EXISTS giveaway_requirements (
                id SERIAL PRIMARY KEY,
                giveaway_id INT REFERENCES giveaways(id) ON DELETE CASCADE,
                guild_id BIGINT NOT NULL,
                req_type VARCHAR(32) NOT NULL,
                req_value TEXT NOT NULL,
                channel_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_gw_reqs ON giveaway_requirements(giveaway_id);",
            "CREATE INDEX IF NOT EXISTS idx_gw_reqs_guild ON giveaway_requirements(guild_id);",
            # KYOKA 3.0 Giveaway Bonus Roles
            """
            CREATE TABLE IF NOT EXISTS giveaway_bonus_roles (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                giveaway_id INT REFERENCES giveaways(id) ON DELETE CASCADE,
                role_id BIGINT NOT NULL,
                multiplier DOUBLE PRECISION DEFAULT 1.0,
                extra_entries INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_gw_bonus ON giveaway_bonus_roles(giveaway_id);",
            "CREATE INDEX IF NOT EXISTS idx_gw_bonus_guild ON giveaway_bonus_roles(guild_id);",
            # KYOKA 3.0 Giveaway Winners & Claims
            """
            CREATE TABLE IF NOT EXISTS giveaway_winners (
                id SERIAL PRIMARY KEY,
                giveaway_id INT NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                claim_deadline TIMESTAMP,
                is_claimed BOOLEAN DEFAULT FALSE,
                claimed_at TIMESTAMP,
                is_rerolled BOOLEAN DEFAULT FALSE,
                rerolled_at TIMESTAMP,
                reroll_user_id BIGINT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_gw_winners ON giveaway_winners(giveaway_id);",
            # KYOKA 3.0 Giveaway Templates
            """
            CREATE TABLE IF NOT EXISTS giveaway_templates (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name VARCHAR(64) NOT NULL,
                prize VARCHAR(255) NOT NULL,
                description TEXT DEFAULT '',
                winner_count INT DEFAULT 1,
                duration_seconds INT DEFAULT 86400,
                requirements_json TEXT DEFAULT '{}',
                bonus_roles_json TEXT DEFAULT '{}',
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_gw_tpl UNIQUE (guild_id, name)
            );
            """,
            # KYOKA 3.0 Giveaway & Config Audit Log
            """
            CREATE TABLE IF NOT EXISTS giveaway_audit_log (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                giveaway_id INT,
                actor_id BIGINT NOT NULL,
                action VARCHAR(64) NOT NULL,
                details TEXT DEFAULT '',
                occurred_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_gw_audit_guild ON giveaway_audit_log(guild_id, occurred_at DESC);",
            # KYOKA 3.0 Server Giveaway & Config
            """
            CREATE TABLE IF NOT EXISTS server_giveaway_config (
                guild_id BIGINT PRIMARY KEY,
                manager_role_id BIGINT,
                giveaway_channel_id BIGINT,
                log_channel_id BIGINT,
                winner_role_id BIGINT,
                embed_color VARCHAR(10) DEFAULT '#7C3AED',
                ping_role_id BIGINT,
                notify_on_start BOOLEAN DEFAULT TRUE,
                notify_on_end BOOLEAN DEFAULT TRUE,
                reminder_intervals TEXT DEFAULT '1h,15m',
                activity_tracking_enabled BOOLEAN DEFAULT TRUE,
                activity_cooldown_seconds INT DEFAULT 5,
                activity_excluded_channels TEXT DEFAULT '',
                activity_min_length INT DEFAULT 3,
                tag_requirement_enabled BOOLEAN DEFAULT FALSE,
                tag_requirement_text VARCHAR(32) DEFAULT '',
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # KYOKA 3.0 Member Activity Tracking
            """
            CREATE TABLE IF NOT EXISTS member_activity (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                message_date DATE NOT NULL,
                message_count INT DEFAULT 1,
                last_message_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id, message_date)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_member_act_date ON member_activity(guild_id, message_date);",
            "CREATE INDEX IF NOT EXISTS idx_member_act_user ON member_activity(guild_id, user_id);",
            """
            CREATE TABLE IF NOT EXISTS member_activity_channel (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_date DATE NOT NULL,
                message_count INT DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, channel_id, message_date)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_member_act_chan ON member_activity_channel(guild_id, channel_id, message_date);",
            # KYOKA 3.0 Multi-Personality AI Config
            """
            CREATE TABLE IF NOT EXISTS kyoka_ai_configs (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                channel_id BIGINT,
                personality VARCHAR(64) DEFAULT 'aizen',
                tone VARCHAR(64) DEFAULT 'composed',
                humor VARCHAR(64) DEFAULT 'dry',
                language VARCHAR(32) DEFAULT 'English',
                response_length VARCHAR(32) DEFAULT 'balanced',
                purpose TEXT DEFAULT 'Server assistant and guide',
                custom_rules TEXT DEFAULT '',
                faqs TEXT DEFAULT '',
                respond_mode VARCHAR(32) DEFAULT 'mentions_and_replies',
                allowed_channels TEXT DEFAULT '',
                excluded_channels TEXT DEFAULT '',
                cooldown_seconds INT DEFAULT 4,
                custom_system_prompt TEXT DEFAULT '',
                updated_by BIGINT,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # KYOKA 3.0 User Privacy Preferences
            """
            CREATE TABLE IF NOT EXISTS user_privacy_preferences (
                user_id BIGINT PRIMARY KEY,
                opt_out_activity BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # KYOKA 3.0 No-Prefix Authorization Registry
            """
            CREATE TABLE IF NOT EXISTS system_no_prefix (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # KYOKA 3.0 Enhanced Verification System Schemas
            """
            CREATE TABLE IF NOT EXISTS kyoka_verification_settings (
                guild_id BIGINT PRIMARY KEY,
                role_id BIGINT NOT NULL,
                unverified_role_id BIGINT,
                channel_id BIGINT,
                log_channel_id BIGINT,
                method VARCHAR(32) DEFAULT 'button',
                enabled BOOLEAN DEFAULT TRUE,
                timeout_seconds INT DEFAULT 300,
                max_retries INT DEFAULT 3,
                min_account_age_days INT DEFAULT 0,
                panel_message_id BIGINT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS unverified_role_id BIGINT;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS channel_id BIGINT;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS log_channel_id BIGINT;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS method VARCHAR(32) DEFAULT 'button';",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS timeout_seconds INT DEFAULT 300;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS max_retries INT DEFAULT 3;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS min_account_age_days INT DEFAULT 0;",
            "ALTER TABLE kyoka_verification_settings ADD COLUMN IF NOT EXISTS panel_message_id BIGINT;",
            """
            CREATE TABLE IF NOT EXISTS kyoka_verification_records (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                joined_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMPTZ,
                method VARCHAR(32) DEFAULT 'button',
                status VARCHAR(32) DEFAULT 'pending',
                failure_count INT DEFAULT 0,
                moderator_id BIGINT,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_v_records_guild ON kyoka_verification_records(guild_id, user_id);",
            "CREATE INDEX IF NOT EXISTS idx_v_records_status ON kyoka_verification_records(guild_id, status);",
            # KYOKA 3.0 Enhanced Ticket System Columns & Notes
            "ALTER TABLE active_tickets ADD COLUMN IF NOT EXISTS category VARCHAR(64) DEFAULT 'General Support';",
            "ALTER TABLE active_tickets ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'Normal';",
            "ALTER TABLE active_tickets ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT '';",
            "ALTER TABLE active_tickets ADD COLUMN IF NOT EXISTS close_reason TEXT DEFAULT '';",
            "ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS categories_json TEXT DEFAULT '[]';",
            "ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS faq_text TEXT DEFAULT '';",
            "ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS max_tickets_per_user INT DEFAULT 0;",
            # Custom Help Categories per Server
            """
            CREATE TABLE IF NOT EXISTS guild_custom_help_categories (
                guild_id BIGINT NOT NULL,
                category_name VARCHAR(64) NOT NULL,
                emoji VARCHAR(32) DEFAULT '📁',
                description VARCHAR(128) DEFAULT 'Custom server commands',
                commands TEXT[] DEFAULT '{}',
                priority INT DEFAULT 0,
                is_hidden BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (guild_id, category_name)
            );
            """,
            # Voice Welcome Configuration per Server
            """
            CREATE TABLE IF NOT EXISTS guild_voice_welcome_config (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                channel_id BIGINT,
                trigger VARCHAR(32) DEFAULT 'both',
                greeting_text TEXT DEFAULT 'Hi there! Thanks for joining {server}. Welcome to our community, {user}!',
                tts_provider VARCHAR(32) DEFAULT 'gtts',
                language VARCHAR(10) DEFAULT 'en',
                cooldown_seconds INT DEFAULT 10,
                queue_expiration_seconds INT DEFAULT 60,
                allow_bots BOOLEAN DEFAULT FALSE,
                defer_if_music_active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ticket_internal_notes (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                author_id BIGINT NOT NULL,
                note_text TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_ticket_notes_ch ON ticket_internal_notes(channel_id);",
            # KYOKA 3.0 Marriage & Romance System
            """
            CREATE TABLE IF NOT EXISTS user_marriages (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                spouse_id BIGINT NOT NULL,
                married_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_marriages_guild ON user_marriages(guild_id, user_id);",
            # KYOKA 3.0 Automatic AI Channel Configurations
            """
            CREATE TABLE IF NOT EXISTS ai_channel_configs (
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                persona VARCHAR(32) NOT NULL DEFAULT 'aigf',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                mention_only BOOLEAN NOT NULL DEFAULT FALSE,
                cooldown_seconds INT NOT NULL DEFAULT 3,
                send_gifs BOOLEAN NOT NULL DEFAULT TRUE,
                configured_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, channel_id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_ai_chan_cfg ON ai_channel_configs(channel_id, enabled);",
            # KYOKA 3.0 Community Suggestions Configuration & Submissions
            """
            CREATE TABLE IF NOT EXISTS guild_suggestions_settings (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                is_enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_suggestions (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                content TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                upvotes INT DEFAULT 0,
                downvotes INT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_suggestions_guild ON guild_suggestions(guild_id);",
        ]
        if not self.pool or self.pool._closed:
            await self._heal_pool()
        async with self.pool.acquire() as conn:
            for query in queries:
                await conn.execute(query)
        logger.info("PostgreSQL database schemas verified successfully.")

    def _convert_query(self, query: str) -> str:
        """Convert SQLite-specific query syntax to standard PostgreSQL."""
        converted = query
        if "INSERT OR IGNORE INTO" in converted:
            converted = converted.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            if "ON CONFLICT" not in converted:
                converted = converted.rstrip(";") + " ON CONFLICT DO NOTHING;"

        if "?" not in converted:
            return converted

        parts = converted.split("?")
        result = []
        for i, part in enumerate(parts[:-1]):
            result.append(part)
            result.append(f"${i + 1}")
        result.append(parts[-1])
        return "".join(result)

    async def execute(self, query: str, *args: Any) -> None:
        """Execute a query with automatic connection recovery and exponential retry."""
        pg_query = self._convert_query(query)
        delays = [0.2, 0.5, 1.5]
        for attempt, delay in enumerate(delays):
            try:
                if not self.pool or self.pool._closed:
                    await self._heal_pool()
                async with self.pool.acquire(timeout=10) as conn:
                    await conn.execute(pg_query, *args)
                return
            except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncio.TimeoutError, ConnectionResetError, OSError) as e:
                logger.warning(f"Database transient error on execute (attempt {attempt+1}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                await self._heal_pool()

        # Final attempt
        if not self.pool or self.pool._closed:
            await self._heal_pool()
        async with self.pool.acquire(timeout=10) as conn:
            await conn.execute(pg_query, *args)

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Fetch a single record with self-healing retry resilience."""
        pg_query = self._convert_query(query)
        delays = [0.2, 0.5, 1.5]
        for attempt, delay in enumerate(delays):
            try:
                if not self.pool or self.pool._closed:
                    await self._heal_pool()
                async with self.pool.acquire(timeout=10) as conn:
                    row = await conn.fetchrow(pg_query, *args)
                    return dict(row) if row else None
            except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncio.TimeoutError, ConnectionResetError, OSError) as e:
                logger.warning(f"Database transient error on fetch_one (attempt {attempt+1}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                await self._heal_pool()

        # Final attempt
        if not self.pool or self.pool._closed:
            await self._heal_pool()
        async with self.pool.acquire(timeout=10) as conn:
            row = await conn.fetchrow(pg_query, *args)
            return dict(row) if row else None

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch multiple records with self-healing retry resilience."""
        pg_query = self._convert_query(query)
        delays = [0.2, 0.5, 1.5]
        for attempt, delay in enumerate(delays):
            try:
                if not self.pool or self.pool._closed:
                    await self._heal_pool()
                async with self.pool.acquire(timeout=10) as conn:
                    rows = await conn.fetch(pg_query, *args)
                    return [dict(r) for r in rows]
            except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncio.TimeoutError, ConnectionResetError, OSError) as e:
                logger.warning(f"Database transient error on fetch_all (attempt {attempt+1}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                await self._heal_pool()

        # Final attempt
        if not self.pool or self.pool._closed:
            await self._heal_pool()
        async with self.pool.acquire(timeout=10) as conn:
            rows = await conn.fetch(pg_query, *args)
            return [dict(r) for r in rows]

    async def set_ai_channel(
        self,
        guild_id: int,
        channel_id: int,
        persona: str = "aigf",
        enabled: bool = True,
        mention_only: bool = False,
        cooldown_seconds: int = 3,
        send_gifs: bool = True,
        configured_by: int | None = None,
    ) -> None:
        """Upsert automatic AI channel configuration."""
        query = (
            "INSERT INTO ai_channel_configs "
            "(guild_id, channel_id, persona, enabled, mention_only, cooldown_seconds, send_gifs, configured_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT (guild_id, channel_id) DO UPDATE SET "
            "persona = EXCLUDED.persona, "
            "enabled = EXCLUDED.enabled, "
            "mention_only = EXCLUDED.mention_only, "
            "cooldown_seconds = EXCLUDED.cooldown_seconds, "
            "send_gifs = EXCLUDED.send_gifs, "
            "configured_by = EXCLUDED.configured_by;"
        )
        await self.execute(
            query,
            guild_id,
            channel_id,
            persona,
            enabled,
            mention_only,
            cooldown_seconds,
            send_gifs,
            configured_by,
        )

    async def get_ai_channel(self, guild_id: int, channel_id: int) -> dict[str, Any] | None:
        """Fetch automatic AI configuration for a specific channel."""
        return await self.fetch_one(
            "SELECT * FROM ai_channel_configs WHERE guild_id = ? AND channel_id = ?;",
            guild_id,
            channel_id,
        )

    async def get_all_ai_channels(self, guild_id: int | None = None) -> list[dict[str, Any]]:
        """Fetch all active automatic AI channel configurations."""
        if guild_id is not None:
            return await self.fetch_all(
                "SELECT * FROM ai_channel_configs WHERE guild_id = ? ORDER BY created_at DESC;",
                guild_id,
            )
        return await self.fetch_all("SELECT * FROM ai_channel_configs ORDER BY created_at DESC;")

    async def disable_ai_channel(self, guild_id: int, channel_id: int) -> None:
        """Disable automatic AI responses in a channel without deleting configuration."""
        await self.execute(
            "UPDATE ai_channel_configs SET enabled = FALSE WHERE guild_id = ? AND channel_id = ?;",
            guild_id,
            channel_id,
        )

    async def remove_ai_channel(self, guild_id: int, channel_id: int) -> None:
        """Permanently remove automatic AI channel configuration."""
        await self.execute(
            "DELETE FROM ai_channel_configs WHERE guild_id = ? AND channel_id = ?;",
            guild_id,
            channel_id,
        )

