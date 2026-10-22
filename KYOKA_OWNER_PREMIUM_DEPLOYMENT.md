# KYOKA owner security and premium deployment

## What changed

- The primary owner is the exact numeric Discord ID `1505515188991033409`; usernames, display names, roles, server ownership, and configured developer lists do not satisfy this check.
- Added centrally guarded prefix + slash owner controls. To avoid overwriting existing public/legacy commands, colliding operations are exposed as `owner-botinfo`, `owner-sync`, `owner-reload`, `owner-load`, and `owner-unload`. The existing prefix `sync` and code-mutating `reload`/`pull` commands now require the primary owner. The configured prefix remains `BOT_PREFIX` (this archive defaults to `?`; it is not changed to `+`).
- Added owner-only `premium` hybrid command group, persistent lifecycle history, audit records, safe DB health checks, extension allowlisting, and fail-closed centralized `PremiumService.has_premium(scope=..., target_id=...)`.
- Premium scopes are separate: `user` checks only `user_premium`; `server` checks only `guild_premium`. Existing premium tables are altered additively; existing rows are not dropped.
- Premium tiers currently represent entitlement levels only. No existing features are automatically advertised as paid benefits, and no payment processor or automatic payment verification is enabled.

## Deployment

1. Back up the PostgreSQL/Supabase database and current bot source.
2. Deploy the contents of this archive over the existing codebase, preserving your existing `.env` and platform configuration. Do not overwrite `.env` with `.env.example`.
3. Install dependencies using the project's existing deployment process (`pip install -r requirements.txt`).
4. Ensure `.env` has the existing required variables `BOT_TOKEN` (or `DISCORD_TOKEN`), `DATABASE_URL`, and the existing `BOT_PREFIX` value. Do not change the prefix unless intentionally changing it for the whole bot.
5. Optional restart behavior: `ALLOW_OWNER_RESTART=false` is the safe default. Set it to `true` only if the hosting process manager is configured to automatically restart an exited process. The existing bot supervisor loop recreates the bot after it closes; the host process itself is not forcibly terminated.
6. Start the bot normally. `PostgresDatabase.initialize_tables()` creates the audit/history tables and adds missing subscription status/update columns using additive `IF NOT EXISTS` migrations. Watch startup logs for migration or extension-load failures.
7. As the configured owner, run the existing prefix command `?sync` (or `?owner-sync`) to synchronize application commands globally. Replace `?` in these examples with the existing configured prefix if yours differs. Discord application-command propagation may take time.
8. Verify `/owner`, `/health`, `/database-status`, and `/premium info` as the owner. Test a non-owner account and confirm it receives a private denial.

## Owner command examples

- `?owner`
- `?owner-botinfo`, `?owner-sync`
- `?owner-reload general.botinfo`, `?owner-load general.avatar`, `?owner-unload general.avatar`
- `?maintenance on` / `?maintenance off`
- `?premium grant server 123456789012345678 premium 30d`
- `?premium grant user 123456789012345678 pro lifetime`
- `?premium extend server 123456789012345678 14d`
- `?premium check server 123456789012345678`
- `?premium revoke server 123456789012345678`

Duration syntax is a positive integer followed by `s`, `m`, `h`, `d`, or `w`, or `lifetime`. Only the owner can grant/revoke/extend. Manual grants are audited. Never paste tokens, database URLs, or credentials into commands or logs.

## Verification performed in this workspace

- `python -m compileall -q src tests` — passed.
- `python -m pytest -q` — 12 unit tests passed.
- The complete Discord bot integration/startup suite and a live PostgreSQL migration were not run here because the workspace runtime does not have the project's `discord.py` dependency or configured Discord/PostgreSQL credentials. Perform the deployment smoke tests above before production rollout.
