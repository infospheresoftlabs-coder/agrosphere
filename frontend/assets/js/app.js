/* AgroSphere — application shell, routing and views. */
import {
  API, api, setSession, img, t, setLang, applyTheme, currentTheme, toast,
  el, esc, inr, pct, fmtDate, titleCase, STATE_TONE, SEV_TONE, chip,
  statCard, moduleHero, emptyState, modal, field, input, select, bar, bindForm,
} from './core.js';

const app = document.getElementById('root');
let META = null;
let ME = null;

/* --------------------------------------------------------------- routing */
const ROUTES = {
  dashboard: { label: 'dashboard', icon: '◎', roles: null, render: viewDashboard },
  modules: { label: 'modules', icon: '▦', roles: null, render: viewModules },
  farms: { label: 'farms', icon: '⬡', roles: ['farmer', 'farm_manager', 'agronomist', 'super_admin'] , render: viewFarms },
  cases: { label: 'cases', icon: '❧', roles: null, render: viewCases },
  drone: { label: 'drone', icon: '✈', roles: ['drone_operator', 'farm_manager', 'super_admin'], render: viewDroneOps },
  fleet: { label: 'fleet', icon: '⛭', roles: ['drone_operator', 'super_admin'], render: viewFleet },
  reports: { label: 'reports', icon: '▤', roles: null, render: viewReports },
  payments: { label: 'payments', icon: '₹', roles: ['farmer', 'farm_manager', 'super_admin'], render: viewPayments },
  notifications: { label: 'notifications', icon: '🔔', roles: null, render: viewNotifications },
  grievances: { label: 'grievances', icon: '☎', roles: null, render: viewGrievances },
  knowledge: { label: 'knowledge', icon: '📚', roles: null, render: viewKnowledge },
  analytics: { label: 'analytics', icon: '📈', roles: null, render: viewAnalytics },
  admin: { label: 'admin', icon: '⚙', roles: ['super_admin'], render: viewAdmin },
  audit: { label: 'audit', icon: '🔒', roles: ['super_admin'], render: viewAudit },
  settings: { label: 'settings', icon: '⚑', roles: null, render: viewSettings },
};

let route = location.hash.replace('#', '') || 'dashboard';

function navigate(r) {
  route = r;
  location.hash = r;
  render();
  document.querySelector('.sidebar')?.classList.remove('open');
}

window.addEventListener('hashchange', () => { route = location.hash.replace('#', '') || 'dashboard'; render(); });

/* --------------------------------------------------------------- bootstrap */
async function boot() {
  applyTheme(currentTheme());
  try {
    META = await api('/meta');
  } catch (e) { console.error(e); }
  if (API.token) {
    try { ME = await api('/auth/me'); } catch { setSession(null, null); ME = null; }
  }
  render();
}

/* --------------------------------------------------------------- auth view */
function viewAuth() {
  app.replaceChildren();
  const wrap = el('div', { class: 'auth-wrap' });

  const hero = el('div', { class: 'auth-hero' },
    el('img', { class: 'bg', src: img('hero'), alt: 'AgroSphere farm landscape' }),
    el('div', { class: 'brandline' },
      el('img', { src: img('logo_mark'), alt: 'AgroSphere logo' }),
      el('div', {}, el('strong', {}, 'AgroSphere'), el('span', {}, 'Agriculture intelligence')),
    ),
    el('div', {},
      el('h1', {}, 'Crop-health intelligence for every Indian farm.'),
      el('p', { class: 'lead' }, 'A secure, multilingual, AI-powered platform connecting farmers, agronomists, farm managers and drone operators — from field capture to verified treatment.'),
      el('div', { class: 'pills' },
        el('span', {}, '5 enforced roles'),
        el('span', {}, '22 Indian languages'),
        el('span', {}, 'Verified ICAR sources'),
        el('span', {}, 'Drone simulator'),
        el('span', {}, 'Light & dark themes'),
      ),
    ),
  );

  const card = el('div', { class: 'auth-card' });
  let mode = 'login';

  const email = input('email', { type: 'email', placeholder: 'you@example.com', autocomplete: 'username' });
  const password = input('password', { type: 'password', placeholder: '••••••••', autocomplete: 'current-password' });
  const fullname = input('full_name', { placeholder: 'Your full name' });
  const roleSel = select('role', (META?.signup_roles || META?.roles || []).map(r => ({ value: r.key, label: r.label })));
  const langSel = select('language', (META?.languages || []).map(l => ({ value: l.code, label: `${l.native} — ${l.name}` })));

  function drawCard() {
    card.replaceChildren();
    const tabs = el('div', { class: 'tabs' },
      el('button', { class: mode === 'login' ? 'active' : '', onclick: () => { mode = 'login'; drawCard(); } }, 'Sign in'),
      el('button', { class: mode === 'register' ? 'active' : '', onclick: () => { mode = 'register'; drawCard(); } }, 'Create account'),
    );
    const form = el('form');
    form.appendChild(field('Email', email));
    form.appendChild(field('Password', password));
    if (mode === 'register') {
      form.appendChild(field('Full name', fullname));
      form.appendChild(field('Role', roleSel, 'Role permissions are enforced on the server.'));
      form.appendChild(field('Preferred language', langSel));
    }
    const btn = el('button', { class: 'btn block', type: 'submit' }, mode === 'login' ? 'Sign in' : 'Create account');
    form.appendChild(btn);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      btn.disabled = true; btn.textContent = 'Please wait…';
      try {
        const body = mode === 'login'
          ? { email: email.value, password: password.value }
          : { email: email.value, password: password.value, full_name: fullname.value, role: roleSel.value, language: langSel.value };
        const res = await api(mode === 'login' ? '/auth/login' : '/auth/register', { method: 'POST', body });
        setSession(res.token, res.user);
        ME = res.user;
        if (res.user.language) { setLang(res.user.language); }
        toast(`Welcome, ${res.user.full_name}`);
        render();
      } catch (err) { toast(err.message, 'error'); }
      finally { btn.disabled = false; btn.textContent = mode === 'login' ? 'Sign in' : 'Create account'; }
    });

    card.appendChild(el('div', {}, el('h2', {}, mode === 'login' ? 'Sign in to AgroSphere' : 'Join AgroSphere'),
      el('p', { style: 'color:var(--text-2);margin:6px 0 20px;font-size:.9rem' },
        mode === 'login' ? 'Use a demo account below or your own credentials.' : 'Create your account to begin.')));
    card.appendChild(tabs);
    card.appendChild(form);

    if (mode === 'login') {
      card.appendChild(el('div', { style: 'margin:22px 0 10px;font-size:.74rem;text-transform:uppercase;letter-spacing:.1em;color:var(--text-3);font-weight:700' }, 'Demo accounts'));
      const grid = el('div', { class: 'demo-grid' });
      for (const a of DEMO_ACCOUNTS) {
        grid.appendChild(el('button', {
          class: 'demo-account', type: 'button',
          onclick: () => { email.value = a.email; password.value = a.password; },
        },
          el('img', { src: img(a.image), alt: a.label }),
          el('div', {}, el('b', {}, a.label), el('small', {}, a.email)),
        ));
      }
      card.appendChild(grid);
    }
  }
  drawCard();
  wrap.append(hero, el('div', { class: 'auth-panel' }, card));
  app.appendChild(wrap);
}

const DEMO_ACCOUNTS = [
  { email: 'farmer@agrosphere.in', password: 'agro1234', label: 'Farmer — Ramesh Patil', image: 'role_farmer' },
  { email: 'agronomist@agrosphere.in', password: 'agro1234', label: 'Agronomist — Dr. Anjali Deshmukh', image: 'role_agronomist' },
  { email: 'manager@agrosphere.in', password: 'agro1234', label: 'Farm Manager — Suresh Kulkarni', image: 'role_manager' },
  { email: 'operator@agrosphere.in', password: 'agro1234', label: 'Drone Operator — Vikram Singh', image: 'role_drone_operator' },
  { email: 'admin@agrosphere.in', password: 'agro1234', label: 'Super Admin — Priya Nair', image: 'role_admin' },
];

/* --------------------------------------------------------------- shell */
function render() {
  if (!ME) { viewAuth(); return; }
  app.replaceChildren();
  const shell = el('div', { class: 'shell' });
  shell.append(buildSidebar(), buildMain());
  app.appendChild(shell);
}

function buildSidebar() {
  const sb = el('aside', { class: 'sidebar' });
  sb.appendChild(el('div', { class: 'brand' },
    el('img', { src: img('logo_mark'), alt: 'AgroSphere' }),
    el('div', {}, el('b', {}, 'AgroSphere'), el('small', {}, 'Agri intelligence')),
  ));
  const nav = el('nav', { class: 'nav' });
  const groups = [
    ['Workspace', ['dashboard', 'modules', 'analytics']],
    ['Operations', ['farms', 'cases', 'reports']],
    ['Field services', ['drone', 'fleet', 'payments']],
    ['Engagement', ['notifications', 'grievances', 'knowledge']],
    ['Governance', ['admin', 'audit', 'settings']],
  ];
  for (const [label, keys] of groups) {
    const visible = keys.filter(k => allowed(k));
    if (!visible.length) continue;
    nav.appendChild(el('div', { class: 'group-label' }, label));
    for (const k of visible) {
      const r = ROUTES[k];
      nav.appendChild(el('a', {
        class: route === k ? 'active' : '', onclick: () => navigate(k),
      }, el('span', { class: 'ic' }, r.icon), el('span', {}, t(r.label))));
    }
  }
  sb.appendChild(nav);
  sb.appendChild(el('div', { class: 'foot' },
    el('div', { style: 'display:flex;gap:10px;align-items:center;margin-bottom:10px' },
      el('img', { src: img(ME.avatar_image), alt: ME.full_name, style: 'width:36px;height:36px;border-radius:9px;object-fit:cover' }),
      el('div', { style: 'min-width:0' }, el('b', { style: 'font-size:.85rem;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis' }, ME.full_name),
        el('small', { style: 'color:var(--text-3);font-size:.74rem' }, ME.role_label)),
    ),
    el('button', { class: 'btn ghost block sm', onclick: () => { setSession(null, null); ME = null; navigate('dashboard'); } }, t('logout')),
  ));
  return sb;
}

function allowed(key) {
  const r = ROUTES[key];
  if (!r || !r.roles) return true;
  return r.roles.includes(ME.role);
}

function buildMain() {
  const main = el('div', { class: 'main' });
  const top = el('header', { class: 'topbar' });
  top.appendChild(el('button', { class: 'icon-btn menu-btn', onclick: () => document.querySelector('.sidebar').classList.toggle('open'), 'aria-label': 'Menu' }, '☰'));
  const head = el('div', { class: 'grow' }, el('h3', {}, t(ROUTES[route]?.label || 'dashboard')));
  top.appendChild(head);
  top.appendChild(el('button', { class: 'icon-btn', title: 'Toggle theme', onclick: toggleTheme }, themeIcon()));
  top.appendChild(el('button', { class: 'icon-btn', title: 'Notifications', onclick: () => navigate('notifications') }, '🔔'));
  top.appendChild(el('img', { src: img(ME.avatar_image), alt: ME.full_name, style: 'width:38px;height:38px;border-radius:10px;object-fit:cover' }));
  main.appendChild(top);

  const content = el('div', { class: 'content' });
  content.id = 'view';
  main.appendChild(content);
  main.appendChild(el('footer', { class: 'app-footer' },
    el('span', {}, 'AgroSphere v1.0.0 — AI findings are preliminary and require agronomist review.'),
    el('span', { style: 'margin-left:auto' }, `${ME.role_label} · ${ME.email}`),
  ));

  const view = ROUTES[route];
  if (!view || !allowed(route)) {
    content.appendChild(emptyState('module_workflow', 'Not available', 'This section is not available for your role.'));
  } else {
    try { view.render(content); } catch (e) { console.error(e); content.appendChild(el('div', { class: 'alert danger' }, `View error: ${e.message}`)); }
  }
  return main;
}

function themeIcon() {
  const m = currentTheme();
  return m === 'dark' ? '🌙' : m === 'light' ? '☀' : '◐';
}
function toggleTheme() {
  const order = ['light', 'dark', 'system'];
  const next = order[(order.indexOf(currentTheme()) + 1) % order.length];
  applyTheme(next);
  if (ME) api('/auth/me', { method: 'PATCH', body: { theme: next } }).catch(() => {});
  render();
  toast(`Theme: ${next}`);
}

/* --------------------------------------------------------------- dashboard */
async function viewDashboard(root) {
  root.appendChild(moduleHero({
    image: 'hero', tag: 'Command centre',
    title: `Welcome back, ${ME.full_name.split(' ')[0]}`,
    body: 'Your farm-to-harvest command centre: crop health, approvals, field operations and verified advisory in one place.',
  }));
  const grid = el('div', { class: 'grid c4' });
  root.appendChild(grid);

  let stats = null, cases = [];
  try { stats = await api('/analytics'); } catch {}
  try { cases = await api('/cases'); } catch {}
  if (stats) {
    grid.append(
      statCard('Active cases', stats.cases_total, `${Object.keys(stats.by_state).length} states in play`),
      statCard('Avg AI uncertainty', pct(stats.avg_uncertainty), 'Lower is more confident', stats.avg_uncertainty > 0.4 ? 'gold' : 'green'),
      statCard('Missions', stats.missions, `${stats.treated_acres} acres treated`),
      statCard('Revenue', inr(stats.revenue_inr), 'Paid invoices', 'gold'),
    );
  }

  const cols = el('div', { class: 'grid c2' });
  root.appendChild(cols);

  const recent = el('div', { class: 'card' });
  recent.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Recent crop-health cases'),
    el('button', { class: 'btn ghost sm', onclick: () => navigate('cases') }, 'View all')));
  if (cases.length) {
    const tbl = el('table', { class: 'table' });
    tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Reference'), el('th', {}, 'Crop'), el('th', {}, 'State'), el('th', {}, 'Severity'))));
    const tb = el('tbody');
    for (const c of cases.slice(0, 6)) {
      tb.appendChild(el('tr', { onclick: () => openCase(c.id) },
        el('td', { class: 'strong' }, c.reference),
        el('td', {}, c.field?.crop || '—'),
        el('td', {}, chip(titleCase(c.state), STATE_TONE[c.state] || 'grey')),
        el('td', {}, chip(titleCase(c.severity), SEV_TONE[c.severity] || 'grey')),
      ));
    }
    tbl.appendChild(tb); recent.appendChild(tbl);
  } else {
    recent.appendChild(emptyState('module_crop_health', 'No cases yet', 'Create your first crop-health case to begin.'));
  }
  cols.appendChild(recent);

  const roleCard = el('div', { class: 'card' });
  roleCard.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Your role at a glance')));
  roleCard.appendChild(el('div', { class: 'kv' },
    el('dt', {}, 'Role'), el('dd', {}, ME.role_label),
    el('dt', {}, 'Verification'), el('dd', {}, chip(titleCase(ME.verification_status), ME.verification_status === 'verified' ? 'green' : 'gold')),
    el('dt', {}, 'Language'), el('dd', {}, (META?.languages || []).find(l => l.code === ME.language)?.name || ME.language),
    el('dt', {}, 'AI provider'), el('dd', {}, META?.ai?.mode === 'live' ? chip('Live provider', 'green') : chip('Simulator (labelled)', 'gold')),
  ));
  roleCard.appendChild(el('div', { class: 'alert info', style: 'margin-top:16px' },
    'Server-side role enforcement is active: each action you can take is validated by the API, not just hidden in the interface.'));
  cols.appendChild(roleCard);

  root.appendChild(await moduleStrip());
}

async function moduleStrip() {
  const wrap = el('div', { class: 'card', style: 'margin-top:18px' });
  wrap.appendChild(el('div', { class: 'card-head' }, el('div', { class: 'grow' },
    el('h3', {}, 'Platform modules'), el('p', {}, 'Every module ships with generative artwork and real backend wiring.'))));
  const grid = el('div', { class: 'module-grid' });
  for (const m of (META?.modules || []).slice(0, 6)) {
    grid.appendChild(el('div', { class: 'module-card', onclick: () => navigate('modules') },
      el('img', { src: img(m.image), alt: m.title, loading: 'lazy' }),
      el('div', { class: 'body' }, el('h3', {}, m.title), el('p', {}, m.summary)),
    ));
  }
  wrap.appendChild(grid);
  return wrap;
}

/* --------------------------------------------------------------- modules */
function viewModules(root) {
  root.appendChild(moduleHero({
    image: 'module_analytics', tag: 'Module catalogue',
    title: 'Platform modules',
    body: 'AgroSphere is a modular platform. Each module below is backed by real API endpoints and illustrated with generative agricultural artwork.',
  }));
  const grid = el('div', { class: 'module-grid' });
  for (const m of (META?.modules || [])) {
    grid.appendChild(el('div', { class: 'module-card' },
      el('img', { src: img(m.image), alt: m.title, loading: 'lazy' }),
      el('div', { class: 'body' }, el('h3', {}, m.title), el('p', {}, m.summary)),
    ));
  }
  root.appendChild(grid);
}

/* --------------------------------------------------------------- farms */
async function viewFarms(root) {
  root.appendChild(moduleHero({
    image: 'module_farm_mapping', tag: 'Precision agriculture',
    title: 'Farms, fields & geospatial records',
    body: 'Boundaries are stored as GeoJSON-compatible polygons and acreage is computed from real geometry, not estimated from screen pixels.',
  }));
  let farms = [];
  try { farms = await api('/farms'); } catch (e) { toast(e.message, 'error'); }

  const head = el('div', { class: 'page-head' }, el('div', { class: 'grow' },
    el('h2', {}, 'Your farms'), el('p', {}, `${farms.length} farm(s) visible to your role.`)));
  if (['farmer', 'farm_manager', 'super_admin'].includes(ME.role)) {
    head.appendChild(el('button', { class: 'btn', onclick: () => newFarmModal(() => viewFarms(root)) }, '＋ New farm'));
  }
  root.appendChild(head);

  if (!farms.length) {
    root.appendChild(emptyState('module_farm_mapping', 'No farms yet', 'Create a farm to start mapping fields and crops.',
      ['farmer', 'farm_manager', 'super_admin'].includes(ME.role) ? el('button', { class: 'btn', onclick: () => newFarmModal(() => viewFarms(root)) }, '＋ New farm') : null));
    return;
  }

  for (const farm of farms) {
    const card = el('div', { class: 'card', style: 'margin-bottom:18px' });
    card.appendChild(el('div', { class: 'card-head' },
      el('img', { src: img(farm.cover_image || 'hero'), style: 'width:52px;height:52px;border-radius:12px;object-fit:cover' }),
      el('div', { class: 'grow' }, el('h3', {}, farm.name),
        el('p', {}, `${farm.village || ''}${farm.district ? ', ' + farm.district : ''}${farm.state ? ', ' + farm.state : ''} · ${farm.total_acres} acres`)),
    ));
    const fg = el('div', { class: 'grid c3' });
    for (const f of farm.fields) {
      fg.appendChild(el('div', { class: 'card', style: 'padding:14px;box-shadow:none;background:var(--surface-2)' },
        el('div', { style: 'display:flex;justify-content:space-between;gap:8px;align-items:start' },
          el('b', {}, f.name), chip(f.crop, 'green')),
        el('div', { class: 'kv', style: 'margin-top:10px;font-size:.82rem' },
          el('dt', {}, 'Variety'), el('dd', {}, f.variety || '—'),
          el('dt', {}, 'Stage'), el('dd', {}, f.growth_stage || '—'),
          el('dt', {}, 'Acreage'), el('dd', {}, `${f.computed_acres ?? f.acreage} acres (computed)`),
          el('dt', {}, 'Irrigation'), el('dd', {}, f.irrigation || '—'),
        ),
        f.boundary ? el('div', { class: 'map', style: 'min-height:120px;margin-top:12px' },
          el('img', { src: img('module_farm_mapping'), alt: 'Field map' }),
          boundarySvg(f.boundary),
        ) : null,
        el('button', { class: 'btn ghost sm', style: 'margin-top:12px', onclick: () => newCaseModal(f, () => viewCases(root)) }, '❧ New case'),
      ));
    }
    if (!farm.fields.length) fg.appendChild(el('div', { class: 'alert' }, 'No fields recorded for this farm yet.'));
    card.appendChild(fg);
    root.appendChild(card);
  }
}

function boundarySvg(boundary) {
  const ring = boundary?.coordinates?.[0] || [];
  if (ring.length < 3) return null;
  const lons = ring.map(p => p[0]), lats = ring.map(p => p[1]);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const w = maxLon - minLon || 1, h = maxLat - minLat || 1;
  const pts = ring.map(([lon, lat]) => {
    const x = 8 + ((lon - minLon) / w) * 84;
    const y = 92 - ((lat - minLat) / h) * 84;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('preserveAspectRatio', 'none');
  const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  poly.setAttribute('points', pts);
  poly.setAttribute('fill', 'rgba(18,183,106,.28)');
  poly.setAttribute('stroke', '#12b76a');
  poly.setAttribute('stroke-width', '1.4');
  svg.appendChild(poly);
  return svg;
}

function newFarmModal(done) {
  const name = input('name', { placeholder: 'Farm name' });
  const village = input('village', { placeholder: 'Village' });
  const district = input('district', { placeholder: 'District' });
  const state = input('state', { placeholder: 'State' });
  const lat = input('latitude', { type: 'number', step: 'any', placeholder: '18.87' });
  const lon = input('longitude', { type: 'number', step: 'any', placeholder: '73.91' });
  const body = el('div', {},
    field('Farm name', name), field('Village', village),
    el('div', { class: 'grid c2' }, field('District', district), field('State', state)),
    el('div', { class: 'grid c2' }, field('Latitude', lat), field('Longitude', lon)),
    el('div', { class: 'alert info' }, 'Coordinates are used for map display and geofence checks. Location consent is recorded against your profile.'),
  );
  const m = modal({
    title: 'Create a farm', body,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn', onclick: async () => {
        try {
          await api('/farms', { method: 'POST', body: {
            name: name.value, village: village.value, district: district.value, state: state.value,
            latitude: lat.value ? Number(lat.value) : null, longitude: lon.value ? Number(lon.value) : null,
          } });
          toast('Farm created'); m.close(); done();
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Create farm')],
  });
}

function newCaseModal(field_, done) {
  const title = input('title', { placeholder: 'e.g. Yellowing leaves in north block' });
  const obs = el('textarea', { name: 'observations', placeholder: 'Describe what you see: colour, pattern, affected area, stage…' });
  const sev = select('severity', [
    { value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium', selected: true }, { value: 'high', label: 'High' }, { value: 'unknown', label: 'Unknown' },
  ]);
  const body = el('div', {},
    field('Case title', title),
    field('Observations', obs, 'Concrete observations improve AI confidence and reduce escalation.'),
    field('Severity', sev),
    el('div', { class: 'alert warn' }, 'AI findings are preliminary. A qualified agronomist must confirm them before any treatment.'),
  );
  const m = modal({
    title: `New case — ${field_.name}`, body,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn', onclick: async () => {
        try {
          const c = await api('/cases', { method: 'POST', body: { field_id: field_.id, title: title.value, observations: obs.value, severity: sev.value } });
          toast(`Case ${c.reference} created`); m.close(); navigate('cases');
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Create case')],
  });
}

/* --------------------------------------------------------------- cases */
let CASE_FILTER = 'all';

async function viewCases(root) {
  root.appendChild(moduleHero({
    image: 'module_workflow', tag: 'Approval workflow',
    title: 'Crop-health cases',
    body: 'An 18-step configurable lifecycle with explicit transitions, role permissions, reasons and a tamper-evident audit trail.',
  }));
  let cases = [];
  try { cases = await api('/cases'); } catch (e) { toast(e.message, 'error'); }

  const head = el('div', { class: 'page-head' }, el('div', { class: 'grow' },
    el('h2', {}, 'Case queue'), el('p', {}, `${cases.length} case(s) in your scope. Open a case to advance it.`)));
  root.appendChild(head);

  const filters = el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px' });
  const states = ['all', ...new Set(cases.map(c => c.state))];
  for (const s of states) {
    filters.appendChild(el('button', {
      class: `btn ${CASE_FILTER === s ? '' : 'ghost'} sm`,
      onclick: () => { CASE_FILTER = s; root.replaceChildren(); viewCases(root); },
    }, s === 'all' ? 'All' : titleCase(s)));
  }
  root.appendChild(filters);

  const list = CASE_FILTER === 'all' ? cases : cases.filter(c => c.state === CASE_FILTER);
  if (!list.length) { root.appendChild(emptyState('module_crop_health', 'No cases', 'Nothing matches this filter.')); return; }

  const card = el('div', { class: 'card pad-0' });
  const tbl = el('table', { class: 'table' });
  tbl.appendChild(el('thead', {}, el('tr', {},
    el('th', {}, 'Reference'), el('th', {}, 'Title'), el('th', {}, 'Crop'),
    el('th', {}, 'State'), el('th', {}, 'Severity'), el('th', {}, 'Created'))));
  const tb = el('tbody');
  for (const c of list) {
    tb.appendChild(el('tr', { onclick: () => openCase(c.id) },
      el('td', { class: 'strong' }, c.reference),
      el('td', {}, c.title),
      el('td', {}, c.field?.crop || '—'),
      el('td', {}, chip(titleCase(c.state), STATE_TONE[c.state] || 'grey')),
      el('td', {}, chip(titleCase(c.severity), SEV_TONE[c.severity] || 'grey')),
      el('td', { style: 'color:var(--text-3);font-size:.8rem' }, fmtDate(c.created_at)),
    ));
  }
  tbl.appendChild(tb); card.appendChild(tbl); root.appendChild(card);
}

async function openCase(id) {
  let c;
  try { c = await api(`/cases/${id}`); } catch (e) { return toast(e.message, 'error'); }
  const body = el('div', {});
  body.appendChild(el('div', { style: 'display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px' },
    chip(titleCase(c.state), STATE_TONE[c.state] || 'grey'),
    chip(titleCase(c.severity), SEV_TONE[c.severity] || 'grey'),
    chip(c.field?.crop || 'crop', 'green'),
  ));
  body.appendChild(el('div', { class: 'alert info', style: 'margin-bottom:16px' },
    el('div', {}, el('b', {}, 'Observations: '), c.observations || '—')));

  const tl = el('div', { class: 'timeline' });
  const order = (META?.states || []).map(s => s.key);
  const idx = order.indexOf(c.state);
  const milestones = [
    ['draft', 'Case created'], ['imagery_captured', 'Imagery captured'],
    ['ai_findings_ready', 'AI findings ready'], ['awaiting_agronomist', 'Submitted for agronomist review'],
    ['plan_prepared', 'Treatment plan prepared'], ['awaiting_manager', 'Manager costing'],
    ['plan_approved', 'Plan approved'], ['implementation_chosen', 'Farmer consent'],
    ['job_assigned', 'Operator assigned'], ['in_progress', 'Mission in progress'],
    ['completed', 'Completed'], ['closed', 'Closed'],
  ];
  for (const [key, label] of milestones) {
    const k = order.indexOf(key);
    const cls = idx > k ? 'done' : idx === k ? 'current' : '';
    tl.appendChild(el('div', { class: 'tl-item' },
      el('div', { class: `tl-dot ${cls}` }, idx > k ? '✓' : idx === k ? '●' : ''),
      el('div', { class: 'tl-body' }, el('b', {}, label),
        el('small', {}, idx > k ? 'Completed' : idx === k ? 'Current stage' : 'Pending')),
    ));
  }
  body.appendChild(el('h3', { style: 'margin:6px 0 14px' }, 'Workflow progress'));
  body.appendChild(tl);

  if (c.analyses?.length) {
    const a = c.analyses[c.analyses.length - 1];
    body.appendChild(el('h3', { style: 'margin:18px 0 10px' }, 'AI findings (preliminary)'));
    const cardA = el('div', { class: 'card', style: 'background:var(--surface-2)' });
    cardA.appendChild(el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px' },
      chip(`Model ${a.model_version}`, 'blue'), chip(`Uncertainty ${pct(a.uncertainty)}`, a.uncertainty > 0.45 ? 'red' : 'green'),
      a.escalate ? chip('Escalated to human', 'red') : chip('Within threshold', 'green')));
    cardA.appendChild(el('p', { style: 'font-size:.88rem' }, a.summary));
    for (const f of (a.findings || [])) {
      cardA.appendChild(el('div', { style: 'margin-top:10px;padding:10px;border-radius:10px;background:var(--surface)' },
        el('div', { style: 'display:flex;justify-content:space-between;gap:10px' },
          el('b', {}, f.label), chip(pct(f.confidence), 'gold')),
        el('div', { style: 'font-size:.82rem;color:var(--text-2);margin-top:6px' }, `Evidence: ${f.evidence}`),
        el('div', { style: 'font-size:.82rem;color:var(--text-3);margin-top:4px' }, `Alternative: ${f.alternative}`),
      ));
    }
    if (a.affected_area_pct != null) {
      cardA.appendChild(el('div', { style: 'margin-top:12px' }, el('small', {}, `Affected area estimate: ${a.affected_area_pct}% (produced only when geospatial data permits)`)));
    }
    body.appendChild(cardA);
  }

  if (c.plan) {
    body.appendChild(el('h3', { style: 'margin:18px 0 10px' }, 'Treatment plan'));
    const p = el('div', { class: 'card', style: 'background:var(--surface-2)' });
    p.appendChild(el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px' },
      chip(`Revision ${c.plan.revision}`, 'blue'), chip(titleCase(c.plan.status), 'gold')));
    p.appendChild(el('div', { class: 'kv' },
      el('dt', {}, 'Problem'), el('dd', {}, c.plan.problem),
      el('dt', {}, 'Product'), el('dd', {}, c.plan.product || '—'),
      el('dt', {}, 'Active ingredient'), el('dd', {}, c.plan.active_ingredient || '—'),
      el('dt', {}, 'Dosage'), el('dd', {}, c.plan.dosage || '—'),
      el('dt', {}, 'Weather limits'), el('dd', {}, c.plan.weather_restrictions || '—'),
      el('dt', {}, 'PPE'), el('dd', {}, c.plan.ppe || '—'),
      el('dt', {}, 'Pre-harvest'), el('dd', {}, c.plan.pre_harvest_interval || '—'),
      el('dt', {}, 'Re-entry'), el('dd', {}, c.plan.re_entry_interval || '—'),
    ));
    if (c.plan.measures?.length) {
      p.appendChild(el('div', { style: 'margin-top:12px' }, el('b', { style: 'font-size:.86rem' }, 'Measures'),
        el('ul', { style: 'margin:6px 0 0 18px;font-size:.85rem;color:var(--text-2)' }, ...c.plan.measures.map(m => el('li', {}, m)))));
    }
    body.appendChild(p);
  }

  if (c.cost) {
    body.appendChild(el('h3', { style: 'margin:18px 0 10px' }, 'Cost estimate'));
    const ct = el('div', { class: 'card', style: 'background:var(--surface-2)' });
    const t2 = el('table', { class: 'table' });
    t2.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Line'), el('th', {}, 'Qty'), el('th', {}, 'Rate'), el('th', {}, 'Amount'))));
    const tb2 = el('tbody');
    for (const l of (c.cost.lines || [])) {
      tb2.appendChild(el('tr', { style: 'cursor:default' }, el('td', {}, l.label), el('td', {}, `${l.qty} ${l.unit}`), el('td', {}, inr(l.rate)), el('td', {}, inr(l.amount))));
    }
    t2.appendChild(tb2); ct.appendChild(t2);
    ct.appendChild(el('div', { class: 'kv', style: 'margin-top:12px' },
      el('dt', {}, 'Subtotal'), el('dd', {}, inr(c.cost.subtotal)),
      el('dt', {}, 'Tax'), el('dd', {}, `${c.cost.tax_pct}%`),
      el('dt', {}, 'Discount'), el('dd', {}, inr(c.cost.discount)),
      el('dt', {}, 'Total'), el('dd', {}, el('b', {}, inr(c.cost.total))),
      el('dt', {}, 'Decision'), el('dd', {}, chip(titleCase(c.cost.decision), c.cost.decision === 'approved' ? 'green' : 'gold')),
    ));
    body.appendChild(ct);
  }

  if (c.job) {
    body.appendChild(el('h3', { style: 'margin:18px 0 10px' }, 'Drone mission'));
    const j = el('div', { class: 'card', style: 'background:var(--surface-2)' });
    j.appendChild(el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px' },
      chip(titleCase(c.job.status), 'blue'), chip('SIMULATED', 'gold')));
    j.appendChild(el('div', { class: 'kv' },
      el('dt', {}, 'Treated acres'), el('dd', {}, c.job.treated_acres ?? '—'),
      el('dt', {}, 'Product used'), el('dd', {}, c.job.product_used_liters ? `${c.job.product_used_liters} L` : '—'),
      el('dt', {}, 'Started'), el('dd', {}, c.job.started_at ? fmtDate(c.job.started_at) : '—'),
      el('dt', {}, 'Completed'), el('dd', {}, c.job.completed_at ? fmtDate(c.job.completed_at) : '—'),
    ));
    if (c.job.telemetry) {
      j.appendChild(el('div', { class: 'alert warn', style: 'margin-top:12px' },
        el('span', {}, `${c.job.telemetry.label || 'Simulated telemetry'} — duration ${c.job.telemetry.duration_min} min, battery used ${c.job.telemetry.battery_used_pct}%`)));
    }
    body.appendChild(j);
  }

  if (c.invoice) {
    body.appendChild(el('h3', { style: 'margin:18px 0 10px' }, 'Invoice'));
    body.appendChild(el('div', { class: 'card', style: 'background:var(--surface-2)' },
      el('div', { class: 'kv' },
        el('dt', {}, 'Number'), el('dd', {}, c.invoice.number),
        el('dt', {}, 'Total'), el('dd', {}, inr(c.invoice.total)),
        el('dt', {}, 'Status'), el('dd', {}, chip(titleCase(c.invoice.status), c.invoice.status === 'paid' ? 'green' : 'gold')),
        el('dt', {}, 'Provider'), el('dd', {}, c.invoice.provider)),
      ME.role === 'farmer' && c.invoice.status !== 'paid'
        ? el('button', { class: 'btn', style: 'margin-top:12px', onclick: async () => {
            try { await api(`/invoices/${c.invoice.id}/pay`, { method: 'POST' }); toast('Payment recorded'); m.close(); openCase(id); }
            catch (e) { toast(e.message, 'error'); }
          } }, 'Pay now (sandbox)') : null,
    ));
  }

  if (c.audit?.length) {
    body.appendChild(el('h3', { style: 'margin:18px 0 10px' }, 'Audit trail'));
    const at = el('div', { class: 'card', style: 'background:var(--surface-2);font-size:.82rem' });
    for (const ev of c.audit.slice().reverse()) {
      at.appendChild(el('div', { style: 'padding:6px 0;border-bottom:1px solid var(--border)' },
        el('b', {}, titleCase(ev.action)), el('span', { style: 'color:var(--text-3)' }, ` · ${fmtDate(ev.at)}`),
        ev.detail?.reason ? el('div', { style: 'color:var(--text-2)' }, `Reason: ${ev.detail.reason}`) : null,
      ));
    }
    body.appendChild(at);
  }

  const actions = el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-top:18px' });
  const reload = () => { m.close(); openCase(id); };
  for (const action of caseActions(c, reload)) actions.appendChild(action);
  body.appendChild(actions);

  const m = modal({ title: `${c.reference} — ${c.title}`, body, wide: true });
}

function caseActions(c, reload) {
  const out = [];
  const R = ME.role;
  const act = (label, cls, fn) => el('button', { class: `btn ${cls}`, onclick: fn }, label);
  const post = (path, body, msg) => async () => {
    try { await api(path, { method: 'POST', body }); toast(msg); reload(); }
    catch (e) { toast(e.message, 'error'); }
  };

  if (R === 'farmer' && c.state === 'draft') out.push(act('Capture imagery', '', post(`/cases/${c.id}/capture`, undefined, 'Imagery captured')));
  if (R === 'farmer' && c.state === 'imagery_captured') out.push(act('Run AI analysis', '', post(`/cases/${c.id}/analyze`, undefined, 'Analysis complete')));
  if (R === 'farmer' && c.state === 'ai_findings_ready') out.push(act('Submit for agronomist review', '', post(`/cases/${c.id}/submit`, undefined, 'Submitted')));
  if (R === 'agronomist' && ['awaiting_agronomist', 'reopened'].includes(c.state)) {
    out.push(act('Confirm findings', '', post(`/cases/${c.id}/review`, { decision: 'confirm', notes: 'Confirmed from field imagery.' }, 'Findings confirmed')));
    out.push(act('Reject case', 'danger', post(`/cases/${c.id}/review`, { decision: 'reject', notes: 'Insufficient evidence.' }, 'Case rejected')));
    out.push(act('Prepare treatment plan', 'gold', () => planModal(c, reload)));
  }
  if (R === 'agronomist' && c.state === 'needs_revision') out.push(act('Revise treatment plan', 'gold', () => planModal(c, reload)));
  if (R === 'farm_manager' && c.state === 'awaiting_manager') out.push(act('Costing & approve', '', () => costModal(c, reload)));
  if (R === 'farmer' && c.state === 'awaiting_farmer') {
    out.push(act('Choose self-implementation', 'ghost', post(`/cases/${c.id}/choose-implementation`, { choice: 'self' }, 'Self implementation chosen')));
    out.push(act('Request drone service', '', post(`/cases/${c.id}/choose-implementation`, { choice: 'drone' }, 'Drone service requested')));
  }
  if (R === 'farm_manager' && c.state === 'implementation_chosen') out.push(act('Assign operator', '', () => assignModal(c, reload)));
  if (R === 'drone_operator' && c.job && ['job_assigned', 'in_progress'].includes(c.state)) {
    out.push(act('Pre-flight checks', 'ghost', async () => {
      try { const r = await api(`/jobs/${c.job.id}/preflight`, { method: 'POST' }); toast(r.ready ? 'Pre-flight passed' : 'Pre-flight issues found', r.ready ? 'ok' : 'warn'); reload(); }
      catch (e) { toast(e.message, 'error'); }
    }));
    if (c.state === 'job_assigned') out.push(act('Start mission', '', post(`/jobs/${c.job.id}/start`, undefined, 'Mission started (simulated)')));
    if (c.state === 'in_progress') out.push(act('Complete mission', '', post(`/jobs/${c.job.id}/complete`, {}, 'Mission completed (simulated)')));
  }
  if (['completed', 'in_progress'].includes(c.state) && ['farmer', 'agronomist'].includes(R)) {
    out.push(act('Schedule follow-up', 'ghost', post(`/cases/${c.id}/follow-up`, undefined, 'Follow-up scheduled')));
  }
  if (['completed', 'follow_up'].includes(c.state) && ['farmer', 'super_admin'].includes(R)) {
    out.push(act('Close case', '', async () => {
      try { await api(`/cases/${c.id}/close?outcome=Outcome+recorded`, { method: 'POST' }); toast('Case closed'); reload(); }
      catch (e) { toast(e.message, 'error'); }
    }));
  }
  if (['closed', 'rejected'].includes(c.state) && ['farmer', 'super_admin'].includes(R)) {
    out.push(act('Reopen case', 'ghost', post(`/cases/${c.id}/reopen`, undefined, 'Case reopened')));
  }
  out.push(act('View report', 'ghost', () => reportModal(c.id)));
  if (out.length === 1) out.unshift(el('div', { class: 'alert' }, 'No workflow action is available for your role at this stage.'));
  return out;
}

function planModal(c, done) {
  const problem = input('problem', { value: c.plan?.problem || c.analyses?.[0]?.findings?.[0]?.label || '' });
  const product = select('product', [{ value: '', label: '— none —' }, { value: 'Mancozeb 75% WP', label: 'Mancozeb 75% WP' }, { value: 'Propiconazole 25% EC', label: 'Propiconazole 25% EC' }, { value: 'Neem Oil 1500 PPM', label: 'Neem Oil 1500 PPM' }]);
  const dosage = input('dosage', { value: c.plan?.dosage || '2.0 ml per litre; 200 L per acre' });
  const ppe = input('ppe', { value: c.plan?.ppe || 'Gloves, N95 mask, goggles, full-sleeve clothing, boots' });
  const phi = input('pre_harvest_interval', { value: c.plan?.pre_harvest_interval || '7 days' });
  const measures = el('textarea', { name: 'measures' });
  measures.value = (c.plan?.measures || ['Remove infected debris', 'Maintain spacing for airflow', 'Apply approved product as per label']).join('\n');
  const follow = input('follow_up', { value: c.plan?.follow_up || 'Re-inspect after 7 days' });
  const body = el('div', {},
    field('Suspected / confirmed problem', problem),
    field('Approved product', product, 'Only label-approved products can be referenced.'),
    field('Dosage', dosage),
    el('div', { class: 'grid c2' }, field('Pre-harvest interval', phi), field('PPE', ppe)),
    field('Measures (one per line)', measures),
    field('Follow-up schedule', follow),
    el('div', { class: 'alert warn' }, 'An uncertain AI diagnosis is never auto-converted into a spraying command. Safety validation is applied on the server.'),
  );
  const m = modal({
    title: 'Treatment plan', body, wide: true,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn gold', onclick: async () => {
        try {
          await api(`/cases/${c.id}/plan`, { method: 'POST', body: {
            problem: problem.value, confidence: 0.86,
            measures: measures.value.split('\n').map(s => s.trim()).filter(Boolean),
            product: product.value || null, active_ingredient: product.value ? product.value.split(' ')[0] : null,
            dosage: dosage.value, application: 'Foliar spray using a calibrated sprayer.',
            weather_restrictions: 'Do not spray if rain is expected within 6 hours or wind > 12 km/h.',
            ppe: ppe.value, pre_harvest_interval: phi.value, re_entry_interval: '24 hours', follow_up: follow.value,
          } });
          toast('Plan sent for costing'); m.close(); done();
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Send for costing')],
  });
}

function costModal(c, done) {
  const defaultLines = [
    { label: 'Approved crop-protection product', unit: 'L', qty: 4, rate: 780 },
    { label: 'Labour - spray operation', unit: 'person-day', qty: 2, rate: 550 },
    { label: 'Equipment and travel', unit: 'job', qty: 1, rate: 900 },
  ];
  const lines = c.cost?.lines || defaultLines;
  const container = el('div', {});
  const inputs = [];
  lines.forEach((l, i) => {
    const qty = input(`qty${i}`, { type: 'number', value: l.qty, step: 'any' });
    const rate = input(`rate${i}`, { type: 'number', value: l.rate, step: 'any' });
    inputs.push({ label: l.label, unit: l.unit, qty, rate });
    container.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 90px 110px;gap:8px;align-items:end;margin-bottom:8px' },
      field(l.label, el('div', { style: 'font-size:.8rem;color:var(--text-3)' }, l.unit)),
      field('Qty', qty), field('Rate ₹', rate)));
  });
  const discount = input('discount', { type: 'number', value: c.cost?.discount ?? 150, step: 'any' });
  const tax = input('tax', { type: 'number', value: c.cost?.tax_pct ?? 18, step: 'any' });
  const body = el('div', {}, container,
    el('div', { class: 'grid c2' }, field('Discount ₹', discount), field('Tax %', tax)),
    el('div', { class: 'alert info' }, 'Manager approval never replaces the agronomist technical approval and cannot override chemical-use restrictions.'),
  );
  const m = modal({
    title: 'Cost estimation & approval', body, wide: true,
    footer: [
      el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn danger', onclick: () => send('revision') }, 'Return for revision'),
      el('button', { class: 'btn', onclick: () => send('approved') }, 'Approve plan'),
    ],
  });
  async function send(decision) {
    const payloadLines = inputs.map(i => ({ label: i.label, unit: i.unit, qty: Number(i.qty.value), rate: Number(i.rate.value) }));
    try {
      await api(`/cases/${c.id}/costing`, { method: 'POST', body: { lines: payloadLines, tax_pct: Number(tax.value), discount: Number(discount.value), decision, notes: 'Reviewed and decided by farm manager.' } });
      toast(decision === 'approved' ? 'Plan approved' : 'Returned for revision'); m.close(); done();
    } catch (e) { toast(e.message, 'error'); }
  }
}

async function assignModal(c, done) {
  let drones = [], users = [];
  try { drones = await api('/drones'); } catch {}
  try { users = await api('/admin/users'); } catch {}
  const operators = users.filter(u => u.role === 'drone_operator');
  const opSel = select('operator', operators.map(o => ({ value: o.id, label: `${o.full_name} (${o.verification_status})` })));
  const devSel = select('device', [{ value: '', label: '— select device —' }, ...drones.map(d => ({ value: d.id, label: `${d.model} · ${d.availability}` }))]);
  const body = el('div', {}, field('Verified operator', opSel), field('Drone device', devSel),
    el('div', { class: 'alert info' }, 'Only verified operators and available devices can be assigned. The mission runs in clearly-labelled simulation mode.'));
  const m = modal({
    title: 'Assign mission', body,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn', onclick: async () => {
        try {
          await api(`/cases/${c.id}/assign`, { method: 'POST', body: { operator_id: opSel.value, device_id: devSel.value || null } });
          toast('Operator assigned'); m.close(); done();
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Assign')],
  });
}

async function reportModal(caseId) {
  let r;
  try { r = await api(`/cases/${caseId}/report`); } catch (e) { return toast(e.message, 'error'); }
  const c = r.case;
  const body = el('div', {});
  body.appendChild(el('div', { style: 'display:flex;gap:10px;align-items:center;margin-bottom:14px' },
    el('img', { src: img('module_reports'), style: 'width:70px;height:70px;border-radius:12px;object-fit:cover' }),
    el('div', {}, el('b', {}, r.report_id), el('div', { style: 'color:var(--text-3);font-size:.8rem' }, `Generated ${fmtDate(r.generated_at)}`))));
  body.appendChild(el('div', { class: 'kv' },
    el('dt', {}, 'Farmer'), el('dd', {}, r.farmer?.name || '—'),
    el('dt', {}, 'Farm'), el('dd', {}, r.farm ? `${r.farm.name}, ${r.farm.district || ''}` : '—'),
    el('dt', {}, 'Field'), el('dd', {}, r.field ? `${r.field.name} (${r.field.computed_acres ?? r.field.acreage} acres)` : '—'),
    el('dt', {}, 'Crop'), el('dd', {}, r.field?.crop || '—'),
    el('dt', {}, 'Case state'), el('dd', {}, titleCase(c.state))));
  if (c.analyses?.length) {
    body.appendChild(el('h3', { style: 'margin:16px 0 8px' }, 'AI findings'));
    body.appendChild(el('p', { style: 'font-size:.86rem' }, c.analyses[c.analyses.length - 1].summary));
  }
  if (c.plan) {
    body.appendChild(el('h3', { style: 'margin:16px 0 8px' }, 'Approved treatment'));
    body.appendChild(el('div', { class: 'kv' },
      el('dt', {}, 'Product'), el('dd', {}, c.plan.product || '—'),
      el('dt', {}, 'Dosage'), el('dd', {}, c.plan.dosage || '—'),
      el('dt', {}, 'PPE'), el('dd', {}, c.plan.ppe || '—')));
  }
  if (r.sources?.length) {
    body.appendChild(el('h3', { style: 'margin:16px 0 8px' }, 'Verified sources'));
    for (const s of r.sources) body.appendChild(el('div', { class: 'alert', style: 'margin-bottom:6px' }, `${s.title} — ${s.organization} (v${s.version})`));
  }
  body.appendChild(el('div', { class: 'alert warn', style: 'margin-top:14px' }, r.disclaimer));
  modal({ title: 'Field report', body, wide: true, footer: [el('button', { class: 'btn ghost', onclick: () => window.print() }, '🖨 Print / Save PDF')] });
}

/* --------------------------------------------------------------- drone ops */
async function viewDroneOps(root) {
  root.appendChild(moduleHero({
    image: 'module_drone_ops', tag: 'Field services',
    title: 'Drone operations',
    body: 'Simulator-backed mission management: pre-flight checks, telemetry, geofence validation and hardware adapters. Simulated data is always labelled.',
  }));
  let jobs = [];
  try { jobs = await api('/jobs'); } catch (e) { toast(e.message, 'error'); }
  const grid = el('div', { class: 'grid c3' });
  const active = jobs.filter(j => j.status !== 'completed');
  const done = jobs.filter(j => j.status === 'completed');
  grid.append(
    statCard('Assigned missions', active.length, 'Awaiting or in progress'),
    statCard('Completed', done.length, `${done.reduce((s, j) => s + (j.treated_acres || 0), 0).toFixed(1)} acres`),
    statCard('Mode', 'Simulated', 'Real spraying disabled until hardware validation', 'gold'),
  );
  root.appendChild(grid);

  const card = el('div', { class: 'card', style: 'margin-top:18px' });
  card.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Mission list')));
  if (!jobs.length) {
    card.appendChild(emptyState('module_drone_ops', 'No missions assigned', 'Missions appear here once a farm manager assigns a drone-assisted case.'));
  } else {
    const tbl = el('table', { class: 'table' });
    tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Case'), el('th', {}, 'Status'), el('th', {}, 'Mode'), el('th', {}, 'Treated acres'), el('th', {}, 'Completed'))));
    const tb = el('tbody');
    for (const j of jobs) {
      tb.appendChild(el('tr', { onclick: () => openCase(j.case_id) },
        el('td', { class: 'strong' }, j.case_reference || '—'),
        el('td', {}, chip(titleCase(j.status), j.status === 'completed' ? 'green' : 'blue')),
        el('td', {}, chip(j.simulated ? 'SIMULATED' : 'Live', j.simulated ? 'gold' : 'red')),
        el('td', {}, j.treated_acres ?? '—'),
        el('td', { style: 'color:var(--text-3);font-size:.8rem' }, j.completed_at ? fmtDate(j.completed_at) : '—'),
      ));
    }
    tbl.appendChild(tb); card.appendChild(tbl);
  }
  root.appendChild(card);

  const note = el('div', { class: 'alert warn', style: 'margin-top:18px' },
    'A software emergency-stop command is not represented as guaranteed physical shutdown. Real spraying stays disabled until hardware validation, authorization checks and explicit operator confirmation.');
  root.appendChild(note);
}

/* --------------------------------------------------------------- fleet */
async function viewFleet(root) {
  root.appendChild(moduleHero({
    image: 'module_drone_ops', tag: 'Hardware adapters',
    title: 'Drone fleet',
    body: 'Register drone models, capabilities, payload capacity and battery health. Capability checks gate which missions a device may fly.',
  }));
  let drones = [];
  try { drones = await api('/drones'); } catch (e) { toast(e.message, 'error'); }
  const head = el('div', { class: 'page-head' }, el('div', { class: 'grow' },
    el('h2', {}, 'Registered devices'), el('p', {}, `${drones.length} device(s) in the fleet.`)));
  if (ME.role === 'drone_operator') head.appendChild(el('button', { class: 'btn', onclick: () => droneModal(() => viewFleet(root)) }, '＋ Register drone'));
  root.appendChild(head);

  const grid = el('div', { class: 'grid c3' });
  for (const d of drones) {
    grid.appendChild(el('div', { class: 'card' },
      el('div', { style: 'display:flex;gap:10px;align-items:center;margin-bottom:12px' },
        el('img', { src: img('module_drone_ops'), style: 'width:52px;height:52px;border-radius:12px;object-fit:cover' }),
        el('div', {}, el('b', {}, d.model), el('div', { style: 'font-size:.78rem;color:var(--text-3)' }, `SN ${d.serial}`))),
      el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px' },
        chip(d.verified ? 'Verified' : 'Pending verification', d.verified ? 'green' : 'gold'),
        chip(titleCase(d.availability), d.availability === 'available' ? 'green' : 'gold'),
        chip('Simulated', 'grey')),
      el('div', { class: 'kv', style: 'font-size:.83rem' },
        el('dt', {}, 'Capabilities'), el('dd', {}, (d.capabilities || []).join(', ') || '—'),
        el('dt', {}, 'Payload'), el('dd', {}, `${d.payload_liters} L`),
        el('dt', {}, 'Battery health'), el('dd', {}, `${d.battery_health_pct}%`)),
      bar(d.battery_health_pct, d.battery_health_pct < 80 ? 'gold' : ''),
    ));
  }
  if (!drones.length) grid.appendChild(emptyState('module_drone_ops', 'No devices registered', 'Register a drone to enable capability-checked mission assignment.'));
  root.appendChild(grid);
}

function droneModal(done) {
  const model = input('model', { placeholder: 'e.g. AgriWing X8 Spray' });
  const serial = input('serial', { placeholder: 'Serial number' });
  const caps = input('capabilities', { value: 'spray,mapping,rtk' });
  const payload = input('payload_liters', { type: 'number', value: 16, step: 'any' });
  const battery = input('battery_health_pct', { type: 'number', value: 100, step: 'any' });
  const body = el('div', {},
    field('Model', model), field('Serial number', serial),
    field('Capabilities (comma separated)', caps, 'e.g. spray, mapping, rtk, multispectral'),
    el('div', { class: 'grid c2' }, field('Payload (litres)', payload), field('Battery health %', battery)),
    el('div', { class: 'alert info' }, 'New devices start unverified. A super administrator must verify credentials before live operations.'));
  const m = modal({ title: 'Register drone', body,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn', onclick: async () => {
        try {
          await api('/drones', { method: 'POST', body: { model: model.value, serial: serial.value,
            capabilities: caps.value.split(',').map(s => s.trim()).filter(Boolean),
            payload_liters: Number(payload.value), battery_health_pct: Number(battery.value) } });
          toast('Drone registered (pending verification)'); m.close(); done();
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Register')] });
}

/* --------------------------------------------------------------- reports */
async function viewReports(root) {
  root.appendChild(moduleHero({
    image: 'module_reports', tag: 'Analytics & reporting',
    title: 'Field reports',
    body: 'Permission-filtered reports with map, imagery metadata, AI findings, agronomist review, costs and verified sources. Print to PDF from any report.',
  }));
  let cases = [];
  try { cases = await api('/cases'); } catch (e) { toast(e.message, 'error'); }
  const card = el('div', { class: 'card pad-0' });
  card.appendChild(el('div', { class: 'card-head', style: 'padding:20px 20px 0' },
    el('h3', { class: 'grow' }, 'Available reports'), el('p', {}, `${cases.length} report(s) in your scope`)));
  if (!cases.length) { card.appendChild(emptyState('module_reports', 'No reports yet', 'Reports are generated per crop-health case.')); root.appendChild(card); return; }
  const tbl = el('table', { class: 'table' });
  tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Report ID'), el('th', {}, 'Title'), el('th', {}, 'State'), el('th', {}, 'Actions'))));
  const tb = el('tbody');
  for (const c of cases) {
    tb.appendChild(el('tr', { onclick: () => reportModal(c.id) },
      el('td', { class: 'strong' }, `RPT-${c.reference}`),
      el('td', {}, c.title),
      el('td', {}, chip(titleCase(c.state), STATE_TONE[c.state] || 'grey')),
      el('td', {}, el('button', { class: 'btn ghost sm', onclick: (e) => { e.stopPropagation(); reportModal(c.id); } }, 'View')),
    ));
  }
  tbl.appendChild(tb); card.appendChild(tbl); root.appendChild(card);
}

/* --------------------------------------------------------------- payments */
async function viewPayments(root) {
  root.appendChild(moduleHero({
    image: 'module_payments', tag: 'Commercial services',
    title: 'Payments & invoicing',
    body: 'Provider-independent payment service with a Razorpay-shaped sandbox, verified webhooks, idempotency keys and auditable records.',
  }));
  let invoices = [];
  try { invoices = await api('/invoices'); } catch (e) { toast(e.message, 'error'); }
  const paid = invoices.filter(i => i.status === 'paid');
  const grid = el('div', { class: 'grid c3' });
  grid.append(
    statCard('Invoices', invoices.length, 'All time'),
    statCard('Paid', paid.length, inr(paid.reduce((s, i) => s + i.total, 0))),
    statCard('Provider', 'Razorpay sandbox', 'Signature-verified webhooks'),
  );
  root.appendChild(grid);
  const card = el('div', { class: 'card pad-0', style: 'margin-top:18px' });
  card.appendChild(el('div', { class: 'card-head', style: 'padding:20px 20px 0' }, el('h3', { class: 'grow' }, 'Invoices')));
  if (!invoices.length) { card.appendChild(emptyState('module_payments', 'No invoices yet', 'Invoices are generated after a completed treatment.')); root.appendChild(card); return; }
  const tbl = el('table', { class: 'table' });
  tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Number'), el('th', {}, 'Amount'), el('th', {}, 'Tax'), el('th', {}, 'Total'), el('th', {}, 'Status'), el('th', {}, ''))));
  const tb = el('tbody');
  for (const i of invoices) {
    tb.appendChild(el('tr', { style: 'cursor:default' },
      el('td', { class: 'strong' }, i.number),
      el('td', {}, inr(i.amount)), el('td', {}, inr(i.tax)), el('td', {}, el('b', {}, inr(i.total))),
      el('td', {}, chip(titleCase(i.status), i.status === 'paid' ? 'green' : 'gold')),
      el('td', {}, ME.role === 'farmer' && i.status !== 'paid'
        ? el('button', { class: 'btn sm', onclick: async () => {
            try { await api(`/invoices/${i.id}/pay`, { method: 'POST' }); toast('Payment recorded (sandbox)'); viewPayments(root.replaceChildren() || root); }
            catch (e) { toast(e.message, 'error'); }
          } }, 'Pay (sandbox)') : null),
    ));
  }
  tbl.appendChild(tb); card.appendChild(tbl); root.appendChild(card);
  root.appendChild(el('div', { class: 'alert info', style: 'margin-top:18px' },
    'Card credentials are never stored. Client-side success screens are never trusted as proof of payment — only signature-verified server records count.'));
}

/* --------------------------------------------------------------- notifications */
async function viewNotifications(root) {
  root.appendChild(moduleHero({
    image: 'module_notifications', tag: 'Engagement',
    title: 'Notifications',
    body: 'Workflow, mission, payment and safety notifications. Delivery is only claimed when the provider returns corresponding evidence.',
  }));
  let items = [];
  try { items = await api('/notifications'); } catch (e) { toast(e.message, 'error'); }
  if (!items.length) { root.appendChild(emptyState('module_notifications', 'No notifications', 'You will be notified about approvals, missions and payments.')); return; }
  const list = el('div', { class: 'grid' });
  for (const n of items) {
    list.appendChild(el('div', { class: 'card', style: `border-left:4px solid ${n.read ? 'var(--border)' : 'var(--brand-500)'}` },
      el('div', { style: 'display:flex;gap:10px;align-items:start' },
        el('div', { class: 'grow' }, el('b', {}, n.title),
          el('p', { style: 'margin:4px 0 0;font-size:.86rem;color:var(--text-2)' }, n.body)),
        chip(titleCase(n.category), 'blue')),
      el('div', { style: 'display:flex;gap:10px;align-items:center;margin-top:10px' },
        el('small', { style: 'color:var(--text-3)' }, fmtDate(n.at)),
        n.delivered ? chip(`Delivered · ${n.delivery_evidence || 'evidenced'}`, 'green') : chip('In-app only', 'grey'),
        !n.read ? el('button', { class: 'btn ghost sm', style: 'margin-left:auto', onclick: async () => {
          try { await api(`/notifications/${n.id}/read`, { method: 'POST' }); viewNotifications(root.replaceChildren() || root); } catch (e) { toast(e.message, 'error'); }
        } }, 'Mark read') : null),
    ));
  }
  root.appendChild(list);
}

/* --------------------------------------------------------------- grievances */
async function viewGrievances(root) {
  root.appendChild(moduleHero({
    image: 'module_grievance', tag: 'Customer support',
    title: 'Grievances & support',
    body: 'Every grievance gets a unique ticket, category, priority, owner and a full timeline from submission to closure.',
  }));
  const head = el('div', { class: 'page-head' }, el('div', { class: 'grow' },
    el('h2', {}, 'Support tickets')));
  head.appendChild(el('button', { class: 'btn', onclick: () => grievanceModal(() => viewGrievances(root)) }, '＋ New grievance'));
  root.appendChild(head);
  let items = [];
  try { items = await api('/grievances'); } catch (e) { toast(e.message, 'error'); }
  if (!items.length) { root.appendChild(emptyState('module_grievance', 'No tickets', 'Raise a grievance and it will be tracked here.')); return; }
  for (const g of items) {
    const card = el('div', { class: 'card', style: 'margin-bottom:14px' });
    card.appendChild(el('div', { style: 'display:flex;gap:10px;flex-wrap:wrap;align-items:center' },
      el('b', {}, g.ticket), chip(titleCase(g.status), g.status === 'closed' ? 'green' : 'gold'),
      chip(titleCase(g.priority), g.priority === 'high' ? 'red' : 'grey'),
      el('span', { style: 'margin-left:auto;color:var(--text-3);font-size:.8rem' }, fmtDate(g.created_at))));
    card.appendChild(el('div', { style: 'margin-top:8px' }, el('b', {}, g.subject), el('p', { style: 'margin:4px 0 0;font-size:.86rem;color:var(--text-2)' }, g.description)));
    if (g.timeline?.length) {
      const tl = el('div', { class: 'timeline', style: 'margin-top:14px' });
      for (const ev of g.timeline) {
        tl.appendChild(el('div', { class: 'tl-item' },
          el('div', { class: 'tl-dot done' }, '•'),
          el('div', { class: 'tl-body' }, el('b', {}, titleCase(ev.status)), el('small', {}, `${ev.note || ''} · ${fmtDate(ev.at)}`))));
      }
      card.appendChild(tl);
    }
    if (['super_admin', 'farm_manager'].includes(ME.role)) {
      card.appendChild(el('div', { style: 'display:flex;gap:8px;margin-top:12px;flex-wrap:wrap' },
        ...['investigating', 'resolved', 'closed'].map(s =>
          el('button', { class: 'btn ghost sm', onclick: async () => {
            try { await api(`/grievances/${g.id}`, { method: 'PATCH', body: { status: s, note: `Moved to ${s}` } }); toast('Updated'); viewGrievances(root.replaceChildren() || root); }
            catch (e) { toast(e.message, 'error'); }
          } }, titleCase(s)))));
    }
    root.appendChild(card);
  }
}

function grievanceModal(done) {
  const category = select('category', ['service_delay', 'treatment_quality', 'payment', 'operator_conduct', 'app_issue', 'other'].map(c => ({ value: c, label: titleCase(c) })));
  const priority = select('priority', [{ value: 'low', label: 'Low' }, { value: 'normal', label: 'Normal', selected: true }, { value: 'high', label: 'High' }]);
  const subject = input('subject', { placeholder: 'Short summary' });
  const desc = el('textarea', { name: 'description', placeholder: 'Describe the issue with dates and details…' });
  const body = el('div', {}, el('div', { class: 'grid c2' }, field('Category', category), field('Priority', priority)),
    field('Subject', subject), field('Description', desc));
  const m = modal({ title: 'Raise a grievance', body,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn', onclick: async () => {
        try {
          const g = await api('/grievances', { method: 'POST', body: { category: category.value, priority: priority.value, subject: subject.value, description: desc.value } });
          toast(`Ticket ${g.ticket} created`); m.close(); done();
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Submit')] });
}

/* --------------------------------------------------------------- knowledge */
async function viewKnowledge(root) {
  root.appendChild(moduleHero({
    image: 'module_knowledge', tag: 'Verified advisory',
    title: 'Knowledge base & product catalogue',
    body: 'Verified advisories from ICAR, state agricultural universities, KVKs and government departments, with provenance and version history. General internet content is never presented as verified advice.',
  }));
  let sources = [], products = [];
  try { sources = await api('/knowledge'); } catch {}
  try { products = await api('/products'); } catch {}
  const cols = el('div', { class: 'grid c2' });
  const sc = el('div', { class: 'card' });
  sc.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Verified sources')));
  for (const s of sources) {
    sc.appendChild(el('div', { style: 'padding:12px 0;border-bottom:1px solid var(--border)' },
      el('div', { style: 'display:flex;gap:8px;align-items:center' }, el('b', {}, s.title), chip(s.status, 'green')),
      el('div', { style: 'font-size:.82rem;color:var(--text-3)' }, `${s.organization} · ${s.crop || 'multi'} · ${s.published} · v${s.version}`),
      el('p', { style: 'font-size:.85rem;color:var(--text-2);margin:6px 0 0' }, s.summary)));
  }
  const pc = el('div', { class: 'card' });
  pc.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Approved product catalogue')));
  for (const p of products) {
    pc.appendChild(el('div', { style: 'padding:12px 0;border-bottom:1px solid var(--border)' },
      el('div', { style: 'display:flex;gap:8px;align-items:center' }, el('b', {}, p.name), chip(p.category, 'blue'), p.approved ? chip('Approved', 'green') : chip('Not approved', 'red')),
      el('div', { style: 'font-size:.82rem;color:var(--text-3)' }, `Active ingredient: ${p.active_ingredient} · ${p.label_registration || ''}`),
      el('p', { style: 'font-size:.84rem;color:var(--text-2);margin:6px 0 0' }, p.restrictions || '')));
  }
  cols.append(sc, pc); root.appendChild(cols);
}

/* --------------------------------------------------------------- analytics */
async function viewAnalytics(root) {
  root.appendChild(moduleHero({
    image: 'module_analytics', tag: 'Insight',
    title: 'Analytics & dashboards',
    body: 'Disease trends, field health, treatment effectiveness, costs and operator performance — always filtered by your permissions.',
  }));
  let s;
  try { s = await api('/analytics'); } catch (e) { return toast(e.message, 'error'); }
  const grid = el('div', { class: 'grid c4' });
  grid.append(
    statCard('Cases', s.cases_total, `${Object.keys(s.by_state).length} states`),
    statCard('Missions', s.missions, `${s.simulated_missions} simulated`),
    statCard('Treated acres', s.treated_acres, 'Across missions'),
    statCard('Revenue', inr(s.revenue_inr), 'Paid invoices', 'gold'),
  );
  root.appendChild(grid);

  const cols = el('div', { class: 'grid c2', style: 'margin-top:18px' });
  cols.appendChild(chartCard('Cases by state', s.by_state, 'green'));
  cols.appendChild(chartCard('Cases by severity', s.by_severity, 'gold'));
  cols.appendChild(chartCard('Cases by crop', s.by_crop, 'green'));
  const ai = el('div', { class: 'card' });
  ai.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'AI operations')));
  ai.appendChild(el('div', { class: 'kv' },
    el('dt', {}, 'Avg uncertainty'), el('dd', {}, pct(s.avg_uncertainty)),
    el('dt', {}, 'AI cost (USD)'), el('dd', {}, `$${s.ai_cost_usd}`),
    el('dt', {}, 'Provider mode'), el('dd', {}, chip(META?.ai?.mode || 'simulated', META?.ai?.mode === 'live' ? 'green' : 'gold'))));
  ai.appendChild(el('div', { class: 'alert info', style: 'margin-top:12px' }, 'Cost, latency and failures are tracked per model version so spending can be capped and audited.'));
  cols.appendChild(ai);
  root.appendChild(cols);
}

function chartCard(title, data, tone) {
  const card = el('div', { class: 'card' });
  card.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, title)));
  const entries = Object.entries(data || {});
  if (!entries.length) { card.appendChild(el('p', { style: 'color:var(--text-3)' }, 'No data yet')); return card; }
  const max = Math.max(...entries.map(([, v]) => v));
  for (const [k, v] of entries) {
    card.appendChild(el('div', { style: 'margin-bottom:12px' },
      el('div', { style: 'display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:4px' },
        el('span', {}, titleCase(k)), el('b', {}, v)),
      bar((v / max) * 100, tone)));
  }
  return card;
}

/* --------------------------------------------------------------- admin */
async function viewAdmin(root) {
  root.appendChild(moduleHero({
    image: 'module_security', tag: 'Governance',
    title: 'Administration',
    body: 'Manage users, verifications, feature flags and platform policies. Super-administrator access is protected and every change is audited.',
  }));
  let users = [], flags = [];
  try { users = await api('/admin/users'); } catch (e) { toast(e.message, 'error'); }
  try { flags = await api('/admin/flags'); } catch {}

  const grid = el('div', { class: 'grid c4' });
  grid.append(
    statCard('Users', users.length, 'All accounts'),
    statCard('Verified', users.filter(u => u.verification_status === 'verified').length, 'Professional verification'),
    statCard('Pending', users.filter(u => u.verification_status === 'pending').length, 'Awaiting review', 'gold'),
    statCard('Feature flags', flags.filter(f => f.enabled).length + '/' + flags.length, 'Enabled', 'gold'),
  );
  root.appendChild(grid);

  const cols = el('div', { class: 'grid c2', style: 'margin-top:18px' });
  const uc = el('div', { class: 'card pad-0' });
  uc.appendChild(el('div', { class: 'card-head', style: 'padding:20px 20px 0' }, el('h3', { class: 'grow' }, 'Users & roles')));
  const tbl = el('table', { class: 'table' });
  tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Name'), el('th', {}, 'Role'), el('th', {}, 'Verification'), el('th', {}, ''))));
  const tb = el('tbody');
  for (const u of users) {
    tb.appendChild(el('tr', { style: 'cursor:default' },
      el('td', {}, el('div', { style: 'display:flex;gap:8px;align-items:center' },
        el('img', { src: img(u.avatar_image), style: 'width:30px;height:30px;border-radius:8px;object-fit:cover' }),
        el('div', {}, el('b', { style: 'font-size:.85rem' }, u.full_name), el('div', { style: 'font-size:.74rem;color:var(--text-3)' }, u.email)))),
      el('td', {}, chip(u.role_label, 'blue')),
      el('td', {}, chip(titleCase(u.verification_status), u.verification_status === 'verified' ? 'green' : 'gold')),
      el('td', {}, u.verification_status !== 'verified'
        ? el('button', { class: 'btn sm', onclick: async () => {
            try { await api(`/admin/users/${u.id}/verify?decision=verified`, { method: 'POST' }); toast('Verified'); viewAdmin(root.replaceChildren() || root); }
            catch (e) { toast(e.message, 'error'); }
          } }, 'Verify') : null),
    ));
  }
  tbl.appendChild(tb); uc.appendChild(tbl); cols.appendChild(uc);

  const fc = el('div', { class: 'card' });
  fc.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Feature flags & policy')));
  for (const f of flags) {
    fc.appendChild(el('div', { style: 'display:flex;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--border)' },
      el('div', { class: 'grow' }, el('b', {}, f.key), el('div', { style: 'font-size:.8rem;color:var(--text-3)' }, f.description)),
      chip(f.enabled ? 'Enabled' : 'Disabled', f.enabled ? 'green' : 'grey'),
      el('button', { class: 'btn ghost sm', onclick: async () => {
        try { await api(`/admin/flags/${f.key}`, { method: 'PATCH', body: { enabled: !f.enabled } }); toast('Flag updated'); viewAdmin(root.replaceChildren() || root); }
        catch (e) { toast(e.message, 'error'); }
      } }, f.enabled ? 'Disable' : 'Enable')));
  }
  cols.appendChild(fc);
  root.appendChild(cols);
}

/* --------------------------------------------------------------- audit */
async function viewAudit(root) {
  root.appendChild(moduleHero({
    image: 'module_security', tag: 'Tamper-evident',
    title: 'Audit trail',
    body: 'Every sensitive operation is appended to a hash-chained audit log. The chain is verified server-side on every read.',
  }));
  let data;
  try { data = await api('/admin/audit?limit=200'); } catch (e) { return toast(e.message, 'error'); }
  const grid = el('div', { class: 'grid c3' });
  grid.append(
    statCard('Events', data.events.length, 'Most recent'),
    statCard('Chain integrity', data.chain.valid ? 'Verified' : 'Broken', data.chain.valid ? 'Hash chain intact' : 'Investigate immediately', data.chain.valid ? 'green' : 'red'),
    statCard('Algorithm', 'SHA-256', 'Prev-hash chained', 'gold'),
  );
  root.appendChild(grid);
  const card = el('div', { class: 'card pad-0', style: 'margin-top:18px' });
  card.appendChild(el('div', { class: 'card-head', style: 'padding:20px 20px 0' }, el('h3', { class: 'grow' }, 'Audit events')));
  const tbl = el('table', { class: 'table' });
  tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Action'), el('th', {}, 'Entity'), el('th', {}, 'Detail'), el('th', {}, 'When'))));
  const tb = el('tbody');
  for (const e of data.events) {
    tb.appendChild(el('tr', { style: 'cursor:default' },
      el('td', { class: 'strong' }, titleCase(e.action)),
      el('td', {}, e.entity),
      el('td', { style: 'font-size:.8rem;color:var(--text-3);max-width:340px' }, JSON.stringify(e.detail || {})),
      el('td', { style: 'font-size:.8rem;color:var(--text-3)' }, fmtDate(e.at))));
  }
  tbl.appendChild(tb); card.appendChild(tbl); root.appendChild(card);
}

/* --------------------------------------------------------------- settings */
function viewSettings(root) {
  root.appendChild(moduleHero({
    image: 'module_light_theme', tag: 'Preferences',
    title: 'Settings',
    body: 'Theme, language and consent. Preferences persist to your account and apply across every screen.',
  }));
  const cols = el('div', { class: 'grid c2' });

  const themeCard = el('div', { class: 'card' });
  themeCard.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Appearance')));
  const sw = el('div', { class: 'theme-switch' });
  for (const [mode, label] of [['light', 'Light'], ['dark', 'Dark'], ['system', 'System']]) {
    sw.appendChild(el('button', { class: currentTheme() === mode ? 'active' : '', onclick: () => {
      applyTheme(mode);
      api('/auth/me', { method: 'PATCH', body: { theme: mode } }).catch(() => {});
      render();
    } }, label));
  }
  themeCard.appendChild(sw);
  themeCard.appendChild(el('p', { style: 'color:var(--text-3);font-size:.84rem;margin-top:12px' }, 'A theme control is available at the bottom of every screen via the top bar, and the preference is shared across navigation.'));
  themeCard.appendChild(el('img', { src: img(currentTheme() === 'dark' ? 'module_dark_theme' : 'module_light_theme'), style: 'width:100%;border-radius:12px;margin-top:12px;height:150px;object-fit:cover' }));
  cols.appendChild(themeCard);

  const langCard = el('div', { class: 'card' });
  langCard.appendChild(el('div', { class: 'card-head' }, el('div', { class: 'grow' },
    el('h3', {}, 'Language'), el('p', {}, 'All 22 Scheduled Indian languages plus English, with native scripts and RTL support.'))));
  const lg = el('div', { class: 'lang-grid' });
  for (const l of (META?.languages || [])) {
    lg.appendChild(el('div', { class: `lang-item ${ME.language === l.code ? 'active' : ''}`, dir: l.dir, onclick: async () => {
      setLang(l.code);
      try { await api('/auth/me', { method: 'PATCH', body: { language: l.code } }); } catch {}
      ME.language = l.code;
      toast(`Language: ${l.name}`);
      render();
    } }, el('b', {}, l.native), el('small', {}, l.name)));
  }
  langCard.appendChild(lg);
  langCard.appendChild(el('div', { class: 'alert info', style: 'margin-top:12px' }, 'A language is not claimed as production-ready until its interface and agricultural terminology have been validated by competent reviewers.'));
  cols.appendChild(langCard);

  const consentCard = el('div', { class: 'card' });
  consentCard.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Consent & privacy')));
  const consent = ME.consent || { location: true, media: true, notifications: true };
  for (const [k, label] of [['location', 'Location access'], ['media', 'Media capture & upload'], ['notifications', 'Notifications']]) {
    const cb = el('input', { type: 'checkbox', checked: consent[k] ? 'checked' : null, style: 'width:auto' });
    cb.addEventListener('change', () => {
      ME.consent = { ...(ME.consent || {}), [k]: cb.checked };
      api('/auth/me', { method: 'PATCH', body: {} }).catch(() => {});
      toast(`${label}: ${cb.checked ? 'granted' : 'withdrawn'}`);
    });
    consentCard.appendChild(el('label', { style: 'display:flex;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer' }, cb, el('span', {}, label)));
  }
  consentCard.appendChild(el('div', { class: 'alert info', style: 'margin-top:12px' }, 'Data minimization and applicable Indian data-protection requirements are enforced server-side.'));
  cols.appendChild(consentCard);

  root.appendChild(cols);

  const aiCard = el('div', { class: 'card', style: 'margin-top:18px' });
  aiCard.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'AI provider configuration')));
  aiCard.appendChild(el('div', { class: 'kv' },
    el('dt', {}, 'Mode'), el('dd', {}, chip(META?.ai?.mode || 'simulated', META?.ai?.mode === 'live' ? 'green' : 'gold')),
    el('dt', {}, 'Provider'), el('dd', {}, META?.ai?.provider || 'simulated'),
    el('dt', {}, 'Status'), el('dd', {}, META?.ai?.note || '')));
  aiCard.appendChild(el('div', { class: 'alert warn', style: 'margin-top:12px' },
    'Set AGROSPHERE_AI_PROVIDER and AGROSPHERE_AI_API_KEY on the server to enable a live provider. Until then all findings are clearly labelled simulated output.'));
  root.appendChild(aiCard);
}

/* --------------------------------------------------------------- boot */
boot();
