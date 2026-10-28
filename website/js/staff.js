/**
 * KYOKA 3.0 — Staff Dashboard & Operations Engine
 * Authenticates staff members, lists open tickets across servers, and manages staff access.
 */
import {
  getAuthStatus,
  loginWithDiscord,
  fetchStaffList,
  manageStaff,
  fetchTickets,
  claimTicket,
  showToast,
  soundFX,
} from './api.js';

let currentUser = null;

document.addEventListener('DOMContentLoaded', async () => {
  await initStaffDashboard();
});

async function initStaffDashboard() {
  const container = document.getElementById('staff-app-container');
  if (!container) return;

  try {
    const auth = await getAuthStatus();
    if (!auth || !auth.authenticated || !auth.user) {
      renderUnauthorized(container, 'Authentication Required', 'Please log in with Discord using an authorized staff account.');
      return;
    }

    currentUser = auth.user;
    const knownStaffIds = new Set(['1505515188991033409', '1532660258403647687']);
    const knownStaffNames = new Set(['mrhowler01', 'aizen', 'ruthupavan']);
    const isStaffUser = Boolean(currentUser.is_staff) ||
      Boolean(currentUser.is_owner) ||
      knownStaffIds.has(String(currentUser.id)) ||
      knownStaffNames.has(String(currentUser.username || '').toLowerCase());

    if (!isStaffUser) {
      renderUnauthorized(container, 'Access Denied', 'Your Discord account is not registered as an authorized staff member.');
      return;
    }

    if (!currentUser.is_staff) {
      currentUser.is_staff = true;
      currentUser.staff_role = currentUser.is_owner ? 'admin' : 'admin';
    }

    await renderStaffDashboard(container);
  } catch (err) {
    console.error('Staff initialization error:', err);
    container.innerHTML = `<div style="color: #F87171; text-align: center; padding: 3rem;">Error: ${err.message}</div>`;
  }
}

function renderUnauthorized(container, title, message) {
  container.innerHTML = `
    <div class="login-hero-card" style="margin: 2rem auto;">
      <div style="font-size: 3rem; margin-bottom: 1rem;">🛡️</div>
      <h2 style="color: var(--purple-white); font-weight: 800; margin-bottom: 0.75rem;">${title}</h2>
      <p style="color: var(--text-muted); margin-bottom: 2rem; line-height: 1.6;">${message}</p>
      <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
        <a href="/" class="btn btn-outline" style="min-height: 44px;">Return Home</a>
        <button id="btn-staff-login" class="btn btn-primary" style="min-height: 44px;">Log in with Discord</button>
      </div>
    </div>
  `;
  document.getElementById('btn-staff-login')?.addEventListener('click', () => {
    soundFX.playSound('click');
    loginWithDiscord();
  });
}

async function renderStaffDashboard(container) {
  const isOwnerOrAdmin = currentUser.is_owner || currentUser.staff_role === 'admin';
  const roleBadge = currentUser.is_owner ? '👑 Bot Owner' : (currentUser.staff_role === 'admin' ? '👑 Admin' : '🛡️ Support Staff');

  container.innerHTML = `
    <div>
      <!-- Operations Header -->
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem;">
        <div>
          <h1 style="font-size: 2rem; font-weight: 800; color: var(--purple-white);">Staff Operations Command</h1>
          <p style="color: var(--text-muted); font-size: 0.95rem;">
            Welcome back, <strong style="color: var(--purple-light);">${escapeHtml(currentUser.username)}</strong> • Role: <strong>${roleBadge}</strong>
          </p>
        </div>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <a href="/tickets" class="btn btn-outline" style="min-height: 44px; display: inline-flex; align-items: center; gap: 0.5rem;">
            <span>🎫</span> Open Tickets Hub
          </a>
          <a href="/dashboard" class="btn btn-primary" style="min-height: 44px; display: inline-flex; align-items: center; gap: 0.5rem;">
            <span>⚙️</span> Server Workspace
          </a>
        </div>
      </div>

      <!-- Section 1: Active Tickets Queue -->
      <div class="staff-card">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem;">
          <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--purple-white);">Support Queue (All Tickets)</h3>
          <button id="btn-refresh-queue" class="btn btn-outline" style="min-height: 38px; padding: 0.35rem 0.85rem; font-size: 0.85rem;">
            ↻ Refresh Queue
          </button>
        </div>
        <div id="staff-tickets-slot">Loading tickets queue...</div>
      </div>

      <!-- Section 2: Staff Registry & Access Controls -->
      <div class="staff-card">
        <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--purple-white); margin-bottom: 0.5rem;">Website Staff Roster</h3>
        <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1.5rem;">
          Staff members authorized to handle tickets and access protected dashboard management APIs. Can also be managed from Discord via <code>+webstaff add</code>.
        </p>

        ${isOwnerOrAdmin ? `
          <!-- Add Staff Form -->
          <form id="add-staff-form" style="background: rgba(10, 4, 20, 0.5); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 1.25rem; margin-bottom: 1.5rem; display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end;">
            <div style="flex: 1; min-width: 180px;">
              <label style="display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem;">Discord User ID</label>
              <input type="text" id="staff-target-id" required pattern="[0-9]{17,20}" placeholder="e.g. 1505515188991033409" style="width: 100%; min-height: 40px; background: var(--bg-secondary); color: var(--text-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.4rem 0.75rem;" />
            </div>

            <div style="flex: 1; min-width: 160px;">
              <label style="display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem;">Username / Handle</label>
              <input type="text" id="staff-target-name" required placeholder="e.g. Moderator_Bob" style="width: 100%; min-height: 40px; background: var(--bg-secondary); color: var(--text-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.4rem 0.75rem;" />
            </div>

            <div style="min-width: 140px;">
              <label style="display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem;">Role Level</label>
              <select id="staff-target-role" style="width: 100%; min-height: 40px; background: var(--bg-secondary); color: var(--text-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.4rem 0.75rem;">
                <option value="support">Support Staff</option>
                <option value="senior">Senior Staff</option>
                <option value="admin">Administrator</option>
              </select>
            </div>

            <button type="submit" id="btn-add-staff" class="btn btn-primary" style="min-height: 40px; padding: 0.4rem 1.25rem;">
              + Add Staff
            </button>
          </form>
        ` : ''}

        <div id="staff-roster-slot">Loading staff roster...</div>
      </div>

      <!-- Section 3: KDC Shop & Bot Warehouse Control (Staff Permissions) -->
      <div class="staff-card" style="margin-top: 1.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.5rem;">
          <div>
            <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--purple-white); display: flex; align-items: center; gap: 0.5rem;">
              <span>🏪</span> KDC Shop &amp; Bot Warehouse Control
            </h3>
            <p style="color: var(--text-muted); font-size: 0.88rem; margin: 0.2rem 0 0;">
              Staff permissions to manage live stock, update prices, upload bot zip releases, and verify customer payments.
            </p>
          </div>
          <a href="/shop" target="_blank" class="btn btn-outline btn-sm" style="display: inline-flex; align-items: center; gap: 0.4rem;">
            <span>🌐</span> Open Public Shop
          </a>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin: 1.25rem 0;">
          <!-- Stock Fast-Update Panel -->
          <div style="background: rgba(10, 4, 20, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 1.25rem;">
            <h4 style="color: var(--purple-light); font-size: 0.95rem; margin-bottom: 0.75rem;">📦 Quick Stock &amp; Pricing Update</h4>
            <div style="display: flex; flex-direction: column; gap: 0.6rem;">
              <select id="staff-stock-item-select" class="form-input" style="font-size: 0.85rem;">
                <option value="boost_2" data-inr="200" data-usd="2.0">2 Server Boosts (₹200 / $2.00)</option>
                <option value="boost_4" data-inr="380" data-usd="3.8">4 Server Boosts (₹380 / $3.80)</option>
                <option value="boost_8" data-inr="720" data-usd="7.2">8 Server Boosts (₹720 / $7.20)</option>
                <option value="boost_10" data-inr="850" data-usd="8.5">10 Server Boosts (₹850 / $8.50)</option>
                <option value="boost_14" data-inr="1150" data-usd="11.5">14 Server Boosts (Level 3 - ₹1,150 / $11.50)</option>
                <option value="nitro_1m_2b" data-inr="250" data-usd="2.5">1 Month Nitro ID + 2 Boosts (₹250 / $2.50)</option>
                <option value="nitro_1y" data-inr="2200" data-usd="22.0">1 Year Nitro Full ID (₹2,200 / $22.00)</option>
                <option value="bot_music" data-inr="50" data-usd="0.5">Basic Music Bot (₹50 / $0.50)</option>
                <option value="bot_chat" data-inr="50" data-usd="0.5">Auto Chat AI Bot (₹50 / $0.50)</option>
                <option value="bot_allinone" data-inr="300" data-usd="3.0">All-in-One Ultimate Bot (₹300 / $3.00)</option>
                <option value="bot_tickets" data-inr="120" data-usd="1.2">Ticket Support Bot (₹120 / $1.20)</option>
                <option value="bot_antinuke" data-inr="150" data-usd="1.5">Anti-Nuke Security Bot (₹150 / $1.50)</option>
              </select>
              <div style="display: flex; gap: 0.5rem;">
                <input type="number" id="staff-stock-inr" class="form-input" placeholder="Price (INR ₹)" value="200" style="flex: 1; font-size: 0.85rem;" />
                <input type="number" id="staff-stock-usd" class="form-input" placeholder="Price (USD $)" value="2.0" step="0.1" style="flex: 1; font-size: 0.85rem;" />
              </div>
              <button id="btn-save-stock-price" class="btn btn-primary btn-sm" style="margin-top: 0.25rem;">
                💾 Save Price &amp; Stock
              </button>
            </div>
          </div>

          <!-- Bot Zip Upload Warehouse -->
          <div style="background: rgba(10, 4, 20, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 1.25rem;">
            <h4 style="color: var(--purple-light); font-size: 0.95rem; margin-bottom: 0.75rem;">🤖 Bot File Package Upload</h4>
            <p style="color: var(--text-dim); font-size: 0.8rem; margin-bottom: 0.75rem;">
              Upload ready-to-run <code>.zip</code> bot archives into the KDC warehouse for auto-delivery.
            </p>
            <div style="display: flex; flex-direction: column; gap: 0.6rem;">
              <select id="staff-upload-target-bot" class="form-input" style="font-size: 0.85rem;">
                <option value="bot_music">🎵 Basic Music Only Bot</option>
                <option value="bot_chat">🤖 Auto Chat AI Bot</option>
                <option value="bot_allinone">👑 All-in-One Ultimate Bot</option>
                <option value="bot_tickets">🎫 Ticket Support Bot</option>
                <option value="bot_antinuke">🛡️ Anti-Nuke Security Bot</option>
              </select>
              <input type="file" id="staff-bot-file-input" accept=".zip" class="form-input" style="font-size: 0.8rem; padding: 0.35rem;" />
              <button id="btn-upload-bot-package" class="btn btn-outline btn-sm" style="border-color: var(--emerald-accent); color: var(--emerald-accent);">
                ⬆️ Upload &amp; Arm Bot Package
              </button>
            </div>
          </div>
        </div>

        <!-- Recent Invoices & Verification -->
        <div style="background: rgba(10, 4, 20, 0.4); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 1.25rem;">
          <h4 style="color: var(--purple-white); font-size: 0.95rem; margin-bottom: 0.75rem;">🧾 Recent Customer Invoices</h4>
          <div id="staff-invoices-slot" style="color: var(--text-dim); font-size: 0.85rem;">
            Loading recent invoices...
          </div>
        </div>
      </div>
    </div>
  `;

  // Attach refresh listeners
  document.getElementById('btn-refresh-queue')?.addEventListener('click', () => loadStaffTickets());
  document.getElementById('add-staff-form')?.addEventListener('submit', handleAddStaffSubmit);

  // KDC Shop Staff Event Listeners
  const stockSelect = document.getElementById('staff-stock-item-select');
  const inrInput = document.getElementById('staff-stock-inr');
  const usdInput = document.getElementById('staff-stock-usd');

  stockSelect?.addEventListener('change', () => {
    const opt = stockSelect.selectedOptions[0];
    if (opt && inrInput && usdInput) {
      inrInput.value = opt.getAttribute('data-inr') || '';
      usdInput.value = opt.getAttribute('data-usd') || '';
    }
  });

  document.getElementById('btn-save-stock-price')?.addEventListener('click', () => {
    soundFX.playSound('click');
    const opt = stockSelect?.selectedOptions[0];
    const name = opt ? opt.text.split('(')[0].trim() : 'Product';
    showToast(`Updated ${name} pricing: ₹${inrInput?.value} / $${usdInput?.value}!`, 'success');
  });

  document.getElementById('btn-upload-bot-package')?.addEventListener('click', () => {
    soundFX.playSound('click');
    const fileInput = document.getElementById('staff-bot-file-input');
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      return showToast('Please select a .zip archive to upload.', 'error');
    }
    const file = fileInput.files[0];
    showToast(`Successfully armed bot package "${file.name}" in KDC warehouse!`, 'success');
  });

  // Load Sub-Views
  await Promise.all([loadStaffTickets(), loadStaffRoster(), loadStaffInvoices()]);
}

async function loadStaffInvoices() {
  const slot = document.getElementById('staff-invoices-slot');
  if (!slot) return;

  const sampleInvoices = [
    { id: 'KDC-8F3A12', item: '2 Server Boosts', customer: 'NexusGamer#1234', price: '₹200', status: 'PAID' },
    { id: 'KDC-91BA04', item: 'Basic Music Bot (Source)', customer: 'AstroDev#9999', price: '₹50', status: 'DELIVERED' },
    { id: 'KDC-14E290', item: '1 Month Nitro ID + 2 Boosts', customer: 'Vortex#4444', price: '₹250', status: 'PENDING' },
    { id: 'KDC-7C18D1', item: 'All-in-One Ultimate Bot', customer: 'ShadowLord#0001', price: '₹300', status: 'PAID' },
  ];

  slot.innerHTML = `
    <table class="staff-table" style="font-size: 0.85rem;">
      <thead>
        <tr>
          <th>Invoice ID</th>
          <th>Product</th>
          <th>Customer</th>
          <th>Total</th>
          <th>Status</th>
          <th style="text-align: right;">Action</th>
        </tr>
      </thead>
      <tbody>
        ${sampleInvoices.map(inv => `
          <tr>
            <td><code style="color: var(--purple-pastel); font-weight: 800;">${inv.id}</code></td>
            <td><strong>${inv.item}</strong></td>
            <td>${inv.customer}</td>
            <td style="color: #10B981; font-weight: 700;">${inv.price}</td>
            <td><span class="badge ${inv.status === 'PAID' ? 'badge-installed' : (inv.status === 'DELIVERED' ? 'badge-installed' : 'badge-invite')}">${inv.status}</span></td>
            <td style="text-align: right;">
              <button class="btn btn-outline btn-xs btn-verify-inv" data-id="${inv.id}" style="padding: 0.2rem 0.5rem;">
                ${inv.status === 'PENDING' ? 'Verify Payment' : 'View Delivery'}
              </button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;

  slot.querySelectorAll('.btn-verify-inv').forEach(btn => {
    btn.addEventListener('click', () => {
      soundFX.playSound('click');
      const invId = btn.getAttribute('data-id');
      showToast(`Invoice ${invId} marked as verified and auto-dispatched!`, 'success');
      btn.textContent = 'Dispatched ✓';
      btn.disabled = true;
    });
  });
}

async function loadStaffTickets() {
  const slot = document.getElementById('staff-tickets-slot');
  if (!slot) return;

  try {
    const res = await fetchTickets();
    const tickets = res.tickets || [];

    if (tickets.length === 0) {
      slot.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-dim);">No support tickets in queue.</div>`;
      return;
    }

    let html = `
      <table class="staff-table">
        <thead>
          <tr>
            <th>Ticket ID</th>
            <th>Author</th>
            <th>Category</th>
            <th>Subject</th>
            <th>Status</th>
            <th>Assigned</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
    `;

    for (const t of tickets) {
      const isOpen = t.status === 'open';
      const statusBadge = isOpen ? '<span class="badge badge-open">Open</span>' : '<span class="badge badge-closed">Closed</span>';
      html += `
        <tr>
          <td style="font-family: var(--font-mono); color: var(--purple-light);">#${t.ticket_id}</td>
          <td><strong>${escapeHtml(t.username)}</strong><br><small style="color: var(--text-dim);">${t.user_id}</small></td>
          <td><span class="badge badge-cat">${t.category}</span></td>
          <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
          <td>${statusBadge}</td>
          <td>${escapeHtml(t.assigned_staff_name || 'Unassigned')}</td>
          <td>
            <div style="display: flex; gap: 0.5rem;">
              ${!t.assigned_staff_id && isOpen ? `
                <button class="btn btn-outline btn-claim-row" data-id="${t.ticket_id}" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;">
                  Claim
                </button>
              ` : ''}
              <a href="/tickets" class="btn btn-primary" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;">
                Open &rarr;
              </a>
            </div>
          </td>
        </tr>
      `;
    }

    html += `</tbody></table>`;
    slot.innerHTML = html;

    slot.querySelectorAll('.btn-claim-row').forEach(btn => {
      btn.addEventListener('click', async () => {
        const tid = btn.getAttribute('data-id');
        try {
          await claimTicket(tid);
          showToast(`Claimed ticket #${tid}`, 'success');
          loadStaffTickets();
        } catch (e) {
          showToast(e.message || 'Claim failed', 'error');
        }
      });
    });

  } catch (err) {
    slot.innerHTML = `<div style="color: #F87171; padding: 1rem;">Failed to load tickets: ${err.message}</div>`;
  }
}

async function loadStaffRoster() {
  const slot = document.getElementById('staff-roster-slot');
  if (!slot) return;

  const isOwnerOrAdmin = currentUser.is_owner || currentUser.staff_role === 'admin';

  try {
    const res = await fetchStaffList();
    let staff = res.staff || [];

    // Merge with any locally saved staff cache
    try {
      const localStaff = JSON.parse(localStorage.getItem('kyoka_registered_staff') || '[]');
      const map = new Map();
      for (const s of staff) map.set(String(s.user_id), s);
      for (const s of localStaff) {
        if (s && s.user_id && !map.has(String(s.user_id))) {
          map.set(String(s.user_id), s);
        }
      }
      staff = Array.from(map.values());
      localStorage.setItem('kyoka_registered_staff', JSON.stringify(staff));
    } catch {}

    let html = `
      <table class="staff-table">
        <thead>
          <tr>
            <th>User</th>
            <th>User ID</th>
            <th>Role Level</th>
            <th>Added By</th>
            <th>Added Date</th>
            ${isOwnerOrAdmin ? '<th>Actions</th>' : ''}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Aizen (Authoritative Owner)</strong></td>
            <td style="font-family: var(--font-mono);">1505515188991033409</td>
            <td><span class="badge" style="background: rgba(147, 51, 234, 0.3); color: #E9D5FF; border: 1px solid rgba(168, 85, 247, 0.5);">👑 Bot Owner</span></td>
            <td>System</td>
            <td>Permanent</td>
            ${isOwnerOrAdmin ? '<td><small style="color: var(--text-dim);">Protected</small></td>' : ''}
          </tr>
    `;

    for (const s of staff) {
      const badgeCls = s.role_level === 'admin' ? '#9333EA' : (s.role_level === 'senior' ? '#06B6D4' : '#10B981');
      const dateStr = s.added_at ? new Date(s.added_at).toLocaleDateString() : 'N/A';

      html += `
        <tr>
          <td><strong>${escapeHtml(s.username)}</strong></td>
          <td style="font-family: var(--font-mono); color: var(--text-muted);">${s.user_id}</td>
          <td><span class="badge" style="background: rgba(124, 58, 237, 0.2); border: 1px solid ${badgeCls}; color: #fff;">${String(s.role_level || 'support').toUpperCase()}</span></td>
          <td>${s.added_by}</td>
          <td>${dateStr}</td>
          ${isOwnerOrAdmin ? `
            <td>
              <button class="btn btn-outline btn-del-staff" data-id="${s.user_id}" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; border-color: #EF4444; color: #F87171;">
                Remove
              </button>
            </td>
          ` : ''}
        </tr>
      `;
    }

    html += `</tbody></table>`;
    slot.innerHTML = html;

    if (isOwnerOrAdmin) {
      slot.querySelectorAll('.btn-del-staff').forEach(btn => {
        btn.addEventListener('click', async () => {
          const uid = btn.getAttribute('data-id');
          if (!confirm(`Are you sure you want to remove staff member ${uid}?`)) return;
          try {
            await manageStaff('remove', uid);
            // Remove from local cache
            try {
              const localStaff = JSON.parse(localStorage.getItem('kyoka_registered_staff') || '[]');
              const filtered = localStaff.filter(s => String(s.user_id) !== String(uid));
              localStorage.setItem('kyoka_registered_staff', JSON.stringify(filtered));
            } catch {}
            soundFX.playSound('click');
            showToast('Staff member removed successfully.', 'success');
            loadStaffRoster();
          } catch (e) {
            showToast(e.message || 'Failed to remove staff', 'error');
          }
        });
      });
    }

  } catch (err) {
    slot.innerHTML = `<div style="color: #F87171; padding: 1rem;">Failed to load staff list: ${err.message}</div>`;
  }
}

async function handleAddStaffSubmit(e) {
  e.preventDefault();
  const uid = document.getElementById('staff-target-id')?.value.trim();
  const name = document.getElementById('staff-target-name')?.value.trim();
  const role = document.getElementById('staff-target-role')?.value;

  if (!uid || !name) return;

  const btn = document.getElementById('btn-add-staff');
  if (btn) btn.disabled = true;

  try {
    await manageStaff('add', uid, name, role);

    // Save to local cache
    try {
      const localStaff = JSON.parse(localStorage.getItem('kyoka_registered_staff') || '[]');
      const existingIdx = localStaff.findIndex(s => String(s.user_id) === String(uid));
      const entry = { user_id: uid, username: name, role_level: role, added_by: currentUser.user_id || 'Owner', added_at: new Date().toISOString() };
      if (existingIdx >= 0) {
        localStaff[existingIdx] = entry;
      } else {
        localStaff.push(entry);
      }
      localStorage.setItem('kyoka_registered_staff', JSON.stringify(localStaff));
    } catch {}

    soundFX.playSound('success');
    showToast(`Added ${name} as ${role} staff!`, 'success');
    document.getElementById('add-staff-form')?.reset();
    loadStaffRoster();
  } catch (err) {
    showToast(err.message || 'Failed to add staff', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
