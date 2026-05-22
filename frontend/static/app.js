/* RoboClub Ultimate — auth, API, i18n, live poll, role nav */
const AUTH_KEY = 'roboclub_token';
const USER_KEY = 'roboclub_user';
const LANG_KEY = 'roboclub_lang';

const ROLE_NAV = {
  ops: ['dashboard', 'attendance', 'checkin', 'payments', 'inventory', 'trainers', 'notifications', 'ceo', 'admin'],
  trainer: ['checkin', 'attendance', 'notifications'],
  ceo: ['ceo', 'dashboard', 'notifications', 'payments'],
};

const PROTECTED_OPS = ['admin'];

const I18N = {
  en: {
    search: 'Search schools, trainers, stock…',
    login: 'Login',
    logout: 'Logout',
    live: 'Live',
    demo: 'Demo',
    mixed: 'Mixed',
    markRead: 'Mark read',
    resolve: 'Resolve',
    snooze: 'Snooze 24h',
    markPaid: 'Mark paid',
    save: 'Save',
  },
  ur: {
    search: 'سکول، ٹرینر، اسٹاک تلاش…',
    login: 'لاگ ان',
    logout: 'لاگ آؤٹ',
    live: 'لائیو',
    demo: 'ڈیمو',
    mixed: 'مخلوط',
    markRead: 'پڑھا',
    resolve: 'حل',
    snooze: '24 گھنٹے',
    markPaid: 'ادا',
    save: 'محفوظ',
  },
};

function getLang() { return localStorage.getItem(LANG_KEY) || 'en'; }
function getToken() { return localStorage.getItem(AUTH_KEY); }

function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

function authHeaders(extra = {}) {
  const h = { ...extra };
  const t = getToken();
  if (t) h.Authorization = 'Bearer ' + t;
  return h;
}

function toast(msg, type = 'ok') {
  let stack = document.getElementById('toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toast-stack';
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }
  const el = document.createElement('div');
  el.className = 'toast toast--' + (type === 'err' ? 'err' : 'ok');
  el.textContent = msg;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function setLang(l) {
  localStorage.setItem(LANG_KEY, l);
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.getAttribute('data-i18n');
    if (I18N[l] && I18N[l][k]) el.textContent = I18N[l][k];
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const k = el.getAttribute('data-i18n-placeholder');
    if (I18N[l] && I18N[l][k]) el.placeholder = I18N[l][k];
  });
}

async function apiFetch(path, opts = {}) {
  const headers = authHeaders(opts.headers || {});
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  const r = await fetch((window.API || '') + path, { ...opts, headers });
  if (r.status === 401) {
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(USER_KEY);
    if (!location.pathname.includes('/login')) {
      location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search);
    }
    throw new Error('Unauthorized');
  }
  if (!r.ok) throw new Error('API ' + r.status);
  if (r.status === 204) return null;
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

function applyRoleNav() {
  const user = getUser();
  const role = user?.role || 'guest';
  const allowed = ROLE_NAV[role] || null;
  document.querySelectorAll('.nav-btn[data-nav-id]').forEach(btn => {
    const id = btn.dataset.navId;
    if (allowed && !allowed.includes(id)) btn.setAttribute('data-hidden', '1');
    else btn.removeAttribute('data-hidden');
  });
  document.querySelectorAll('.mobile-nav a[data-nav-id]').forEach(a => {
    const id = a.dataset.navId;
    if (allowed && !allowed.includes(id)) a.style.display = 'none';
    else a.style.display = '';
  });
  if (user) {
    const loginBtn = document.querySelector('a[href="/login"], .btn-login');
    if (loginBtn) {
      loginBtn.textContent = user.name.split(' ')[0];
      loginBtn.href = role === 'trainer' ? '/checkin' : role === 'ceo' ? '/ceo' : '/dashboard';
      loginBtn.title = 'Signed in as ' + user.email;
    }
  }
}

function guardProtectedPages() {
  const page = document.body.dataset.page;
  const user = getUser();
  if (PROTECTED_OPS.includes(page) && (!user || user.role !== 'ops')) {
    location.href = '/login?next=' + encodeURIComponent(location.pathname);
  }
}

function applyOpsMode(shell) {
  if (!shell?.ops_mode) return;
  const demo = document.getElementById('demo-nav-section');
  if (demo) demo.setAttribute('data-collapsed', '1');
  const ver = document.getElementById('app-version');
  if (ver && shell.version) ver.textContent = 'v' + shell.version + ' · OPS';
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
  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !box.contains(e.target)) box.style.display = 'none';
  });
}

function renderCritical(items) {
  const el = document.getElementById('critical-banner');
  if (!el) return;
  if (!items || !items.length) { el.style.display = 'none'; return; }
  el.style.display = 'flex';
  el.innerHTML = items.map(n =>
    `<a href="/notifications" class="critical-banner__item">${n.type === 'error' ? '🔴' : '🟡'} ${n.title}</a>`
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
    applyOpsMode(shell);
    const ver = document.getElementById('app-version');
    if (ver && shell.version) ver.textContent = 'v' + shell.version;
  } catch (_) {}
}

window.RoboClub = {
  apiFetch,
  toast,
  getUser,
  getToken,
  getLang,
  authHeaders,
  setBadgeCount,
  renderCritical,
};

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-set-lang]').forEach(b =>
    b.addEventListener('click', () => setLang(b.dataset.setLang))
  );
  setLang(getLang());
  setupSearch();
  applyRoleNav();
  guardProtectedPages();
  initShell();
  startLivePoll();

  if (window.api && window.RoboClub) {
    const origApi = window.api;
    window.api = async path => {
      try {
        const el = document.getElementById('api-error');
        const d = await apiFetch(path);
        if (el) el.style.display = 'none';
        return d;
      } catch (e) {
        console.error('API error', path, e);
        showApiError?.('Could not load data. Check connection or try again.');
        return null;
      }
    };
    window.apiPost = async (path, body) => {
      try {
        return await apiFetch(path, { method: 'POST', body: JSON.stringify(body) });
      } catch (e) {
        console.error('API POST', path, e);
        toast('Action failed — sign in as ops or trainer', 'err');
        return null;
      }
    };
    window.apiPut = async (path, body) => {
      try {
        return await apiFetch(path, { method: 'PUT', body: JSON.stringify(body) });
      } catch (e) {
        console.error('API PUT', path, e);
        toast('Update failed', 'err');
        return null;
      }
    };
  }
});
