/* AgroSphere — weather intelligence: forecast, spray windows, disease pressure.
 *
 * The value here is the decision, not the numbers: is a spray window open, and
 * how does the coming weather change the crop-health and treatment advice.
 */
import { api, el, chip, toast, moduleHero, field, select, emptyState } from './core.js';
import { ctx } from './context.js';

const BAND_TONE = { low: 'green', moderate: 'gold', high: 'red', unknown: 'grey' };

export async function viewWeather(root) {
  root.appendChild(moduleHero({
    image: 'module_weather', tag: 'Field services',
    title: 'Weather & spray-window intelligence',
    body: 'A seven-day forecast for each farm, turned into an actionable decision: whether a spray window is open, how much disease pressure is building, and how that changes the treatment advice.',
  }));

  let farms = [];
  try { farms = await api('/farms'); } catch (e) { toast(e.message, 'error'); }

  const farmSel = select('farm', farms.length
    ? farms.map(f => ({ value: f.id, label: `${f.name} — ${f.village || f.district || ''}` }))
    : [{ value: '', label: 'No farms available' }]);
  const fieldSel = select('field', [{ value: '', label: 'Whole farm' }]);
  const pane = el('div', {});

  function refreshFields() {
    const farm = farms.find(f => f.id === farmSel.value);
    fieldSel.replaceChildren(el('option', { value: '' }, 'Whole farm'),
      ...(farm?.fields || []).map(f => el('option', { value: f.id }, `${f.name} (${f.crop})`)));
  }

  async function load() {
    if (!farmSel.value) { pane.replaceChildren(el('div', { class: 'alert' }, 'Register a farm with coordinates to see weather.')); return; }
    pane.replaceChildren(el('div', { class: 'skeleton', style: 'height:220px' }));
    const qs = new URLSearchParams();
    if (fieldSel.value) qs.set('field_id', fieldSel.value); else qs.set('farm_id', farmSel.value);
    qs.set('days', '7');
    try {
      const w = await api(`/weather?${qs.toString()}`);
      pane.replaceChildren(render(w));
    } catch (e) { pane.replaceChildren(el('div', { class: 'alert danger' }, e.message)); }
  }

  const controls = el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Choose a location')),
    el('div', { class: 'grid c2' }, field('Farm', farmSel), field('Field (optional)', fieldSel)),
    el('div', { class: 'map-toolbar' }, el('button', { class: 'btn', onclick: load }, '⛅ Load forecast')),
  );

  farmSel.addEventListener('change', () => { refreshFields(); load(); });
  fieldSel.addEventListener('change', load);
  refreshFields();

  root.append(controls, pane);
  await load();
}

function render(w) {
  const c = w.current || {};
  const dp = w.disease_pressure || {};
  const sw = w.spray_windows || {};
  const g = w.guidance || {};
  const wrap = el('div', {});

  // Current conditions.
  wrap.appendChild(el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('h3', { class: 'grow' }, `${w.location?.name || 'Location'} — now`),
      chip(c.condition || 'Unknown', 'blue'),
      chip(w.location?.kind === 'field' ? 'Field' : 'Farm', 'grey')),
    el('div', { class: 'weather-grid' },
      tile('Temperature', c.temperature_c != null ? `${c.temperature_c}` : '—', '°C'),
      tile('Humidity', c.humidity_pct != null ? `${c.humidity_pct}` : '—', '%'),
      tile('Wind', c.wind_kmh != null ? `${c.wind_kmh}` : '—', 'km/h'),
      tile('Rain now', c.precipitation_mm != null ? `${c.precipitation_mm}` : '—', 'mm'),
      tile('Cloud', c.cloud_pct != null ? `${c.cloud_pct}` : '—', '%'),
    ),
  ));

  // Spray window + disease pressure side by side.
  const nextOpen = sw.next_open;
  const twoCol = el('div', { class: 'grid c2', style: 'margin-top:16px' });

  twoCol.appendChild(el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Spray window')),
    nextOpen
      ? el('div', { class: 'alert info' }, el('b', {}, `Next open window: ${(nextOpen.time || '').replace('T', ' ')}`),
          el('div', { style: 'font-size:.84rem;margin-top:4px' }, `Wind ${nextOpen.wind_kmh} km/h · rain risk ${nextOpen.rain_prob_pct}% · ${nextOpen.temperature_c}°C`))
      : el('div', { class: 'alert warn' }, 'No clear spray window in the next 48 hours. Defer treatment rather than spraying into wind, heat or rain.'),
    el('div', { style: 'display:flex;gap:8px;margin-top:10px' },
      chip(`${sw.open_hours_next_48 ?? 0} open hours`, 'green'),
      chip(`${sw.blocked_hours_next_48 ?? 0} blocked hours`, 'gold')),
    el('div', { style: 'font-size:.78rem;color:var(--text-3);margin-top:10px' },
      `Thresholds — wind ≤ ${sw.thresholds?.max_wind_kmh} km/h, temp ≤ ${sw.thresholds?.max_temp_c}°C, humidity ≥ ${sw.thresholds?.min_humidity_pct}%, rain risk < ${sw.thresholds?.rain_risk_pct}%`),
  ));

  twoCol.appendChild(el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Disease pressure')),
    el('div', { class: 'pressure-meter' },
      el('div', { class: `pressure-ring ${dp.band || 'unknown'}` }, `${dp.index ?? 0}`),
      el('div', {}, el('b', {}, `${(dp.band || 'unknown').toUpperCase()} risk`),
        el('div', { style: 'font-size:.8rem;color:var(--text-3)' }, `Average humidity ${dp.average_humidity_pct ?? '—'}%`))),
    (dp.drivers || []).length
      ? el('ul', { class: 'guidance-list' }, ...dp.drivers.map(d => el('li', {}, d)))
      : el('div', { class: 'alert' }, 'No notable disease drivers in the forecast window.'),
  ));

  wrap.appendChild(twoCol);

  // Guidance for crop health and treatment.
  wrap.appendChild(el('div', { class: 'card', style: 'margin-top:16px' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'What this means for your crop')),
    el('h4', { style: 'margin:8px 0 4px;font-size:.86rem;color:var(--green-600)' }, 'Crop health'),
    el('ul', { class: 'guidance-list' }, ...(g.crop_health || []).map(x => el('li', {}, x))),
    el('h4', { style: 'margin:12px 0 4px;font-size:.86rem;color:var(--green-600)' }, 'Treatment planning'),
    el('ul', { class: 'guidance-list' }, ...(g.treatment || []).map(x => el('li', {}, x))),
    el('div', { class: 'alert warn', style: 'margin-top:12px' }, w.disclaimer),
  ));

  // Hourly strip (next 24 hours).
  const hours = (w.hourly || []).slice(0, 24);
  if (hours.length) {
    wrap.appendChild(el('div', { class: 'card', style: 'margin-top:16px' },
      el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Next 24 hours'),
        chip('green border = sprayable', 'green')),
      el('div', { class: 'hour-strip' }, ...hours.map(h => el('div', { class: `hour-cell ${h.spray_ok ? 'ok' : 'no'}` },
        el('div', { class: 't' }, (h.time || '').slice(11, 16)),
        el('div', { class: 'n' }, `${h.temperature_c ?? '—'}°`),
        el('div', {}, `💧${h.rain_prob_pct ?? 0}%`),
        el('div', {}, `🌬${h.wind_kmh ?? 0}`),
        h.spray_ok ? el('div', { style: 'color:var(--green-600);font-weight:600' }, 'spray ✓') : el('div', { style: 'color:var(--text-3)' }, h.spray_blockers?.[0] || 'no'),
      )))));
  }

  // Daily forecast.
  wrap.appendChild(el('div', { class: 'card', style: 'margin-top:16px' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Seven-day outlook')),
    el('table', { class: 'table' },
      el('thead', {}, el('tr', {}, el('th', {}, 'Day'), el('th', {}, 'Conditions'), el('th', {}, 'High / Low'), el('th', {}, 'Rain'), el('th', {}, 'Rain risk'), el('th', {}, 'Wind max'))),
      el('tbody', {}, ...(w.daily || []).map(d => el('tr', {},
        el('td', { class: 'strong' }, d.date),
        el('td', {}, d.condition),
        el('td', {}, `${d.temp_max_c ?? '—'}° / ${d.temp_min_c ?? '—'}°`),
        el('td', {}, `${d.rain_mm ?? 0} mm`),
        el('td', {}, chip(`${d.rain_prob_pct ?? 0}%`, (d.rain_prob_pct ?? 0) >= 60 ? 'blue' : 'grey')),
        el('td', {}, `${d.wind_max_kmh ?? '—'} km/h`),
      )))),
  ));

  return wrap;
}

function tile(k, v, u) {
  return el('div', { class: 'weather-tile' }, el('div', { class: 'k' }, k),
    el('div', { class: 'v' }, v), el('div', { class: 'u' }, u));
}
