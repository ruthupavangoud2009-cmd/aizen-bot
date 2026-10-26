# KYOKA 3.0 Website & Dashboard Frontend

Modern, mobile-responsive, Aizen-inspired dark-purple frontend for the **KYOKA 3.0** Discord bot and server management dashboard.

## Features
- **Landing Page (`/`)**: Hero section, real aggregate live stats counter, platform features breakdown, and interactive command terminal.
- **Features (`/features.html`)**: Deep dive into Anti-Nuke, Modular Giveaways, Neural AI, 24/7 Audio, Voice Greetings, and Member Gate.
- **Commands (`/commands.html`)**: Interactive, live-searchable, and category-filtered inventory of official 50 slash commands + legacy cogs with 1-click syntax copying.
- **Support (`/support.html`)**: Community support links, Anti-Nuke role hierarchy checklist, and FAQs.
- **Dashboard (`/dashboard.html`)**: Discord OAuth2 server selector (filtering servers where the user has `MANAGE_GUILD` or `ADMINISTRATOR`) and multi-tab live settings configurator with unsaved changes tracking.

---

## Deployment to Cloudflare Pages (100% Free)

Cloudflare Pages provides free static hosting with zero maintenance, global edge CDN, and unlimited bandwidth.

### Step 1: Connect GitHub Repository
1. Log into your [Cloudflare Dashboard](https://dash.cloudflare.com/) and go to **Workers & Pages** > **Create application** > **Pages** > **Connect to Git**.
2. Select your repository: `https://github.com/ruthupavangoud2009-cmd/aizen-bot`.
3. Choose the branch: `main`.

### Step 2: Configure Build Settings
Fill in the build configuration:
- **Framework preset**: `None`
- **Build command**: Leave completely empty (no build step required for static HTML/CSS/JS)
- **Build output directory**: `website`
- **Root directory**: `/` (or leave default)

### Step 3: Environment Variables (Optional)
If your backend API is hosted at a separate domain (e.g., `https://kyoka-api.onrender.com`), you can add a script tag or variable in `index.html` / `dashboard.html` or set:
- If hosted together with backend reverse proxy: `/api` works automatically without configuration.
- If decoupled across domains: configure `window.KYOKA_API_BASE = 'https://your-api-url.com/api'` in the HTML `<head>`.

### Step 4: Click "Save and Deploy"
Cloudflare Pages will publish your site in seconds at `https://<project-name>.pages.dev` with free SSL and edge delivery.
