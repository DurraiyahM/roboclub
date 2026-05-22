/* RoboClub shared client */
const AUTH_KEY = 'roboclub_token';
const LANG_KEY = 'roboclub_lang';

const I18N = {
  en: {
    search: 'Search schools, trainers, stock…',
    login: 'Login',
    logout: 'Logout',
    live: 'Live',
    demo: 'Demo',
    mixed: 'Mixed',
  },
  ur: {
    search: 'سکول، ٹرینر، اسٹاک تلاش…',
    login: 'لاگ ان',
    logout: 'لاگ آؤٹ',
    live: 'لائیو',
    demo: 'ڈیمو',
    mixed: 'مخلوط',
  },
};

function getLang() {
  return localStorage.getItem(LANG_KEY) || 'en';
}

function setLang(l) {
  localStorage.setItem(LANG_KEY, l);
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.getAttribute('data-i18n');
    if (I18N[l] && I18N[l][k]) el.textContent = I18N[l][k];
  });
}

function getToken() {
  return localStorage.getItem(AUTH_KEY);
}

function setToken(t) {
  if (t) localStorage.setItem(AUTH_KEY, t);
  else localStorage.removeItem(AUTH_KEY);
}

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: 'Bearer ' + t } : {};
}

async function apiAuth(path, opts = {}) {
  const headers = { ...authHeaders(), ...(opts.headers || {}) };
  const r = await fetch((window.API || '') + path, { ...opts, headers });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

async function loadPageMeta() {
  const m = await api('/api/meta/pages');
  if (!m) return;
  window.PAGE_META = m;
  const page = document.body.dataset.page;
  if (!page || !m[page]) return;
  const badge = document.getElementById('page-source-badge');
  if (!badge) return;
  const src = m[page];
  const labels = { live: I18N[getLang()].live, demo: I18N[getLang()].demo, mixed: I18N[getLang()].mixed };
  badge.textContent = labels[src] || src;
  badge.className = 'page-badge page-badge--' + src;
}

async function loadCriticalBanner() {
  const el = document.getElementById('critical-banner');
  if (!el) return;
  const items = await api('/api/notifications/critical');
  if (!items || !items.length) {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'block';
  el.innerHTML = items.map(n =>
    `<span class="critical-banner__item">${n.type === 'error' ? '🔴' : '🟡'} ${n.title}</span>`
  ).join('');
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
      const d = await api('/api/search?q=' + encodeURIComponent(q));
      if (!d) return;
      const rows = [
        ...(d.schools || []).map(x => `<a href="${x.href}" class="search-hit">🏫 ${x.name} · ${x.city}</a>`),
        ...(d.trainers || []).map(x => `<a href="${x.href}" class="search-hit">👨‍🏫 ${x.name}</a>`),
        ...(d.inventory || []).map(x => `<a href="${x.href}" class="search-hit">📦 ${x.sku} ${x.name}</a>`),
      ];
      box.innerHTML = rows.length ? rows.join('') : '<div class="search-hit">No results</div>';
      box.style.display = 'block';
    }, 300);
  });
}

function setupLangToggle() {
  document.querySelectorAll('[data-set-lang]').forEach(btn => {
    btn.addEventListener('click', () => setLang(btn.dataset.setLang));
  });
  setLang(getLang());
}

document.addEventListener('DOMContentLoaded', () => {
  setupLangToggle();
  setupSearch();
  loadPageMeta();
  loadCriticalBanner();
  setInterval(loadCriticalBanner, 20000);
});
