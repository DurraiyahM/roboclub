/* RoboClub app — auth, API, i18n, single live poll */
const AUTH_KEY = 'roboclub_token';
const LANG_KEY = 'roboclub_lang';

const I18N = {
  en: { search: 'Search schools, trainers, stock…', login: 'Login', logout: 'Logout', live: 'Live', demo: 'Demo', mixed: 'Mixed' },
  ur: { search: 'سکول، ٹرینر، اسٹاک تلاش…', login: 'لاگ ان', logout: 'لاگ آؤٹ', live: 'لائیو', demo: 'ڈیمو', mixed: 'مخلوط' },
};

function getLang() { return localStorage.getItem(LANG_KEY) || 'en'; }
function getToken() { return localStorage.getItem(AUTH_KEY); }

function authHeaders(extra = {}) {
  const h = { ...extra };
  const t = getToken();
  if (t) h.Authorization = 'Bearer ' + t;
  return h;
}

function setLang(l) {
  localStorage.setItem(LANG_KEY, l);
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.getAttribute('data-i18n');
    if (I18N[l] && I18N[l][k]) el.textContent = I18N[l][k];
  });
}

async function apiFetch(path, opts = {}) {
  const r = await fetch((window.API || '') + path, { ...opts, headers: authHeaders(opts.headers || {}) });
  if (!r.ok) throw new Error('API ' + r.status);
  return r.json();
}

function setupSearch() {
  const input = document.getElementById('global-search');
  const box = document.getElementById('search-results');
  if (!input || !box) return;
  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { box.innerHTML = ''; box.style.display = 'none'; return; }
    timer = setTimeout(async () => {
      try {
        const d = await apiFetch('/api/v1/search?q=' + encodeURIComponent(q));
        const rows = [
          ...(d.schools || []).map(x => `<a href="${x.href}" class="search-hit">🏫 ${x.name}</a>`),
          ...(d.trainers || []).map(x => `<a href="${x.href}" class="search-hit">👨‍🏫 ${x.name}</a>`),
          ...(d.inventory || []).map(x => `<a href="${x.href}" class="search-hit">📦 ${x.name}</a>`),
        ];
        box.innerHTML = rows.length ? rows.join('') : '<div class="search-hit">No results</div>';
        box.style.display = 'block';
      } catch (_) {}
    }, 280);
  });
}

function renderCritical(items) {
  const el = document.getElementById('critical-banner');
  if (!el) return;
  if (!items || !items.length) { el.style.display = 'none'; return; }
  el.style.display = 'flex';
  el.innerHTML = items.map(n =>
    `<span class="critical-banner__item">${n.type === 'error' ? '🔴' : '🟡'} ${n.title}</span>`
  ).join('');
}

function setBadgeCount(n) {
  const b = document.getElementById('notif-badge');
  if (!b) return;
  b.textContent = n;
  b.style.display = n > 0 ? 'inline' : 'none';
}

function applyPageBadge(meta) {
  const page = document.body.dataset.page;
  const badge = document.getElementById('page-source-badge');
  if (!badge || !meta || !page || !meta[page]) return;
  const src = meta[page];
  const L = I18N[getLang()];
  badge.textContent = L[src] || src;
  badge.className = 'page-badge page-badge--' + src;
}

function startLivePoll() {
  if (!window.USE_POLLING) return;
  const poll = async () => {
    try {
      const d = await apiFetch('/api/v1/live');
      window.dispatchEvent(new CustomEvent('roboclub:tick', { detail: d }));
      if (typeof d.unread_count === 'number') setBadgeCount(d.unread_count);
      if (d.critical) renderCritical(d.critical);
    } catch (_) {}
  };
  poll();
  setInterval(poll, 4000);
}

async function initShell() {
  try {
    const shell = await apiFetch('/api/v1/bundle/shell');
    setBadgeCount(shell.unread_count);
    renderCritical(shell.critical);
    applyPageBadge(shell.meta);
  } catch (_) {}
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-set-lang]').forEach(b =>
    b.addEventListener('click', () => setLang(b.dataset.setLang))
  );
  setLang(getLang());
  setupSearch();
  initShell();
  startLivePoll();
  const user = localStorage.getItem('roboclub_user');
  if (user) {
    const loginBtn = document.querySelector('a[href="/login"]');
    if (loginBtn) {
      const u = JSON.parse(user);
      loginBtn.textContent = u.name.split(' ')[0];
      loginBtn.href = u.role === 'trainer' ? '/checkin' : '/dashboard';
    }
  }
});
