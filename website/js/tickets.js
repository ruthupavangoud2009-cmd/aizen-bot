/**
 * KYOKA 3.0 — Interactive Support Tickets Client Engine
 * Provides live ticket management, message history, replies, claiming, and status controls.
 */
import {
  getAuthStatus,
  loginWithDiscord,
  createTicket,
  fetchTickets,
  fetchTicketDetails,
  replyTicket,
  updateTicketStatus,
  claimTicket,
  showToast,
  soundFX,
} from './api.js';

let currentUser = null;
let currentTickets = [];
let viewingTicketId = null;

document.addEventListener('DOMContentLoaded', async () => {
  setupModalEvents();
  await initTicketsApp();
});

async function initTicketsApp() {
  const container = document.getElementById('ticket-view-container');
  if (!container) return;

  // 1. Verify User Authentication
  try {
    const auth = await getAuthStatus();
    if (!auth || !auth.authenticated || !auth.user) {
      renderLoggedOutState(container);
      return;
    }
    currentUser = auth.user;

    // Show staff nav link if user is staff or owner
    if (currentUser.is_staff || currentUser.is_owner) {
      const staffLink = document.getElementById('nav-staff-link');
      if (staffLink) staffLink.style.display = 'block';
    }

    // 2. Load User Tickets
    await loadTicketsList();
  } catch (err) {
    console.error('Failed to initialize ticket engine:', err);
    container.innerHTML = `
      <div style="text-align: center; padding: 3rem 1.5rem; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <h3 style="color: #F87171; margin-bottom: 0.5rem;">Connection Notice</h3>
        <p style="color: var(--text-muted); font-size: 0.95rem; margin-bottom: 1.5rem;">${err.message || 'Unable to communicate with ticket backend.'}</p>
        <button id="btn-retry-tickets" class="btn btn-outline" style="min-height: 44px;">Retry Connection</button>
      </div>
    `;
    document.getElementById('btn-retry-tickets')?.addEventListener('click', () => initTicketsApp());
  }
}

function renderLoggedOutState(container) {
  container.innerHTML = `
    <div class="login-hero-card" style="margin: 2rem auto;">
      <div style="font-size: 3rem; margin-bottom: 1rem;">🎫</div>
      <h2 style="color: var(--purple-white); font-weight: 800; margin-bottom: 0.75rem;">Discord Authentication Required</h2>
      <p style="color: var(--text-muted); margin-bottom: 2rem; line-height: 1.6;">
        To create and view support tickets synchronized with Discord staff threads, please authenticate securely with your Discord account.
      </p>
      <button id="btn-ticket-login" class="btn btn-primary" style="font-size: 1.05rem; padding: 0.85rem 2rem; min-height: 48px;">
        <span style="font-size: 1.25rem;">⚡</span> Log in with Discord
      </button>
      <div class="security-note" style="margin-top: 2rem;">
        <span>🔒</span>
        <span>Authentication uses Discord OAuth2. We never request your password or token.</span>
      </div>
    </div>
  `;
  document.getElementById('btn-ticket-login')?.addEventListener('click', () => {
    soundFX.playSound('click');
    loginWithDiscord();
  });
}

async function loadTicketsList() {
  const container = document.getElementById('ticket-view-container');
  if (!container) return;

  try {
    const res = await fetchTickets();
    currentTickets = res.tickets || [];

    // Update stats
    const openCount = currentTickets.filter(t => t.status === 'open').length;
    const statEl = document.getElementById('stat-open-tickets');
    if (statEl) statEl.textContent = openCount;

    if (currentTickets.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 4rem 1.5rem; background: var(--bg-card); border-radius: var(--radius-md); border: 1px dashed var(--border-subtle);">
          <div style="font-size: 2.5rem; margin-bottom: 1rem;">🎫</div>
          <h3 style="color: var(--purple-white); font-weight: 700; margin-bottom: 0.5rem;">No Support Tickets Found</h3>
          <p style="color: var(--text-muted); font-size: 0.95rem; margin-bottom: 1.5rem;">
            You haven't opened any support tickets yet. Need help with setup, anti-nuke, or premium?
          </p>
          <button id="btn-empty-open" class="btn btn-primary" style="min-height: 44px;">
            Open Your First Ticket
          </button>
        </div>
      `;
      document.getElementById('btn-empty-open')?.addEventListener('click', () => {
        openCreateModal();
      });
      return;
    }

    // Render tickets list
    let html = `
      <div style="margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;">
        <span style="color: var(--text-dim); font-size: 0.85rem; font-weight: 600;">
          Showing ${currentTickets.length} ticket(s)
        </span>
      </div>
    `;

    for (const t of currentTickets) {
      const isOpen = t.status === 'open';
      const badgeCls = isOpen ? 'badge-open' : 'badge-closed';
      const updatedDate = t.updated_at ? new Date(t.updated_at).toLocaleString() : 'Recently';

      html += `
        <div class="ticket-card" data-ticket-id="${t.ticket_id}">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
            <div>
              <span class="badge ${badgeCls}" style="margin-right: 0.5rem;">${t.status}</span>
              <span class="badge badge-cat">${t.category}</span>
              <span style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--purple-light); margin-left: 0.5rem;">#${t.ticket_id}</span>
            </div>
            <span style="font-size: 0.8rem; color: var(--text-dim);">${updatedDate}</span>
          </div>

          <h4 style="color: var(--purple-white); font-size: 1.1rem; font-weight: 700; margin-bottom: 0.35rem;">
            ${escapeHtml(t.subject)}
          </h4>
          <p style="color: var(--text-muted); font-size: 0.9rem; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
            ${escapeHtml(t.description)}
          </p>

          <div style="margin-top: 0.85rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-dim);">
            <span>Staff Assigned: <strong style="color: var(--text-main);">${t.assigned_staff_name || 'Unassigned'}</strong></span>
            <span style="color: var(--purple-light); font-weight: 600;">View Conversation &rarr;</span>
          </div>
        </div>
      `;
    }

    container.innerHTML = html;

    // Attach click listeners to cards
    container.querySelectorAll('.ticket-card').forEach(card => {
      card.addEventListener('click', () => {
        const tid = card.getAttribute('data-ticket-id');
        viewTicketDetails(tid);
      });
    });

  } catch (err) {
    console.error('Error loading tickets list:', err);
    container.innerHTML = `<div style="color: #F87171; padding: 2rem; text-align: center;">Error loading tickets: ${err.message}</div>`;
  }
}

async function viewTicketDetails(ticketId) {
  viewingTicketId = ticketId;
  const container = document.getElementById('ticket-view-container');
  if (!container) return;

  container.innerHTML = `
    <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
      <div class="server-icon-placeholder" style="width: 44px; height: 44px; margin: 0 auto 1rem; animation: loading 1.5s infinite;">💬</div>
      <p>Loading ticket #${ticketId}...</p>
    </div>
  `;

  try {
    const res = await fetchTicketDetails(ticketId);
    const ticket = res.ticket;
    const messages = res.messages || [];
    const isStaff = res.is_staff;
    const canReply = res.can_reply;

    const isOpen = ticket.status === 'open';
    const badgeCls = isOpen ? 'badge-open' : 'badge-closed';

    let msgsHtml = '';
    for (const m of messages) {
      const isUserMsg = m.sender_role === 'user';
      const isSystem = m.sender_role === 'system';
      const bubbleCls = isSystem ? 'bubble-system' : (isUserMsg ? 'bubble-user' : 'bubble-staff');
      const timeStr = m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
      const roleBadge = m.sender_role === 'admin' ? '👑 Admin' : (m.sender_role === 'staff' ? '🛡️ Staff' : '👤 User');

      if (isSystem) {
        msgsHtml += `
          <div class="chat-bubble bubble-system">
            <span>⚙️ ${escapeHtml(m.content)} • <small>${timeStr}</small></span>
          </div>
        `;
      } else {
        msgsHtml += `
          <div class="chat-bubble ${bubbleCls}">
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-dim); margin-bottom: 0.35rem;">
              <strong style="color: ${isUserMsg ? 'var(--purple-pastel)' : '#C084FC'};">${escapeHtml(m.sender_name)} (${roleBadge})</strong>
              <span>${timeStr}</span>
            </div>
            <div style="white-space: pre-wrap; word-break: break-word; color: var(--text-main); font-size: 0.95rem;">${escapeHtml(m.content)}</div>
          </div>
        `;
      }
    }

    container.innerHTML = `
      <div>
        <!-- Back Navigation & Status Actions Header -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem;">
          <button id="btn-back-tickets" class="btn btn-outline" style="min-height: 40px; padding: 0.4rem 1rem;">
            &larr; Back to Tickets List
          </button>

          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            ${isStaff && !ticket.assigned_staff_id ? `
              <button id="btn-claim-ticket" class="btn btn-outline" style="min-height: 40px; border-color: #10B981; color: #34D399;">
                Claim Ticket
              </button>
            ` : ''}
            ${isOpen ? `
              <button id="btn-toggle-status" class="btn btn-outline" style="min-height: 40px; border-color: #EF4444; color: #F87171;">
                Close Ticket
              </button>
            ` : (isStaff ? `
              <button id="btn-toggle-status" class="btn btn-outline" style="min-height: 40px; border-color: #10B981; color: #34D399;">
                Reopen Ticket
              </button>
            ` : '')}
          </div>
        </div>

        <!-- Ticket Summary Card -->
        <div style="background: var(--bg-card); border: 1px solid var(--border-active); border-radius: var(--radius-md); padding: 1.5rem; margin-bottom: 1.5rem;">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
            <div>
              <span class="badge ${badgeCls}">${ticket.status}</span>
              <span class="badge badge-cat">${ticket.category}</span>
              <span style="font-family: var(--font-mono); font-size: 0.9rem; color: var(--purple-light); margin-left: 0.5rem;">#${ticket.ticket_id}</span>
            </div>
            <div style="font-size: 0.85rem; color: var(--text-dim);">
              Opened by <strong style="color: var(--text-main);">${escapeHtml(ticket.username)}</strong>
            </div>
          </div>

          <h2 style="font-size: 1.4rem; font-weight: 800; color: var(--purple-white); margin-bottom: 0.5rem;">
            ${escapeHtml(ticket.subject)}
          </h2>

          <div style="font-size: 0.85rem; color: var(--text-dim); display: flex; gap: 1.5rem; flex-wrap: wrap;">
            <span>Staff Assigned: <strong style="color: var(--text-main);">${escapeHtml(ticket.assigned_staff_name || 'Unassigned')}</strong></span>
            <span>Discord Thread: <strong style="color: var(--purple-light);">${ticket.discord_thread_id ? '🟢 Connected' : '🟡 Offline'}</strong></span>
          </div>
        </div>

        <!-- Conversation History Area -->
        <div style="background: rgba(10, 4, 20, 0.5); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.5rem; margin-bottom: 1.5rem; max-height: 500px; overflow-y: auto;">
          ${msgsHtml}
        </div>

        <!-- Reply Input Form -->
        ${canReply ? `
          <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.25rem;">
            <form id="reply-ticket-form">
              <label style="display: block; font-size: 0.85rem; font-weight: 700; color: var(--text-muted); margin-bottom: 0.5rem;">
                Write a reply
              </label>
              <textarea id="reply-content" required minlength="1" maxlength="4000" rows="3" placeholder="Type your reply to staff... Messages synchronize directly into Discord." style="width: 100%; background: var(--bg-secondary); color: var(--text-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.75rem; font-family: inherit; resize: vertical; margin-bottom: 0.75rem;"></textarea>
              <div style="display: flex; justify-content: flex-end;">
                <button type="submit" id="btn-submit-reply" class="btn btn-primary" style="min-height: 44px; padding: 0.5rem 1.5rem;">
                  Send Reply
                </button>
              </div>
            </form>
          </div>
        ` : `
          <div style="text-align: center; padding: 1rem; color: var(--text-dim); font-size: 0.9rem; background: rgba(0, 0, 0, 0.3); border-radius: var(--radius-sm);">
            This ticket is closed. Only authorized staff members can post replies or reopen it.
          </div>
        `}
      </div>
    `;

    // Attach Event Handlers
    document.getElementById('btn-back-tickets')?.addEventListener('click', () => {
      viewingTicketId = null;
      loadTicketsList();
    });

    document.getElementById('btn-claim-ticket')?.addEventListener('click', async () => {
      try {
        await claimTicket(ticketId);
        showToast('You claimed this ticket.', 'success');
        viewTicketDetails(ticketId);
      } catch (e) {
        showToast(e.message || 'Failed to claim ticket', 'error');
      }
    });

    document.getElementById('btn-toggle-status')?.addEventListener('click', async () => {
      const newStatus = isOpen ? 'closed' : 'open';
      try {
        await updateTicketStatus(ticketId, newStatus);
        showToast(`Ticket status changed to ${newStatus}.`, 'success');
        viewTicketDetails(ticketId);
      } catch (e) {
        showToast(e.message || 'Status update failed', 'error');
      }
    });

    document.getElementById('reply-ticket-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('reply-content');
      const content = input?.value.trim();
      if (!content) return;

      const btn = document.getElementById('btn-submit-reply');
      if (btn) btn.disabled = true;

      try {
        await replyTicket(ticketId, content);
        soundFX.playSound('success');
        showToast('Reply posted & synchronized to Discord.', 'success');
        viewTicketDetails(ticketId);
      } catch (err) {
        showToast(err.message || 'Failed to send reply', 'error');
        if (btn) btn.disabled = false;
      }
    });

  } catch (err) {
    container.innerHTML = `<div style="color: #F87171; padding: 2rem; text-align: center;">Error viewing ticket: ${err.message}</div>`;
  }
}

function setupModalEvents() {
  const modalBackdrop = document.getElementById('ticket-modal-backdrop');
  const openBtn = document.getElementById('btn-open-ticket-modal');
  const closeBtn = document.getElementById('btn-close-modal');
  const cancelBtn = document.getElementById('btn-cancel-modal');
  const form = document.getElementById('create-ticket-form');

  openBtn?.addEventListener('click', () => openCreateModal());
  closeBtn?.addEventListener('click', () => closeCreateModal());
  cancelBtn?.addEventListener('click', () => closeCreateModal());

  modalBackdrop?.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) closeCreateModal();
  });

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cat = document.getElementById('ticket-category')?.value;
    const sub = document.getElementById('ticket-subject')?.value.trim();
    const desc = document.getElementById('ticket-description')?.value.trim();

    if (!sub || sub.length < 3) {
      showToast('Subject must be at least 3 characters.', 'error');
      return;
    }
    if (!desc || desc.length < 10) {
      showToast('Description must be at least 10 characters.', 'error');
      return;
    }

    const submitBtn = document.getElementById('btn-submit-ticket');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';
    }

    try {
      const res = await createTicket(cat, sub, desc);
      soundFX.playSound('success');
      showToast(res.message || 'Ticket created successfully!', 'success');
      closeCreateModal();
      form.reset();
      if (res.ticket?.ticket_id) {
        viewTicketDetails(res.ticket.ticket_id);
      } else {
        loadTicketsList();
      }
    } catch (err) {
      showToast(err.message || 'Failed to create ticket', 'error');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit Ticket';
      }
    }
  });
}

function openCreateModal() {
  if (!currentUser) {
    showToast('Please log in with Discord first.', 'error');
    loginWithDiscord();
    return;
  }
  const modal = document.getElementById('ticket-modal-backdrop');
  if (modal) modal.classList.add('active');
}

function closeCreateModal() {
  const modal = document.getElementById('ticket-modal-backdrop');
  if (modal) modal.classList.remove('active');
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
