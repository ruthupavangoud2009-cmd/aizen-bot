/**
 * KYOKA 3.0 Web Client API Interface
 * Handles Discord OAuth2 session verification, guild queries, and settings persistence.
 */

// API Base: defaults to /api or window.KYOKA_API_BASE if custom domain configured
const API_BASE = window.KYOKA_API_BASE || '/api';

/**
 * Standard authenticated fetch helper with credentials and error handling
 */
export async function apiFetch(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`;

  const defaultHeaders = {
    'Accept': 'application/json',
  };

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const fetchOptions = {
    ...options,
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
      return { authenticated: false, status: 401 };
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || data.error || `HTTP ${res.status}`);
    }

    return data;
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

/**
 * Check current logged-in user profile
 */
export async function getAuthStatus() {
  try {
    const data = await apiFetch('/auth/me');
    return data;
  } catch (err) {
    return { authenticated: false, user: null };
  }
}

/**
 * Trigger Discord OAuth2 authorization flow
 */
export function loginWithDiscord() {
  window.location.href = `${API_BASE}/auth/login`;
}

/**
 * Log out and clear session cookie
 */
export async function logoutUser() {
  try {
    await apiFetch('/auth/logout', { method: 'POST' });
  } catch (err) {
    console.warn('Logout API notification failed, redirecting anyway:', err);
  }
  window.location.href = '/dashboard.html';
}

/**
 * Fetch all Discord servers manageable by the authenticated user
 */
export async function fetchGuilds(forceRefresh = false) {
  const query = forceRefresh ? '?refresh=1' : '';
  const res = await apiFetch(`/guilds${query}`);
  return res.guilds || [];
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
    return await apiFetch('/stats');
  } catch {
    return { guilds: 0, users: 0, commands_available: 50, status: 'online' };
  }
}

/**
 * Official command inventory
 */
export async function fetchOfficialCommands() {
  try {
    const res = await apiFetch('/commands');
    return res.commands || [];
  } catch {
    return [];
  }
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

