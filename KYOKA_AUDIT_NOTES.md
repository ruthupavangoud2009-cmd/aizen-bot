# KYŌKA 3.0 — Integration and Verification Notes

## Included changes
- Gemini REST endpoint now uses `GEMINI_MODEL` instead of hardcoding a model. Default: `gemini-3.8-flash`.
- `?aistatus` continues to show integration status without revealing credentials. HTTP 404/400 errors now give model/request-specific guidance without printing the API key.
- Vouch and Bill cogs have explicit help categories and guild-only guards.
- Vouch submissions use a global five-minute per-user cooldown; repeated voucher/recipient pairs are held. Opening the held queue assigns unclaimed entries to the reviewer, and held-vouch deletion is limited to the assigned reviewer, a server administrator, or the primary owner.
- Friend-provided Lavalink deployment artifacts were added. The existing KYŌKA music cog and Lavalink client are unchanged because their source matched the donor ZIP.
- Removed the duplicate `discord.py[voice]` requirement entry.

## Required hosting configuration
Set these in the hosting provider's environment settings (do not commit real secrets):
- `DISCORD_TOKEN`
- `DATABASE_URL`
- `LAVALINK_URI` and `LAVALINK_PASSWORD` if using Lavalink
- `GEMINI_API_KEY` for AI
- `GEMINI_MODEL=gemini-3.8-flash` (override this if that model is not available to your key)
- `GIPHY_API_KEY` or `TENOR_API_KEY` for real GIF search

For local use, copy `.env.example` to `.env` and fill in your own credentials. Never upload or distribute the real `.env`.

## Verification performed
- Both uploaded ZIPs passed archive integrity checks.
- All Python source files passed `py_compile`.
- Static checks confirmed owner ID `1505515188991033409`, prefix-based game commands, guess reactions, owner-only spam authorization and five-second message deletion, vouch/bill categories, configurable Gemini model, and the donor music source match.
- The pytest suite could not collect in this environment because `discord.py` is not installed (`ModuleNotFoundError: discord`). No live Discord, PostgreSQL, Lavalink, GIF provider, or Gemini request was executed here. Those integrations still require deployment credentials and a runtime test.
