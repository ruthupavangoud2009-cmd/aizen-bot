/**
 * KYOKA 3.0 — Guided Server Onboarding & Setup Wizard
 * Inspired by Koya Bot's effortless setup flow, crafted in Aizen Edition aesthetic.
 * 9 Resumable Steps with Server-Side State Synchronization & Atomic Apply.
 */

import {
  fetchWizardState,
  saveWizardProgress,
  applyWizardSettings,
  testEventSimulation,
  showToast,
} from './api.js';

export class SetupWizard {
  constructor(options = {}) {
    this.guilds = options.guilds || [];
    this.currentGuild = options.selectedGuild || null;
    this.onFinish = options.onFinish || (() => {});
    this.onClose = options.onClose || (() => {});
    this.currentStep = 1;
    this.maxStep = 9;
    this.draft = {};
    this.isCompleted = false;
    this.container = null;
    this.stepNames = [
      'Server Check',
      'Welcome & Leave',
      'Verification Gate',
      'Security & Automod',
      'Support Tickets',
      'Leveling & Giveaways',
      'Roles & Logs',
      'AI & Audio',
      'Review & Apply',
    ];
  }

  /**
   * Launch and mount the wizard modal
   */
  async open(targetGuildId = null) {
    if (targetGuildId) {
      this.currentGuild = this.guilds.find(g => g.id === targetGuildId) || {
        id: targetGuildId,
        name: 'Discord Server',
        bot_installed: true,
      };
    } else if (!this.currentGuild && this.guilds.length > 0) {
      this.currentGuild = this.guilds[0];
    }

    this.initDefaultDraft();
    this.buildModal();
    this.renderStep();

    if (this.currentGuild?.id) {
      // Non-blocking background fetch so modal renders instantly with zero blank lag
      this.loadPersistedState(this.currentGuild.id).then(() => {
        if (this.container) this.renderStep();
      }).catch(() => {});
    }
  }

  /**
   * Fetch saved progress from backend
   */
  async loadPersistedState(guildId) {
    try {
      const res = await fetchWizardState(guildId);
      const state = res.wizard_state || {};
      this.draft = state.draft || {};
      this.isCompleted = !!state.is_completed;
      // If resuming an incomplete session, resume from saved step or 1
      if (state.current_step && state.current_step >= 1 && state.current_step <= 9) {
        this.currentStep = state.current_step;
      }
      this.initDefaultDraft();
    } catch (err) {
      console.warn('Could not load wizard state:', err);
      this.initDefaultDraft();
    }
  }

  /**
   * Ensure draft has sensible baseline defaults
   */
  initDefaultDraft() {
    if (!this.draft.welcome) {
      this.draft.welcome = {
        enabled: true,
        channel_id: '',
        message: 'Welcome {user} to {server}! You are member #{member_count}. Check out our guidelines to get started.',
        leave_enabled: true,
        leave_channel_id: '',
        leave_message: '{user} has departed from {server}. We now have {member_count} members.',
        dm_enabled: false,
      };
    }
    if (!this.draft.verification) {
      this.draft.verification = {
        enabled: true,
        channel_id: '',
        role_id: '',
        method: 'button',
        timeout_seconds: 300,
        min_account_age_days: 0,
        unverified_role_id: '',
      };
    }
    if (!this.draft.security) {
      this.draft.security = {
        antinuke_enabled: false,
        punishment: 'strip_roles',
        automod_spam: true,
        automod_mentions: true,
        automod_invites: true,
        log_channel_id: '',
        confirm_destructive: false,
      };
    }
    if (!this.draft.tickets) {
      this.draft.tickets = {
        enabled: true,
        category_id: '',
        support_role_id: '',
        log_channel_id: '',
        panel_name: 'Kyoka Support Portal',
        button_label: 'Open Ticket',
      };
    }
    if (!this.draft.leveling) {
      this.draft.leveling = {
        enabled: true,
        xp_rate: 1.0,
        channel_id: '',
        message: 'Congratulations {user}! You advanced to **Level {level}**!',
        giveaways_enabled: true,
      };
    }
    if (!this.draft.roles_logs) {
      this.draft.roles_logs = {
        human_role_id: '',
        bot_role_id: '',
        mod_channel_id: '',
        member_channel_id: '',
        message_channel_id: '',
      };
    }
    if (!this.draft.optional_modules) {
      this.draft.optional_modules = {
        ai_enabled: true,
        ai_personality: 'aizen',
        music_247: false,
        default_volume: 100,
      };
    }
  }

  buildModal() {
    // Remove any existing wizard modal
    const existing = document.getElementById('kyoka-wizard-modal');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'kyoka-wizard-modal';
    overlay.className = 'wizard-backdrop';
    overlay.innerHTML = `
      <div class="wizard-window" style="display: flex !important; opacity: 1 !important; transform: none !important;">
        <!-- Wizard Header -->
        <div class="wizard-header">
          <div class="wizard-title-group">
            <span class="wizard-brand-badge">⚡ SETUP ASSISTANT</span>
            <h2 class="wizard-title">Welcome to KYOKA 3.0</h2>
            <p class="wizard-subtitle">Let's configure your server in a few simple steps.</p>
          </div>
          <button id="wizard-close-btn" class="wizard-close-btn" title="Exit Setup Wizard">✕</button>
        </div>

        <!-- Stepper Navigation Indicator -->
        <div class="wizard-stepper" id="wizard-stepper">
          ${this.stepNames.map((name, i) => {
            const stepNum = i + 1;
            return `
              <div class="wizard-step-node ${stepNum === this.currentStep ? 'active' : ''} ${stepNum < this.currentStep ? 'completed' : ''}" data-step="${stepNum}">
                <div class="wizard-step-circle">
                  ${stepNum < this.currentStep ? '✓' : stepNum}
                </div>
                <span class="wizard-step-label">${name}</span>
              </div>
            `;
          }).join('')}
        </div>

        <!-- Dynamic Step Body -->
        <div class="wizard-body" id="wizard-step-body">
          <!-- Step form inserted here -->
        </div>

        <!-- Wizard Navigation Footer -->
        <div class="wizard-footer">
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button id="wizard-exit-btn" class="btn btn-outline btn-sm" style="border-color: rgba(239, 68, 68, 0.4); color: #F87171;" title="Exit Setup Wizard">
              ✕ Exit
            </button>
            <button id="wizard-back-btn" class="btn btn-outline btn-sm">
              ← Back
            </button>
          </div>
          <div class="wizard-footer-right">
            <button id="wizard-save-btn" class="btn btn-secondary btn-sm" title="Save draft progress to PostgreSQL">
              💾 Save Progress
            </button>
            <button id="wizard-skip-btn" class="btn btn-outline btn-sm" style="border-color: rgba(168, 85, 247, 0.4); color: var(--text-muted);">
              Skip Step
            </button>
            <button id="wizard-next-btn" class="btn btn-primary btn-sm">
              Next Step →
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    this.container = overlay;

    // Attach Header and Footer Listeners
    overlay.querySelector('#wizard-close-btn')?.addEventListener('click', () => this.close());
    overlay.querySelector('#wizard-exit-btn')?.addEventListener('click', () => this.close());
    overlay.querySelector('#wizard-back-btn')?.addEventListener('click', () => this.prevStep());
    overlay.querySelector('#wizard-skip-btn')?.addEventListener('click', () => this.skipStep());
    overlay.querySelector('#wizard-save-btn')?.addEventListener('click', () => this.saveDraft(false));
    overlay.querySelector('#wizard-next-btn')?.addEventListener('click', () => this.nextStep());

    // Click outside backdrop to close
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) this.close();
    });

    // ESC key to dismiss modal
    this.keyHandler = (e) => {
      if (e.key === 'Escape') this.close();
    };
    window.addEventListener('keydown', this.keyHandler);
  }

  updateStepper() {
    if (!this.container) return;
    const nodes = this.container.querySelectorAll('.wizard-step-node');
    nodes.forEach((node, idx) => {
      const stepNum = idx + 1;
      node.classList.remove('active', 'completed');
      if (stepNum === this.currentStep) {
        node.classList.add('active');
        node.querySelector('.wizard-step-circle').textContent = stepNum;
      } else if (stepNum < this.currentStep) {
        node.classList.add('completed');
        node.querySelector('.wizard-step-circle').textContent = '✓';
      } else {
        node.querySelector('.wizard-step-circle').textContent = stepNum;
      }
    });

    const backBtn = this.container.querySelector('#wizard-back-btn');
    const skipBtn = this.container.querySelector('#wizard-skip-btn');
    const nextBtn = this.container.querySelector('#wizard-next-btn');

    if (backBtn) backBtn.disabled = this.currentStep === 1;
    if (skipBtn) {
      // Step 1 and Step 9 cannot be skipped
      skipBtn.style.display = (this.currentStep === 1 || this.currentStep === 9) ? 'none' : 'inline-flex';
    }
    if (nextBtn) {
      if (this.currentStep === 9) {
        nextBtn.textContent = '🚀 Confirm & Apply Setup';
        nextBtn.className = 'btn btn-primary btn-sm wizard-apply-btn';
      } else {
        nextBtn.textContent = 'Next Step →';
        nextBtn.className = 'btn btn-primary btn-sm';
      }
    }
  }

  renderStep() {
    this.updateStepper();
    const body = this.container?.querySelector('#wizard-step-body');
    if (!body) return;
    body.style.display = 'block';
    body.style.opacity = '1';

    try {
      switch (this.currentStep) {
        case 1:
          this.renderStep1(body);
          break;
        case 2:
          this.renderStep2(body);
          break;
        case 3:
          this.renderStep3(body);
          break;
        case 4:
          this.renderStep4(body);
          break;
        case 5:
          this.renderStep5(body);
          break;
        case 6:
          this.renderStep6(body);
          break;
        case 7:
          this.renderStep7(body);
          break;
        case 8:
          this.renderStep8(body);
          break;
        case 9:
          this.renderStep9(body);
          break;
      }
    } catch (err) {
      console.error('Wizard render step error:', err);
      body.innerHTML = `
        <div class="wizard-step-card" style="text-align: center; padding: 2.5rem 1.5rem;">
          <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">⚠️</div>
          <h3 style="color: #fca5a5; margin-bottom: 0.5rem;">Step Initialization Notice</h3>
          <p style="color: var(--text-dim); font-size: 0.9rem; max-width: 480px; margin: 0 auto 1.5rem;">
            ${err.message || 'Error initializing step controls.'}
          </p>
          <button id="retry-wizard-step-btn" class="btn btn-primary btn-sm">Retry Step</button>
        </div>
      `;
      body.querySelector('#retry-wizard-step-btn')?.addEventListener('click', () => this.renderStep());
    }
  }

  // =========================================================================
  // STEP 1: Select Your Server & Verify Bot Presence
  // =========================================================================
  renderStep1(body) {
    const isInstalled = this.currentGuild?.bot_installed !== false;
    const inviteUrl = this.currentGuild?.invite_url ||
      'https://discord.com/oauth2/authorize?client_id=1474805799988756673&permissions=8&scope=bot%20applications.commands';

    const guildsList = (Array.isArray(this.guilds) && this.guilds.length > 0)
      ? this.guilds
      : (this.currentGuild ? [this.currentGuild] : [{ id: '1515995663903752213', name: 'Kyoka Server', bot_installed: true }]);

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 1 OF 9</span>
          <h3>Select & Verify Server Connection</h3>
          <p>Choose the Discord server you wish to configure. KYOKA requires verified manager permissions.</p>
        </div>

        <div class="wizard-form-group">
          <label class="wizard-label">Target Discord Server</label>
          <select id="w-guild-select" class="form-input wizard-select">
            ${guildsList.map(g => `
              <option value="${g.id}" ${this.currentGuild?.id === g.id ? 'selected' : ''}>
                ${g.name} ${g.bot_installed ? ' (KYOKA Active)' : ' (Invite Required)'}
              </option>
            `).join('')}
          </select>
        </div>

        <div class="wizard-server-status-box ${isInstalled ? 'status-connected' : 'status-missing'}">
          <div class="status-icon">${isInstalled ? '🛡️' : '⚠️'}</div>
          <div class="status-details">
            <h4 style="color: ${isInstalled ? 'var(--emerald-accent)' : 'var(--amber-accent)'};">
              ${isInstalled ? 'KYOKA is present in this server' : 'KYOKA is not yet added to this server'}
            </h4>
            <p>
              ${isInstalled
                ? 'Bot permissions and WebSocket connection verified. You can proceed with rapid configuration.'
                : 'KYOKA needs to join your server before it can manage roles, channels, and security gates.'}
            </p>
          </div>
          ${!isInstalled ? `
            <a href="${inviteUrl}" target="_blank" class="btn btn-primary btn-sm" style="white-space: nowrap;">
              Invite KYOKA Now ↗
            </a>
          ` : `
            <span class="badge badge-installed">Ready to Configure</span>
          `}
        </div>

        <div class="wizard-info-callout">
          <strong>Security Note:</strong> KYOKA uses standard Discord OAuth2 and requires <code>Administrator</code> or <code>Manage Guild</code> permissions to monitor raid vectors and enforce verification.
        </div>
      </div>
    `;

    body.querySelector('#w-guild-select')?.addEventListener('change', async (e) => {
      const gid = e.target.value;
      this.currentGuild = this.guilds.find(g => g.id === gid) || { id: gid, name: 'Server' };
      await this.loadPersistedState(gid);
      this.renderStep1(body);
    });
  }

  // =========================================================================
  // STEP 2: Welcome and Leave
  // =========================================================================
  renderStep2(body) {
    const w = this.draft.welcome;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 2 OF 9</span>
          <h3>Welcome & Farewell Dispatcher</h3>
          <p>Greet new members with personalized embeds and track departing users seamlessly.</p>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <label class="wizard-label" style="margin-bottom: 0;">Welcome Announcements</label>
              <label class="switch">
                <input type="checkbox" id="w-welcome-en" ${w.enabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
            <label class="wizard-sublabel">Welcome Channel (Snowflake ID)</label>
            <input type="text" id="w-welcome-ch" class="form-input" placeholder="e.g. 110022334455667788" value="${w.channel_id || ''}" />
          </div>

          <div class="wizard-form-group">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <label class="wizard-label" style="margin-bottom: 0;">Leave Announcements</label>
              <label class="switch">
                <input type="checkbox" id="w-leave-en" ${w.leave_enabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
            <label class="wizard-sublabel">Leave Channel (Snowflake ID)</label>
            <input type="text" id="w-leave-ch" class="form-input" placeholder="e.g. 110022334455667788" value="${w.leave_channel_id || ''}" />
          </div>
        </div>

        <div class="wizard-form-group">
          <label class="wizard-label">Welcome Message Template</label>
          <textarea id="w-welcome-msg" class="form-input" rows="3">${w.message || ''}</textarea>
          <div class="wizard-tag-bar">
            <span>Supported variables:</span>
            <code>{user}</code> <code>{server}</code> <code>{member_count}</code>
          </div>
        </div>

        <!-- Live Preview & Test Box -->
        <div class="wizard-preview-card">
          <div class="preview-header">
            <span>✨ LIVE EMBED PREVIEW</span>
            <button id="w-test-sim-btn" class="btn btn-outline btn-xs">
              Simulate Test Event
            </button>
          </div>
          <div id="w-preview-content" class="preview-message-box">
            ${(w.message || '')
              .replace(/{user}/g, '<strong>@NewTraveler</strong>')
              .replace(/{server}/g, `<strong>${this.currentGuild?.name || 'Kyoka Citadel'}</strong>`)
              .replace(/{member_count}/g, '<strong>1,420</strong>')}
          </div>
          <div id="w-sim-status" class="preview-note">Click "Simulate Test Event" to test safe backend dispatch without spamming members.</div>
        </div>
      </div>
    `;

    // Interactive updates
    const updatePreview = () => {
      const msg = body.querySelector('#w-welcome-msg')?.value || '';
      w.message = msg;
      const preview = body.querySelector('#w-preview-content');
      if (preview) {
        preview.innerHTML = msg
          .replace(/{user}/g, '<strong>@NewTraveler</strong>')
          .replace(/{server}/g, `<strong>${this.currentGuild?.name || 'Kyoka Citadel'}</strong>`)
          .replace(/{member_count}/g, '<strong>1,420</strong>');
      }
    };

    body.querySelector('#w-welcome-en')?.addEventListener('change', (e) => { w.enabled = e.target.checked; });
    body.querySelector('#w-welcome-ch')?.addEventListener('input', (e) => { w.channel_id = e.target.value.trim(); });
    body.querySelector('#w-leave-en')?.addEventListener('change', (e) => { w.leave_enabled = e.target.checked; });
    body.querySelector('#w-leave-ch')?.addEventListener('input', (e) => { w.leave_channel_id = e.target.value.trim(); });
    body.querySelector('#w-welcome-msg')?.addEventListener('input', updatePreview);

    body.querySelector('#w-test-sim-btn')?.addEventListener('click', async () => {
      const statusEl = body.querySelector('#w-sim-status');
      if (statusEl) statusEl.textContent = 'Simulating backend dispatch...';
      try {
        const res = await testEventSimulation(this.currentGuild.id, 'welcome');
        if (statusEl) {
          statusEl.innerHTML = `<span style="color: var(--emerald-accent);">✓ Simulation Passed:</span> ${res.simulated_message}`;
        }
      } catch (err) {
        if (statusEl) {
          statusEl.innerHTML = `<span style="color: var(--rose-accent);">Error:</span> ${err.message}`;
        }
      }
    });
  }

  // =========================================================================
  // STEP 3: Verification Gate
  // =========================================================================
  renderStep3(body) {
    const v = this.draft.verification;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 3 OF 9</span>
          <h3>Member Verification Gate</h3>
          <p>Protect your server from raid bots with one-click verification or interactive captcha gates.</p>
        </div>

        <div class="setting-row" style="padding: 1rem 0; border-bottom: 1px solid var(--border-subtle); margin-bottom: 1.25rem;">
          <div class="setting-info">
            <label style="color: var(--purple-white); font-weight: 700;">Enable Verification Gate</label>
            <p>Require incoming members to verify before unlocking server channels.</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="w-v-en" ${v.enabled ? 'checked' : ''} />
            <span class="slider"></span>
          </label>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <label class="wizard-label">Verification Channel ID</label>
            <input type="text" id="w-v-ch" class="form-input" placeholder="e.g. 110022334455667788" value="${v.channel_id || ''}" />
            <span class="wizard-hint">The dedicated channel where the verification panel will be posted.</span>
          </div>

          <div class="wizard-form-group">
            <label class="wizard-label">Verified Role ID</label>
            <input type="text" id="w-v-role" class="form-input" placeholder="e.g. 110022334455667788" value="${v.role_id || ''}" />
            <span class="wizard-hint">Role awarded immediately once the member completes verification.</span>
          </div>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <label class="wizard-label">Verification Method</label>
            <select id="w-v-method" class="form-input wizard-select">
              <option value="button" ${v.method === 'button' ? 'selected' : ''}>One-Click Button (Fast & Simple)</option>
              <option value="captcha" ${v.method === 'captcha' ? 'selected' : ''}>Graphic Captcha Challenge (High Security)</option>
            </select>
          </div>

          <div class="wizard-form-group">
            <label class="wizard-label">Minimum Account Age (Days)</label>
            <input type="number" id="w-v-age" class="form-input" min="0" max="365" value="${v.min_account_age_days || 0}" />
            <span class="wizard-hint">Block newly created Discord accounts under this threshold (0 = disable).</span>
          </div>
        </div>

        <div class="wizard-warning-box">
          <span style="font-size: 1.25rem;">⚠️</span>
          <div>
            <strong>Role Hierarchy Rule:</strong> Ensure KYOKA's highest role is positioned <em>above</em> the Verified Role in Discord Server Settings &gt; Roles. KYOKA will never lock channels without explicit confirmation.
          </div>
        </div>
      </div>
    `;

    body.querySelector('#w-v-en')?.addEventListener('change', (e) => { v.enabled = e.target.checked; });
    body.querySelector('#w-v-ch')?.addEventListener('input', (e) => { v.channel_id = e.target.value.trim(); });
    body.querySelector('#w-v-role')?.addEventListener('input', (e) => { v.role_id = e.target.value.trim(); });
    body.querySelector('#w-v-method')?.addEventListener('change', (e) => { v.method = e.target.value; });
    body.querySelector('#w-v-age')?.addEventListener('input', (e) => { v.min_account_age_days = parseInt(e.target.value) || 0; });
  }

  // =========================================================================
  // STEP 4: Moderation & Security
  // =========================================================================
  renderStep4(body) {
    const sec = this.draft.security;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 4 OF 9</span>
          <h3>Moderation & Anti-Nuke Defense</h3>
          <p>Deploy real-time threat mitigation to thwart token raids, unauthorized kicks, and malicious bans.</p>
        </div>

        <div class="wizard-form-group">
          <label class="wizard-label">Moderation Audit Log Channel (Snowflake ID)</label>
          <input type="text" id="w-sec-log" class="form-input" placeholder="e.g. 110022334455667788" value="${sec.log_channel_id || ''}" />
        </div>

        <div style="background: rgba(26, 12, 50, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1.5rem;">
          <h4 style="color: var(--purple-pastel); font-size: 0.95rem; margin-bottom: 0.75rem; font-weight: 700;">AUTOMOD FILTERS</h4>
          <div style="display: flex; flex-direction: column; gap: 0.75rem;">
            <label class="wizard-checkbox-item">
              <input type="checkbox" id="w-am-spam" ${sec.automod_spam ? 'checked' : ''} />
              <span><strong>Anti-Spam Rate Limiter:</strong> Automatically mute members sending rapid repeated messages.</span>
            </label>
            <label class="wizard-checkbox-item">
              <input type="checkbox" id="w-am-mentions" ${sec.automod_mentions ? 'checked' : ''} />
              <span><strong>Mass-Mention Shield:</strong> Delete messages pinging more than 5 users simultaneously.</span>
            </label>
            <label class="wizard-checkbox-item">
              <input type="checkbox" id="w-am-invites" ${sec.automod_invites ? 'checked' : ''} />
              <span><strong>Discord Invite Filter:</strong> Intercept and remove unsolicited server invites.</span>
            </label>
          </div>
        </div>

        <div style="background: rgba(36, 12, 74, 0.6); border: 1px solid var(--border-active); border-radius: var(--radius-md); padding: 1.25rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
            <div>
              <h4 style="color: var(--purple-white); font-size: 1rem; font-weight: 700;">Supreme Anti-Nuke Multi-Shield</h4>
              <p style="color: var(--text-muted); font-size: 0.85rem;">Monitors unauthorized channel deletions, mass kicks, and role stripping.</p>
            </div>
            <label class="switch">
              <input type="checkbox" id="w-an-en" ${sec.antinuke_enabled ? 'checked' : ''} />
              <span class="slider"></span>
            </label>
          </div>

          <div class="wizard-grid-2" style="margin-top: 1rem;">
            <div class="wizard-form-group">
              <label class="wizard-label">Offender Punishment</label>
              <select id="w-an-pun" class="form-input wizard-select">
                <option value="strip_roles" ${sec.punishment === 'strip_roles' ? 'selected' : ''}>Strip All Administrative Roles (Safe Default)</option>
                <option value="kick" ${sec.punishment === 'kick' ? 'selected' : ''}>Kick From Server</option>
                <option value="ban" ${sec.punishment === 'ban' ? 'selected' : ''}>Permanent Ban</option>
              </select>
            </div>
            <div class="wizard-form-group" style="display: flex; align-items: flex-end;">
              <label class="wizard-checkbox-item" style="margin-bottom: 0.5rem;">
                <input type="checkbox" id="w-an-confirm" ${sec.confirm_destructive ? 'checked' : ''} />
                <span style="font-size: 0.82rem; color: var(--amber-accent);">I understand high-impact punishments trigger on malicious actions.</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    `;

    body.querySelector('#w-sec-log')?.addEventListener('input', (e) => { sec.log_channel_id = e.target.value.trim(); });
    body.querySelector('#w-am-spam')?.addEventListener('change', (e) => { sec.automod_spam = e.target.checked; });
    body.querySelector('#w-am-mentions')?.addEventListener('change', (e) => { sec.automod_mentions = e.target.checked; });
    body.querySelector('#w-am-invites')?.addEventListener('change', (e) => { sec.automod_invites = e.target.checked; });
    body.querySelector('#w-an-en')?.addEventListener('change', (e) => { sec.antinuke_enabled = e.target.checked; });
    body.querySelector('#w-an-pun')?.addEventListener('change', (e) => { sec.punishment = e.target.value; });
    body.querySelector('#w-an-confirm')?.addEventListener('change', (e) => { sec.confirm_destructive = e.target.checked; });
  }

  // =========================================================================
  // STEP 5: Support Tickets
  // =========================================================================
  renderStep5(body) {
    const tk = this.draft.tickets;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 5 OF 9</span>
          <h3>Support Ticket Gateway</h3>
          <p>Empower members to open private support rooms with staff role routing and HTML transcripts.</p>
        </div>

        <div class="setting-row" style="padding: 1rem 0; border-bottom: 1px solid var(--border-subtle); margin-bottom: 1.25rem;">
          <div class="setting-info">
            <label style="color: var(--purple-white); font-weight: 700;">Enable Ticket System</label>
            <p>Deploy interactive ticket panels in designated community channels.</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="w-tk-en" ${tk.enabled ? 'checked' : ''} />
            <span class="slider"></span>
          </label>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <label class="wizard-label">Ticket Category ID</label>
            <input type="text" id="w-tk-cat" class="form-input" placeholder="Discord Category Snowflake" value="${tk.category_id || ''}" />
            <span class="wizard-hint">Discord category under which new tickets will spawn.</span>
          </div>

          <div class="wizard-form-group">
            <label class="wizard-label">Support Staff Role ID</label>
            <input type="text" id="w-tk-role" class="form-input" placeholder="Staff Role Snowflake" value="${tk.support_role_id || ''}" />
            <span class="wizard-hint">Role automatically granted access to private member tickets.</span>
          </div>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <label class="wizard-label">Transcript Channel ID</label>
            <input type="text" id="w-tk-trans" class="form-input" placeholder="Transcript Channel Snowflake" value="${tk.log_channel_id || ''}" />
            <span class="wizard-hint">Where saved conversation transcripts are archived on ticket close.</span>
          </div>

          <div class="wizard-form-group">
            <label class="wizard-label">Button Callout Text</label>
            <input type="text" id="w-tk-lbl" class="form-input" value="${tk.button_label || 'Open Ticket'}" />
          </div>
        </div>

        <!-- Ticket Preview -->
        <div class="wizard-preview-card">
          <div class="preview-header">
            <span>🎫 TICKET PANEL PREVIEW</span>
          </div>
          <div style="background: rgba(18, 9, 36, 0.9); border-left: 4px solid var(--purple-glow); padding: 1.25rem; border-radius: 4px;">
            <h5 style="color: var(--purple-white); font-size: 1.05rem; margin-bottom: 0.4rem;">${tk.panel_name || 'Kyoka Support Portal'}</h5>
            <p style="color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1rem;">Click the button below to open a private assistance ticket with our moderation staff.</p>
            <button class="btn btn-primary btn-sm" style="pointer-events: none;">
              📩 ${tk.button_label || 'Open Ticket'}
            </button>
          </div>
        </div>
      </div>
    `;

    body.querySelector('#w-tk-en')?.addEventListener('change', (e) => { tk.enabled = e.target.checked; });
    body.querySelector('#w-tk-cat')?.addEventListener('input', (e) => { tk.category_id = e.target.value.trim(); });
    body.querySelector('#w-tk-role')?.addEventListener('input', (e) => { tk.support_role_id = e.target.value.trim(); });
    body.querySelector('#w-tk-trans')?.addEventListener('input', (e) => { tk.log_channel_id = e.target.value.trim(); });
    body.querySelector('#w-tk-lbl')?.addEventListener('input', (e) => {
      tk.button_label = e.target.value;
      const btn = body.querySelector('.preview-header + div button');
      if (btn) btn.innerHTML = `📩 ${e.target.value}`;
    });
  }

  // =========================================================================
  // STEP 6: Leveling & Giveaways
  // =========================================================================
  renderStep6(body) {
    const lvl = this.draft.leveling;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 6 OF 9</span>
          <h3>Leveling, XP & Giveaways</h3>
          <p>Gamify member engagement with message XP, rank cards, and fair giveaway raffles.</p>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <label class="wizard-label" style="margin-bottom: 0;">Leveling Engine</label>
              <label class="switch">
                <input type="checkbox" id="w-lvl-en" ${lvl.enabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
            <label class="wizard-sublabel">Announcement Channel ID</label>
            <input type="text" id="w-lvl-ch" class="form-input" placeholder="e.g. 110022334455667788 (Leave blank for current channel)" value="${lvl.channel_id || ''}" />
          </div>

          <div class="wizard-form-group">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <label class="wizard-label" style="margin-bottom: 0;">Giveaway Engine</label>
              <label class="switch">
                <input type="checkbox" id="w-gw-en" ${lvl.giveaways_enabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
            <label class="wizard-sublabel">XP Multiplier Rate</label>
            <select id="w-lvl-rate" class="form-input wizard-select">
              <option value="0.5" ${lvl.xp_rate === 0.5 ? 'selected' : ''}>0.5x (Slow Progression)</option>
              <option value="1.0" ${lvl.xp_rate === 1.0 ? 'selected' : ''}>1.0x (Standard Default)</option>
              <option value="1.5" ${lvl.xp_rate === 1.5 ? 'selected' : ''}>1.5x (Accelerated Growth)</option>
              <option value="2.0" ${lvl.xp_rate === 2.0 ? 'selected' : ''}>2.0x (Double XP Weekend)</option>
            </select>
          </div>
        </div>

        <div class="wizard-form-group">
          <label class="wizard-label">Level-Up Milestone Message</label>
          <input type="text" id="w-lvl-msg" class="form-input" value="${lvl.message || ''}" />
          <div class="wizard-tag-bar">
            <span>Variables:</span>
            <code>{user}</code> <code>{level}</code>
          </div>
        </div>
      </div>
    `;

    body.querySelector('#w-lvl-en')?.addEventListener('change', (e) => { lvl.enabled = e.target.checked; });
    body.querySelector('#w-lvl-ch')?.addEventListener('input', (e) => { lvl.channel_id = e.target.value.trim(); });
    body.querySelector('#w-gw-en')?.addEventListener('change', (e) => { lvl.giveaways_enabled = e.target.checked; });
    body.querySelector('#w-lvl-rate')?.addEventListener('change', (e) => { lvl.xp_rate = parseFloat(e.target.value) || 1.0; });
    body.querySelector('#w-lvl-msg')?.addEventListener('input', (e) => { lvl.message = e.target.value; });
  }

  // =========================================================================
  // STEP 7: Roles & Audit Logging
  // =========================================================================
  renderStep7(body) {
    const rl = this.draft.roles_logs;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 7 OF 9</span>
          <h3>Auto-Roles & Modular Audit Logs</h3>
          <p>Automate role assignments upon join and direct event audits to dedicated oversight channels.</p>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <label class="wizard-label">Human Member Auto-Role</label>
            <input type="text" id="w-rl-human" class="form-input" placeholder="Role Snowflake ID" value="${rl.human_role_id || ''}" />
            <span class="wizard-hint">Assigned automatically to real members upon joining.</span>
          </div>

          <div class="wizard-form-group">
            <label class="wizard-label">Bot Auto-Role</label>
            <input type="text" id="w-rl-bot" class="form-input" placeholder="Role Snowflake ID" value="${rl.bot_role_id || ''}" />
            <span class="wizard-hint">Assigned automatically to newly invited bots.</span>
          </div>
        </div>

        <h4 style="color: var(--purple-pastel); font-size: 0.95rem; margin: 1.5rem 0 0.75rem; font-weight: 700;">AUDIT LOG ROUTING</h4>

        <div class="wizard-grid-3">
          <div class="wizard-form-group">
            <label class="wizard-sublabel">Mod Action Logs</label>
            <input type="text" id="w-rl-mod-ch" class="form-input" placeholder="Channel Snowflake" value="${rl.mod_channel_id || ''}" />
          </div>

          <div class="wizard-form-group">
            <label class="wizard-sublabel">Member Join/Leave Logs</label>
            <input type="text" id="w-rl-mem-ch" class="form-input" placeholder="Channel Snowflake" value="${rl.member_channel_id || ''}" />
          </div>

          <div class="wizard-form-group">
            <label class="wizard-sublabel">Message Edit/Delete Logs</label>
            <input type="text" id="w-rl-msg-ch" class="form-input" placeholder="Channel Snowflake" value="${rl.message_channel_id || ''}" />
          </div>
        </div>
      </div>
    `;

    body.querySelector('#w-rl-human')?.addEventListener('input', (e) => { rl.human_role_id = e.target.value.trim(); });
    body.querySelector('#w-rl-bot')?.addEventListener('input', (e) => { rl.bot_role_id = e.target.value.trim(); });
    body.querySelector('#w-rl-mod-ch')?.addEventListener('input', (e) => { rl.mod_channel_id = e.target.value.trim(); });
    body.querySelector('#w-rl-mem-ch')?.addEventListener('input', (e) => { rl.member_channel_id = e.target.value.trim(); });
    body.querySelector('#w-rl-msg-ch')?.addEventListener('input', (e) => { rl.message_channel_id = e.target.value.trim(); });
  }

  // =========================================================================
  // STEP 8: Optional Modules (AI & Audio)
  // =========================================================================
  renderStep8(body) {
    const opt = this.draft.optional_modules;

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 8 OF 9</span>
          <h3>Intelligence & High-Fidelity Audio</h3>
          <p>Choose your conversational AI persona and voice settings. These can be adjusted anytime.</p>
        </div>

        <div class="wizard-grid-2">
          <div class="wizard-form-group">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <label class="wizard-label" style="margin-bottom: 0;">Neural AI Chat Engine</label>
              <label class="switch">
                <input type="checkbox" id="w-opt-ai-en" ${opt.ai_enabled ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
            <label class="wizard-sublabel">Persona Tone</label>
            <select id="w-opt-ai-pers" class="form-input wizard-select">
              <option value="aizen" ${opt.ai_personality === 'aizen' ? 'selected' : ''}>Aizen (Philosophical, Composed & Strategic)</option>
              <option value="kyoka" ${opt.ai_personality === 'kyoka' ? 'selected' : ''}>Kyoka (Analytical, Precise & Protective)</option>
              <option value="playful" ${opt.ai_personality === 'playful' ? 'selected' : ''}>Playful (Energetic & Humorous)</option>
              <option value="formal" ${opt.ai_personality === 'formal' ? 'selected' : ''}>Formal (Neutral Moderation Assistant)</option>
            </select>
          </div>

          <div class="wizard-form-group">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <label class="wizard-label" style="margin-bottom: 0;">24/7 Voice Channel Stay</label>
              <label class="switch">
                <input type="checkbox" id="w-opt-m247" ${opt.music_247 ? 'checked' : ''} />
                <span class="slider"></span>
              </label>
            </div>
            <label class="wizard-sublabel">Default Playback Volume</label>
            <input type="range" id="w-opt-vol" min="10" max="150" value="${opt.default_volume || 100}" style="width: 100%; accent-color: var(--purple-primary);" />
            <span id="w-vol-val" style="font-size: 0.85rem; color: var(--purple-light);">${opt.default_volume || 100}%</span>
          </div>
        </div>

        <div class="wizard-info-callout">
          <strong>Need to skip?</strong> You can skip this step or fine-tune custom rules and YouTube/Spotify audio filters later in the main dashboard.
        </div>
      </div>
    `;

    body.querySelector('#w-opt-ai-en')?.addEventListener('change', (e) => { opt.ai_enabled = e.target.checked; });
    body.querySelector('#w-opt-ai-pers')?.addEventListener('change', (e) => { opt.ai_personality = e.target.value; });
    body.querySelector('#w-opt-m247')?.addEventListener('change', (e) => { opt.music_247 = e.target.checked; });
    body.querySelector('#w-opt-vol')?.addEventListener('input', (e) => {
      opt.default_volume = parseInt(e.target.value) || 100;
      const vEl = body.querySelector('#w-vol-val');
      if (vEl) vEl.textContent = `${e.target.value}%`;
    });
  }

  // =========================================================================
  // STEP 9: Review & Apply
  // =========================================================================
  renderStep9(body) {
    const w = this.draft.welcome || {};
    const v = this.draft.verification || {};
    const sec = this.draft.security || {};
    const tk = this.draft.tickets || {};
    const lvl = this.draft.leveling || {};
    const rl = this.draft.roles_logs || {};
    const opt = this.draft.optional_modules || {};

    body.innerHTML = `
      <div class="wizard-step-card">
        <div class="wizard-step-header">
          <span class="step-counter">STEP 9 OF 9</span>
          <h3>Review & Apply Server Settings</h3>
          <p>Carefully verify your configurations below. Settings are applied atomically upon confirmation.</p>
        </div>

        <div class="wizard-review-table-wrapper">
          <table class="wizard-review-table">
            <thead>
              <tr>
                <th>Module</th>
                <th>Status</th>
                <th>Configuration Summary</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>👋 Welcome & Leave</strong></td>
                <td><span class="badge ${w.enabled ? 'badge-installed' : 'badge-invite'}">${w.enabled ? 'Active' : 'Disabled'}</span></td>
                <td>${w.channel_id ? `Channel: <code>${w.channel_id}</code>` : 'No channel specified'}</td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="2">Edit</button></td>
              </tr>
              <tr>
                <td><strong>🛡️ Verification Gate</strong></td>
                <td><span class="badge ${v.enabled ? 'badge-installed' : 'badge-invite'}">${v.enabled ? 'Active' : 'Disabled'}</span></td>
                <td>Method: <code>${v.method || 'button'}</code> • Role: <code>${v.role_id || 'Not set'}</code></td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="3">Edit</button></td>
              </tr>
              <tr>
                <td><strong>🔨 Moderation & Defense</strong></td>
                <td><span class="badge ${sec.antinuke_enabled ? 'badge-installed' : 'badge-invite'}">${sec.antinuke_enabled ? 'Anti-Nuke Armed' : 'Automod Only'}</span></td>
                <td>Punishment: <code>${sec.punishment || 'strip_roles'}</code></td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="4">Edit</button></td>
              </tr>
              <tr>
                <td><strong>🎫 Support Tickets</strong></td>
                <td><span class="badge ${tk.enabled ? 'badge-installed' : 'badge-invite'}">${tk.enabled ? 'Active' : 'Disabled'}</span></td>
                <td>Category: <code>${tk.category_id || 'Auto'}</code> • Staff Role: <code>${tk.support_role_id || 'Not set'}</code></td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="5">Edit</button></td>
              </tr>
              <tr>
                <td><strong>📈 Leveling & Giveaways</strong></td>
                <td><span class="badge ${lvl.enabled ? 'badge-installed' : 'badge-invite'}">${lvl.enabled ? 'Active' : 'Disabled'}</span></td>
                <td>Rate: <code>${lvl.xp_rate || 1.0}x</code></td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="6">Edit</button></td>
              </tr>
              <tr>
                <td><strong>🎭 Auto-Roles & Logs</strong></td>
                <td><span class="badge ${rl.human_role_id ? 'badge-installed' : 'badge-invite'}">${rl.human_role_id ? 'Configured' : 'Optional'}</span></td>
                <td>Human Role: <code>${rl.human_role_id || 'None'}</code></td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="7">Edit</button></td>
              </tr>
              <tr>
                <td><strong>🧠 AI & Music</strong></td>
                <td><span class="badge ${opt.ai_enabled ? 'badge-installed' : 'badge-invite'}">${opt.ai_enabled ? 'AI Active' : 'Basic Audio'}</span></td>
                <td>Persona: <code>${opt.ai_personality || 'aizen'}</code></td>
                <td><button class="btn btn-outline btn-xs w-edit-step" data-step="8">Edit</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div id="wizard-apply-result" style="display: none; margin-top: 1.5rem;"></div>
      </div>
    `;

    body.querySelectorAll('.w-edit-step').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = parseInt(btn.getAttribute('data-step'));
        if (target >= 1 && target <= 9) {
          this.currentStep = target;
          this.renderStep();
        }
      });
    });
  }

  // =========================================================================
  // Navigation & Persistence
  // =========================================================================
  async nextStep() {
    if (this.currentStep === 9) {
      await this.applySetup();
      return;
    }

    // Auto-save draft on step transition
    await this.saveDraft(true);
    if (this.currentStep < this.maxStep) {
      this.currentStep++;
      this.renderStep();
    }
  }

  prevStep() {
    if (this.currentStep > 1) {
      this.currentStep--;
      this.renderStep();
    }
  }

  skipStep() {
    showToast(`Skipped step ${this.currentStep}. You can configure it later in Settings.`, 'info');
    if (this.currentStep < this.maxStep) {
      this.currentStep++;
      this.renderStep();
    }
  }

  async saveDraft(isSilent = false) {
    if (!this.currentGuild?.id) return;
    try {
      await saveWizardProgress(this.currentGuild.id, {
        current_step: this.currentStep,
        draft: this.draft,
      });
      if (!isSilent) {
        showToast('Setup wizard draft saved! You can resume anytime.', 'success');
      }
    } catch (err) {
      if (!isSilent) {
        showToast(`Failed to save draft: ${err.message}`, 'error');
      }
    }
  }

  async applySetup() {
    if (!this.currentGuild?.id) return;

    const nextBtn = this.container.querySelector('#wizard-next-btn');
    const resultBox = this.container.querySelector('#wizard-apply-result');

    if (nextBtn) {
      nextBtn.disabled = true;
      nextBtn.textContent = 'Applying Settings to PostgreSQL...';
    }

    try {
      const res = await applyWizardSettings(this.currentGuild.id, { draft: this.draft });
      this.isCompleted = true;

      if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = `
          <div class="wizard-success-card">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">🎉</div>
            <h3 style="color: var(--emerald-accent); font-weight: 800; font-size: 1.5rem; margin-bottom: 0.5rem;">
              Setup Successfully Completed!
            </h3>
            <p style="color: var(--text-main); font-size: 0.95rem; margin-bottom: 1.25rem;">
              KYOKA 3.0 has successfully saved and applied your configuration to <strong>${this.currentGuild.name}</strong>.
            </p>
            <div style="display: flex; gap: 0.75rem; justify-content: center;">
              <button id="w-success-dashboard-btn" class="btn btn-primary">
                Open Full Server Dashboard
              </button>
            </div>
          </div>
        `;

        resultBox.querySelector('#w-success-dashboard-btn')?.addEventListener('click', () => {
          this.close();
          this.onFinish(this.currentGuild.id);
        });
      }

      showToast('Configuration successfully applied to live bot!', 'success');
    } catch (err) {
      showToast(`Setup application failed: ${err.message}`, 'error');
      if (nextBtn) {
        nextBtn.disabled = false;
        nextBtn.textContent = 'Retry Application';
      }
    }
  }

  close() {
    if (this.keyHandler) {
      window.removeEventListener('keydown', this.keyHandler);
      this.keyHandler = null;
    }
    if (this.container) {
      this.container.remove();
      this.container = null;
    }
    this.onClose();
  }
}
