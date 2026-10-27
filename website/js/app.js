/**
 * KYOKA 3.0 — General Website Interactions
 * Mobile navigation, live stats counter, and global auth button sync
 */
import { getAuthStatus, fetchPublicStats, loginWithDiscord } from './api.js';

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Mobile Menu Toggle
  const navToggle = document.getElementById('nav-toggle');
  const navLinks = document.getElementById('nav-links');

  if (navToggle && navLinks) {
    navToggle.addEventListener('click', () => {
      navLinks.classList.toggle('open');
    });
  }

  // 2. Global Auth State in Header
  const authNavSlot = document.getElementById('auth-nav-slot');
  if (authNavSlot) {
    try {
      const auth = await getAuthStatus();
      if (auth && auth.authenticated && auth.user) {
        const ownerBtn = auth.user.is_owner
          ? `<a href="/owner" class="btn btn-outline btn-sm" style="border-color: var(--purple-vibrant); color: var(--purple-pastel); font-size: 0.8rem; padding: 0.35rem 0.65rem;" title="Aizen Owner Control Center">👑 Owner Suite</a>`
          : '';
        authNavSlot.innerHTML = `
          <div style="display: flex; align-items: center; gap: 0.6rem;">
            ${ownerBtn}
            <a href="/dashboard" class="user-profile-btn" title="Open Dashboard">
              <img src="${auth.user.avatar_url}" alt="${auth.user.username}" class="user-avatar" />
              <span style="font-weight: 600; font-size: 0.9rem;">${auth.user.username}</span>
            </a>
          </div>
        `;
      } else {
        authNavSlot.innerHTML = `
          <button id="nav-login-btn" class="btn btn-discord btn-sm">
            <span>Login with Discord</span>
          </button>
        `;
        document.getElementById('nav-login-btn')?.addEventListener('click', loginWithDiscord);
      }
    } catch {
      // Offline fallback
    }
  }

  // 3. Live Stats Counter on Homepage
  const guildsCounter = document.getElementById('stat-guilds');
  const usersCounter = document.getElementById('stat-users');
  const commandsCounter = document.getElementById('stat-commands');

  if (guildsCounter || usersCounter) {
    try {
      const stats = await fetchPublicStats();
      if (guildsCounter && stats.guilds !== undefined) {
        guildsCounter.textContent = stats.guilds > 0 ? stats.guilds.toLocaleString() : '50+';
      }
      if (usersCounter && stats.users !== undefined) {
        usersCounter.textContent = stats.users > 0 ? stats.users.toLocaleString() : '10,000+';
      }
      if (commandsCounter && stats.commands_available) {
        commandsCounter.textContent = stats.commands_available;
      }
    } catch (e) {
      console.warn('Could not fetch dynamic stats, displaying baseline metrics.');
    }
  }
});
