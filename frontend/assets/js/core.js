/* AgroSphere — core: API client, i18n, state, helpers, UI primitives. */

export const API = {
  token: localStorage.getItem('agrosphere.token') || null,
  user: JSON.parse(localStorage.getItem('agrosphere.user') || 'null'),
};

export async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } };
  if (API.token) opts.headers.Authorization = `Bearer ${API.token}`;
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, opts);
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data && data.detail;
    const msg = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join('; ')
      : detail && typeof detail === 'object' ? JSON.stringify(detail)
      : `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

export function setSession(token, user) {
  API.token = token; API.user = user;
  if (token) {
    localStorage.setItem('agrosphere.token', token);
    localStorage.setItem('agrosphere.user', JSON.stringify(user));
  } else {
    localStorage.removeItem('agrosphere.token');
    localStorage.removeItem('agrosphere.user');
  }
}

/* --------------------------------------------------------------- images */
export const img = (key) => (key ? `/images/${key}.jpg` : '/images/hero.jpg');
const FALLBACK_IMG = '/images/hero.jpg';

// Any image that fails to load (e.g. artwork still being generated) degrades to
// the hero image instead of showing a broken-image icon.
document.addEventListener('error', (e) => {
  const target = e.target;
  if (target instanceof HTMLImageElement && target.src !== location.origin + FALLBACK_IMG) {
    target.src = FALLBACK_IMG;
  }
}, true);

/* --------------------------------------------------------------- i18n */
export const STRINGS = {
  en: {
    dashboard: 'Dashboard', farms: 'Farms & Fields', cases: 'Crop Health Cases',
    analysis: 'AI Analysis', plans: 'Treatment Plans', approvals: 'Approvals',
    drone: 'Drone Operations', fleet: 'Drone Fleet', reports: 'Reports',
    payments: 'Payments', notifications: 'Notifications', grievances: 'Support',
    knowledge: 'Knowledge Base', analytics: 'Analytics', modules: 'Platform Modules',
    admin: 'Administration', audit: 'Audit Trail', settings: 'Settings', advisor: 'AI Advisor',
    map: 'Live Map', capture: 'Live Capture', weather: 'Weather',
    directions: 'Directions', track: 'Live tracking',

    logout: 'Sign out', welcome: 'Welcome', save: 'Save', cancel: 'Cancel',
    submit: 'Submit', approve: 'Approve', reject: 'Reject', theme: 'Theme',
    light: 'Light', dark: 'Dark', system: 'System', language: 'Language',
    overview: 'Overview', role: 'Role', state: 'State', actions: 'Actions',
    newCase: 'New case', loading: 'Loading…', noData: 'Nothing here yet',
  },
  hi: {
    dashboard: 'डैशबोर्ड', farms: 'खेत और भूखंड', cases: 'फसल स्वास्थ्य मामले',
    analysis: 'एआई विश्लेषण', plans: 'उपचार योजनाएँ', approvals: 'स्वीकृतियाँ',
    drone: 'ड्रोन संचालन', fleet: 'ड्रोन बेड़ा', reports: 'रिपोर्ट',
    payments: 'भुगतान', notifications: 'सूचनाएँ', grievances: 'सहायता',
    knowledge: 'ज्ञान आधार', analytics: 'विश्लेषिकी', modules: 'प्लेटफ़ॉर्म मॉड्यूल',
    admin: 'प्रशासन', audit: 'लेखा परीक्षा', settings: 'सेटिंग्स', advisor: 'एआई सलाहकार',
    map: 'लाइव नक्शा', capture: 'लाइव कैप्चर', weather: 'मौसम',
    directions: 'दिशा-निर्देश', track: 'लाइव ट्रैकिंग',

    logout: 'साइन आउट', welcome: 'स्वागत', save: 'सहेजें', cancel: 'रद्द करें',
    submit: 'जमा करें', approve: 'स्वीकृत', reject: 'अस्वीकृत', theme: 'थीम',
    light: 'हल्का', dark: 'गहरा', system: 'सिस्टम', language: 'भाषा',
    overview: 'अवलोकन', role: 'भूमिका', state: 'स्थिति', actions: 'क्रियाएँ',
    newCase: 'नया मामला', loading: 'लोड हो रहा है…', noData: 'अभी कुछ नहीं',
  },
  mr: {
    dashboard: 'डॅशबोर्ड', farms: 'शेते व क्षेत्रे', cases: 'पीक आरोग्य प्रकरणे',
    analysis: 'एआय विश्लेषण', plans: 'उपचार योजना', approvals: 'मंजुरी',
    drone: 'ड्रोन कामकाज', fleet: 'ड्रोन ताफा', reports: 'अहवाल',
    payments: 'देयके', notifications: 'सूचना', grievances: 'सहाय्य',
    knowledge: 'ज्ञानकोश', analytics: 'विश्लेषण', modules: 'मंच मॉड्यूल',
    admin: 'प्रशासन', audit: 'लेखापरीक्षण', settings: 'सेटिंग्ज', advisor: 'एआय सल्लागार',
    logout: 'बाहेर पडा', welcome: 'स्वागत', save: 'जतन करा', cancel: 'रद्द',
    submit: 'सबमिट', approve: 'मंजूर', reject: 'नामंजूर', theme: 'थीम',
    light: 'फिकट', dark: 'गडद', system: 'सिस्टम', language: 'भाषा',
    overview: 'आढावा', role: 'भूमिका', state: 'स्थिती', actions: 'क्रिया',
    newCase: 'नवीन प्रकरण', loading: 'लोड होत आहे…', noData: 'अजून काही नाही',
  },
  ta: {
    dashboard: 'டாஷ்போர்டு', farms: 'பண்ணைகள்', cases: 'பயிர் ஆரோக்கிய வழக்குகள்',
    analysis: 'AI பகுப்பாய்வு', plans: 'சிகிச்சை திட்டங்கள்', approvals: 'ஒப்புதல்கள்',
    drone: 'ட்ரோன் செயல்பாடுகள்', fleet: 'ட்ரோன் குழு', reports: 'அறிக்கைகள்',
    payments: 'கொடுப்பனவுகள்', notifications: 'அறிவிப்புகள்', grievances: 'ஆதரவு',
    knowledge: 'அறிவுத் தளம்', analytics: 'பகுப்பாய்வு', modules: 'தள தொகுதிகள்',
    admin: 'நிர்வாகம்', audit: 'தணிக்கை', settings: 'அமைப்புகள்',
    logout: 'வெளியேறு', welcome: 'வரவேற்பு', save: 'சேமி', cancel: 'ரத்து',
    submit: 'சமர்ப்பி', approve: 'ஒப்புதல்', reject: 'நிராகரி', theme: 'தீம்',
    light: 'வெளிர்', dark: 'இருள்', system: 'சிஸ்டம்', language: 'மொழி',
    overview: 'மேலோட்டம்', role: 'பங்கு', state: 'நிலை', actions: 'செயல்கள்',
    newCase: 'புதிய வழக்கு', loading: 'ஏற்றுகிறது…', noData: 'இன்னும் இல்லை',
  },
  te: {
    dashboard: 'డాష్‌బోర్డ్', farms: 'పొలాలు', cases: 'పంట ఆరోగ్య కేసులు',
    analysis: 'AI విశ్లేషణ', plans: 'చికిత్స ప్రణాళికలు', approvals: 'ఆమోదాలు',
    drone: 'డ్రోన్ కార్యకలాపాలు', fleet: 'డ్రోన్ సమూహం', reports: 'నివేదికలు',
    payments: 'చెల్లింపులు', notifications: 'నోటిఫికేషన్లు', grievances: 'సహాయం',
    knowledge: 'జ్ఞాన కేంద్రం', analytics: 'విశ్లేషణలు', modules: 'ప్లాట్‌ఫారమ్ మాడ్యూల్స్',
    admin: 'నిర్వహణ', audit: 'ఆడిట్', settings: 'సెట్టింగ్‌లు',
    logout: 'సైన్ అవుట్', welcome: 'స్వాగతం', save: 'సేవ్', cancel: 'రద్దు',
    submit: 'సమర్పించు', approve: 'ఆమోదించు', reject: 'తిరస్కరించు', theme: 'థీమ్',
    light: 'లైట్', dark: 'డార్క్', system: 'సిస్టమ్', language: 'భాష',
    overview: 'అవలోకనం', role: 'పాత్ర', state: 'స్థితి', actions: 'చర్యలు',
    newCase: 'కొత్త కేసు', loading: 'లోడ్ అవుతోంది…', noData: 'ఇంకా ఏమీ లేదు',
  },
  bn: {
    dashboard: 'ড্যাশবোর্ড', farms: 'খামার', cases: 'ফসল স্বাস্থ্য কেস',
    analysis: 'এআই বিশ্লেষণ', plans: 'চিকিৎসা পরিকল্পনা', approvals: 'অনুমোদন',
    drone: 'ড্রোন পরিচালনা', fleet: 'ড্রোন বহর', reports: 'প্রতিবেদন',
    payments: 'পেমেন্ট', notifications: 'বিজ্ঞপ্তি', grievances: 'সহায়তা',
    knowledge: 'জ্ঞানভাণ্ডার', analytics: 'বিশ্লেষণ', modules: 'মডিউল',
    admin: 'প্রশাসন', audit: 'অডিট', settings: 'সেটিংস',
    logout: 'সাইন আউট', welcome: 'স্বাগতম', save: 'সংরক্ষণ', cancel: 'বাতিল',
    submit: 'জমা', approve: 'অনুমোদন', reject: 'প্রত্যাখ্যান', theme: 'থিম',
    light: 'হালকা', dark: 'গাঢ়', system: 'সিস্টেম', language: 'ভাষা',
    overview: 'সারসংক্ষেপ', role: 'ভূমিকা', state: 'অবস্থা', actions: 'কার্য',
    newCase: 'নতুন কেস', loading: 'লোড হচ্ছে…', noData: 'এখনও কিছু নেই',
  },
  gu: {
    dashboard: 'ડેશબોર્ડ', farms: 'ખેતરો', cases: 'પાક આરોગ્ય કેસ',
    analysis: 'AI વિશ્લેષણ', plans: 'સારવાર યોજના', approvals: 'મંજૂરી',
    drone: 'ડ્રોન કામગીરી', fleet: 'ડ્રોન કાફલો', reports: 'અહેવાલ',
    payments: 'ચુકવણી', notifications: 'સૂચનાઓ', grievances: 'સહાય',
    knowledge: 'જ્ઞાન આધાર', analytics: 'વિશ્લેષણ', modules: 'મોડ્યુલ',
    admin: 'વહીવટ', audit: 'ઓડિટ', settings: 'સેટિંગ્સ',
    logout: 'સાઇન આઉટ', welcome: 'સ્વાગત', save: 'સાચવો', cancel: 'રદ',
    submit: 'સબમિટ', approve: 'મંજૂર', reject: 'નામંજૂર', theme: 'થીમ',
    light: 'હળવું', dark: 'ઘેરું', system: 'સિસ્ટમ', language: 'ભાષા',
    overview: 'ઝલક', role: 'ભૂમિકા', state: 'સ્થિતિ', actions: 'ક્રિયાઓ',
    newCase: 'નવો કેસ', loading: 'લોડ થઈ રહ્યું છે…', noData: 'હજી કંઈ નથી',
  },
  kn: {
    dashboard: 'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್', farms: 'ಜಮೀನುಗಳು', cases: 'ಬೆಳೆ ಆರೋಗ್ಯ ಪ್ರಕರಣಗಳು',
    analysis: 'AI ವಿಶ್ಲೇಷಣೆ', plans: 'ಚಿಕಿತ್ಸಾ ಯೋಜನೆಗಳು', approvals: 'ಅನುಮೋದನೆಗಳು',
    drone: 'ಡ್ರೋನ್ ಕಾರ್ಯಾಚರಣೆ', fleet: 'ಡ್ರೋನ್ ಪಡೆ', reports: 'ವರದಿಗಳು',
    payments: 'ಪಾವತಿಗಳು', notifications: 'ಅಧಿಸೂಚನೆಗಳು', grievances: 'ಸಹಾಯ',
    knowledge: 'ಜ್ಞಾನ ಆಧಾರ', analytics: 'ವಿಶ್ಲೇಷಣೆ', modules: 'ಮಾಡ್ಯೂಲ್‌ಗಳು',
    admin: 'ಆಡಳಿತ', audit: 'ಲೆಕ್ಕಪರಿಶೋಧನೆ', settings: 'ಸೆಟ್ಟಿಂಗ್‌ಗಳು',
    map: 'ಲೈವ್ ನಕ್ಷೆ', capture: 'ಲೈವ್ ಕ್ಯಾಪ್ಚರ್', weather: 'ಹವಾಮಾನ',
    directions: 'ದಿಕ್ಕುಗಳು', track: 'ಲೈವ್ ಟ್ರ್ಯಾಕಿಂಗ್', advisor: 'AI ಸಲಹೆಗಾರ',
    logout: 'ಸೈನ್ ಔಟ್', welcome: 'ಸ್ವಾಗತ', save: 'ಉಳಿಸಿ', cancel: 'ರದ್ದು',
    submit: 'ಸಲ್ಲಿಸಿ', approve: 'ಅನುಮೋದಿಸಿ', reject: 'ತಿರಸ್ಕರಿಸಿ', theme: 'ಥೀಮ್',
    light: 'ಬೆಳಕು', dark: 'ಕತ್ತಲೆ', system: 'ಸಿಸ್ಟಂ', language: 'ಭಾಷೆ',
    overview: 'ಅವಲೋಕನ', role: 'ಪಾತ್ರ', state: 'ಸ್ಥಿತಿ', actions: 'ಕ್ರಿಯೆಗಳು',
    newCase: 'ಹೊಸ ಪ್ರಕರಣ', loading: 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…', noData: 'ಇನ್ನೂ ಏನೂ ಇಲ್ಲ',
  },
  pa: {
    dashboard: 'ਡੈਸ਼ਬੋਰਡ', farms: 'ਖੇਤ', cases: 'ਫਸਲ ਸਿਹਤ ਕੇਸ',
    analysis: 'AI ਵਿਸ਼ਲੇਸ਼ਣ', plans: 'ਇਲਾਜ ਯੋਜਨਾ', approvals: 'ਮਨਜ਼ੂਰੀ',
    drone: 'ਡਰੋਨ ਕਾਰਵਾਈ', fleet: 'ਡਰੋਨ ਫਲੀਟ', reports: 'ਰਿਪੋਰਟਾਂ',
    payments: 'ਭੁਗਤਾਨ', notifications: 'ਸੂਚਨਾਵਾਂ', grievances: 'ਸਹਾਇਤਾ',
    knowledge: 'ਗਿਆਨ ਅਧਾਰ', analytics: 'ਵਿਸ਼ਲੇਸ਼ਣ', modules: 'ਮੋਡਿਊਲ',
    admin: 'ਪ੍ਰਸ਼ਾਸਨ', audit: 'ਆਡਿਟ', settings: 'ਸੈਟਿੰਗਾਂ',
    map: 'ਲਾਈਵ ਨਕਸ਼ਾ', capture: 'ਲਾਈਵ ਕੈਪਚਰ', weather: 'ਮੌਸਮ',
    directions: 'ਦਿਸ਼ਾਵਾਂ', track: 'ਲਾਈਵ ਟਰੈਕਿੰਗ', advisor: 'AI ਸਲਾਹਕਾਰ',
    logout: 'ਸਾਈਨ ਆਊਟ', welcome: 'ਜੀ ਆਇਆਂ', save: 'ਸੰਭਾਲੋ', cancel: 'ਰੱਦ',
    submit: 'ਭੇਜੋ', approve: 'ਮਨਜ਼ੂਰ', reject: 'ਅਸਵੀਕਾਰ', theme: 'ਥੀਮ',
    light: 'ਹਲਕਾ', dark: 'ਗੂੜ੍ਹਾ', system: 'ਸਿਸਟਮ', language: 'ਭਾਸ਼ਾ',
    overview: 'ਸੰਖੇਪ', role: 'ਭੂਮਿਕਾ', state: 'ਹਾਲਤ', actions: 'ਕਾਰਵਾਈਆਂ',
    newCase: 'ਨਵਾਂ ਕੇਸ', loading: 'ਲੋਡ ਹੋ ਰਿਹਾ…', noData: 'ਹਾਲੇ ਕੁਝ ਨਹੀਂ',
  },
};

let currentLang = localStorage.getItem('agrosphere.lang') || 'en';
export function setLang(code) {
  currentLang = code;
  localStorage.setItem('agrosphere.lang', code);
}
export function t(key) {
  const dict = STRINGS[currentLang] || STRINGS.en;
  return dict[key] || STRINGS.en[key] || key;
}

/* --------------------------------------------------------------- theme */
export function applyTheme(mode) {
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const resolved = mode === 'system' ? (prefersDark ? 'dark' : 'light') : mode;
  document.documentElement.dataset.theme = resolved;
  localStorage.setItem('agrosphere.theme', mode);
}
export function currentTheme() { return localStorage.getItem('agrosphere.theme') || 'system'; }

/* --------------------------------------------------------------- toasts */
export function toast(message, kind = 'ok') {
  let wrap = document.querySelector('.toast-wrap');
  if (!wrap) { wrap = document.createElement('div'); wrap.className = 'toast-wrap'; document.body.appendChild(wrap); }
  const el = document.createElement('div');
  el.className = `toast ${kind === 'ok' ? '' : kind}`;
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; setTimeout(() => el.remove(), 250); }, 4200);
}

/* --------------------------------------------------------------- helpers */
export const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
};

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

export const inr = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
export const pct = (n) => `${Math.round(Number(n || 0) * 100)}%`;
export const fmtDate = (s) => { try { return new Date(s).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }); } catch { return s || ''; } };
export const titleCase = (s) => String(s || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export const STATE_TONE = {
  draft: 'grey', imagery_captured: 'blue', analysis_running: 'blue', ai_findings_ready: 'blue',
  awaiting_agronomist: 'gold', plan_prepared: 'gold', awaiting_manager: 'gold',
  plan_approved: 'green', awaiting_farmer: 'gold', implementation_chosen: 'green',
  job_assigned: 'blue', in_progress: 'blue', completed: 'green', follow_up: 'blue',
  closed: 'grey', reopened: 'red', rejected: 'red', needs_revision: 'red',
};
export const SEV_TONE = { high: 'red', medium: 'gold', low: 'green', unknown: 'grey' };

export function chip(text, tone = 'grey') { return el('span', { class: `chip ${tone}` }, text); }

export function statCard(label, value, sub, tone = 'green') {
  return el('div', { class: 'stat' },
    el('span', { class: 'accent', style: tone === 'gold' ? 'background:var(--gold-500)' : tone === 'red' ? 'background:var(--danger-500)' : '' }),
    el('div', { class: 'label' }, label),
    el('div', { class: 'value' }, value),
    sub ? el('div', { class: 'sub' }, sub) : null,
  );
}

export function moduleHero({ image, tag, title, body }) {
  return el('div', { class: 'module-hero' },
    el('img', { src: img(image), alt: title, loading: 'lazy' }),
    el('div', { class: 'inner' },
      tag ? el('span', { class: 'tag' }, tag) : null,
      el('h2', {}, title),
      body ? el('p', {}, body) : null,
    ),
  );
}

export function emptyState(image, title, body, action) {
  return el('div', { class: 'empty' },
    image ? el('img', { src: img(image), alt: title, loading: 'lazy' }) : null,
    el('h3', {}, title),
    body ? el('p', {}, body) : null,
    action || null,
  );
}

export function modal({ title, body, footer, wide }) {
  const back = el('div', { class: 'modal-backdrop' });
  const close = () => back.remove();
  const box = el('div', { class: `modal ${wide ? 'wide' : ''}` },
    el('div', { class: 'modal-head' },
      el('h3', { class: 'grow' }, title),
      el('button', { class: 'icon-btn', onclick: close, 'aria-label': 'Close' }, '✕'),
    ),
    el('div', { class: 'modal-body' }, body),
    footer ? el('div', { class: 'modal-foot' }, footer) : null,
  );
  back.addEventListener('click', e => { if (e.target === back) close(); });
  back.appendChild(box);
  document.body.appendChild(back);
  return { close, box };
}

export function field(label, input, hint) {
  return el('div', { class: 'field' }, el('label', {}, label), input, hint ? el('div', { class: 'hint' }, hint) : null);
}

export function input(name, attrs = {}) {
  return el('input', { name, ...attrs });
}
export function select(name, options, attrs = {}) {
  const s = el('select', { name, ...attrs });
  for (const o of options) s.appendChild(el('option', { value: o.value, selected: o.selected ? 'selected' : null }, o.label));
  return s;
}

export function bar(value, tone = '') {
  const b = el('div', { class: `bar ${tone}` });
  b.appendChild(el('span', { style: `width:${Math.max(0, Math.min(100, value))}%` }));
  return b;
}

export function bindForm(root) {
  const data = {};
  root.querySelectorAll('input[name], select[name], textarea[name]').forEach(n => {
    data[n.name] = n.type === 'checkbox' ? n.checked : n.value;
  });
  return data;
}
