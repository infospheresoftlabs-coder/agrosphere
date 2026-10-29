/* AgroSphere — live map: farms, fields, live actors, directions and geotagging.
 *
 * One map serves four jobs the platform needs: see every farm you may see,
 * watch field actors (people and drones) move in near-real time, get directions
 * to a booked farm, and geotag a farm at registration time.
 */
import { api, el, chip, toast, fmtDate, titleCase, modal, field, input, select, emptyState, moduleHero } from './core.js';
import { ctx } from './context.js';
import {
  hasLeaflet, createMap, addTiles, fitCoords, drawFarm, drawRoute, drawTrack,
  actorIcon, dotIcon, locationPicker, currentPosition, watchPosition,
  searchPlaces, reverseGeocode, routeTo, geoEnabled,
} from './maps.js';

const ROLE_LABEL = {
  farmer: 'Farmer', farm_manager: 'Farm manager', agronomist: 'Agronomist',
  drone_operator: 'Drone operator', super_admin: 'Administrator',
};

export async function viewMap(root) {
  root.appendChild(moduleHero({
    image: 'module_farm_mapping', tag: 'Geospatial',
    title: 'Live map & field tracking',
    body: 'Every farm you may see, its field boundaries, and the live position of farmers, agronomists and drones in the field. Directions to a booked farm are computed on real road geometry.',
  }));

  if (!hasLeaflet()) {
    root.appendChild(el('div', { class: 'alert danger' }, 'Map library failed to load. Reload the page.'));
    return;
  }

  let farms = [];
  try { farms = await api('/farms'); } catch (e) { toast(e.message, 'error'); }

  const meta = ctx.META || {};
  const canvas = el('div', { class: 'map-canvas tall' });
  const toolbar = el('div', { class: 'map-toolbar' });
  const sidePanel = el('div', {});

  const farmList = el('div', { class: 'card' });
  farmList.appendChild(el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Your farms')));

  const liveCard = el('div', { class: 'card', style: 'margin-top:16px' });
  liveCard.appendChild(el('div', { class: 'card-head' },
    el('h3', { class: 'grow' }, 'Live field actors'),
    el('button', { class: 'btn ghost sm', onclick: () => loadLive() }, '↻ Refresh')));
  const liveBody = el('div', {});
  liveCard.appendChild(liveBody);

  // The map container must be in the document before Leaflet measures it,
  // otherwise it initialises at zero size and loads a single tile.
  root.appendChild(toolbar);
  root.appendChild(el('div', { class: 'map-side' }, el('div', {}, canvas), el('div', {}, farmList, liveCard)));

  // ---- map ------------------------------------------------------------- //
  const map = createMap(canvas, { center: [19.5, 74.5], zoom: 6 });
  addTiles(map, meta);
  const layers = { farms: window.L.layerGroup().addTo(map), live: window.L.layerGroup().addTo(map), route: window.L.layerGroup().addTo(map) };
  // The container may still be settling when Leaflet measures it.
  setTimeout(() => map.invalidateSize(), 150);

  for (const farm of farms) drawFarm(map, farm);
  const allCoords = farms.flatMap(f => (f.fields || []).flatMap(x => x.boundary?.coordinates?.[0] || []));
  if (allCoords.length) fitCoords(map, allCoords, { maxZoom: 14 });
  else if (farms.length && farms[0].latitude != null) map.setView([farms[0].latitude, farms[0].longitude], 12);

  // ---- farm list ------------------------------------------------------- //
  if (!farms.length) farmList.appendChild(el('div', { class: 'alert' }, 'No farms are visible to your role yet.'));
  for (const f of farms) {
    farmList.appendChild(el('div', { class: 'actor-row', onclick: () => {
      if (f.latitude != null) { map.setView([f.latitude, f.longitude], 14); }
      else {
        const ring = (f.fields || []).flatMap(x => x.boundary?.coordinates?.[0] || []);
        if (ring.length) fitCoords(map, ring, { maxZoom: 15 });
      }
    } },
      el('span', { class: 'map-pin farm', style: 'flex:none' }, '🌾'),
      el('div', { class: 'who' }, el('b', {}, f.name),
        el('small', {}, `${f.village || ''}${f.district ? ', ' + f.district : ''} · ${f.fields.length} field(s)`)),
      el('button', { class: 'btn ghost sm', onclick: (e) => { e.stopPropagation(); directionsModal(f); } }, '🧭'),
    ));
  }

  // ---- live actors ----------------------------------------------------- //
  async function loadLive() {
    liveBody.replaceChildren(el('div', { class: 'skeleton', style: 'height:70px' }));
    let data;
    try { data = await api('/tracking/live?max_age_min=180'); }
    catch (e) { liveBody.replaceChildren(el('div', { class: 'alert' }, e.message)); return; }
    layers.live.clearLayers();
    if (!data.actors?.length) {
      liveBody.replaceChildren(el('div', { class: 'alert' }, 'No live positions in the last 3 hours. Share your location to appear here.'));
      return;
    }
    const list = el('div', {});
    for (const a of data.actors) {
      const p = a.latest;
      const marker = window.L.marker([p.latitude, p.longitude], { icon: actorIcon(a.role, a.source) })
        .bindPopup(`<b>${a.name}</b><br>${ROLE_LABEL[a.role] || a.role}<br>${p.source === 'drone' ? 'Drone' : 'On foot'}<br>±${Math.round(p.accuracy_m || 0)} m`);
      layers.live.addLayer(marker);
      if (a.track?.length > 1) layers.live.addLayer(window.L.polyline(a.track.map(([lon, lat]) => [lat, lon]),
        { color: a.source === 'drone' ? '#f59e0b' : '#0ea5e9', weight: 3, opacity: 0.6, dashArray: '6 6' }));

      list.appendChild(el('div', { class: 'actor-row', onclick: () => map.setView([p.latitude, p.longitude], 16) },
        el('span', { class: 'map-pin actor', style: `--pin:${a.source === 'drone' ? '#f59e0b' : '#0ea5e9'};flex:none` }, a.source === 'drone' ? '✈' : '👤'),
        el('div', { class: 'who' }, el('b', {}, a.name),
          el('small', {}, `${ROLE_LABEL[a.role] || a.role} · ±${Math.round(p.accuracy_m || 0)} m · ${fmtDate(p.recorded_at)}`)),
      ));
    }
    liveBody.replaceChildren(list);
  }

  // ---- my location + sharing ------------------------------------------- //
  const shareBtn = el('button', { class: 'btn ghost sm' }, '📍 Share my location');
  let watching = null;
  shareBtn.onclick = async () => {
    if (watching) {
      watching(); watching = null; shareBtn.textContent = '📍 Share my location'; toast('Live sharing stopped');
      return;
    }
    shareBtn.textContent = '⏳ Starting…';
    try {
      const pos = await currentPosition();
      const send = async (fix) => {
        try {
          await api('/tracking/ping', { method: 'POST', body: {
            latitude: fix.lat, longitude: fix.lon, source: 'person',
            accuracy_m: fix.accuracy ?? null, heading_deg: fix.heading ?? null, speed_ms: fix.speed ?? null,
          } });
        } catch (e) { console.warn(e); }
      };
      await send(pos);
      watching = watchPosition(send, e => console.warn(e));
      shareBtn.textContent = '⏹ Stop sharing';
      toast('Live location sharing on');
      loadLive();
    } catch (e) { toast(e.message, 'error'); shareBtn.textContent = '📍 Share my location'; }
  };

  toolbar.append(
    el('span', { class: 'chip green' }, `${farms.length} farm(s)`),
    el('span', { class: 'chip blue' }, geoEnabled(meta) ? 'Geoapify routing on' : 'Routing not configured'),
    shareBtn,
    el('button', { class: 'btn ghost sm', onclick: () => loadLive() }, '↻ Live actors'),
  );

  loadLive();
}

/* --------------------------------------------------------------- directions */
export async function directionsModal(farm) {
  const stage = el('div', { class: 'map-canvas short' });
  const summary = el('div', { class: 'alert info' }, 'Choose your starting point, then get directions.');
  const steps = el('div', { class: 'route-steps' });
  const modeSel = select('mode', [
    { value: 'drive', label: 'Car / tractor' },
    { value: 'motorcycle', label: 'Motorcycle' },
    { value: 'bicycle', label: 'Bicycle' },
    { value: 'walk', label: 'On foot' },
  ]);

  const dest = farm.latitude != null
    ? [farm.latitude, farm.longitude]
    : ((farm.fields || []).flatMap(f => f.boundary?.coordinates?.[0] || []).reduce(
        (acc, p) => acc ? [acc[0] + p[0], acc[1] + p[1]] : [p[0], p[1]], null));

  let origin = null;
  const originLabel = el('span', { class: 'chip grey' }, 'origin: not set');
  const routeLayers = [];
  function layers_route_clear() { routeLayers.forEach(l => l?.remove?.()); routeLayers.length = 0; }

  async function compute(from) {
    origin = from;
    originLabel.textContent = `origin: ${from.lat.toFixed(4)}, ${from.lon.toFixed(4)}`;
    if (from.marker) from.marker.remove?.();
    const mk = window.L.marker([from.lat, from.lon], { icon: dotIcon('#0ea5e9', 14, true) }).addTo(map);
    mk.bindTooltip('You are here');
    summary.replaceChildren(el('div', { class: 'skeleton', style: 'height:20px' }));
    steps.replaceChildren();
    try {
      const r = await routeTo(api, farm.id, { lat: from.lat, lon: from.lon }, modeSel.value);
      layers_route_clear();
      if (r.route?.geometry) {
        const line = drawRoute(map, r.route.geometry, r.route.mode);
        routeLayers.push(line);
        const pts = r.route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
        map.fitBounds(window.L.latLngBounds(pts), { padding: [30, 30] });
      }
      const rt = r.route;
      summary.replaceChildren(el('div', {},
        el('b', {}, rt ? `${rt.distance_km} km · about ${Math.round(rt.duration_min)} min` : `${r.straight_line_km} km straight line`),
        rt?.fallback ? el('div', { class: 'small', style: 'color:var(--text-3)' }, `No road route for the selected mode; showing the ${rt.mode} route.`) : null,
        !rt ? el('div', { class: 'small' }, r.route_error || '') : null,
      ));
      if (rt?.steps?.length) {
        const ol = el('ol');
        for (const s of rt.steps.slice(0, 60)) ol.appendChild(el('li', {}, s.instruction || `${Math.round(s.distance_m || 0)} m`));
        steps.replaceChildren(el('div', { style: 'font-size:.8rem;color:var(--text-3);margin-bottom:6px' }, 'Turn-by-turn'), ol);
      }
    } catch (e) {
      summary.replaceChildren(el('div', { class: 'alert warn' }, e.message));
    }
  }

  const body = el('div', {},
    stage,
    el('div', { class: 'map-toolbar', style: 'margin-top:12px' },
      el('button', { class: 'btn ghost sm', onclick: async () => {
        try { const p = await currentPosition(); await compute(p); } catch (e) { toast(e.message, 'error'); }
      } }, '📍 From my location'),
      el('button', { class: 'btn ghost sm', onclick: () => searchOrigin() }, '🔎 From a place'),
      field('Mode', modeSel), originLabel,
    ),
    summary, steps,
    el('div', { class: 'alert', style: 'margin-top:12px' },
      'Directions are for reaching the farm. Use hands-free navigation while driving and follow local road conditions.'),
  );

  // The modal is mounted first so the map container has a real size when
  // Leaflet initialises; otherwise it renders a single tile.
  const m = modal({ title: `Directions to ${farm.name}`, body, wide: true,
    footer: [el('button', { class: 'btn ghost', onclick: () => window.open(
      `https://www.google.com/maps/dir/?api=1&destination=${dest ? dest[0] + ',' + dest[1] : ''}`, '_blank') }, 'Open in Google Maps'),
      el('button', { class: 'btn', onclick: () => window.open(
      `https://www.openstreetmap.org/directions?to=${dest ? dest[0] + ',' + dest[1] : ''}`, '_blank') }, 'Open in OSM')] });

  const map = createMap(stage, { center: [farm.latitude || 19.5, farm.longitude || 74.5], zoom: 12 });
  addTiles(map, ctx.META || {});
  drawFarm(map, farm);
  // Leaflet caches the container size on init; recompute once layout settles.
  setTimeout(() => map.invalidateSize(), 120);

  function searchOrigin() {
    const q = input('q', { placeholder: 'Village, town or landmark' });
    const results = el('div', {});
    const m2 = modal({ title: 'Start from', body: el('div', {}, field('Search a place', q), results),
      footer: [el('button', { class: 'btn ghost', onclick: () => m2.close() }, 'Close')] });
    const run = async () => {
      results.replaceChildren(el('div', { class: 'skeleton', style: 'height:40px' }));
      try {
        const rs = await searchPlaces(api, q.value, 5);
        if (!rs.length) { results.replaceChildren(el('div', { class: 'alert' }, 'No places found.')); return; }
        results.replaceChildren(...rs.map(r => el('div', { class: 'actor-row', onclick: async () => {
          m2.close(); await compute({ lat: r.latitude, lon: r.longitude });
        } }, el('div', { class: 'who' }, el('b', {}, r.formatted), el('small', {}, `${r.village || ''} ${r.district || ''} ${r.state || ''}`)))));
      } catch (e) { results.replaceChildren(el('div', { class: 'alert warn' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); run(); } });
    setTimeout(run, 50);
  }
}

/* --------------------------------------------------------------- geotag farm */
/* Reused by farm registration: draw or click the exact farm location, reverse
 * geocode it into village/district/state, and return {lat, lon, address}. */
export function geotagFarmModal({ onPick } = {}) {
  const stage = el('div', { class: 'map-canvas' });
  const addr = el('div', { class: 'alert info' }, 'Click the map or use your location to set the farm pin.');
  const coordsLine = el('div', { class: 'geo-line' }, 'No point selected yet.');
  let picked = null;

  const body = el('div', {}, stage,
    el('div', { class: 'map-toolbar', style: 'margin-top:10px' },
      el('button', { class: 'btn ghost sm', onclick: async () => {
        try { const p = await picker.useDevice(); } catch (e) { toast(e.message, 'error'); }
      } }, '📍 Use my current location'),
      el('button', { class: 'btn ghost sm', onclick: () => searchHere() }, '🔎 Search a village'),
    ),
    addr, coordsLine,
    el('div', { class: 'alert warn', style: 'margin-top:10px' },
      'Geotagging a farm records where it is. It does not grant anyone access to your device location beyond the point you place here.'),
  );

  const m = modal({ title: 'Geotag the farm', body, wide: true,
    footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Cancel'),
      el('button', { class: 'btn', onclick: () => {
        if (!picked) return toast('Pick a point on the map first', 'error');
        onPick?.(picked); m.close();
      } }, 'Use this location')] });

  // Initialise the map after the modal is in the DOM so it has a real size.
  const picker = locationPicker(stage, ctx.META || {}, {
    onPick: async ({ lat, lon }) => {
      picked = { lat, lon };
      coordsLine.textContent = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
      addr.replaceChildren(el('span', { class: 'skeleton', style: 'display:block;height:16px' }));
      if (!geoEnabled(ctx.META)) { addr.replaceChildren('Coordinates captured (reverse geocoding not configured).'); return; }
      try {
        const r = await reverseGeocode(api, lat, lon);
        picked = { ...picked, address: r };
        addr.replaceChildren(el('div', {}, el('b', {}, r.formatted || 'Address resolved'),
          el('div', { class: 'small', style: 'color:var(--text-3)' },
            [r.village, r.district, r.state, r.postcode].filter(Boolean).join(' · '))));
      } catch (e) { addr.replaceChildren(el('div', { class: 'alert warn' }, e.message)); }
    },
  });
  setTimeout(() => picker.map.invalidateSize(), 120);

  function searchHere() {
    const q = input('q', { placeholder: 'Village or town' });
    const results = el('div', {});
    const m2 = modal({ title: 'Find a place', body: el('div', {}, field('Search', q), results),
      footer: [el('button', { class: 'btn ghost', onclick: () => m2.close() }, 'Close')] });
    const run = async () => {
      results.replaceChildren(el('div', { class: 'skeleton', style: 'height:40px' }));
      try {
        const rs = await searchPlaces(api, q.value, 5);
        results.replaceChildren(...(rs.length ? rs.map(r => el('div', { class: 'actor-row', onclick: () => {
          m2.close(); picker.map.setView([r.latitude, r.longitude], 15); picker.setPin(r.latitude, r.longitude);
        } }, el('div', { class: 'who' }, el('b', {}, r.formatted),
          el('small', {}, `${r.village || ''} ${r.district || ''} ${r.state || ''}`)))) : [el('div', { class: 'alert' }, 'No places found.')]));
      } catch (e) { results.replaceChildren(el('div', { class: 'alert warn' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); run(); } });
    setTimeout(run, 50);
  }
  return m;
}
