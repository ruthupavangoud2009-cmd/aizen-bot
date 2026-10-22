# KYOKA 3.0 — Aizen-themed Discord bot

<div align="center">
  <img src="./assets/branding/kyoka_banner.webp" alt="KYOKA Banner" width="100%" style="border-radius: 10px; margin-bottom: 20px;" />

  <h3>Made by Aizen</h3>
  <p>KYOKA 3.0 keeps communities safe, premium-aware, and stylish with a dark-violet Aizen aesthetic.</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
    <img src="https://img.shields.io/badge/discord.py-2.7+-5865F2?style=for-the-badge&logo=discord&logoColor=white" />
    <img src="https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" />
    <img src="https://img.shields.io/badge/Deployment-Render%20Cloud-46E3B7?style=for-the-badge&logo=render&logoColor=white" />
    <img src="https://img.shields.io/badge/UI-Components%20V2%20(Type%2017)-FF73FA?style=for-the-badge" />
  </p>
</div>

---

## 📖 Overview

**KYOKA 3.0** is the active Aizen-themed Discord bot project in this repository. It preserves the existing command set, adds public help separation and owner-only checks, and keeps compatibility with the current Discord.py and PostgreSQL-based deployment model.

The bot includes a modular command structure, support and verification flows, Aizen-branding, member welcome cards, premium entitlement logic, ticket flows, and performance monitoring while keeping public commands visible and owner-only commands hidden from public help.

---

## 🏛️ System Architecture

```text
                       ┌─────────────────────────────────────────┐
                       │           Discord Gateway API           │
                       └────────────────────┬────────────────────┘
                                            │
                                  (Interaction/Message)
                                            ▼
                       ┌─────────────────────────────────────────┐
                       │         Kyoka Async Core Client         │
                       └──────────────┬───────────────────┬──────┘
                                      │                   │
                     (0ms Memory Read)│                   │(Atomic Write)
                                      ▼                   ▼
                       ┌─────────────────────────┐  ┌─────────────────────────┐
                       │  In-Memory Fast Caches  │  │  Supabase PostgreSQL    │
                       │  • Guild Prefixes       │  │  • Connection Pool      │
                       │  • Active Subscriptions │  │  • Persistent Schemas   │
                       │  • System Maintenance   │  │  • Customer Analytics   │
                       │  • Global Blacklists    │  │  • Audit Logs           │
                       └─────────────────────────┘  └─────────────────────────┘
                                      │
                                      ▼
                       ┌─────────────────────────────────────────┐
                       │    Components V2 REST Dispatcher        │
                       │    (Type 17 Container Layout Cards)     │
                       └─────────────────────────────────────────┘
```

### ⚡ 1. Hybrid 0ms In-Memory Caching
- Critical configurations (Guild Prefixes, Developer IDs, Maintenance State, Blacklists, and Subscriptions) are preloaded into memory upon startup.
- Message processing reads from RAM cache directly (`<0.001ms`), bypassing database round-trips entirely.
- Write operations atomically update both the PostgreSQL database pool and the in-memory cache.

### 🎨 2. Native Discord Components V2 Containers (Type 17)
- Replaces outdated, noisy Discord Embeds with native **Components V2 Containers**.
- Structured Text Displays, Section Rows, dynamic Separators, and integrated Action Rows.
- Zero standard unicode emoji spam — dynamically uses custom **Application Emojis** cached directly from the Discord Developer Portal.

### 🌐 3. 24/7 Cloud Resilience (Render Web Service)
- Integrated `aiohttp` HTTP health server running on port `8080`.
- Provides an active `/health` endpoint for continuous zero-downtime monitoring on Render.com, Railway, or VPS.

---

## 📂 Project Structure

```text
Kyoka/
├── .env                  # Secrets, Bot Token & Supabase Database URL
├── .env.example          # Environment configuration template
├── render.yaml           # 1-Click Render Cloud Deployment Blueprint
├── requirements.txt      # Python dependencies
├── README.md             # Bot overview & documentation
├── PROJECT_CONTEXT.md    # Exhaustive Technical Specification for AI & Developers
│
├── assets/               # Branding assets & custom application emojis
│   ├── branding/
│   │   ├── kyoka_banner.webp
│   │   └── kyoka_icon.webp
│   ├── emoji/
│   ├── emoji2/
│   └── music/
│
└── src/
    ├── main.py           # Application bootstrap & lifecycle manager
    │
    ├── core/             # Core Engine & HTTP Server
    │   ├── bot.py        # KyokaBot custom client with setup hooks
    │   ├── config.py     # Environment variable validator & constants
    │   ├── context.py    # CustomContext with container dispatcher methods
    │   └── server.py     # 24/7 aiohttp Keep-Alive Health Server
    │
    ├── database/         # Database Persistence Layer
    │   ├── base.py       # Abstract database protocol
    │   └── postgres.py   # asyncpg Supabase PostgreSQL pool & table schemas
    │
    ├── managers/         # Domain Logic & In-Memory Cache Engines
    │   ├── blacklist_manager.py   # Global user and guild blacklist filter
    │   ├── guild_manager.py       # Custom per-guild prefix caching
    │   ├── log_manager.py         # Multi-channel audit logging settings
    │   ├── permission_manager.py  # Bot owner & developer access control
    │   ├── premium_manager.py     # Subscriptions, keys, and customer analytics
    │   └── system_manager.py      # Global maintenance mode & command toggles
    │
    ├── utils/            # Shared Utilities & Design System
    │   ├── containers.py # Discord Components V2 builder & REST dispatcher
    │   ├── decorators.py # @require_guild_premium() and @require_user_premium()
    │   ├── emojis.py     # Dynamic Custom Application Emoji registry
    │   ├── embeds.py     # Fallback legacy embed utilities
    │   ├── logger.py     # Colored console logger
    │   └── views.py      # Base interaction view utilities
    │
    ├── errors/           # Centralized Error Handling
    │   ├── exceptions.py # Domain custom exceptions
    │   └── handler.py    # Global on_command_error listener & error UI cards
    │
    └── cogs/             # Modular Feature Packages (Ready for custom expansion)
```

---

## 🚀 Getting Started & Local Setup

### 1. Prerequisites
- Python **3.11** or higher
- A PostgreSQL or Supabase database instance
- A Discord Bot Application from [Discord Developer Portal](https://discord.com/developers/applications)
- Required Discord intents: Guilds, Members, Message Content, Presences (as configured in the bot's `KyokaBot` client)

### 2. Installation
```bash
# Clone the repository
git clone <repository_url>
cd kyoka_extracted

# Create and activate virtual environment
python -m venv venv
# On Windows:
.
\venv\Scripts\activate
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
python -m pip install --no-cache-dir -r requirements.txt
```

### 3. Environment Variables
Create `.env` based on `.env.example`:
```env
BOT_TOKEN=your_discord_bot_token_here
DATABASE_URL=postgresql://postgres.xxxx:password@aws-0-region.pooler.supabase.com:6543/postgres
DEFAULT_PREFIX=?
ENVIRONMENT=DEVELOPMENT
PORT=8080
```

### 4. Run the Bot
```bash
python -m src.main
```

---

## ☁️ 24/7 Cloud Deployment (Render.com)

1. Link your GitHub repository to [Render.com](https://render.com).
2. Create a **Web Service** using `render.yaml`.
3. Set Build Command: `python -m pip install --no-cache-dir -r requirements.txt`.
4. Set Start Command: `python -m src.main`.
5. Add Environment Variables (`BOT_TOKEN`, `DATABASE_URL`, `DEVELOPER_IDS`, etc.).

Render will automatically deploy KYOKA alongside the built-in health server on port `8080` for continuous 24/7 operation.

---

## 🛡️ Ownership & Branding

- **Bot Name**: `KYOKA 3.0`
- **Creator**: `Aizen`
- **Primary Owner ID**: `1505515188991033409`
- **Support Server**: `https://discord.gg/5DBQTQJa9`
- **Framework**: `discord.py` with Components V2 cards
- **Database**: `PostgreSQL` / `Supabase` with `asyncpg`

---
<div align="center">
  <sub>Made by Aizen.</sub>
</div>

## KYOKA Verification Panel

Server administrators with **Manage Server** can run `/verify setup` and choose the role members receive after clicking **Verify Me**. The bot needs **Manage Roles**, and KYOKA's highest role must be above the configured verification role. Verification settings are stored in PostgreSQL in `kyoka_verification_settings` and the button remains available after restarts.

The server-join greeting thanks the server for inviting KYOKA and includes the support invite configured by `SUPPORT_URL` (defaults to `https://discord.gg/5DBQTQJa9`). Set `AIZEN_IMAGE_URL` in the deployment environment to use a preferred hosted Aizen-themed image URL. Prefix commands and existing slash commands are preserved; slash command availability still depends on the bot's application-command sync settings.
