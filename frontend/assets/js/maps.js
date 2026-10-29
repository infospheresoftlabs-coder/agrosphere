/* AgroSphere — maps: Leaflet helpers for farms, fields, live tracking and routing.
 *
 * Leaflet is loaded globally (window.L) from /assets/vendor/leaflet. Tiles come
 * from Geoapify when a key is configured, otherwise OpenStreetMap; the server
 * tells us which through /api/meta so the frontend never hardcodes a key.
 */

const L = () => window.L;

export const hasLeaflet = () => Boolean(window.L);

/* Tiles and attribution, taken from /api/meta so the key lives in one place. */
export function tileLayer(META) {
  const maps = META?.maps || {};
  const url = maps.tile_url || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  return L().tileLayer(url, {
    maxZoom: 19,
    attribution: maps.attribution || '&copy; OpenStreetMap contributors',
  });
}

export function geoEnabled(META) {
  return Boolean(META?.maps?.geocoding);
}

/* --------------------------------------------------------------- base map */
export function createMap(node, { center = [20.5937, 78.9629], zoom = 5, scrollWheel = true } = {}) {
  const map = L().map(node, {
    center, zoom,
    scrollWheelZoom: scrollWheel,
    zoomControl: true,
    attributionControl: true,
  });
  return map;
}

export function addTiles(map, META) {
  tileLayer(META).addTo(map);
  return map;
}

/* Fit the view to a set of GeoJSON-ish coordinates [[lon,lat],...]. */
export function fitCoords(map, coords, opts = {}) {
  if (!coords || !coords.length) return;
  const latlngs = coords.map(([lon, lat]) => [lat, lon]);
  map.fitBounds(L().latLngBounds(latlngs), { padding: [28, 28], maxZoom: opts.maxZoom ?? 16 });
}

/* --------------------------------------------------------------- markers */
const ROLE_COLOR = {
  farmer: '#12b76a', farm_manager: '#0ea5e9', agronomist: '#8b5cf6',
  drone_operator: '#f59e0b', super_admin: '#ef4444',
};

export function dotIcon(color = '#12b76a', size = 14, pulse = false) {
  return L().divIcon({
    className: '',
    html: `<span class="map-dot${pulse ? ' pulse' : ''}" style="--dot:${color};width:${size}px;height:${size}px"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export function farmIcon() {
  return L().divIcon({
    className: '',
    html: '<span class="map-pin farm">🌾</span>',
    iconSize: [30, 30],
    iconAnchor: [15, 28],
    popupAnchor: [0, -26],
  });
}

export function actorIcon(role, source) {
  const color = source === 'drone' ? '#f59e0b' : (ROLE_COLOR[role] || '#12b76a');
  const glyph = source === 'drone' ? '✈' : '👤';
  return L().divIcon({
    className: '',
    html: `<span class="map-pin actor" style="--pin:${color}">${glyph}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

/* --------------------------------------------------------------- drawing */
export function fieldPolygon(field, { color = '#12b76a' } = {}) {
  const ring = field?.boundary?.coordinates?.[0];
  if (!ring || ring.length < 3) return null;
  const latlngs = ring.map(([lon, lat]) => [lat, lon]);
  return L().polygon(latlngs, {
    color, weight: 2, fillColor: color, fillOpacity: 0.22,
  });
}

export function drawFarm(map, farm) {
  const layer = L().layerGroup();
  if (farm.latitude != null && farm.longitude != null) {
    layer.addLayer(L().marker([farm.latitude, farm.longitude], { icon: farmIcon() })
      .bindPopup(`<b>${farm.name}</b><br>${farm.village || ''}${farm.district ? ', ' + farm.district : ''}<br>${farm.total_acres} acres`));
  }
  for (const f of farm.fields || []) {
    const poly = fieldPolygon(f);
    if (poly) {
      poly.bindPopup(`<b>${f.name}</b><br>${f.crop} · ${f.computed_acres ?? f.acreage} acres`);
      layer.addLayer(poly);
    }
  }
  layer.addTo(map);
  return layer;
}

export function routeStyle(mode) {
  const colors = { drive: '#12b76a', truck: '#0ea5e9', motorcycle: '#8b5cf6',
    bicycle: '#f59e0b', walk: '#ef4444', transit: '#64748b' };
  return { color: colors[mode] || '#12b76a', weight: 5, opacity: 0.85 };
}

export function drawRoute(map, geometry, mode = 'drive') {
  if (!geometry?.coordinates?.length) return null;
  const latlngs = geometry.coordinates.map(([lon, lat]) => [lat, lon]);
  const line = L().polyline(latlngs, routeStyle(mode)).addTo(map);
  return line;
}

export function drawTrack(map, track, { color = '#0ea5e9' } = {}) {
  if (!track || track.length < 2) return null;
  const latlngs = track.map(([lon, lat]) => [lat, lon]);
  return L().polyline(latlngs, { color, weight: 3, opacity: 0.7, dashArray: '6 6' }).addTo(map);
}

/* --------------------------------------------------------------- geolocation */
export function currentPosition({ timeout = 12000 } = {}) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Geolocation is not available on this device.'));
    navigator.geolocation.getCurrentPosition(
      p => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy, raw: p.coords }),
      err => reject(new Error(err.code === 1
        ? 'Location permission denied. Enable location access to use live maps.'
        : 'Could not determine your location.')),
      { enableHighAccuracy: true, timeout, maximumAge: 15000 },
    );
  });
}

/* Continuous watch, used by the live-tracking toggle. Returns a stop function. */
export function watchPosition(onFix, onError) {
  if (!navigator.geolocation) { onError?.(new Error('Geolocation unavailable')); return () => {}; }
  const id = navigator.geolocation.watchPosition(
    p => onFix({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy,
      heading: p.coords.heading, speed: p.coords.speed, altitude: p.coords.altitude }),
    e => onError?.(e),
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 },
  );
  return () => navigator.geolocation.clearWatch(id);
}

/* --------------------------------------------------------------- search */
export async function searchPlaces(api, text, limit = 5) {
  const res = await api('/geo/search', { method: 'POST', body: { text, limit } });
  return res.results || [];
}

export async function reverseGeocode(api, lat, lon) {
  return api(`/geo/reverse?lat=${lat}&lon=${lon}`);
}

export async function routeTo(api, farmId, from, mode = 'drive') {
  const qs = new URLSearchParams({ mode });
  if (from) { qs.set('from_lat', from.lat); qs.set('from_lon', from.lon); }
  return api(`/geo/directions/${farmId}?${qs.toString()}`);
}

/* A compact location picker: click or drag the pin, or use the device GPS.
 * Calls onPick({lat, lon}) whenever the pin moves. */
export function locationPicker(node, META, { initial = null, onPick } = {}) {
  const start = initial || { lat: 18.8712, lon: 73.9123 };
  const map = createMap(node, { center: [start.lat, start.lon], zoom: initial ? 14 : 11 });
  addTiles(map, META);
  let marker = null;

  const setPin = (lat, lon, notify = true) => {
    if (marker) map.removeLayer(marker);
    marker = L().marker([lat, lon], { draggable: true, icon: farmIcon() }).addTo(map);
    marker.on('dragend', () => {
      const p = marker.getLatLng();
      onPick?.({ lat: p.lat, lon: p.lng });
    });
    if (notify) onPick?.({ lat, lon });
  };

  map.on('click', e => setPin(e.latlng.lat, e.latlng.lng));
  if (initial) setPin(initial.lat, initial.lon, false);

  return {
    map,
    setPin,
    async useDevice() {
      const pos = await currentPosition();
      map.setView([pos.lat, pos.lon], 16);
      setPin(pos.lat, pos.lon);
      return pos;
    },
    showResults(results) {
      const group = L().layerGroup().addTo(map);
      for (const r of results) {
        if (r.latitude == null) continue;
        const mk = L().marker([r.latitude, r.longitude], { icon: dotIcon('#0ea5e9', 12) })
          .bindTooltip(r.formatted || '')
          .on('click', () => {
            map.setView([r.latitude, r.longitude], 15);
            setPin(r.latitude, r.longitude);
          });
        group.addLayer(mk);
      }
      if (results[0]?.latitude != null) map.fitBounds(group.getBounds(), { padding: [30, 30], maxZoom: 15 });
      return group;
    },
  };
}
