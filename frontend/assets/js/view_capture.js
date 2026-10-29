/* AgroSphere — live capture: camera, video, drone feed and real-time AI analysis.
 *
 * A farmer points a phone at a crop; a drone operator streams a sweep. Either
 * way a frame is geotagged and posted to /api/ai/analyze-frame, which returns a
 * preliminary disease assessment the operator can attach to a case.
 */
import { api, el, chip, toast, fmtDate, titleCase, modal, field, input, select, emptyState, moduleHero, SEV_TONE, pct } from './core.js';
import { ctx } from './context.js';
import {
  hasCamera, startCamera, stopStream, grabFrame, startRecording,
  createSimulatedDroneFeed, toThumb,
} from './capture.js';
import { currentPosition, dotIcon, createMap, addTiles, drawFarm } from './maps.js';

export async function viewCapture(root) {
  root.appendChild(moduleHero({
    image: 'module_crop_health', tag: 'Real-time AI',
    title: 'Live capture & instant crop analysis',
    body: 'Capture a photo or video from a phone or a drone, tag it with the exact field location, and get a preliminary disease assessment in your language within seconds.',
  }));

  let farms = [];
  try { farms = await api('/farms'); } catch (e) { toast(e.message, 'error'); }
  const allFields = farms.flatMap(f => (f.fields || []).map(x => ({ ...x, farmName: f.name })));

  const deviceSel = select('device', [
    { value: 'phone', label: '📱 Phone camera' },
    { value: 'drone', label: '✈ Drone feed' },
  ]);
  const fieldSel = select('field', [{ value: '', label: '— no field (analysis only) —' },
    ...allFields.map(f => ({ value: f.id, label: `${f.farmName} · ${f.name} (${f.crop})` }))]);
  const cropInput = input('crop', { placeholder: 'Crop (e.g. wheat, cotton, tomato)' });
  const obsInput = el('textarea', { name: 'observations', placeholder: 'What do you see? Colour, pattern, which part of the plant, how much of the field…' });
  const langSel = select('language', (ctx.META?.languages || []).map(l => ({ value: l.code, label: `${l.native} — ${l.name}` })));
  langSel.value = ctx.ME?.language || 'en';

  // ---- stage ----------------------------------------------------------- //
  const stage = el('div', { class: 'cam-stage' });
  const overlay = el('div', { class: 'cam-overlay' });
  const video = el('video', { autoplay: '', muted: '', playsinline: '' });
  const droneCanvas = el('canvas', { width: 960, height: 600 });
  droneCanvas.style.display = 'none';
  const placeholder = el('div', { class: 'cam-placeholder' }, 'Camera is off. Start the camera or the drone feed.');
  stage.append(video, droneCanvas, overlay, placeholder);

  const controls = el('div', { class: 'cam-controls' });
  const thumbs = el('div', { class: 'thumb-strip' });
  const analysisPane = el('div', {});

  let stream = null, drone = null, recording = null, frames = [];
  let liveSessionId = null, geoFix = null;

  function setOverlay(...badges) { overlay.replaceChildren(...badges.filter(Boolean)); }
  function badge(text, cls = '') { return el('span', { class: `cam-badge ${cls}` }, text); }

  function currentSourceEl() {
    return deviceSel.value === 'drone' ? droneCanvas : video;
  }

  async function captureFix() {
    try { geoFix = await currentPosition(); return geoFix; }
    catch { geoFix = null; return null; }
  }

  function syncControls() {
    const isDrone = deviceSel.value === 'drone';
    controls.replaceChildren();
    if (isDrone) {
      controls.append(
        el('button', { class: 'btn', onclick: startDroneFeed }, '▶ Start drone feed'),
        el('button', { class: 'btn ghost', onclick: stopDroneFeed }, '⏹ Stop feed'),
        el('button', { class: 'btn gold', onclick: () => analyseFrame('drone') }, '✦ Analyse frame'),
      );
    } else {
      controls.append(
        el('button', { class: 'btn', onclick: startPhoneCamera }, '📷 Start camera'),
        el('button', { class: 'btn ghost', onclick: switchCamera }, '🔄 Flip camera'),
        el('button', { class: 'btn gold', onclick: () => analyseFrame('phone') }, '✦ Capture & analyse'),
        el('button', { class: 'btn ghost', onclick: toggleRecording }, '⏺ Record video'),
        el('button', { class: 'btn ghost', onclick: stopPhoneCamera }, '⏹ Stop'),
      );
    }
    placeholder.style.display = 'none';
  }

  // ---- phone camera ---------------------------------------------------- //
  let facing = 'environment';
  async function startPhoneCamera() {
    try {
      stream = await startCamera(video, { facing });
      video.style.display = 'block'; droneCanvas.style.display = 'none';
      setOverlay(badge('Phone camera', 'live'), badge(facing === 'environment' ? 'Rear' : 'Front'));
      await captureFix();
      await ensureLiveSession('phone');
      toast('Camera started');
    } catch (e) { toast(e.message, 'error'); }
  }
  async function switchCamera() {
    facing = facing === 'environment' ? 'user' : 'environment';
    if (stream) { stopStream(stream); await startPhoneCamera(); }
  }
  function stopPhoneCamera() {
    stopStream(stream); stream = null;
    video.style.display = 'none'; placeholder.style.display = 'grid';
    setOverlay();
    if (recording) { recording = null; }
    toast('Camera stopped');
  }

  async function toggleRecording() {
    if (!stream) return toast('Start the camera first', 'error');
    if (recording) {
      const blob = await recording.stop();
      recording = null;
      const url = URL.createObjectURL(blob);
      const a = el('a', { href: url, download: `agrosphere-clip-${Date.now()}.webm`, class: 'btn ghost sm' }, '⬇ Download clip');
      controls.appendChild(a);
      a.click();
      toast('Recording saved');
      return;
    }
    try {
      recording = startRecording(stream);
      setOverlay(badge('Phone camera', 'live'), badge('● Recording', 'live'));
      toast('Recording…');
    } catch (e) { toast(e.message, 'error'); }
  }

  // ---- drone feed ------------------------------------------------------ //
  async function startDroneFeed() {
    const field = allFields.find(f => f.id === fieldSel.value) || allFields[0];
    if (!field) return toast('Register a farm and field first', 'error');
    stopPhoneCamera();
    video.style.display = 'none'; droneCanvas.style.display = 'block';
    drone = createSimulatedDroneFeed(droneCanvas, { field });
    setOverlay(badge('Drone feed (simulated)', 'live'), badge(field.name));
    await ensureLiveSession('drone');
    toast('Drone feed started (simulated sweep)');
  }
  function stopDroneFeed() {
    drone?.stop(); drone = null;
    droneCanvas.style.display = 'none'; placeholder.style.display = 'grid';
    setOverlay();
    toast('Drone feed stopped');
  }

  // ---- live session ---------------------------------------------------- //
  async function ensureLiveSession(device) {
    if (liveSessionId) return liveSessionId;
    try {
      const s = await api('/live-sessions', { method: 'POST', body: {
        device, field_id: fieldSel.value || null,
        farm_id: allFields.find(f => f.id === fieldSel.value)?.farm_id || null,
        notes: 'Live capture from the field',
      } });
      liveSessionId = s.id;
    } catch (e) { console.warn(e); }
    return liveSessionId;
  }

  // ---- analysis -------------------------------------------------------- //
  async function analyseFrame(device) {
    const source = currentSourceEl();
    let image;
    try { image = grabFrame(source, { maxWidth: 960, quality: 0.72 }); }
    catch { return toast('Nothing to capture yet — start the camera or feed first', 'error'); }

    const fix = geoFix || (drone ? drone.position() : null) || (await captureFix());
    const crop = cropInput.value || allFields.find(f => f.id === fieldSel.value)?.crop || 'crop';

    analysisPane.replaceChildren(el('div', { class: 'skeleton', style: 'height:120px' }));
    try {
      const res = await api('/ai/analyze-frame', { method: 'POST', body: {
        image, crop, observations: obsInput.value, language: langSel.value,
        latitude: fix?.lat ?? null, longitude: fix?.lon ?? null, device,
        field_id: fieldSel.value || null, save_media: Boolean(fieldSel.value),
      } });
      const a = res.analysis;
      frames.unshift({ image, analysis: a, at: new Date().toISOString(), fix });
      renderThumbs();
      renderAnalysis(a, res, fix);
      if (liveSessionId) {
        api(`/live-sessions/${liveSessionId}`, { method: 'PATCH', body: {
          latitude: fix?.lat ?? null, longitude: fix?.lon ?? null, frames: 1, geotagged_frames: fix ? 1 : 0,
        } }).catch(() => {});
      }
      toast(a.mode === 'live' ? 'AI assessment ready' : 'Assessment ready (labelled simulator)');
    } catch (e) {
      analysisPane.replaceChildren(el('div', { class: 'alert danger' }, e.message));
    }
  }

  function renderThumbs() {
    thumbs.replaceChildren(...frames.slice(0, 8).map((f, i) =>
      el('img', { class: `thumb${i === 0 ? ' active' : ''}`, src: f.image, title: f.analysis.findings?.[0]?.label || 'frame',
        onclick: () => renderAnalysis(f.analysis, { media_id: null }, f.fix) })));
  }

  function renderAnalysis(a, res, fix) {
    const modeChip = chip(a.mode === 'live' ? 'LIVE AI' : a.mode === 'simulated' ? 'SIMULATED' : 'FALLBACK',
      a.mode === 'live' ? 'green' : 'gold');
    const cards = (a.findings || []).map(f => el('div', { class: 'finding-card' },
      el('div', { class: 'head' }, el('b', {}, f.label), el('div', {}, chip(titleCase(f.severity), SEV_TONE[f.severity] || 'grey'), ' ', chip(pct(f.confidence), 'blue'))),
      f.evidence ? el('div', { class: 'ev' }, f.evidence) : null,
      f.alternative ? el('div', { class: 'alt' }, `Alternative: ${f.alternative}`) : null,
    ));
    analysisPane.replaceChildren(
      el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px' },
        modeChip, chip(`uncertainty ${pct(a.uncertainty)}`, 'grey'),
        res?.media_id ? chip('saved to field', 'green') : null),
      a.summary ? el('p', { style: 'font-size:.88rem' }, a.summary) : null,
      fix ? el('div', { class: 'geo-line' }, `📍 ${fix.lat.toFixed(5)}, ${fix.lon.toFixed(5)}`) : el('div', { class: 'geo-line' }, '📍 location unavailable'),
      ...cards,
      el('div', { class: 'alert warn' }, 'Preliminary only. A qualified agronomist must confirm before treatment.'),
      el('div', { class: 'cam-controls' },
        el('button', { class: 'btn gold sm', onclick: () => draftTreatment(a.findings?.[0]?.label) }, '✦ Draft treatment plan'),
        el('button', { class: 'btn ghost sm', onclick: () => saveAsCase(a, fix) }, '❧ Open a case from this'),
      ),
    );
  }

  async function draftTreatment(problem) {
    if (!problem) return toast('No finding to draft from', 'error');
    const m = modal({ title: 'AI treatment draft', body: el('div', { class: 'skeleton', style: 'height:160px' }),
      wide: true, footer: [el('button', { class: 'btn ghost', onclick: () => m.close() }, 'Close')] });
    try {
      const d = await api('/ai/treatment-draft', { method: 'POST', body: {
        problem, crop: cropInput.value || 'crop', severity: 'medium', language: langSel.value } });
      m.box.querySelector('.modal-body').replaceChildren(el('div', {},
        el('div', { style: 'display:flex;gap:8px;margin-bottom:10px' }, chip(d.mode === 'live' ? 'LIVE AI' : 'TEMPLATE', d.mode === 'live' ? 'green' : 'gold')),
        el('div', { class: 'kv' },
          el('dt', {}, 'Problem'), el('dd', {}, d.problem || '—'),
          el('dt', {}, 'Product'), el('dd', {}, d.product || '—'),
          el('dt', {}, 'Active ingredient'), el('dd', {}, d.active_ingredient || '—'),
          el('dt', {}, 'Dosage'), el('dd', {}, d.dosage || '—'),
          el('dt', {}, 'Pre-harvest interval'), el('dd', {}, d.pre_harvest_interval || '—'),
          el('dt', {}, 'Re-entry'), el('dd', {}, d.re_entry_interval || '—'),
          el('dt', {}, 'PPE'), el('dd', {}, d.ppe || '—'),
          el('dt', {}, 'Weather'), el('dd', {}, d.weather_restrictions || '—')),
        el('h4', { style: 'margin:12px 0 6px' }, 'Measures'),
        el('ul', { class: 'guidance-list' }, ...(d.measures || []).map(x => el('li', {}, x))),
        el('div', { class: 'alert warn', style: 'margin-top:12px' }, 'An agronomist must review and approve this draft before it becomes a plan.'),
      ));
    } catch (e) { m.box.querySelector('.modal-body').replaceChildren(el('div', { class: 'alert danger' }, e.message)); }
  }

  async function saveAsCase(a, fix) {
    const fieldId = fieldSel.value;
    if (!fieldId) return toast('Select a field to open a case', 'error');
    try {
      const c = await api('/cases', { method: 'POST', body: {
        field_id: fieldId, title: a.findings?.[0]?.label || 'Field capture',
        observations: obsInput.value || a.summary, severity: a.findings?.[0]?.severity || 'unknown' } });
      toast(`Case ${c.reference} created`); navigateTo('cases');
    } catch (e) { toast(e.message, 'error'); }
  }

  // ---- layout ---------------------------------------------------------- //
  const setup = el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Capture setup')),
    el('div', { class: 'grid c2' }, field('Device', deviceSel), field('Field', fieldSel)),
    el('div', { class: 'grid c2' }, field('Crop', cropInput), field('Analysis language', langSel)),
    field('Observations', obsInput),
    el('div', { class: 'alert info' }, 'Only still frames you analyse leave your device. Video stays on the phone unless you download it.'),
  );

  const stageCard = el('div', { class: 'card' }, stage, controls, thumbs);
  const analysisCard = el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Real-time AI assessment')), analysisPane);

  root.appendChild(el('div', { class: 'capture-grid' }, el('div', {}, stageCard), el('div', {}, setup, analysisCard)));

  deviceSel.addEventListener('change', () => { syncControls(); });
  fieldSel.addEventListener('change', () => {
    const f = allFields.find(x => x.id === fieldSel.value);
    if (f) cropInput.value = f.crop;
  });
  syncControls();
  placeholder.style.display = 'grid';

  // Live sessions list.
  let sessions = [];
  try { sessions = await api('/live-sessions'); } catch {}
  const sessCard = el('div', { class: 'card', style: 'margin-top:16px' },
    el('div', { class: 'card-head' }, el('h3', { class: 'grow' }, 'Recent capture sessions')));
  if (!sessions.length) sessCard.appendChild(el('div', { class: 'alert' }, 'No capture sessions yet.'));
  else {
    const tbl = el('table', { class: 'table' });
    tbl.appendChild(el('thead', {}, el('tr', {}, el('th', {}, 'Device'), el('th', {}, 'Status'), el('th', {}, 'Frames'), el('th', {}, 'Geotagged'), el('th', {}, 'Started'))));
    const tb = el('tbody');
    for (const s of sessions.slice(0, 10)) {
      tb.appendChild(el('tr', {}, el('td', {}, chip(s.device === 'drone' ? '✈ Drone' : '📱 Phone', s.device === 'drone' ? 'gold' : 'blue')),
        el('td', {}, chip(titleCase(s.status), s.status === 'live' ? 'green' : 'grey')),
        el('td', {}, s.frames), el('td', {}, s.geotagged_frames),
        el('td', { style: 'color:var(--text-3);font-size:.8rem' }, fmtDate(s.started_at))));
    }
    tbl.appendChild(tb); sessCard.appendChild(tbl);
  }
  root.appendChild(sessCard);
}

function navigateTo(r) { location.hash = r; }
