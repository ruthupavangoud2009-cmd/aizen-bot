/**
 * KDC Shop — Interactive Client-Side Catalog, Currency Engine & QR Payment Scanner
 * Supports Discord Boosts, Nitro IDs, and Auto-Delivered Discord Bots.
 */

import { showToast, soundFX } from './api.js';

const KDC_PRODUCTS = [
  // ── Server Boosts ──
  {
    id: 'boost_2',
    category: 'boosts',
    name: '2 Server Boosts',
    icon: '🚀',
    badge: 'POPULAR',
    badgeClass: 'green',
    desc: '2x Discord Server Boosts with 1-month stability & instant fulfillment.',
    price_inr: 200,
    price_usd: 2.0,
    stock: 150,
    is_auto_deliver: false,
    features: [
      '2x Server Boosts applied instantly',
      'Level 1 Perks (50 custom emojis, 128kbps audio)',
      '30-Day Non-Drop Replacement Guarantee',
      'Delivery via temporary server invite link',
    ],
  },
  {
    id: 'boost_4',
    category: 'boosts',
    name: '4 Server Boosts',
    icon: '🚀',
    badge: 'BEST VALUE',
    badgeClass: 'gold',
    desc: '4x Discord Server Boosts for growing communities, clans, and creator hubs.',
    price_inr: 380,
    price_usd: 3.8,
    stock: 120,
    is_auto_deliver: false,
    features: [
      '4x Server Boosts applied in a single batch',
      'Solid Level 1 + 50 custom sticker slots',
      'High-stability aged Discord boost accounts',
      'Full replacement coverage',
    ],
  },
  {
    id: 'boost_8',
    category: 'boosts',
    name: '8 Server Boosts',
    icon: '🚀',
    badge: 'LEVEL 2 READY',
    badgeClass: 'green',
    desc: '8x Discord Server Boosts to instantly unlock Server Level 2 & custom banner.',
    price_inr: 720,
    price_usd: 7.2,
    stock: 90,
    is_auto_deliver: false,
    features: [
      '8x Server Boosts to unlock Level 2',
      'Server Banner & 256kbps HD Voice',
      '50MB file upload limit for all members',
      'Priority fast queue activation',
    ],
  },
  {
    id: 'boost_10',
    category: 'boosts',
    name: '10 Server Boosts',
    icon: '🚀',
    badge: 'HIGH TIER',
    badgeClass: '',
    desc: '10x High-Grade Discord Boosts package with buffer margin for established servers.',
    price_inr: 850,
    price_usd: 8.5,
    stock: 75,
    is_auto_deliver: false,
    features: [
      '10x High-Grade Server Boosts',
      'Guaranteed locked Level 2 with buffer margin',
      'Priority staff delivery & screenshot proof',
      '30-day extended warranty coverage',
    ],
  },
  {
    id: 'boost_14',
    category: 'boosts',
    name: '14 Server Boosts (Level 3)',
    icon: '👑',
    badge: 'ULTIMATE LEVEL 3',
    badgeClass: 'gold',
    desc: '14x Full Server Level 3 Boosts unlocking Custom Vanity URL & 100MB uploads.',
    price_inr: 1150,
    price_usd: 11.5,
    stock: 50,
    is_auto_deliver: false,
    features: [
      '14x Full Server Level 3 Boosts',
      'Custom Vanity URL (discord.gg/yourname)',
      '100MB member file upload limit',
      '384kbps supreme studio audio quality',
      'Animated Server Banner & 500 total emojis',
    ],
  },

  // ── Discord Nitro Subscriptions ──
  {
    id: 'nitro_1m_2b',
    category: 'nitro',
    name: '1 Month Nitro ID (with 2 Boosts)',
    icon: '💎',
    badge: 'HOT DEAL',
    badgeClass: 'gold',
    desc: 'Full Discord Nitro Account / ID with 2 Server Boosts & full global perks.',
    price_inr: 250,
    price_usd: 2.5,
    stock: 80,
    is_auto_deliver: false,
    features: [
      'Full Discord Nitro (1 Month Active)',
      '2 Free Server Boosts included to boost any server',
      '500MB file uploads & HD 4K 60fps streaming',
      'Global custom emojis & animated avatars',
    ],
  },
  {
    id: 'nitro_3m',
    category: 'nitro',
    name: '3 Months Nitro Promo Link',
    icon: '💎',
    badge: 'TRIAL PROMO',
    badgeClass: '',
    desc: '3-Month Discord Nitro Promo Activation for fresh/qualifying Discord accounts.',
    price_inr: 350,
    price_usd: 3.5,
    stock: 60,
    is_auto_deliver: false,
    features: [
      '90 Days of full Discord Nitro perks',
      '2 Boosts included per month',
      'Official Discord partnership promo link',
      'Instant automated delivery link',
    ],
  },
  {
    id: 'nitro_1y',
    category: 'nitro',
    name: '1 Year Nitro Full ID',
    icon: '💎',
    badge: 'ANNUAL VIP',
    badgeClass: 'gold',
    desc: 'Full 12-Month Annual Discord Nitro Account with recurring boosts.',
    price_inr: 2200,
    price_usd: 22.0,
    stock: 25,
    is_auto_deliver: false,
    features: [
      '365 Days of unmetered Discord Nitro',
      '2 Recurring Server Boosts included all year',
      'Exclusive Discord Nitro profile badge',
      'Massive savings vs monthly pricing',
    ],
  },

  // ── Auto-Delivery Pre-Built Discord Bots ──
  {
    id: 'bot_music',
    category: 'bots',
    name: 'Basic Music Only Bot (Python / Lavalink v4)',
    icon: '🎵',
    badge: 'AUTO DELIVER ⚡',
    badgeClass: 'green',
    desc: 'High-fidelity 24/7 Discord Music Bot source code. Plug & Play ready with setup guide.',
    price_inr: 50,
    price_usd: 0.5,
    stock: 999,
    is_auto_deliver: true,
    features: [
      'Complete working Python source code & dependencies',
      'Lavalink v4 / Wavelink audio engine support',
      'Commands: !play, !skip, !pause, !volume, !queue, !loop',
      'Includes .env.example, requirements.txt & 1-minute setup guide',
      'Instant automatic zip package delivery upon payment',
    ],
  },
  {
    id: 'bot_chat',
    category: 'bots',
    name: 'Auto Chat AI Bot (Gemini Neural Engine)',
    icon: '🤖',
    badge: 'AUTO DELIVER ⚡',
    badgeClass: 'green',
    desc: 'Smart AI conversation Discord bot powered by Google Gemini Neural API.',
    price_inr: 50,
    price_usd: 0.5,
    stock: 999,
    is_auto_deliver: true,
    features: [
      'Full Python Discord.py AI companion source code',
      'Connected to Google Gemini Pro / Flash API',
      'Dedicated chat channel triggers & DM support',
      'Context memory & customizable bot persona / system prompt',
      'Instant automated zip file delivery upon payment',
    ],
  },
  {
    id: 'bot_allinone',
    category: 'bots',
    name: 'All-In-One Ultimate Bot (Aizen / Kyoka Edition)',
    icon: '👑',
    badge: 'FLAGSHIP SUITE 👑',
    badgeClass: 'gold',
    desc: 'The Absolute Ultimate Discord Bot suite: Music, Antinuke, Tickets, AI & Mod.',
    price_inr: 300,
    price_usd: 3.0,
    stock: 999,
    is_auto_deliver: true,
    features: [
      'Full multi-cog production architecture (Music, Mod, Tickets, AI, Welcome)',
      'Automated Antinuke defense & audit logger',
      'Appy-style interactive button tickets with HTML transcripts',
      'Dual SQLite / PostgreSQL async database support',
      'Complete deployment guide for VPS, Render & Railway',
      'Instant automatic zip package delivery',
    ],
  },
  {
    id: 'bot_tickets',
    category: 'bots',
    name: 'Ticket & Support Hub Bot',
    icon: '🎫',
    badge: 'ENTERPRISE 🎫',
    badgeClass: 'green',
    desc: 'Enterprise Discord support ticket bot with interactive buttons & transcripts.',
    price_inr: 120,
    price_usd: 1.2,
    stock: 999,
    is_auto_deliver: true,
    features: [
      'Persistent Discord Button & Select Menu panels',
      'Multi-category inquiries & staff role claiming',
      'Automatic HTML transcript generation & channel archiving',
      'Full Python source code with setup guide',
    ],
  },
  {
    id: 'bot_antinuke',
    category: 'bots',
    name: 'Anti-Nuke Security Guard Bot',
    icon: '🛡️',
    badge: 'MAX SECURITY 🛡️',
    badgeClass: '',
    desc: 'Military-grade Discord server protection with sub-millisecond anti-raid locks.',
    price_inr: 150,
    price_usd: 1.5,
    stock: 999,
    is_auto_deliver: true,
    features: [
      'Anti-ban, anti-kick, anti-channel-delete, and anti-role-delete',
      'Whitelisted administrator hierarchy & quarantine role strip',
      'Panic emergency server lockdown command',
      'Real-time forensic security audit logging',
    ],
  },
];

let currentCurrency = 'INR'; // 'INR' or 'USD'
let currentCategory = 'all';  // 'all' | 'boosts' | 'nitro' | 'bots'
let activeModalItem = null;

function renderCatalog() {
  const container = document.getElementById('shop-products-grid');
  if (!container) return;

  const filtered = KDC_PRODUCTS.filter(p => {
    if (currentCategory === 'all') return true;
    return p.category === currentCategory;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 4rem 1rem; color: var(--text-dim);">
        <span style="font-size: 3rem; display: block; margin-bottom: 0.5rem;">🔍</span>
        <h3>No products found in this category.</h3>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(item => {
    return `
      <div class="product-card" data-id="${item.id}">
        <span class="product-badge ${item.badgeClass || ''}">${item.badge || 'IN STOCK'}</span>
        <div class="product-icon">${item.icon}</div>
        <h3 class="product-title">${item.name}</h3>
        <p class="product-desc">${item.desc}</p>

        <div class="product-price-box" style="flex-wrap: wrap; gap: 0.35rem; align-items: baseline;">
          <span class="price-val">₹${item.price_inr}</span>
          <span style="font-size: 0.82rem; color: #F87171; text-decoration: line-through; margin-left: 0.2rem;">$${item.price_usd.toFixed(2)}</span>
          <span style="font-size: 0.68rem; color: #EF4444; background: rgba(239, 68, 68, 0.18); padding: 0.1rem 0.35rem; border-radius: 4px; font-weight: 700;">USD Unavailable</span>
          <span class="price-stock" style="margin-left: auto;">
            <span>●</span> ${item.is_auto_deliver ? '⚡ Instant Auto-Deliver' : `🟢 In Stock (${item.stock})`}
          </span>
        </div>

        <ul class="feature-list">
          ${item.features.map(f => `<li>${f}</li>`).join('')}
        </ul>

        <button class="btn btn-primary btn-buy-item" data-id="${item.id}" style="width: 100%; margin-top: auto;">
          <span>🧾</span>
          <span>Buy Now / Make Bill (₹ INR)</span>
        </button>
      </div>
    `;
  }).join('');

  // Attach button listeners
  container.querySelectorAll('.btn-buy-item').forEach(btn => {
    btn.addEventListener('click', () => {
      soundFX.playSound('click');
      const itemId = btn.getAttribute('data-id');
      const item = KDC_PRODUCTS.find(p => p.id === itemId);
      if (item) openCheckoutModal(item);
    });
  });
}

function openCheckoutModal(item) {
  activeModalItem = item;
  const modal = document.getElementById('shop-checkout-modal');
  if (!modal) return;

  const randomId = 'KDC-' + Math.random().toString(36).substring(2, 8).toUpperCase();
  const qrUrl = '/assets/kdc_payment_qr.png';

  document.getElementById('modal-item-icon').textContent = item.icon;
  document.getElementById('modal-item-title').textContent = item.name;
  document.getElementById('modal-bill-id').textContent = randomId;
  document.getElementById('modal-total-price').innerHTML = `₹${item.price_inr} <span style="font-size: 0.8rem; color: #FCA5A5; text-decoration: line-through; margin-left: 0.4rem; font-weight: 600;">$${item.price_usd.toFixed(2)} USD</span> <span style="font-size: 0.7rem; color: #EF4444; font-weight: 800; background: rgba(239, 68, 68, 0.18); padding: 0.1rem 0.4rem; border-radius: 4px;">USD Unavailable</span>`;
  document.getElementById('modal-fulfillment').textContent = item.is_auto_deliver ? '⚡ Instant Zip Auto-Delivery' : '🚀 Server Invite / Staff Delivery';
  
  const qrImg = document.getElementById('modal-qr-img');
  if (qrImg) {
    qrImg.src = qrUrl;
    qrImg.alt = 'Official KDC UPI Payment QR Scanner';
  }

  const usdNotice = document.getElementById('modal-usd-notice');
  if (usdNotice) {
    usdNotice.style.display = 'block';
  }

  modal.style.display = 'flex';
}

function closeCheckoutModal() {
  const modal = document.getElementById('shop-checkout-modal');
  if (modal) modal.style.display = 'none';
  activeModalItem = null;
}

document.addEventListener('DOMContentLoaded', () => {
  renderCatalog();

  // Category Tabs
  document.querySelectorAll('.shop-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      soundFX.playSound('click');
      document.querySelectorAll('.shop-tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentCategory = btn.getAttribute('data-cat') || 'all';
      renderCatalog();
    });
  });

  // Currency Switcher
  const inrBtn = document.getElementById('curr-inr-btn');
  const usdBtn = document.getElementById('curr-usd-btn');

  inrBtn?.addEventListener('click', () => {
    soundFX.playSound('click');
    currentCurrency = 'INR';
    inrBtn.classList.add('active');
    usdBtn?.classList.remove('active');
    renderCatalog();
  });

  usdBtn?.addEventListener('click', () => {
    soundFX.playSound('click');
    showToast('❌ USD payments are currently unavailable. Please pay in ₹ INR using the official scanner.', 'error');
    currentCurrency = 'INR';
    inrBtn?.classList.add('active');
    usdBtn?.classList.remove('active');
    renderCatalog();
  });

  // Modal Close Listeners
  document.getElementById('modal-close-btn')?.addEventListener('click', closeCheckoutModal);
  document.getElementById('shop-checkout-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'shop-checkout-modal') closeCheckoutModal();
  });



  // Auto Deliver / Verify button inside modal
  document.getElementById('modal-claim-btn')?.addEventListener('click', () => {
    soundFX.playSound('success');
    if (!activeModalItem) return;
    if (activeModalItem.is_auto_deliver) {
      showToast(`⚡ Bot Auto-Delivery: Open Discord and type "stock" or verify Transaction ID for ${activeModalItem.name}!`, 'success');
    } else {
      showToast(`🚀 Boost / Nitro Order: Open Discord and send your server invite link with invoice ID!`, 'info');
    }
  });

  // ─── Super Simple Customer Reviews Engine ───
  initReviewsEngine();

  // Keyboard Escape
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeCheckoutModal();
      closeReviewModal();
    }
  });
});

const DEFAULT_REVIEWS = [
  {
    id: 'REV-BOOTS4',
    name: 'vortex_gamer',
    rating: 5,
    product: '4 Server Boosts',
    comment: 'Ordered 4 boosts and they were applied to my server within 2 minutes! Legit and fast.',
    date: '3 days ago',
  },
  {
    id: 'REV-ALLBOT',
    name: 'dev_rahul',
    rating: 5,
    product: 'All-In-One Ultimate Bot',
    comment: 'Bought the All-In-One bot zip for 300rs. Fully coded, clean multi-cog architecture, runs like a dream!',
    date: '2 days ago',
  },
  {
    id: 'REV-NITRO1',
    name: 'shadow_strike',
    rating: 5,
    product: '1 Month Nitro ID + 2 Boosts',
    comment: '1 Month Nitro ID + 2 boosts worked instantly. Great support from Aizen and team.',
    date: '1 day ago',
  },
  {
    id: 'REV-MUSICB',
    name: 'melodix_dj',
    rating: 5,
    product: 'Basic Music Only Bot',
    comment: 'Super simple 50rs music bot with Lavalink support. Audio quality is crisp 10/10.',
    date: '12 hours ago',
  },
  {
    id: 'REV-BOOST10',
    name: 'blaze_rider',
    rating: 5,
    product: '10 Server Boosts',
    comment: 'Best Discord shop, cheapest rates for 10 boosts and scanner verification was instant.',
    date: '4 hours ago',
  },
];

function getStoredReviews() {
  try {
    const raw = localStorage.getItem('kdc_customer_reviews');
    if (raw) return JSON.parse(raw);
  } catch (e) {
    // fallback
  }
  return DEFAULT_REVIEWS;
}

function storeReviews(revList) {
  try {
    localStorage.setItem('kdc_customer_reviews', JSON.stringify(revList));
  } catch (e) {
    // ignore
  }
}

function renderReviews() {
  const container = document.getElementById('reviews-grid');
  const avgElem = document.getElementById('review-stat-avg');
  const countElem = document.getElementById('review-stat-count');
  if (!container) return;

  const reviews = getStoredReviews();
  const total = reviews.length;
  const avg = total > 0 ? (reviews.reduce((acc, r) => acc + Number(r.rating || 5), 0) / total).toFixed(1) : '5.0';

  if (avgElem) avgElem.textContent = `${avg} / 5.0`;
  if (countElem) countElem.textContent = `Based on ${total} verified reviews`;

  container.innerHTML = reviews.map(r => {
    const stars = '⭐'.repeat(Math.max(1, Math.min(5, Number(r.rating) || 5)));
    return `
      <div style="background: rgba(15, 7, 30, 0.7); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between;">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <span style="font-size: 1.05rem;">${stars}</span>
            <span style="font-size: 0.72rem; color: #10B981; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); padding: 0.15rem 0.45rem; border-radius: 4px; font-weight: 700;">VERIFIED BUYER</span>
          </div>
          <div style="color: var(--purple-pastel); font-size: 0.82rem; font-weight: 700; margin-bottom: 0.5rem;">
            ${r.product || 'KDC Services'}
          </div>
          <p style="color: #E2E8F0; font-size: 0.88rem; font-style: italic; line-height: 1.4; margin: 0 0 1rem;">
            "${r.comment || 'Great service!'}"
          </p>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 0.6rem; font-size: 0.78rem; color: var(--text-dim);">
          <span style="font-weight: 700; color: #fff;">@${r.name || 'Anonymous'}</span>
          <span>${r.date || 'Recently'}</span>
        </div>
      </div>
    `;
  }).join('');
}

function openReviewModal() {
  soundFX.playSound('open');
  const modal = document.getElementById('write-review-modal');
  if (modal) modal.style.display = 'flex';
}

function closeReviewModal() {
  soundFX.playSound('close');
  const modal = document.getElementById('write-review-modal');
  if (modal) modal.style.display = 'none';
}

function initReviewsEngine() {
  renderReviews();

  document.getElementById('open-review-modal-btn')?.addEventListener('click', openReviewModal);
  document.getElementById('review-modal-close-btn')?.addEventListener('click', closeReviewModal);

  document.getElementById('write-review-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'write-review-modal') closeReviewModal();
  });

  const form = document.getElementById('write-review-form');
  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    const rating = document.getElementById('review-form-rating')?.value || '5';
    const name = document.getElementById('review-form-name')?.value.trim() || 'Customer';
    const product = document.getElementById('review-form-product')?.value.trim() || 'KDC Shop';
    const comment = document.getElementById('review-form-comment')?.value.trim();

    if (!comment) {
      showToast('Please enter your review comment', 'warning');
      return;
    }

    const newRev = {
      id: `REV-${Date.now().toString(36).toUpperCase()}`,
      name,
      rating: Number(rating),
      product,
      comment,
      date: 'Just now',
    };

    const currentList = getStoredReviews();
    currentList.unshift(newRev);
    storeReviews(currentList);

    soundFX.playSound('success');
    renderReviews();
    closeReviewModal();
    form.reset();

    showToast('⭐ Thank you! Your review is now live on KDC Shop.', 'success');
  });
}
