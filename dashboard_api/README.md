# KYOKA 3.0 Dashboard API Backend

Secure, asynchronous Python backend API for the **KYOKA 3.0** Discord bot dashboard.

## Capabilities & Security Standards
- **Discord OAuth2**: Secure code exchange with timestamped HMAC state nonces to prevent CSRF.
- **Tamper-Proof Sessions**: Signed HTTP-only session cookies with configurable TTL.
- **Cross-Server Isolation**: Validates live Discord permissions on **every** sensitive settings read or write. Users cannot access or modify guilds they do not manage (`403 Forbidden`).
- **Database Reusability**: Directly reads from and writes to the existing Supabase / PostgreSQL schema defined in `src/database/postgres.py` using parameterized queries.
- **Rate Limiting**: In-memory sliding-window rate limiting per client IP to safeguard Discord API limits.
- **Security Headers**: HSTS, CSP, X-Frame-Options, X-Content-Type-Options.
- **Zero Shell / Eval Endpoints**: Strictly no arbitrary code execution or developer eval exposed via HTTP.

---

## Free-Tier Deployment Guide

You can deploy this backend API on free cloud platforms such as **[Render](https://render.com)**, **[Koyeb](https://koyeb.com)**, or **[Fly.io](https://fly.io)**.

### Deploying to Render (Free Web Service)

1. Sign up at [Render.com](https://render.com) and click **New > Web Service**.
2. Connect your GitHub repository: `https://github.com/ruthupavangoud2009-cmd/aizen-bot`.
3. Configure the service settings:
   - **Name**: `kyoka-dashboard-api`
   - **Region**: Closest to your database (e.g., Oregon or Frankfurt)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m dashboard_api.run`
   - **Instance Type**: `Free`
4. Add the following **Environment Variables** (see `.env.example`):
   - `CLIENT_ID`: Your Discord Application Client ID.
   - `CLIENT_SECRET`: Your Discord Application Client Secret.
   - `DISCORD_TOKEN`: Your Discord Bot Token.
   - `DISCORD_REDIRECT_URI`: `https://<your-render-app>.onrender.com/api/auth/callback` (or your custom domain).
   - `DASHBOARD_SECRET_KEY`: A random 32+ character string for HMAC signing.
   - `DATABASE_URL`: Your Supabase/PostgreSQL connection string.
   - `FRONTEND_ORIGIN`: Your Cloudflare Pages URL (e.g., `https://kyoka.pages.dev`) or `*`.
   - `ENVIRONMENT`: `production`
5. Click **Create Web Service**.

---

### Discord Developer Portal Configuration

1. Visit [Discord Developer Portal > Applications](https://discord.com/developers/applications).
2. Select your KYOKA application.
3. Navigate to **OAuth2 > General**.
4. In **Redirects**, add your callback URL:
   - For Production: `https://<your-backend-domain>/api/auth/callback`
   - For Local Testing: `http://localhost:8080/api/auth/callback`
5. Click **Save Changes**.

---

## Local Development & Testing

Run the dashboard server locally:
```bash
# Starts both the API and serves the website/ folder on port 8080:
python -m dashboard_api.run
```
Visit `http://localhost:8080` in your browser.

Run automated test suite:
```bash
pytest tests/test_dashboard_*.py -v
```
