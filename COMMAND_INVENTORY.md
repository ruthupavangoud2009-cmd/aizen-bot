# KYŌKA 3.0 — COMMAND INVENTORY & SPECIFICATION

## Official Documented Top-Level Slash Commands (Exactly 50)

KYOKA 3.0 exposes an official 50-command slash interface categorized into 4 command groups and 10 standalone commands:

### 1. `/giveaway` Group (18 Subcommands)
1. `/giveaway create` — Create and publish an interactive giveaway with rich options.
2. `/giveaway quick` — Launch a giveaway with sensible default parameters.
3. `/giveaway end` — Conclude an active giveaway early and pick winners now.
4. `/giveaway cancel` — Cancel an active giveaway without drawing winners.
5. `/giveaway pause` — Pause entries and freeze countdown for an active giveaway.
6. `/giveaway resume` — Resume a paused giveaway with preserved duration.
7. `/giveaway reroll` — Select replacement winners for unclaimed/ineligible prizes.
8. `/giveaway edit` — Edit live giveaway settings (prize, winner count, description).
9. `/giveaway list` — List active, scheduled, paused, and recent giveaways.
10. `/giveaway info` — View detailed giveaway information and status.
11. `/giveaway entries` — View participant count and authorized entry details.
12. `/giveaway check` — Check a specific member's eligibility.
13. `/giveaway exclude` — Administratively exclude a user with an audit reason.
14. `/giveaway include` — Restore an excluded user to eligible status.
15. `/giveaway remind` — Broadcast a reminder announcement for an ending giveaway.
16. `/giveaway clone` — Clone an existing giveaway's configuration.
17. `/giveaway export` — Export participant weights and entry breakdown to CSV.
18. `/giveaway templates` — Save, load, list, or delete reusable giveaway templates.

### 2. `/requirements` Group (8 Subcommands)
19. `/requirements add` — Attach eligibility requirements to a giveaway or server defaults.
20. `/requirements remove` — Remove a configured eligibility requirement by ID.
21. `/requirements list` — List all configured requirements for a giveaway or server.
22. `/requirements test` — Test a member's eligibility against configured rules.
23. `/requirements activity` — Configure daily or 7-day message volume requirements.
24. `/requirements roles` — Configure required, permitted (any-of), or excluded roles.
25. `/requirements tag` — Configure server clan tag verification (with capability check).
26. `/requirements bonus` — Configure role-based bonus entries and multiplier stacking.

### 3. `/config` Group (8 Subcommands)
27. `/config view` — Inspect complete server giveaway and activity configurations.
28. `/config channel` — Designate default giveaway and announcement channels.
29. `/config roles` — Set custom giveaway manager role and staff exceptions.
30. `/config permissions` — Configure management permissions and host access.
31. `/config appearance` — Configure embed accent color, banner, and thumbnail.
32. `/config notifications` — Configure winner DMs, claim deadlines, and reminder intervals.
33. `/config activity` — Configure message tracking cooldowns and channel exclusions.
34. `/config reset` — Reset selected server settings to defaults after confirmation.

### 4. `/ai` Group (6 Subcommands)
35. `/ai setup` — Configure AI personality, channel, tone, and rules for this server.
36. `/ai personality` — Choose from 10 presets or configure a custom persona.
37. `/ai test` — Preview AI conversational responses under current settings.
38. `/ai reset` — Reset AI configuration to default after confirmation.
39. `/ai enable` — Enable AI conversational responses in configured channels.
40. `/ai disable` — Disable AI in specific channels or server-wide.

### 5. Utility & Administration (10 Top-Level Commands)
41. `/help` — Interactive command guide and category help.
42. `/ping` — WebSocket latency, API heartbeat, and database query latency.
43. `/botinfo` — Bot version, uptime, server count, and environment status.
44. `/serverinfo` — Server statistics, owner, creation date, and feature toggles.
45. `/userinfo` — Member details, join dates, roles, and avatar display.
46. `/activity` — View requesting member's message statistics (today & 7 days).
47. `/leaderboard` — Show server message activity leaderboard.
48. `/auditlog` — View administrative giveaway and configuration audit trail.
49. `/diagnostics` — System health: database pool, background workers, and gateway.
50. `/privacy` — Privacy information, tracking opt-out, and right-to-be-forgotten erasure.

---

## Complete Source-Declared Handlers (Prefix Commands & Existing Cogs Preserved)

Legacy `+` prefix commands (`+gstart`, `+gend`, `+greroll`, `+glist`, `+ai`, `+ping`, `+botinfo`, etc.) and legacy moderation/utility cogs are fully preserved alongside the 50 top-level slash commands.

| Module | Command | Aliases | Description |
|---|---|---|---|
| `src/cogs/admin/prefix.py` | `setprefix` | — | Change the bot command prefix for this server. |
| `src/cogs/admin/prefix.py` | `resetprefix` | — | Reset the bot command prefix to default '?' for this server. |
| `src/cogs/admin/prefix.py` | `prefix` | — | View the bot command prefix for this server. |
| `src/cogs/admin/sync.py` | `sync` | — | Sync application commands globally and remove duplicate guild commands. |
| `src/cogs/admin/sync.py` | `syncemojis` | emojisync, uploademojis | Scan assets folders and sync custom application emojis to Discord. |
| `src/cogs/antinuke/extraowner.py` | `extraowner` | eo | Manage Extra Owners who can configure Antinuke and bypass triggers. |
| `src/cogs/antinuke/extraowner.py` | `add` | — | Promote a trusted user to Extra Owner (Server Owner only). |
| `src/cogs/antinuke/extraowner.py` | `remove` | — | Remove Extra Owner status from a user (Server Owner only). |
| `src/cogs/antinuke/extraowner.py` | `list` | show | List all registered Extra Owners. |
| `src/cogs/antinuke/panel.py` | `antinuke` | security, an | Open the Antinuke setup for your server. |
| `src/cogs/antinuke/panel.py` | `show` | config, settings, status, info | Show current Antinuke configuration, modules, punishment, and logs. |
| `src/cogs/antinuke/panel.py` | `setup` | — | Launch the step-by-step Antinuke setup wizard. |
| `src/cogs/antinuke/panel.py` | `enable` | — | Enable Antinuke protection on your server. |
| `src/cogs/antinuke/panel.py` | `disable` | — | Disable Antinuke protection on your server. |
| `src/cogs/antinuke/panel.py` | `punishment` | — | Set the punishment for unauthorized actions. |
| `src/cogs/antinuke/panel.py` | `log` | — | Bind a channel for antinuke incident alerts. |
| `src/cogs/antinuke/panel.py` | `lockdown` | — | Freeze or unfreeze public messaging across all channels. |
| `src/cogs/antinuke/panel.py` | `lockdown` | — | Freeze or unfreeze public messaging across all channels. |
| `src/cogs/antinuke/whitelist.py` | `whitelist` | wl | Manage users or roles immune to antinuke triggers. |
| `src/cogs/antinuke/whitelist.py` | `add` | — | Add a user or role to the antinuke whitelist. |
| `src/cogs/antinuke/whitelist.py` | `remove` | — | Remove a user or role from the antinuke whitelist. |
| `src/cogs/antinuke/whitelist.py` | `list` | show | List all whitelisted users and roles. |
| `src/cogs/developer/blacklist.py` | `blacklist` | bl | Manage Global Blacklist restrictions for users or guilds. |
| `src/cogs/developer/blacklist.py` | `add` | — | — |
| `src/cogs/developer/blacklist.py` | `remove` | rm, del, unbl, unblacklist | — |
| `src/cogs/developer/blacklist.py` | `list` | ls, show | — |
| `src/cogs/developer/dm.py` | `dm` | directmessage, pm | — |
| `src/cogs/developer/eval.py` | `eval` | e, py | — |
| `src/cogs/developer/git.py` | `git` | repo, commit, version | — |
| `src/cogs/developer/guilds.py` | `guilds` | servers | — |
| `src/cogs/developer/identity.py` | `botedit` | setbot, identity, botset | Interactive Bot Identity & Persona console with Embed prompts. |
| `src/cogs/developer/identity.py` | `avatar` | — | — |
| `src/cogs/developer/identity.py` | `banner` | — | — |
| `src/cogs/developer/identity.py` | `name` | — | — |
| `src/cogs/developer/identity.py` | `status` | — | — |
| `src/cogs/developer/identity.py` | `setavatar` | changeavatar | — |
| `src/cogs/developer/identity.py` | `setname` | changename, botname | — |
| `src/cogs/developer/identity.py` | `setstatus` | activity, changestatus | — |
| `src/cogs/developer/monitor.py` | `live` | monitor, htop, watch | — |
| `src/cogs/developer/monitor.py` | `bench` | speed, benchmark | — |
| `src/cogs/developer/noprefix.py` | `noprefix` | np | Manage Direct Command Execution (No-Prefix) authority. |
| `src/cogs/developer/noprefix.py` | `add` | — | — |
| `src/cogs/developer/noprefix.py` | `remove` | rm, del | — |
| `src/cogs/developer/noprefix.py` | `list` | ls, show | — |
| `src/cogs/developer/owner_system.py` | `owner` | — | Show owner-only administration help. |
| `src/cogs/developer/owner_system.py` | `owner-botinfo` | — | Owner-only bot diagnostics. |
| `src/cogs/developer/owner_system.py` | `owner-sync` | — | Synchronize application commands. |
| `src/cogs/developer/owner_system.py` | `owner-reload` | — | Safely reload an approved extension. |
| `src/cogs/developer/owner_system.py` | `owner-load` | — | Load an approved extension. |
| `src/cogs/developer/owner_system.py` | `owner-unload` | — | Unload a nonessential extension. |
| `src/cogs/developer/owner_system.py` | `restart` | — | Request a controlled host restart. |
| `src/cogs/developer/owner_system.py` | `maintenance` | — | Toggle maintenance mode. |
| `src/cogs/developer/owner_system.py` | `health` | — | Show safe operational health. |
| `src/cogs/developer/owner_system.py` | `extensions` | — | List loaded and failed extensions. |
| `src/cogs/developer/owner_system.py` | `database-status` | — | Show database connectivity without credentials. |
| `src/cogs/developer/owner_system.py` | `errors` | — | Show a limited recent error summary. |
| `src/cogs/developer/owner_system.py` | `owner-premium` | — | Owner-only manual premium management. |
| `src/cogs/developer/owner_system.py` | `grant` | — | Manually grant user or server premium. |
| `src/cogs/developer/owner_system.py` | `revoke` | — | Revoke user or server premium. |
| `src/cogs/developer/owner_system.py` | `check` | — | Check a user's or server's premium status. |
| `src/cogs/developer/owner_system.py` | `list` | — | List active premium subscriptions. |
| `src/cogs/developer/owner_system.py` | `extend` | — | Extend an existing premium subscription. |
| `src/cogs/developer/owner_system.py` | `info` | — | Show premium tiers and configured benefit scope. |
| `src/cogs/developer/owner_system.py` | `servers` | — | List servers with premium subscriptions. |
| `src/cogs/developer/portal.py` | `portal` | ginv, guildinvite | — |
| `src/cogs/developer/reload.py` | `pull` | update | — |
| `src/cogs/developer/reload.py` | `reload` | rl, re | — |
| `src/cogs/developer/shell.py` | `shell` | sh, bash, cmd, exec | — |
| `src/cogs/developer/source.py` | `source` | src, inspect | — |
| `src/cogs/developer/sql.py` | `sql` | db, query | — |
| `src/cogs/developer/system.py` | `sys` | cluster, aura, nodes, host, hardware | — |
| `src/cogs/fun/ai_interactions.py` | `aisetup` | — | Admin: configure automatic AI replies in a channel, or turn them off. |
| `src/cogs/fun/ai_interactions.py` | `ai` | chat, askai, aizenai | Ask KYŌKA a question using Gemini AI. |
| `src/cogs/fun/ai_interactions.py` | `aiclear` | — | Clear your private KYŌKA conversation history. |
| `src/cogs/fun/ai_interactions.py` | `aistatus` | — | Show AI and GIF integration configuration without revealing secrets. |
| `src/cogs/fun/ai_interactions.py` | `gif` | — | Search for a real GIF using the configured GIF provider. |
| `src/cogs/fun/ai_interactions.py` | `meme` | — | Search for an anime meme GIF, optionally by topic. |
| `src/cogs/fun/ai_interactions.py` | `randomgif` | — | Get a random GIF, optionally by search topic. |
| `src/cogs/fun/ai_interactions.py` | `wave` | — | Wave at a member with an optional GIF. |
| `src/cogs/fun/ai_interactions.py` | `wink` | — | Wink at a member with an optional GIF. |
| `src/cogs/fun/ai_interactions.py` | `dance` | — | Celebrate with an anime dance GIF. |
| `src/cogs/fun/ai_interactions.py` | `blush` | — | Show a blushing anime reaction. |
| `src/cogs/fun/ai_interactions.py` | `cry` | — | Show a crying anime reaction. |
| `src/cogs/fun/ai_interactions.py` | `laugh` | — | Show a laughing anime reaction. |
| `src/cogs/fun/ai_interactions.py` | `happy` | — | Show a happy anime reaction. |
| `src/cogs/fun/ai_interactions.py` | `angry` | — | Show an angry anime reaction. |
| `src/cogs/fun/ai_interactions.py` | `sleepy` | — | Show a sleepy anime reaction. |
| `src/cogs/fun/ai_interactions.py` | `thumbsup` | — | Give a thumbs-up reaction. |
| `src/cogs/fun/ai_interactions.py` | `facepalm` | — | Show a dramatic facepalm reaction. |
| `src/cogs/fun/ai_interactions.py` | `shrug` | — | Show a shrug reaction. |
| `src/cogs/fun/ai_interactions.py` | `killme` | — | A harmless, comedic anime reaction; not an encouragement of self-harm. |
| `src/cogs/fun/ai_interactions.py` | `guesshostadd` | — | Owner-only: authorize a number-game host in this server. |
| `src/cogs/fun/ai_interactions.py` | `guesshostremove` | — | Owner-only: remove a number-game host in this server. |
| `src/cogs/fun/ai_interactions.py` | `guesshosts` | — | Owner-only: list authorized number-game hosts for this server. |
| `src/cogs/fun/fun.py` | `slap` | — | Aizen gives someone an anime-style slap. |
| `src/cogs/fun/fun.py` | `hug` | — | Send someone a friendly anime hug. |
| `src/cogs/fun/fun.py` | `pat` | — | Give someone a friendly head pat. |
| `src/cogs/fun/fun.py` | `kiss` | — | Send a playful, virtual anime kiss. |
| `src/cogs/fun/fun.py` | `bonk` | — | Give someone a harmless cartoon bonk. |
| `src/cogs/fun/fun.py` | `cuddle` | — | Send someone a friendly cuddle. |
| `src/cogs/fun/fun.py` | `poke` | — | Give someone a gentle poke. |
| `src/cogs/fun/fun.py` | `highfive` | — | Give someone a high five. |
| `src/cogs/fun/fun.py` | `kill` | — | Defeat someone in a fictional anime roleplay duel. |
| `src/cogs/fun/fun.py` | `compliment` | — | Give someone a friendly compliment. |
| `src/cogs/fun/fun.py` | `roast` | — | Give someone a playful roast. |
| `src/cogs/fun/fun.py` | `ship` | — | Calculate two users' completely scientific compatibility. |
| `src/cogs/fun/fun.py` | `8ball` | eightball | Ask Aizen's mysterious 8-ball a question. |
| `src/cogs/fun/fun.py` | `coinflip` | flip | Flip a coin. |
| `src/cogs/fun/fun.py` | `dice` | roll | Roll a die with 2–100 sides. |
| `src/cogs/fun/fun.py` | `choose` | — | Choose between options separated by \|. |
| `src/cogs/fun/fun.py` | `rate` | — | Give something a completely scientific rating. |
| `src/cogs/fun/fun.py` | `joke` | — | Ask Aizen for a quick joke. |
| `src/cogs/fun/fun.py` | `rps` | — | Play rock-paper-scissors against Aizen. |
| `src/cogs/fun/fun.py` | `trivia` | — | Answer a quick anime-themed trivia question. |
| `src/cogs/fun/fun.py` | `guessanumber` | guessnumber, guess | Start an authorized number guessing game, e.g. ?guessanumber 1-10000. |
| `src/cogs/fun/fun.py` | `guessstatus` | — | Check the current number game in this channel. |
| `src/cogs/fun/fun.py` | `guesscancel` | — | Cancel the number game you started in this channel. |
| `src/cogs/fun/fun.py` | `spam` | — | Owner-only: repeat a message up to 100 times; explicit @user mentions are pinged. |
| `src/cogs/fun/fun.py` | `spamcancel` | — | Owner-only: cancel a running repeat-message task. |
| `src/cogs/fun/fun.py` | `guesshelp` | — | Explain number-game rules and host authorization. |
| `src/cogs/fun/fun.py` | `fact` | — | Hear a random harmless fact. |
| `src/cogs/fun/fun.py` | `quote` | — | Get a short strategic quote. |
| `src/cogs/fun/fun.py` | `wyr` | — | Get a safe would-you-rather prompt. |
| `src/cogs/fun/fun.py` | `truth` | — | Get a safe truth question. |
| `src/cogs/fun/fun.py` | `dare` | — | Get a safe, harmless dare. |
| `src/cogs/fun/fun.py` | `premium` | — | Learn how to request Aizen Premium. |
| `src/cogs/fun/fun.py` | `funhelp` | — | Quick guide to fun commands. |
| `src/cogs/general/avatar.py` | `avatar` | av | Display a user's high-resolution avatar. |
| `src/cogs/general/banner.py` | `banner` | — | Display a user's high-resolution profile banner or accent color. |
| `src/cogs/general/botinfo.py` | `botinfo` | bi, about, info | View KYOKA's identity, runtime, latency, and support information. |
| `src/cogs/general/channelinfo.py` | `channelinfo` | ci | View details, category, topic, and creation date of a channel. |
| `src/cogs/general/help.py` | `help` | commands, modules, h | Display the Kyoka command directory tailored to your permissions. |
| `src/cogs/general/invite.py` | `invite` | inv, addbot, links, support | Get official authorization links to invite Kyoka to your server. |
| `src/cogs/general/membercount.py` | `membercount` | mc | View live server member count breakdown (humans vs bots). |
| `src/cogs/general/ping.py` | `ping` | pong, pung, latency | Check Kyoka Bot's websocket, latency, and database response speed. |
| `src/cogs/general/profile.py` | `profile` | pr, prof, userprofile | View your or another member's Kyoka Bot Identity & Standing. |
| `src/cogs/general/server_avatar.py` | `server` | — | Display server media and branding assets. |
| `src/cogs/general/server_avatar.py` | `avatar` | icon | Display this server's high-resolution icon. |
| `src/cogs/general/server_avatar.py` | `banner` | splash | Display this server's high-resolution banner or invite splash. |
| `src/cogs/general/server_avatar.py` | `serveravatar` | — | — |
| `src/cogs/general/server_avatar.py` | `serverbanner` | — | — |
| `src/cogs/general/serverinfo.py` | `serverinfo` | si, guildinfo | View interactive server dossier across dedicated modules. |
| `src/cogs/general/stats.py` | `stats` | uptime | View live system telemetry, RAM/CPU metrics, and process health. |
| `src/cogs/general/userinfo.py` | `userinfo` | ui, whois | View interactive user dossier with Profile, Server, and Roles tabs. |
| `src/cogs/logging/server_logs.py` | `logs` | log, serverlogs | View and configure server audit logging channels. |
| `src/cogs/logging/server_logs.py` | `show` | view, config, status | Display all configured logging channels. |
| `src/cogs/logging/server_logs.py` | `channel` | set | Bind a channel for a specific log category. |
| `src/cogs/logging/server_logs.py` | `reset` | — | Clear logging channel configurations. |
| `src/cogs/moderation/admins.py` | `admins` | adminroles, listadmins, adminlist | Audit and list all members holding Administrator permissions. |
| `src/cogs/moderation/ban.py` | `ban` | — | Ban a member from the server. |
| `src/cogs/moderation/ban.py` | `unban` | — | Unban a user by their user ID or tag. |
| `src/cogs/moderation/bots.py` | `bots` | botlist, listbots | Display all bot accounts integrated into this server. |
| `src/cogs/moderation/emojis.py` | `emojis` | expr, expressions, emojimanager, stickers, delemoji, delsticker | Interactive studio to browse, preview, and delete server emojis or stickers. |
| `src/cogs/moderation/kick.py` | `kick` | — | Kick a member from the server. |
| `src/cogs/moderation/listroles.py` | `listroles` | roles, rolelist | Display all roles in this server sorted by hierarchy with member counts. |
| `src/cogs/moderation/lock.py` | `lock` | — | Lock a channel to prevent regular members from sending messages. |
| `src/cogs/moderation/lock.py` | `unlock` | — | Unlock a channel to allow members to send messages. |
| `src/cogs/moderation/media.py` | `media` | — | Configure and manage media-only channels in the server. |
| `src/cogs/moderation/media.py` | `setup` | — | Configure one or more channels as media-only (images/videos/GIFs only). |
| `src/cogs/moderation/media.py` | `disable` | — | Disable media-only restriction for one or more channels. |
| `src/cogs/moderation/media.py` | `show` | — | Show all configured media-only channels in this server. |
| `src/cogs/moderation/modlog.py` | `modlog` | — | Set or view the moderation audit log channel. |
| `src/cogs/moderation/mods.py` | `mods` | listmods, staff, modlist | List all active staff and moderators possessing moderation privileges. |
| `src/cogs/moderation/purge.py` | `purge` | prune, clean | Bulk delete messages in the current channel (1 to 100). |
| `src/cogs/moderation/purge.py` | `bot` | bots | Bulk delete messages sent by bot accounts (1 to 100). |
| `src/cogs/moderation/purge.py` | `human` | humans, user, users | Bulk delete messages sent by real humans/users (1 to 100). |
| `src/cogs/moderation/role.py` | `role` | r | Toggle, assign, or remove a role from a member. |
| `src/cogs/moderation/role.py` | `add` | give | Assign a role to a member. |
| `src/cogs/moderation/role.py` | `remove` | rm, take, del | Remove a role from a member. |
| `src/cogs/moderation/roleall.py` | `roleall` | — | Mass assign a role to all human members in the server. |
| `src/cogs/moderation/roleall.py` | `remove` | rm, take, del | Mass remove a role from all members who have it. |
| `src/cogs/moderation/roleall.py` | `cancel` | stop, abort | Cancel an active mass role operation in this server. |
| `src/cogs/moderation/roleinfo.py` | `roleinfo` | inrole, rolemembers, role-info | View comprehensive role dossier, permissions matrix, and roster. |
| `src/cogs/moderation/slowmode.py` | `slowmode` | — | Set slowmode delay for a channel (0 to disable, max 21600s). |
| `src/cogs/moderation/timeout.py` | `timeout` | mute | Timeout a member for a specified duration (e.g., 10m, 1h, 1d). |
| `src/cogs/moderation/timeout.py` | `unmute` | untimeout | Remove timeout from a member. |
| `src/cogs/moderation/warn.py` | `warn` | — | Issue an official warning to a server member. |
| `src/cogs/moderation/warn.py` | `warnings` | warns | View all recorded warnings for a member. |
| `src/cogs/moderation/warn.py` | `delwarn` | unwarn, removewarn | Delete a warning record by its ID. |
| `src/cogs/music/music.py` | `join` | connect, j | Connect Kyoka to your current voice channel. |
| `src/cogs/music/music.py` | `play` | p | Play high-fidelity music tracks directly in your voice channel. |
| `src/cogs/music/music.py` | `autoplay` | ap | Toggle Smart Autoplay to play continuous radio based on played songs. |
| `src/cogs/music/music.py` | `pause` | — | Pause the currently playing music stream. |
| `src/cogs/music/music.py` | `resume` | unpause | Resume paused music stream. |
| `src/cogs/music/music.py` | `skip` | s, next | Skip the current track to the next song in queue. |
| `src/cogs/music/music.py` | `stop` | disconnect, dc | Stop playback, clear queue, and disconnect from voice. |
| `src/cogs/music/music.py` | `queue` | q | Display the upcoming server music playlist. |
| `src/cogs/music/music.py` | `nowplaying` | now, playing | Display the currently playing song with interactive controls. |
| `src/cogs/music/music.py` | `loop` | — | Toggle loop mode between off, track, and entire queue. |
| `src/cogs/music/music.py` | `shuffle` | — | Randomize the order of upcoming songs in queue. |
| `src/cogs/music/music.py` | `clear` | — | Clear all upcoming tracks from the queue. |
| `src/cogs/music/music.py` | `volume` | vol | Adjust playback volume (0 to 200 percent). |
| `src/cogs/music/music.py` | `like` | fav, favorite | Save the currently playing song into your personal Favorites playlist. |
| `src/cogs/music/music.py` | `unlike` | unfav, dislike | Remove a song from your personal Favorites playlist by title or playing track. |
| `src/cogs/music/music.py` | `playlist` | pl | Manage, play, view, and save custom song playlists. |
| `src/cogs/music/music.py` | `remove` | — | Remove a specific track from the upcoming queue by its number. |
| `src/cogs/music/music.py` | `jump` | skipto | Skip directly to a specific track number in the queue. |
| `src/cogs/music/music.py` | `247` | stay | Toggle 24/7 mode to keep Kyoka connected in voice even when empty. |
| `src/cogs/ticket/ticket_system.py` | `ticket` | tickets, ticketpanel | Enterprise Ticket System management commands and interactive setup wizard. |
| `src/cogs/ticket/ticket_system.py` | `setup` | — | Launch the interactive Slide Dashboard to configure and deploy a ticket panel. |
| `src/cogs/ticket/ticket_system.py` | `close` | — | Close the active ticket channel with optional reason. |
| `src/cogs/ticket/ticket_system.py` | `claim` | — | Claim the current active ticket for staff handling. |
| `src/cogs/ticket/ticket_system.py` | `unclaim` | — | Release your claim on the current ticket channel. |
| `src/cogs/ticket/ticket_system.py` | `transfer` | — | Transfer active ticket claim to another staff member. |
| `src/cogs/ticket/ticket_system.py` | `add` | — | Add a member to the current ticket channel. |
| `src/cogs/ticket/ticket_system.py` | `remove` | — | Remove a member from the current ticket channel. |
| `src/cogs/ticket/ticket_system.py` | `rename` | — | Rename the current ticket channel. Usage: +ticket rename <new_name> |
| `src/cogs/ticket/ticket_system.py` | `priority` | — | Set ticket priority level (low, normal, high, urgent). |
| `src/cogs/ticket/ticket_system.py` | `note` | — | Record an internal staff-only note on this ticket. |
| `src/cogs/ticket/ticket_system.py` | `stats` | — | View server ticket resolution metrics and category distribution. |
| `src/cogs/ticket/ticket_system.py` | `transcript` | — | Generate and download the secure HTML transcript of this ticket channel. |
| `src/cogs/ticket/ticket_system.py` | `list` | — | List all active ticket panels configured in this server. |
| `src/cogs/ticket/ticket_system.py` | `delete` | — | Delete a configured ticket panel. Usage: +ticket delete <panel_name> |
| `src/cogs/utility/afk.py` | `afk` | — | Set your AFK status with an optional reason. |
| `src/cogs/utility/dev_pulse.py` | `dev` | devpulse, opportunities, bounties, devjobs | Autonomous Developer Opportunities & Career Dashboard. |
| `src/cogs/utility/embed_builder.py` | `embed` | embedbuilder, container, card | Design, customize, preview, save, edit, and post Components V2 container cards. |
| `src/cogs/utility/embed_builder.py` | `create` | — | Create a new named embed. Usage: ?embed create <name> |
| `src/cogs/utility/embed_builder.py` | `edit` | — | Edit an existing named embed. Usage: ?embed edit <name> |
| `src/cogs/utility/embed_builder.py` | `show` | view, preview | Preview a saved embed card. Usage: ?embed show <name> |
| `src/cogs/utility/embed_builder.py` | `send` | post | Send a saved template to a channel. Usage: ?embed send [#channel] <name> |
| `src/cogs/utility/embed_builder.py` | `delete` | remove | Delete a saved template. Usage: ?embed delete <name> |
| `src/cogs/utility/embed_builder.py` | `list` | all, templates | List all saved embeds in this server. Usage: ?embed list |
| `src/cogs/utility/events.py` | `autorole` | joinrole | Configure automatic role assignment for humans and bots. |
| `src/cogs/utility/events.py` | `human` | humans, user, users | Configure automatic role assignment for real human members. |
| `src/cogs/utility/events.py` | `remove` | disable, reset | Disable auto-role for human members. |
| `src/cogs/utility/events.py` | `bot` | bots | Configure automatic role assignment for invited bot accounts. |
| `src/cogs/utility/events.py` | `remove` | disable, reset | Disable auto-role for bot accounts. |
| `src/cogs/utility/events.py` | `welcome` | greet | Configure automated server welcome container cards. |
| `src/cogs/utility/events.py` | `set` | — | Bind channel, outer text, and custom embed for welcome messages. |
| `src/cogs/utility/events.py` | `test` | — | Test the current welcome message and embed live in channel. |
| `src/cogs/utility/events.py` | `toggle` | — | Enable or disable the welcome message. |
| `src/cogs/utility/events.py` | `reset` | clear, delete | Reset and disable welcome messages. |
| `src/cogs/utility/events.py` | `announce` | — | Dispatch a saved embed card with an outer mention ping (@everyone, role, etc.). |
| `src/cogs/utility/events.py` | `announce` | embedannounce | Dispatch a saved embed card with an outer mention ping (@everyone, role, etc.). |
| `src/cogs/utility/events.py` | `leave` | goodbye, farewell | Configure automated server leave / goodbye container cards. |
| `src/cogs/utility/events.py` | `set` | — | Bind channel, outer text, and custom embed for departure messages. |
| `src/cogs/utility/events.py` | `test` | — | Test the current leave message live in channel. |
| `src/cogs/utility/events.py` | `toggle` | — | Enable or disable leave messages. |
| `src/cogs/utility/events.py` | `reset` | clear, delete | Reset and disable leave messages. |
| `src/cogs/utility/events.py` | `boost` | — | Configure automated server boost celebration container cards. |
| `src/cogs/utility/events.py` | `set` | — | Bind channel, outer text, and custom embed for boost announcements. |
| `src/cogs/utility/events.py` | `test` | — | Test the boost celebration message live in channel. |
| `src/cogs/utility/events.py` | `toggle` | — | Enable or disable boost celebration messages. |
| `src/cogs/utility/events.py` | `reset` | clear, delete | Reset and disable boost messages. |
| `src/cogs/utility/giveaway.py` | `giveaway` | g | Enterprise giveaway system with interactive Components V2 cards. |
| `src/cogs/utility/giveaway.py` | `start` | — | Start a new interactive giveaway. |
| `src/cogs/utility/giveaway.py` | `end` | — | End an active giveaway now and pick winners. |
| `src/cogs/utility/giveaway.py` | `reroll` | — | Pick new random winners from an ended giveaway. |
| `src/cogs/utility/giveaway.py` | `list` | — | List all active giveaways currently running in this server. |
| `src/cogs/utility/giveaway.py` | `gstart` | — | Launch a new giveaway with quick prefix parameters. |
| `src/cogs/utility/giveaway.py` | `gend` | — | Conclude an active giveaway immediately via prefix. |
| `src/cogs/utility/giveaway.py` | `greroll` | — | Reroll replacement winners for an ended giveaway. |
| `src/cogs/utility/giveaway.py` | `glist` | — | List all running giveaways in this server. |
| `src/cogs/utility/giveaway.py` | `gpause` | — | Freeze countdown and entries on an active giveaway. |
| `src/cogs/utility/giveaway.py` | `gresume` | — | Unfreeze and resume countdown on a paused giveaway. |
| `src/cogs/utility/giveaway.py` | `gcancel` | — | Terminate a running giveaway without drawing winners. |
| `src/cogs/utility/giveaway.py` | `ginfo` | — | View detailed metadata and participants for a giveaway. |
| `src/cogs/utility/giveaway.py` | `gcheck` | — | Test a member's eligibility against giveaway requirements. |
| `src/cogs/utility/giveaway.py` | `gbonus` | — | Configure role-based bonus entries and multiplier stacking. |
| `src/cogs/utility/giveaway.py` | `greq` | — | Configure required roles or message activity thresholds. |
| `src/cogs/utility/reaction_roles.py` | `reactionrole` | rr | Enterprise reaction role and button panel manager. |
| `src/cogs/utility/reaction_roles.py` | `setup` | — | Interactive guided wizard to build and publish a button role panel. |
| `src/cogs/utility/reaction_roles.py` | `create` | — | Create an emoji-reaction based role panel. |
| `src/cogs/utility/reaction_roles.py` | `button` | — | Create an interactive button role panel. |
| `src/cogs/utility/reaction_roles.py` | `add` | — | Attach an emoji/button role mapping to an existing panel. |
| `src/cogs/utility/reaction_roles.py` | `remove` | — | Remove a role mapping from a panel. |
| `src/cogs/utility/reaction_roles.py` | `clear` | — | Clear all role bindings from a panel. |
| `src/cogs/utility/reaction_roles.py` | `list` | — | List all active reaction/button role panels in the server. |
| `src/cogs/utility/reaction_roles.py` | `modes` | — | View reaction role panel behavior modes (normal, unique, verify). |
| `src/cogs/utility/snipe.py` | `snipe` | sn | View recently deleted messages in this channel. |
| `src/cogs/utility/snipe.py` | `clearsnipe` | csnipe | Purge the deleted message snipe cache for this channel (or 'all' for entire server). |
| `src/cogs/utility/snipe_all.py` | `snipeall` | sall, globalsnipe, serversnipe | Show recent deleted messages across all channels in the server. |
| `src/cogs/utility/snipe_all.py` | `clearsnipeall` | csnipeall, wipesnipeall | Wipe the server-wide deleted message cache across all channels. |
| `src/cogs/utility/steal.py` | `steal` | stealemoji, stealsticker, addemoji | Steal emojis or stickers with an interactive dashboard. |
| `src/cogs/utility/sticky.py` | `set` | — | Set or update an auto-pinned sticky notice for a channel |
| `src/cogs/utility/sticky.py` | `remove` | — | Remove the sticky message from a channel |
| `src/cogs/utility/sticky.py` | `list` | — | List all active sticky notices in this server |
| `src/cogs/utility/sticky.py` | `toggle` | — | Pause or resume the sticky message in a channel |
| `src/cogs/utility/tech_feed.py` | `tech` | technews, techfeed | Autonomous Tech Intelligence terminal & feed dashboard. |
| `src/cogs/utility/temp_voice.py` | `j2c` | jointocreate, join-to-create | Setup Join-to-Create voice infrastructure with automated channel generator and control dashboard. |
| `src/cogs/utility/translator.py` | `translate` | — | Translate any text into your chosen language |
| `src/cogs/utility/translator.py` | `translator-settings` | — | Configure server translation settings |
| `src/cogs/utility/verification.py` | `verify` | — | Complete member verification or access verification configuration commands. |
| `src/cogs/utility/verification.py` | `setup` | — | Interactive guided wizard to configure and deploy server gatekeeping verification. |
| `src/cogs/utility/verification.py` | `role` | — | Set the role granted upon successful verification. |
| `src/cogs/utility/verification.py` | `unverifiedrole` | — | Set the role assigned to unverified members upon joining. |
| `src/cogs/utility/verification.py` | `channel` | — | Set the dedicated verification channel. |
| `src/cogs/utility/verification.py` | `method` | — | Set verification challenge mode: button, rules, or math challenge. |
| `src/cogs/utility/verification.py` | `enable` | — | Activate verification enforcement on join. |
| `src/cogs/utility/verification.py` | `disable` | — | Deactivate verification enforcement. |
| `src/cogs/utility/verification.py` | `panel` | — | Post or update the interactive verification panel card. |
| `src/cogs/utility/verification.py` | `stats` | — | View server verification metrics and success rates. |
| `src/cogs/utility/verification.py` | `user` | — | Inspect a member's verification status and history. |
| `src/cogs/utility/verification.py` | `remove` | — | Revoke verified role from a user and return them to unverified status. |
| `src/cogs/utility/verification.py` | `reset` | — | Reset server verification configuration to defaults. |
| `src/cogs/fun/ai_interactions.py` | `ai` | ask, chat | Chat directly with Kyoka's configured AI personality. |
| `src/cogs/fun/ai_interactions.py` | `aipersonality` | — | Select from 10 personality presets or configure custom persona instructions. |
| `src/cogs/fun/ai_interactions.py` | `aiconfig` | — | View active server AI configuration, channel restrictions, and tone. |
| `src/cogs/fun/ai_interactions.py` | `aitest` | — | Test sample prompt output against the active server personality. |
