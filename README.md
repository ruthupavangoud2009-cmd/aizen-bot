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
ENVIRONMENT=PRODUCTION
PORT=8080

# (Optional) Cloudflare / Datacenter Outage Proxy
# DISCORD_PROXY=http://username:password@ip:port

# (Optional) Configurable Aizen Themed Artwork & GIF URLs
# KYOKA_BANNER_URL=https://assets.example.com/aizen_banner.webp
# KYOKA_HELP_GIF_URL=https://assets.example.com/aizen_help.gif
# KYOKA_WELCOME_IMAGE_URL=https://assets.example.com/aizen_welcome.webp
# KYOKA_LEVELUP_IMAGE_URL=https://assets.example.com/aizen_levelup.webp
# KYOKA_DEFAULT_THUMBNAIL_URL=https://assets.example.com/aizen_thumbnail.webp
# KYOKA_AIZEN_AVATAR_URL=https://assets.example.com/aizen_avatar.webp
```

### 4. Run the Bot
```bash
python -m src.main
```

### 5. Running Automated Tests
```bash
# Run the complete test suite (134 automated unit & integration tests)
pytest -v

# Run only the Aizen UI and design system tests
pytest tests/test_aizen_ui.py -v

# Run help command tests
pytest tests/test_help_module_repair.py -v
```

---

## 🎨 Aizen Visual Identity & UI Design System

KYOKA 3.0 features a centralized, modular Aizen design framework located in `src/utils/ui.py` and `src/core/config.py`:

- **Aizen Color Palette (`AizenPalette`)**:
  - `PRIMARY`: Midnight Royal Violet (`0x7C3AED` / `8141549`)
  - `DARK`: Void Black (`0x0D0B18`)
  - `ACCENT`: Soul Society Silver (`0xE2E8F0`)
  - `CRIMSON`: Bankai Crimson (`0xDC2626`)
  - `SUCCESS`: Emerald (`0x10B981`)
  - `WARNING`: Amber Gold (`0xF59E0B`)
  - `INFO`: Cyan Blue (`0x3B82F6`)
- **Configurable Asset Registry (`AizenAssets`)**:
  - Centralized in `src.core.config.AizenAssets` with graceful fallbacks.
  - Can be customized via environment variables (`KYOKA_BANNER_URL`, `KYOKA_HELP_GIF_URL`, etc.) without touching code.
- **Unified Embed Factory (`KyokaEmbed`)**:
  - Pre-styled embed builders: `standard()`, `success()`, `error()`, `warning()`, `info()`, `loading()`, and `denied()`.
  - Built-in ASCII visual progress bar generator: `KyokaEmbed.progress_bar(current, total, length=12)`.
- **Interactive Paginator (`KyokaPaginator`)**:
  - Author-isolated, multi-page component view with `First`, `Prev`, `Page Counter`, `Next`, `Last`, and `Close` buttons.
  - Automatically disables on interaction timeout (default 180 seconds).

---

## 🧩 Extending KYOKA: Adding Modules & Commands

### How to Add a New Cog / Module
1. Create your cog file in the appropriate directory under `src/cogs/` (e.g. `src/cogs/utility/my_feature.py`).
2. Subclass `commands.Cog`:
```python
import discord
from discord.ext import commands
from src.utils.ui import KyokaEmbed

class MyFeature(commands.Cog, name="Utility"):
    """Description for this module category in help."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mycommand", help="Description of what mycommand does.")
    async def my_command(self, ctx: commands.Context):
        embed = KyokaEmbed.success(
            title="Action Complete",
            description="Command executed smoothly under Aizen's will.",
            author=ctx.author
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(MyFeature(bot))
```
3. Load the extension in `src/core/bot.py` or `src/main.py`.

### Categorizing Commands in Help
The help system dynamically groups commands by their cog's `category` attribute or cog name:
- Set `category = "Moderation"` (or any of the 14 supported categories) on your cog class.
- The help dropdown will automatically register your new command with pagination, alias discovery, and modal search indexing.

---

## 🔧 Troubleshooting & Common Issues

| Issue / Error | Root Cause | Solution |
|---|---|---|
| **Cloudflare Rate Limit (HTTP 429)** | Render shared IP address is temporarily blocked by Discord Cloudflare edge. | Configure `DISCORD_PROXY=http://user:pass@ip:port` in `.env` using a clean datacenter proxy, or switch the Render service region (e.g., Frankfurt/Ohio). |
| **`audioop` Deprecation Warning** | Python 3.11 built-in warning for planned 3.13 deprecation. | Safe to ignore on Python 3.11/3.12. |
| **Opus Voice Not Loaded on Linux** | Missing native `libopus-dev` binary. | Handled automatically in `src/main.py` via dynamic library discovery (`libopus.so.0`). Ensure `apt-get install -y libopus-dev` if compiling custom containers. |
| **Interaction Failed / Ephemeral Timeout** | Operation took longer than 3 seconds without deferring. | Use `await interaction.response.defer(thinking=True)` for slow operations. |
| **Supabase Connection Limit** | Direct connection pool exhausted. | Use Supabase Transaction Pooler (port `6543`) in `DATABASE_URL` instead of direct session connection (port `5432`). |

---

## ☁️ 24/7 Cloud Deployment (Render.com)

1. Link your GitHub repository to [Render.com](https://render.com).
2. Create a **Web Service** using `render.yaml`.
3. Set Build Command: `python -m pip install --no-cache-dir -r requirements.txt`.
4. Set Start Command: `python -m src.main`.
5. Add Environment Variables (`BOT_TOKEN`, `DATABASE_URL`, `DEVELOPER_IDS`, etc.).

Render will automatically deploy KYOKA alongside the built-in health server on port `8080` for continuous 24/7 operation.

---

## 🎁 KYOKA 3.0 Advanced Giveaway Engine

KYOKA 3.0 introduces a state-of-the-art persistent giveaway engine comparable to Giveaway Boat, featuring:

- **Efraimidis-Spirakis Cryptographic Weighted Selection**: Mathematically sound $k_i = u_i^{1/w_i}$ sampling without memory expansion using Python's `secrets.SystemRandom`.
- **Dynamic Entry Multipliers**: Configurable role bonuses (`highest`, `additive`, `multiplicative` with configurable caps).
- **Persistent Anti-Race Entry Locks**: Asynchronous database transactions prevent double entries, retry spam, or race conditions.
- **Message Activity Requirements**: Calendar-based (today) or rolling-window (7 days) message minimums, channel-specific quotas, and account/membership age thresholds.
- **Server Tag Verification**: Leverages `discord.py 2.7` `member.primary_guild` clan tags with graceful fallback when clan tags are unsupported on a guild.
- **Giveaway Lifecycle Controls**: Pause, resume with duration preservation, early conclusion, cancellation, template saving, and reroll history.
- **Anti-Abuse & Privacy**: Rate limits, flood cooldowns, administrative exclusion logs, and member privacy controls (`/privacy`).
- **CSV Data Export**: Authorized giveaway audit reports with full entry weights, qualifying roles, and timestamps.

---

## 🤖 Multi-Personality AI Engine (Not Aizen-Only)

KYOKA 3.0 frees servers from hardcoded single-persona AI. Every server independently configures its AI channel, persona, tone, rules, and triggers via `/ai setup`.

### 10 Built-In Personality Presets:
1. `happy_boy`: Cheerful, positive, energetic boy personality with light humor.
2. `friendly_helper`: Warm, patient, highly structured community assistant.
3. `professional`: Direct, formal, concise business assistant.
4. `funny_sarcastic`: Witty, humorous, sarcastic responses while remaining helpful.
5. `calm_supportive`: Gentle, mindful, encouraging, and emotionally supportive.
6. `aizen`: The classic Kyoka preset — confident, philosophical, commanding, dramatic Bleach Aizen persona.
7. `cheerful_anime`: Enthusiastic anime companion with expressive phrasing and emojis.
8. `gaming_expert`: Specialized in gaming mechanics, Blox Fruits, meta builds, and leveling strategies.
9. `short_answer`: Ultra-concise, TL;DR answers strictly under 2 sentences.
10. `custom`: Server administrators specify their own custom prompt, tone, and guidelines.

Independent server isolation ensures configuring AI on Server A never affects Server B or Server C.

---

## ⚡ Exactly 50 Top-Level Slash Commands

KYOKA 3.0 structures its new slash interface into exactly 50 documented top-level commands across 4 groups and 10 standalone utility/admin commands:

### Giveaway Group (`/giveaway`) — 18 Subcommands
| Command | Description |
|---|---|
| `/giveaway create` | Create and publish a rich interactive giveaway with custom settings. |
| `/giveaway quick` | Launch a giveaway quickly using sensible default parameters. |
| `/giveaway end` | Conclude an active giveaway early and draw winners immediately. |
| `/giveaway cancel` | Cancel an active giveaway without drawing winners. |
| `/giveaway pause` | Pause entries and freeze the countdown on an active giveaway. |
| `/giveaway resume` | Resume a paused giveaway with preserved remaining duration. |
| `/giveaway reroll` | Draw replacement winners for unclaimed or ineligible prizes. |
| `/giveaway edit` | Update live giveaway settings (prize, winner count, description). |
| `/giveaway list` | Display active, scheduled, paused, and recent giveaways. |
| `/giveaway info` | Inspect in-depth giveaway configuration and current status. |
| `/giveaway entries` | View participant counts and authorized entry details. |
| `/giveaway check` | Pre-check a specific member's eligibility before or during a draw. |
| `/giveaway exclude` | Administratively exclude a user from winning with an audit reason. |
| `/giveaway include` | Restore an excluded user back to eligible status. |
| `/giveaway remind` | Broadcast a reminder ping about an ending giveaway. |
| `/giveaway clone` | Replicate an existing giveaway's configuration into a new one. |
| `/giveaway export` | Export complete participant weights and entry breakdown to CSV. |
| `/giveaway templates` | Save, list, load, or delete reusable giveaway templates. |

### Requirements Group (`/requirements`) — 8 Subcommands
| Command | Description |
|---|---|
| `/requirements add` | Attach custom eligibility requirements to a giveaway or server defaults. |
| `/requirements remove` | Remove a configured eligibility requirement by ID. |
| `/requirements list` | Review all configured requirements for a giveaway or server. |
| `/requirements test` | Test a member's eligibility against configured rules with full breakdown. |
| `/requirements activity` | Configure daily or 7-day message volume requirements. |
| `/requirements roles` | Configure required, permitted (any-of), or excluded roles. |
| `/requirements tag` | Configure server clan tag verification (with capability check). |
| `/requirements bonus` | Configure role-based bonus entries and multiplier stacking policies. |

### Configuration Group (`/config`) — 8 Subcommands
| Command | Description |
|---|---|
| `/config view` | Inspect complete server giveaway and activity configurations. |
| `/config channel` | Designate default giveaway and announcement channels. |
| `/config roles` | Set the custom giveaway manager role and staff bypasses. |
| `/config permissions` | Configure who can host or manage giveaways on this server. |
| `/config appearance` | Customize embed accent colors, branding images, and thumbnails. |
| `/config notifications` | Configure winner DMs, claim deadlines, and reminder intervals. |
| `/config activity` | Configure message activity tracking cooldowns and channel exclusions. |
| `/config reset` | Reset selected server configurations to factory defaults with confirmation. |

### AI Group (`/ai`) — 6 Subcommands
| Command | Description |
|---|---|
| `/ai setup` | Configure AI personality, channel, tone, and rules for this server. |
| `/ai personality` | Switch between the 10 built-in personality presets or define a custom style. |
| `/ai test` | Preview how the AI responds under current server settings. |
| `/ai reset` | Reset the server's AI configuration to default. |
| `/ai enable` | Activate AI conversational responses in configured channels. |
| `/ai disable` | Deactivate AI in specific channels or server-wide. |

### Utility & Administration — 10 Top-Level Commands
| Command | Description |
|---|---|
| `/help` | Interactive command guide and category documentation. |
| `/ping` | Real-time WebSocket latency, API heartbeat, and database response time. |
| `/botinfo` | Bot version, uptime, server count, and environment status. |
| `/serverinfo` | Server statistics, owner, creation date, and feature toggles. |
| `/userinfo` | Member details, join dates, roles, and avatar display. |
| `/activity` | View personal qualifying message counts (today & past 7 days). |
| `/leaderboard` | Server-wide message activity leaderboard. |
| `/auditlog` | Administrative audit trail for giveaway changes and exclusions. |
| `/diagnostics` | Deep system diagnostics: database pool, background tasks, and permissions. |
| `/privacy` | Data transparency, privacy information, opt-out, and right-to-be-forgotten erasure. |

*Note: All legacy `+` prefix commands (`+gstart`, `+gend`, `+greroll`, `+glist`, `+ai`, `+ping`, `+botinfo`, etc.) and existing Cogs remain 100% operational and backward-compatible.*

---

## 🎫 Premium Ticket System

KYOKA 3.0 provides an enterprise ticket management suite with custom visual panels and HTML transcripts:

- **Interactive Setup Wizard**: `+ticket setup` guides administrators through selecting a channel, naming, support roles, and category assignments.
- **Inside-Ticket Controls**: Persistent buttons for closing, claiming, and downloading transcripts directly in the channel.
- **Staff Commands**:
  - `+ticket claim` / `+ticket unclaim`: Claim or release a ticket.
  - `+ticket transfer <@staff>`: Hand off a ticket to another team member.
  - `+ticket add <@user>` / `+ticket remove <@user>`: Manage ticket participants dynamically.
  - `+ticket rename <new-name>`: Rename ticket channels seamlessly.
  - `+ticket priority <low|normal|high|urgent>`: Set priority levels.
  - `+ticket note <text>`: Record internal staff notes.
  - `+ticket close [reason]`: Safely archive ticket, DM user with HTML transcript, and log to ticket log channel.
  - `+ticket transcript`: Instant HTML transcript generation with attachments and participant timeline.
  - `+ticket stats`: Real-time server ticket volume and resolution analytics.

---

## 🛡️ Discord-Style Server Verification System

Real channel gatekeeping enforced through Discord role and permission hierarchies:

- **Joining Flow**: Automatically assigns the configured `unverified` role upon join, restricting new members from viewing regular channels until verified.
- **Verification Methods**:
  - `Button`: Instant human click verification.
  - `Rules`: Community rules agreement modal before granting access.
  - `Challenge`: Arithmetic / anti-bot challenge modal with rate limits.
- **Anti-Raid Protections**: Verification cooldowns, max retry limits, failure logging, and optional minimum account age thresholds.
- **Commands**:
  - `+verify setup <@verified_role> [@unverified_role] [#channel]`: Full guided setup.
  - `+verify panel`: Deploy persistent verification card and button view.
  - `+verify method <button|rules|challenge>`: Toggle verification challenges.
  - `+verify stats`: Real-time pass/fail metrics and completion rates.
  - `+verify user <@member>`: Staff manual verification bypass.
  - `+verify remove <@member>`: Re-isolate member back to unverified.

---

## 🏷️ Easy Reaction Roles System

Carl-bot & Dyno style reaction and button role portal:

- **Beginner Guided Setup**: `+rr setup #channel @Role "Button Label"` creates a clean toggle button role immediately.
- **Interactive Button Panels**: `+rr button #channel "Title" Label1=@Role1 Label2=@Role2`.
- **Classic Emoji Panels**: `+rr create #channel "Title" 🎮=@Gamers 💻=@Devs`.
- **Modes Supported**:
  - `Normal`: Toggle on / toggle off.
  - `Unique`: Radio button mode (only one role at a time; picking a new role strips the previous).
  - `Verify`: One-way permanent claim.
- **Management**: `+rr list`, `+rr remove <msg_id> <emoji>`, `+rr clear <msg_id>`.

---

## 🏓 Ping & Genuine Performance Diagnostics

KYOKA 3.0 reports real, transparent system performance:

- **Gateway Latency**: Measured directly from Discord WebSocket heartbeat (`bot.latency`).
- **Command Roundtrip**: Exact execution time taken to compute and dispatch the response.
- **Database Latency**: Fast, resilient `SELECT 1` ping with graceful offline detection.
- **System Uptime & Shard Tracking**: Continuous process uptime metrics.
- Usage: `+ping` or `/ping`.

---

## 📚 Complete Automatic Help System

- **Permission-Aware Filtering**: Members only see commands they are authorized to run.
- **Owner-Only Security**: Developer and owner-restricted commands (`eval`, `restart`, `maintenance`, etc.) are hidden from unauthorized users.
- **Category Navigation**: Interactive select menu categorized into 14 distinct modules including General, Moderation, Security, Verification, Tickets, Reaction Roles, Giveaways, AI, Configuration, and more.
- **Interactive Command Search**: In-help modal search button (`🔍 Search`) enabling members to find commands by keywords with smart ranking.
- **Command Lookup**: Detailed syntax, aliases, and usage examples via `+help <command>`.

---

## 🛡️ Ownership & Branding

- **Bot Name**: `KYOKA 3.0`
- **Creator**: `Aizen`
- **Primary Owner ID**: `1505515188991033409`
- **Support Server**: `https://discord.gg/5DBQTQJa9`
- **Framework**: `discord.py 2.7+` with Components V2 cards
- **Database**: `PostgreSQL` / `Supabase` with `asyncpg`

---
<div align="center">
  <sub>Made by Aizen.</sub>
</div>
