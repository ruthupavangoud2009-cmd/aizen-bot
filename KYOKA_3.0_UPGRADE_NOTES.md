# KYOKA 3.0 — Upgrade Notes and Deployment Guide

## What was changed in this package

- Preserved the existing Python/`discord.py` project, PostgreSQL/Supabase database layer, entry point (`src/main.py`), and existing cog/module layout.
- Set the release identity to **KYOKA 3.0** (`Config.VERSION = 3.0.0`).
- Centralized the privileged identity on Discord user ID **1505515188991033409** through `src/security/owner.py`.
- Removed hard-coded legacy developer bypasses from the developer permission manager and moderation purge check.
- The permission manager no longer imports application/team owners or grants privileges from legacy `system_developers` rows. Existing legacy rows remain in the database for safe compatibility but do not authorize anyone.
- Prevented the `on_ready` application-info lookup from replacing the configured owner with Discord application/team members.
- Updated the environment template and removed the old `DEVELOPER_IDS` configuration example.
- Standardized the requested public creator label to `zerox.exe8` in project text files.
- Kept the project's existing default command prefix (`?`) rather than silently changing prefix behavior.
- Kept optional AI/GIF environment variables optional; this package does not claim those integrations are live without provider credentials.

## Project inventory

- Discord library: `discord.py` (`discord.py[voice]` in `requirements.txt`).
- Entry point: `python -m src.main` (or `python src/main.py` from the project root).
- Database: PostgreSQL-compatible backend, commonly Supabase, accessed through `asyncpg`.
- Command implementation: `src/cogs/` (including moderation, ticket, music, developer, general, utility and community-related modules).
- Core configuration: `src/core/config.py`; environment template: `.env.example`.
- Existing persistent Premium service: `src/managers/premium_service.py`.
- Existing security owner helper: `src/security/owner.py`.
- Runtime requires a supported Python version compatible with installed `discord.py`, `asyncpg`, and the pinned/declared dependencies. Python 3.11+ is recommended; verify the VisiHost runtime image before upgrading it.

## VisiHost installation

1. Back up your current deployment files and PostgreSQL/Supabase database before replacing code.
2. Upload/extract the ZIP contents to the app directory. Do not upload `.venv`; use the host's Python environment.
3. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`, `CLIENT_ID`, and `DATABASE_URL`. Never paste a real token into public logs or commit it.
4. Install dependencies using the host's build/start setup: `python -m pip install -r requirements.txt`.
5. Set the start command to `python -m src.main` (unless your existing VisiHost panel already invokes `src/main.py`).
6. In Discord Developer Portal, enable **Server Members Intent** and **Message Content Intent** if the enabled features require them; enable Presence Intent only if a feature actually uses it.
7. Invite the bot with `bot` and `applications.commands` scopes. Grant only the permissions required by the features you intend to use (commonly View Channels, Send Messages, Embed Links, Read Message History, Manage Messages, Manage Channels, Manage Roles, Moderate Members, Kick Members, Ban Members, and Connect/Speak for music). Place the bot role above roles it must manage.
8. Start/restart the service and inspect logs for missing environment variables, PostgreSQL connection errors, failed extension loads, or Discord permission errors.
9. Slash command registration depends on the existing command sync configuration. Check `SYNC_COMMANDS_ON_STARTUP` and the existing sync command before enabling global sync on a large bot.

## Owner and Premium security

- The only bot-level owner/developer ID is `1505515188991033409`.
- Guild owners and administrators still have ordinary guild-management authority where commands explicitly check guild permissions; that is separate from bot-wide ownership.
- Legacy developer records are not authorization. Do not re-add a developer-ID environment variable or rely on usernames/roles for bot-owner checks.
- Premium grant/revoke commands are implemented in the existing owner system and use persistent database service methods. Confirm the database schema is up to date before using them.
- Shell, eval, SQL, reload and restart commands are high-impact. They remain intended for the primary owner only; protect the owner account and bot token carefully.

## Database backup and recovery

- Before deploying, create a PostgreSQL/Supabase backup using your provider's backup/export feature.
- Do not delete or recreate existing tables to apply this upgrade. Existing data is intentionally retained.
- If a deployment fails, stop the bot, restore the previous code package, and restore the database only if a migration or data change actually occurred.
- Keep backup files outside the public web root and never include credentials in the backup archive.

## Environment variables

Required:
- `DISCORD_TOKEN`: Discord bot token.
- `CLIENT_ID`: Discord application ID.
- `DATABASE_URL`: PostgreSQL connection URL.

Optional:
- `BOT_NAME` (defaults to KYOKA 3.0).
- `BOT_PREFIX` (defaults to the existing `?` prefix).
- `INVITE_URL`, `SUPPORT_URL`, `PORT`, `ENVIRONMENT`, `ALLOW_OWNER_RESTART`.
- `AIZEN_IMAGE_URL`, `GEMINI_API_KEY`, `TENOR_API_KEY`, `GIF_PROVIDER`.

The Gemini and GIF variables are templates for optional providers; they do not mean an external integration is configured or verified.

## Command reference

This is an index, not a guarantee that every command is available in every guild. The actual commands depend on which cogs load successfully and which Discord permissions are granted.

- Help and general information: use the bot's configured prefix followed by `help`, or `/help` if the slash command is synced.
- Prefix configuration and command synchronization: see the `src/cogs/admin/` cogs and existing setup documentation.
- Tickets: see `src/cogs/ticket/ticket_system.py` and `src/managers/ticket_manager.py`.
- Moderation: see `src/cogs/moderation/`.
- Music: see `src/cogs/music/`; voice playback also requires a compatible Lavalink/provider setup as defined by the existing project.
- Premium and bot-owner operations: see the owner-only commands in `src/cogs/developer/owner_system.py`.
- Server configuration and utility commands: see `src/cogs/utility/` and `src/cogs/general/`.

## Verification and test status

- Syntax compilation should be run with `python -m compileall -q src tests`.
- Run tests with `python -m pytest -q` after installing dependencies.
- The provided test suite could not be fully collected in the packaging environment because the environment does not have the `discord` package installed. This is an environment/dependency limitation, not a passing test result.
- No live Discord login, live slash sync, VisiHost deployment, Supabase connection, AI-provider request, GIF-provider request, or music stream was performed in this environment. Those integrations must be smoke-tested in your actual host after setting credentials.


## Follow-up update: number game and owner repeat-message utility

- `guessanumber` now permits members to make multiple distinct guesses; duplicate guesses are marked with a repeat reaction.
- A correct guess is serialized per channel to prevent concurrent winners, persisted as completed, announced in chat, and sent to the winner by DM when DMs are open.
- After a winner is announced, the bot attempts to deny `@everyone` the ability to send messages in that channel. The bot requires **Manage Channels** (and appropriate channel permissions); if it cannot lock the channel, it reports that limitation.
- `spam <count> <message>` and `spamcancel` are restricted to primary owner ID `1505515188991033409`. Count is limited to 1–100, sends are spaced by 0.8 seconds, mass mentions are blocked, and a running task can be cancelled. Tasks are cancelled when the cog unloads.
- The existing configured prefix is preserved. Use your server's configured prefix (examples below use `&`): `&guessanumber 1-1000`, `&spam 50 Hello everyone!`, and `&spamcancel`.
- Validation performed for this follow-up: Python source compilation passed. The full unittest suite could not be collected in this environment because `discord.py` is not installed; run tests after installing `requirements.txt` in the VisiHost environment. Live Discord permissions, DMs, and PostgreSQL behavior remain deployment checks.

## AI, GIF, and game additions

- Added `src/cogs/fun/ai_interactions.py`: optional Gemini conversation commands, persistent per-server AI-channel configuration, per-user bounded conversation history, cooldowns, GIPHY search with Tenor fallback, reaction GIFs, and owner-managed per-server number-game host allowlists.
- Existing fun interaction commands now attempt a real provider-backed GIF after their interaction message. They continue to work when no GIF provider is configured.
- Number-game starts now require the primary owner or a server allowlisted host; the secret is DM'd privately to the host and primary owner; low/high feedback uses `+` and `-`; winner handling no longer locks the entire channel; completed results are persisted when the result table is available.
- Added optional integration environment documentation in `ENV_ADDITIONS.md`. No real `.env` is bundled.
- The `.env.example` file documents optional `GEMINI_API_KEY`, `GIPHY_API_KEY`, and `TENOR_API_KEY` settings; placeholders must be replaced in the deployment environment.
