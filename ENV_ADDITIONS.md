# KYŌKA 3.0 optional integration settings

The repository's `.env.example` is a **template**, not a copy of a live `.env`: its token and database URL are placeholders. Do not deploy those placeholder values. Keep your deployment's existing `.env` and Lavalink values untouched; add these optional variables in your hosting provider's environment settings if you want the integrations enabled:

- `GEMINI_API_KEY` — enables actual Gemini responses for `?ai`, `?chat`, `?askai`, `?aizenai`, and automatic replies in a channel configured with `?aisetup #channel`.
- `GIPHY_API_KEY` — enables GIPHY GIF search; the bot validates returned HTTPS GIPHY URLs.
- `TENOR_API_KEY` — optional fallback GIF provider if GIPHY is not configured or returns no results.

The bot does not fabricate AI replies or GIF URLs when an integration is unavailable. Existing music/Lavalink source files and runtime configuration defaults were not rewritten as part of this update. The new host allowlist is managed by the primary owner (Discord ID `1505515188991033409`) with `?guesshostadd @member`, `?guesshostremove @member`, and `?guesshosts` in the relevant server.
