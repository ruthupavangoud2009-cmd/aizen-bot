/**
 * KYOKA 3.0 — Interactive Commands Directory
 * Instant search, category tabs, and 1-click syntax copy
 */
import { fetchOfficialCommands, showToast } from './api.js';

let allCommands = [];
let activeCategory = 'all';

document.addEventListener('DOMContentLoaded', async () => {
  const container = document.getElementById('commands-list');
  const searchInput = document.getElementById('command-search');
  const categoryContainer = document.getElementById('category-pills');

  if (!container) return;

  try {
    allCommands = await fetchOfficialCommands();
    renderCategories(categoryContainer);
    renderCommands(allCommands, container);
  } catch (err) {
    container.innerHTML = `<p style="color: var(--rose-accent);">Failed to load commands: ${err.message}</p>`;
  }

  // Live Search listener
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      filterAndRender(e.target.value.toLowerCase(), container);
    });
  }
});

function renderCategories(container) {
  if (!container) return;

  const categories = ['all', ...new Set(allCommands.map(c => c.category))];

  container.innerHTML = categories.map(cat => `
    <button class="btn btn-sm ${cat === activeCategory ? 'btn-primary' : 'btn-secondary'} category-pill" data-category="${cat}">
      ${cat.charAt(0).toUpperCase() + cat.slice(1)}
    </button>
  `).join('');

  container.querySelectorAll('.category-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      activeCategory = btn.getAttribute('data-category');
      container.querySelectorAll('.category-pill').forEach(b => {
        b.className = `btn btn-sm ${b === btn ? 'btn-primary' : 'btn-secondary'} category-pill`;
      });
      const query = document.getElementById('command-search')?.value.toLowerCase() || '';
      filterAndRender(query, document.getElementById('commands-list'));
    });
  });
}

function filterAndRender(query, container) {
  const filtered = allCommands.filter(cmd => {
    const matchesCat = activeCategory === 'all' || cmd.category === activeCategory;
    const matchesQuery = !query || cmd.name.toLowerCase().includes(query) || cmd.description.toLowerCase().includes(query);
    return matchesCat && matchesQuery;
  });

  renderCommands(filtered, container);
}

function renderCommands(commands, container) {
  if (!container) return;

  if (commands.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 3rem; color: var(--text-dim); grid-column: 1 / -1;">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">No commands found matching your search.</p>
        <span style="font-size: 0.9rem;">Try different keywords or switch categories.</span>
      </div>
    `;
    return;
  }

  container.innerHTML = commands.map(cmd => `
    <div class="feature-card" style="padding: 1.25rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.6rem;">
        <span class="tag" style="background: rgba(168, 85, 247, 0.15); font-weight: 700;">${cmd.category}</span>
        <button class="btn btn-outline btn-sm copy-btn" data-syntax="${cmd.name}" title="Copy Command">
          Copy
        </button>
      </div>
      <h4 style="font-family: var(--font-mono); color: var(--purple-light); font-size: 1.05rem; margin-bottom: 0.4rem;">
        ${cmd.name}
      </h4>
      <p style="color: var(--text-muted); font-size: 0.88rem; line-height: 1.5;">
        ${cmd.description}
      </p>
    </div>
  `).join('');

  // Attach copy listeners
  container.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const syntax = btn.getAttribute('data-syntax');
      navigator.clipboard.writeText(syntax).then(() => {
        showToast(`Copied ${syntax} to clipboard!`, 'success');
      }).catch(() => {
        showToast(`Selected: ${syntax}`, 'info');
      });
    });
  });
}
