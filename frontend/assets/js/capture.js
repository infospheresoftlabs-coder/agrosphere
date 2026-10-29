/* AgroSphere — live capture: phone camera, video recording and drone feed.
 *
 * Everything here runs in the browser. Frames are grabbed from a <video>
 * element, downscaled on a canvas and geotagged before being sent for
 * analysis. No video is uploaded; only individual still frames the user
 * chooses to analyse leave the device.
 */

export const hasCamera = () => Boolean(navigator.mediaDevices?.getUserMedia);

/* Start a camera stream. `facing` lets a farmer switch to the rear camera,
 * which is the one pointing at the crop. */
export async function startCamera(videoEl, { facing = 'environment', audio = false } = {}) {
  if (!hasCamera()) throw new Error('This device or browser does not expose a camera.');
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: facing, width: { ideal: 1280 }, height: { ideal: 720 } },
    audio,
  });
  videoEl.srcObject = stream;
  videoEl.setAttribute('playsinline', '');
  await videoEl.play().catch(() => {});
  return stream;
}

export function stopStream(stream) {
  stream?.getTracks?.().forEach(t => t.stop());
}

/* Grab a still from the video element, downscaled so the upload stays small. */
export function grabFrame(videoEl, { maxWidth = 960, quality = 0.72 } = {}) {
  const vw = videoEl.videoWidth || 1280;
  const vh = videoEl.videoHeight || 720;
  const scale = Math.min(1, maxWidth / vw);
  const w = Math.round(vw * scale);
  const h = Math.round(vh * scale);
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  canvas.getContext('2d').drawImage(videoEl, 0, 0, w, h);
  return canvas.toDataURL('image/jpeg', quality);
}

/* Record a clip from the stream with MediaRecorder. Returns the recorder and a
 * stop() that resolves with the recorded Blob. */
export function startRecording(stream, { mimeType } = {}) {
  if (!window.MediaRecorder) throw new Error('Video recording is not supported in this browser.');
  const preferred = mimeType
    || ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4']
      .find(t => MediaRecorder.isTypeSupported?.(t));
  const rec = new MediaRecorder(stream, preferred ? { mimeType: preferred } : undefined);
  const chunks = [];
  rec.ondataavailable = e => { if (e.data?.size) chunks.push(e.data); };
  rec.start(1000);
  return {
    recorder: rec,
    stop: () => new Promise(resolve => {
      rec.onstop = () => resolve(new Blob(chunks, { type: rec.mimeType || 'video/webm' }));
      rec.stop();
    }),
  };
}

/* --------------------------------------------------------------- drone feed */
/* A drone feed is normally an HLS/WebRTC URL. Where none is configured the
 * platform renders a clearly-labelled simulated sweep so the rest of the
 * pipeline (geotagging, frame analysis) can be exercised end to end. */
export function createSimulatedDroneFeed(canvas, { field } = {}) {
  const ctx = canvas.getContext('2d');
  const ring = field?.boundary?.coordinates?.[0] || [];
  let t = 0, raf = null;

  const lons = ring.map(p => p[0]), lats = ring.map(p => p[1]);
  const bounds = ring.length ? {
    minLon: Math.min(...lons), maxLon: Math.max(...lons),
    minLat: Math.min(...lats), maxLat: Math.max(...lats),
  } : { minLon: 0, maxLon: 1, minLat: 0, maxLat: 1 };

  function draw() {
    const w = canvas.width, h = canvas.height;
    // Sweeping rows of "crop" with a moving scan line and a few stress patches.
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, '#2f7d4f'); grad.addColorStop(1, '#1c5233');
    ctx.fillStyle = grad; ctx.fillRect(0, 0, w, h);

    const rows = 22;
    for (let r = 0; r < rows; r++) {
      const y = (r / rows) * h;
      ctx.strokeStyle = 'rgba(255,255,255,.06)';
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    // Simulated disease patches, seeded by the field so they stay put.
    for (let i = 0; i < 5; i++) {
      const px = ((i * 137) % 100) / 100 * w;
      const py = ((i * 71) % 100) / 100 * h;
      const rad = 18 + (i % 3) * 12 + Math.sin(t / 22 + i) * 3;
      const g2 = ctx.createRadialGradient(px, py, 0, px, py, rad);
      g2.addColorStop(0, 'rgba(214,158,46,.55)');
      g2.addColorStop(1, 'rgba(214,158,46,0)');
      ctx.fillStyle = g2; ctx.beginPath(); ctx.arc(px, py, rad, 0, Math.PI * 2); ctx.fill();
    }
    // Scan line.
    const sy = ((t * 2.2) % (h + 60)) - 30;
    ctx.strokeStyle = 'rgba(120,240,180,.75)';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(w, sy); ctx.stroke();

    ctx.fillStyle = 'rgba(255,255,255,.85)';
    ctx.font = '600 13px Inter, system-ui, sans-serif';
    ctx.fillText('SIMULATED DRONE FEED — not a real flight', 12, 22);
    ctx.font = '12px Inter, system-ui, sans-serif';
    ctx.fillStyle = 'rgba(255,255,255,.7)';
    ctx.fillText(`alt ${(4 + Math.sin(t / 30)).toFixed(1)} m · ${(3.4 + Math.cos(t / 25) * 0.6).toFixed(1)} m/s`, 12, 40);
    t += 1;
    raf = requestAnimationFrame(draw);
  }
  draw();
  return {
    stop() { if (raf) cancelAnimationFrame(raf); raf = null; },
    /* Where the drone currently is, as a fraction across the field boundary. */
    position() {
      const f = (Math.sin(t / 60) + 1) / 2;
      return {
        lat: bounds.minLat + (bounds.maxLat - bounds.minLat) * f,
        lon: bounds.minLon + (bounds.maxLon - bounds.minLon) * ((Math.cos(t / 70) + 1) / 2),
      };
    },
  };
}

/* Downscale an <img> or canvas to a data URL, used for thumbnails in the UI. */
export function toThumb(source, maxWidth = 320, quality = 0.7) {
  const canvas = document.createElement('canvas');
  const sw = source.naturalWidth || source.width;
  const sh = source.naturalHeight || source.height;
  const scale = Math.min(1, maxWidth / sw);
  canvas.width = Math.round(sw * scale);
  canvas.height = Math.round(sh * scale);
  canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', quality);
}
