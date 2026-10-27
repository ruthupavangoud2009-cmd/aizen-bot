/**
 * KYOKA 3.0 Web Client API Interface
 * Handles Discord OAuth2 session verification, guild queries, and settings persistence.
 */

// API Base resolution: supports window.KYOKA_API_BASE, localStorage override, or default /api
export function getApiBase() {
  if (typeof window !== 'undefined') {
    if (window.KYOKA_API_BASE) return window.KYOKA_API_BASE.replace(/\/+$/, '');
    const stored = localStorage.getItem('kyoka_api_base');
    if (stored) return stored.replace(/\/+$/, '');
  }
  return '/api';
}

export function setApiBase(url) {
  if (typeof window !== 'undefined') {
    if (url) {
      localStorage.setItem('kyoka_api_base', url.replace(/\/+$/, ''));
      window.KYOKA_API_BASE = url.replace(/\/+$/, '');
    } else {
      localStorage.removeItem('kyoka_api_base');
      delete window.KYOKA_API_BASE;
    }
  }
}

// Automatically extract session token from URL hash fragment upon OAuth callback redirect
if (typeof window !== 'undefined') {
  try {
    const hash = window.location.hash;
    if (hash && hash.includes('token=')) {
      const params = new URLSearchParams(hash.substring(1));
      const token = params.get('token') || params.get('access_token');
      if (token) {
        sessionStorage.setItem('kyoka_session_token', token);
        // Clean URL fragment so token is not exposed in address bar history
        const cleanUrl = window.location.pathname + window.location.search;
        window.history.replaceState(null, '', cleanUrl);
      }
    }
  } catch (err) {
    console.debug('Token fragment check notice:', err);
  }
}

const DIRECT_BACKEND_FALLBACK = 'https://kyokasugisetsu.onrender.com/api';

/**
 * Standard authenticated fetch helper with credentials and error handling
 */
export async function apiFetch(endpoint, options = {}, isRetry = false) {
  const base = isRetry ? DIRECT_BACKEND_FALLBACK : getApiBase();
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
  const url = `${base}${cleanEndpoint}`;

  const defaultHeaders = {
    'Accept': 'application/json',
  };

  // Attach session token Bearer authorization if stored from cross-domain OAuth callback
  const storedToken = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('kyoka_session_token') : null;
  if (storedToken) {
    defaultHeaders['Authorization'] = `Bearer ${storedToken}`;
  }

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  // Fast edge request timeout (3.5s max to eliminate LTE stalls)
  let controller = null;
  let signal = options.signal;
  if (!signal && typeof AbortController !== 'undefined') {
    controller = new AbortController();
    signal = controller.signal;
    setTimeout(() => {
      try { controller.abort(); } catch {}
    }, options.timeout || 3500);
  }

  const fetchOptions = {
    ...options,
    signal,
    credentials: 'include', // Guarantees HttpOnly session cookie transmission
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const res = await fetch(url, fetchOptions);

    // Check for rate limit
    if (res.status === 429) {
      const retryAfter = res.headers.get('Retry-After') || 5;
      throw new Error(`Rate limit exceeded. Please wait ${retryAfter} seconds.`);
    }

    if (res.status === 401) {
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('kyoka_session_token');
      }
      return { authenticated: false, status: 401 };
    }

    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`API returned non-JSON response (HTTP ${res.status}).`);
    }

    if (!res.ok) {
      throw new Error(data.message || data.error || `HTTP ${res.status}`);
    }

    return data;
  } catch (err) {
    console.debug(`API Request on ${endpoint}:`, err?.message || err);
    throw err;
  }
}

/**
 * Check current logged-in user profile
 */
export async function getAuthStatus() {
  try {
    const data = await apiFetch('/auth/me');
    if (data && data.authenticated && data.user) {
      return data;
    }
    return { authenticated: false, user: null };
  } catch (err) {
    return { authenticated: false, user: null };
  }
}

export function loginWithDiscord() {
  window.location.href = '/api/auth/login';
}

/**
 * Log out and clear session cookie & bearer token
 */
export async function logoutUser() {
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem('kyoka_session_token');
  }
  try {
    await apiFetch('/auth/logout', { method: 'POST' });
  } catch (err) {
    console.warn('Logout API notification failed, redirecting anyway:', err);
  }
  window.location.href = '/dashboard';
}

/**
 * Fetch all Discord servers manageable by the authenticated user
 */
export async function fetchGuilds(forceRefresh = false) {
  const query = forceRefresh ? '?refresh=1' : '';
  const res = await apiFetch(`/guilds${query}`);
  const guilds = Array.isArray(res?.guilds) ? res.guilds : [];
  return guilds.filter(g => g.can_manage);
}

/**
 * Fetch modular settings for a specific guild
 */
export async function fetchGuildSettings(guildId) {
  return await apiFetch(`/guilds/${guildId}/settings`);
}

/**
 * Update modular settings for a specific guild with validation
 */
export async function updateGuildSettings(guildId, updates) {
  return await apiFetch(`/guilds/${guildId}/settings`, {
    method: 'PATCH',
    body: updates,
  });
}

/**
 * Public bot statistics for landing page
 */
export async function fetchPublicStats() {
  try {
    const data = await apiFetch('/stats');
    if (data && typeof data === 'object') {
      return {
        guilds: data.guilds ?? 15,
        users: data.users ?? (data.total_users ?? 2450),
        commands_available: data.commands_available ?? (data.total_commands ?? 50),
        status: data.status || 'online',
      };
    }
  } catch {}
  return { guilds: 15, users: 2450, commands_available: 50, status: 'online' };
}

/**
 * Complete official command catalog fallback
 */
export const OFFICIAL_COMMANDS_CATALOG = [
  { group: "Giveaway", name: "/giveaway create", description: "Create and publish an interactive giveaway with rich options.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway quick", description: "Launch a giveaway with sensible default parameters.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway end", description: "Conclude an active giveaway early and pick winners now.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway cancel", description: "Cancel an active giveaway without drawing winners.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway pause", description: "Pause entries and freeze countdown for an active giveaway.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway resume", description: "Resume a paused giveaway with preserved duration.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway reroll", description: "Select replacement winners for unclaimed/ineligible prizes.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway edit", description: "Edit live giveaway settings (prize, winner count, description).", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway list", description: "List active, scheduled, paused, and recent giveaways.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway info", description: "View detailed giveaway information and status.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway entries", description: "View participant count and authorized entry details.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway check", description: "Check a specific member's eligibility.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway exclude", description: "Administratively exclude a user with an audit reason.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway include", description: "Restore an excluded user to eligible status.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway remind", description: "Broadcast a reminder announcement for an ending giveaway.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway clone", description: "Clone an existing giveaway's configuration.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway export", description: "Export participant weights and entry breakdown to CSV.", category: "Giveaways" },
  { group: "Giveaway", name: "/giveaway templates", description: "Save, load, list, or delete reusable giveaway templates.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements add", description: "Attach eligibility requirements to a giveaway or server defaults.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements remove", description: "Remove a configured eligibility requirement by ID.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements list", description: "List all configured requirements for a giveaway or server.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements test", description: "Test a member's eligibility against configured rules.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements activity", description: "Configure daily or 7-day message volume requirements.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements roles", description: "Configure required, permitted (any-of), or excluded roles.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements tag", description: "Configure server clan tag verification.", category: "Giveaways" },
  { group: "Requirements", name: "/requirements bonus", description: "Configure role-based bonus entries and multiplier stacking.", category: "Giveaways" },
  { group: "Config", name: "/config view", description: "Inspect complete server giveaway and activity configurations.", category: "Administration" },
  { group: "Config", name: "/config channel", description: "Designate default giveaway and announcement channels.", category: "Administration" },
  { group: "Config", name: "/config roles", description: "Set custom giveaway manager role and staff exceptions.", category: "Administration" },
  { group: "Config", name: "/config permissions", description: "Configure management permissions and host access.", category: "Administration" },
  { group: "Config", name: "/config appearance", description: "Configure embed accent color, banner, and thumbnail.", category: "Administration" },
  { group: "Config", name: "/config notifications", description: "Configure winner DMs, claim deadlines, and reminder intervals.", category: "Administration" },
  { group: "Config", name: "/config activity", description: "Configure message tracking cooldowns and channel exclusions.", category: "Administration" },
  { group: "Config", name: "/config reset", description: "Reset selected server settings to defaults after confirmation.", category: "Administration" },
  { group: "AI", name: "/ai setup", description: "Configure AI personality, channel, tone, and rules for this server.", category: "Artificial Intelligence" },
  { group: "AI", name: "/ai personality", description: "Choose from 10 presets or configure a custom persona.", category: "Artificial Intelligence" },
  { group: "AI", name: "/ai test", description: "Preview AI conversational responses under current settings.", category: "Artificial Intelligence" },
  { group: "AI", name: "/ai reset", description: "Reset AI configuration to default after confirmation.", category: "Artificial Intelligence" },
  { group: "AI", name: "/ai enable", description: "Enable AI conversational responses in configured channels.", category: "Artificial Intelligence" },
  { group: "AI", name: "/ai disable", description: "Disable AI in specific channels or server-wide.", category: "Artificial Intelligence" },
  { group: "General", name: "/help", description: "Interactive command guide and category help with dropdowns.", category: "General" },
  { group: "General", name: "/ping", description: "WebSocket latency, API heartbeat, and database query latency.", category: "General" },
  { group: "General", name: "/botinfo", description: "Bot version, uptime, server count, and environment status.", category: "General" },
  { group: "General", name: "/serverinfo", description: "Server statistics, owner, creation date, and feature toggles.", category: "General" },
  { group: "General", name: "/userinfo", description: "Member details, join dates, roles, and avatar display.", category: "General" },
  { group: "General", name: "/activity", description: "View requesting member's message statistics (today & 7 days).", category: "Analytics" },
  { group: "General", name: "/leaderboard", description: "Show server message activity leaderboard.", category: "Analytics" },
  { group: "General", name: "/auditlog", description: "View administrative giveaway and configuration audit trail.", category: "Administration" },
  { group: "General", name: "/diagnostics", description: "System health: database pool, background workers, and gateway.", category: "Administration" },
  { group: "General", name: "/privacy", description: "Privacy information, tracking opt-out, and right-to-be-forgotten erasure.", category: "General" },
  { group: "Antinuke", name: "+antinuke", description: "Anti-nuke security suite with vanity, role, channel, and bot protection.", category: "Security" },
  { group: "Antinuke", name: "+whitelist", description: "Manage users or roles immune to antinuke triggers.", category: "Security" },
  { group: "Antinuke", name: "+extraowner", description: "Designate trusted extra owners for server protection bypass.", category: "Security" },
  { group: "Verification", name: "+verification setup", description: "Enhanced member verification system with button or captcha modes.", category: "Security" },
  { group: "Music", name: "+play <song>", description: "High-fidelity audio playback with smart autoplay queue.", category: "Music" },
  { group: "Music", name: "+247", description: "Toggle 24/7 voice channel stay mode.", category: "Music" }
];

/**
 * Official command inventory
 */
export async function fetchOfficialCommands() {
  try {
    const res = await apiFetch('/commands');
    if (res && Array.isArray(res.commands) && res.commands.length > 0) {
      return res.commands;
    }
  } catch {}
  return OFFICIAL_COMMANDS_CATALOG;
}

/**
 * Safely simulate an event preview (welcome, leave) without live member spam
 */
export async function testEventSimulation(guildId, eventType) {
  return await apiFetch(`/guilds/${guildId}/test-event`, {
    method: 'POST',
    body: { event_type: eventType },
  });
}

/**
 * Setup Wizard API client interfaces
 */
export async function fetchWizardState(guildId) {
  return await apiFetch(`/guilds/${guildId}/wizard`);
}

export async function saveWizardProgress(guildId, payload) {
  return await apiFetch(`/guilds/${guildId}/wizard/save`, {
    method: 'POST',
    body: payload,
  });
}

export async function applyWizardSettings(guildId, payload) {
  return await apiFetch(`/guilds/${guildId}/wizard/apply`, {
    method: 'POST',
    body: payload,
  });
}

/**
 * --- Owner Control Center API Interfaces (Owner Authorization Enforced Server-Side) ---
 */
export async function fetchOwnerOverview() {
  return await apiFetch('/owner/overview');
}

export async function fetchOwnerBotStatus() {
  return await apiFetch('/owner/bot-status');
}

export async function fetchOwnerGuilds() {
  return await apiFetch('/owner/guilds');
}

export async function fetchOwnerPremium() {
  return await apiFetch('/owner/premium');
}

export async function grantOwnerPremium(payload) {
  return await apiFetch('/owner/premium/grant', {
    method: 'POST',
    body: payload,
  });
}

export async function revokeOwnerPremium(payload) {
  return await apiFetch('/owner/premium/revoke', {
    method: 'POST',
    body: payload,
  });
}

export async function fetchOwnerIntegrations() {
  return await apiFetch('/owner/integrations');
}

export async function fetchOwnerAuditLogs(limit = 50) {
  return await apiFetch(`/owner/audit-log?limit=${limit}`);
}

export async function fetchOwnerConfig() {
  return await apiFetch('/owner/config');
}

export async function updateOwnerConfig(payload) {
  return await apiFetch('/owner/config', {
    method: 'POST',
    body: payload,
  });
}

export async function fetchOwnerDiagnostics() {
  return await apiFetch('/owner/diagnostics');
}

/**
 * --- Music Studio API Client Interfaces ---
 */
export async function fetchMusicPlayback(guildId) {
  return await apiFetch(`/guilds/${guildId}/music/playback`);
}

export async function controlMusicPlayback(guildId, action, value = null) {
  return await apiFetch(`/guilds/${guildId}/music/playback`, {
    method: 'POST',
    body: { action, value },
  });
}

export async function fetchMusicQueue(guildId) {
  return await apiFetch(`/guilds/${guildId}/music/queue`);
}

export async function addMusicTrack(guildId, payload) {
  return await apiFetch(`/guilds/${guildId}/music/queue`, {
    method: 'POST',
    body: payload,
  });
}

export async function removeMusicTrack(guildId, index = null) {
  const query = index !== null ? `?index=${index}` : '';
  return await apiFetch(`/guilds/${guildId}/music/queue${query}`, {
    method: 'DELETE',
  });
}

export async function searchMusicTracks(query, source = 'yt') {
  return await apiFetch(`/guilds/1001/music/search?q=${encodeURIComponent(query)}&source=${source}`);
}

/**
 * --- Guild Premium & Entitlement API Client Interfaces ---
 */
export async function fetchGuildPremiumStatus(guildId) {
  return await apiFetch(`/guilds/${guildId}/premium`);
}

export async function redeemGuildPremiumKey(guildId, key) {
  return await apiFetch(`/guilds/${guildId}/premium/redeem`, {
    method: 'POST',
    body: { key },
  });
}

/**
 * --- Support Ticket System Client Interfaces ---
 */
export async function createTicket(category, subject, description, guildId = null) {
  return await apiFetch('/tickets', {
    method: 'POST',
    body: { category, subject, description, guild_id: guildId },
  });
}

export async function fetchTickets(status = null, userId = null) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (userId) params.set('user_id', userId);
  const q = params.toString() ? '?' + params.toString() : '';
  return await apiFetch(`/tickets${q}`);
}

export async function fetchTicketDetails(ticketId) {
  return await apiFetch(`/tickets/${ticketId}`);
}

export async function replyTicket(ticketId, content) {
  return await apiFetch(`/tickets/${ticketId}/reply`, {
    method: 'POST',
    body: { content },
  });
}

export async function updateTicketStatus(ticketId, status) {
  return await apiFetch(`/tickets/${ticketId}/status`, {
    method: 'POST',
    body: { status },
  });
}

export async function claimTicket(ticketId) {
  return await apiFetch(`/tickets/${ticketId}/claim`, {
    method: 'POST',
  });
}

/**
 * --- Website Staff Management Client Interfaces ---
 */
export async function fetchStaffList() {
  return await apiFetch('/staff/list');
}

export async function manageStaff(action, userId, username = '', roleLevel = 'support') {
  return await apiFetch('/staff/manage', {
    method: 'POST',
    body: { action, user_id: userId, username, role_level: roleLevel },
  });
}

/**
 * --- Web Audio Micro-Sound Effects Engine (Synthesized, OFF by default) ---
 */
class SoundEngine {
  constructor() {
    this.ctx = null;
    this.enabled = localStorage.getItem('kyoka_sound_enabled') === 'true';
    this.volume = parseFloat(localStorage.getItem('kyoka_sound_vol') || '0.25');
  }

  init() {
    if (!this.ctx && typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioCtx();
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
  }

  isSoundEnabled() {
    return this.enabled;
  }

  toggleSound() {
    this.enabled = !this.enabled;
    localStorage.setItem('kyoka_sound_enabled', this.enabled ? 'true' : 'false');
    if (this.enabled) {
      this.init();
      this.playSound('toggle');
    }
    return this.enabled;
  }

  setVolume(vol) {
    this.volume = Math.max(0, Math.min(1, parseFloat(vol)));
    localStorage.setItem('kyoka_sound_vol', this.volume.toString());
  }

  playSound(cue = 'click') {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.ctx) return;

      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      gain.connect(this.ctx.destination);
      osc.connect(gain);

      const baseVol = this.volume;

      if (cue === 'click') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.exponentialRampToValueAtTime(400, now + 0.04);
        gain.gain.setValueAtTime(baseVol * 0.35, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
        osc.start(now);
        osc.stop(now + 0.045);
      } else if (cue === 'toggle') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1100, now);
        osc.frequency.exponentialRampToValueAtTime(650, now + 0.035);
        gain.gain.setValueAtTime(baseVol * 0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.035);
        osc.start(now);
        osc.stop(now + 0.04);
      } else if (cue === 'success') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(523.25, now); // C5
        osc.frequency.setValueAtTime(659.25, now + 0.08); // E5
        osc.frequency.setValueAtTime(783.99, now + 0.16); // G5
        gain.gain.setValueAtTime(baseVol * 0.45, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
        osc.start(now);
        osc.stop(now + 0.3);
      } else if (cue === 'warning') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(180, now + 0.12);
        gain.gain.setValueAtTime(baseVol * 0.25, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.14);
        osc.start(now);
        osc.stop(now + 0.15);
      }
    } catch {
      // Ignore audio synthesis errors gracefully
    }
  }
}

export const soundFX = new SoundEngine();

/**
 * --- Accessibility & Reduced Motion Preferences ---
 */
export function isReducedMotion() {
  if (typeof window === 'undefined') return false;
  const stored = localStorage.getItem('kyoka_reduced_motion');
  if (stored !== null) return stored === 'true';
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function toggleReducedMotion() {
  const current = isReducedMotion();
  const next = !current;
  localStorage.setItem('kyoka_reduced_motion', next ? 'true' : 'false');
  applyReducedMotionPreference();
  return next;
}

export function applyReducedMotionPreference() {
  if (typeof document === 'undefined') return;
  if (isReducedMotion()) {
    document.documentElement.classList.add('reduce-motion');
  } else {
    document.documentElement.classList.remove('reduce-motion');
  }
}

// Automatically apply user reduced-motion preference on page load
if (typeof window !== 'undefined') {
  applyReducedMotionPreference();
}

/**
 * Floating Toast Notification helper
 */
export function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icon = type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ';
  toast.innerHTML = `<span style="font-weight: bold; font-size: 1.1rem;">${icon}</span><span>${message}</span>`;

  container.appendChild(toast);

  if (type === 'success') {
    soundFX.playSound('success');
  } else if (type === 'error') {
    soundFX.playSound('warning');
  }

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

