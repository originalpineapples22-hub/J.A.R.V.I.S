/* Face and voice recognition — 0.5.4.M.4 knowing its operator.
   Face: 128-d descriptors from face-api.js, computed in the browser.
   Voice: a spectral fingerprint from the Web Audio API.
   Only the numbers are stored — never a photo or a recording. */
(function () {
  const $ = s => document.querySelector(s);
  const TOKEN = () => window.TOKEN || localStorage.getItem('jarvis_token') || '';
  const api = (p, body) => fetch(p, {method: body ? 'POST' : 'GET',
      headers: {'Content-Type': 'application/json', 'X-JARVIS-TOKEN': TOKEN()},
      body: body ? JSON.stringify(body) : undefined}).then(r => r.json());

  const ID = {faceReady: false, stream: null, lastGreet: 0};
  function say(msg) { const el = $('#id-status'); if (el) el.textContent = msg; }

  /* ---------- FACE ---------- */
  async function loadFaceModels() {
    if (ID.faceReady) return true;
    say('loading face models…');
    try {
      if (!window.faceapi) {
        await new Promise((res, rej) => {
          const s = document.createElement('script');
          s.src = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/dist/face-api.js';
          s.onload = res; s.onerror = rej; document.head.appendChild(s);
        });
      }
      const M = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model';
      await faceapi.nets.tinyFaceDetector.loadFromUri(M);
      await faceapi.nets.faceLandmark68Net.loadFromUri(M);
      await faceapi.nets.faceRecognitionNet.loadFromUri(M);
      ID.faceReady = true; say('face models ready'); return true;
    } catch (e) { say('could not load face models: ' + e.message); return false; }
  }

  async function camera() {
    if (ID.stream) return ID.stream;
    ID.stream = await navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480, facingMode: 'user'}});
    const v = $('#id-cam'); v.srcObject = ID.stream; await v.play();
    return ID.stream;
  }
  function stopCamera() { if (ID.stream) { ID.stream.getTracks().forEach(t => t.stop()); ID.stream = null; } }

  async function faceVector() {
    const v = $('#id-cam');
    const det = await faceapi.detectSingleFace(v, new faceapi.TinyFaceDetectorOptions())
      .withFaceLandmarks().withFaceDescriptor();
    return det ? Array.from(det.descriptor) : null;
  }

  async function enrolFace() {
    if (!(await loadFaceModels())) return;
    $('#id-panel').hidden = false;
    await camera();
    for (let i = 1; i <= 5; i++) {
      say(`look at the camera — capturing ${i}/5 (move slightly between shots)`);
      await new Promise(r => setTimeout(r, 1200));
      const vec = await faceVector();
      if (!vec) { say('no face detected — move into the light and try again'); i--; continue; }
      await api('/api/identity/enrol', {kind: 'face', vector: vec});
    }
    say('✅ face enrolled — I will know you now, sir.');
    stopCamera(); refreshCounts();
  }

  async function verifyFace(quiet) {
    if (!(await loadFaceModels())) return null;
    $('#id-panel').hidden = false;
    await camera();
    await new Promise(r => setTimeout(r, 900));
    const vec = await faceVector();
    if (!vec) { say('no face detected'); stopCamera(); return null; }
    const res = await api('/api/identity/verify', {kind: 'face', vector: vec});
    say((res.known ? '✅ ' : '⚠️ ') + res.message + ` (score ${res.score})`);
    if (!quiet && window.speak) window.speak(res.known ? 'Welcome back, sir.' : 'I do not recognise you.');
    stopCamera(); return res;
  }

  /* ---------- VOICE ---------- */
  async function voiceVector(seconds = 3) {
    say('speak normally for ' + seconds + ' seconds…');
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    const an = ctx.createAnalyser(); an.fftSize = 2048; src.connect(an);
    const bins = new Uint8Array(an.frequencyBinCount);
    const BANDS = 32, acc = new Float64Array(BANDS); let frames = 0;
    const t0 = performance.now();
    await new Promise(res => {
      (function tick() {
        an.getByteFrequencyData(bins);
        let energy = 0; for (const b of bins) energy += b;
        if (energy > 2000) {                       // only count frames with actual speech
          const per = Math.floor(bins.length / BANDS);
          for (let i = 0; i < BANDS; i++) {
            let s = 0; for (let j = 0; j < per; j++) s += bins[i * per + j];
            acc[i] += s / per;
          }
          frames++;
        }
        if (performance.now() - t0 < seconds * 1000) requestAnimationFrame(tick); else res();
      })();
    });
    stream.getTracks().forEach(t => t.stop()); ctx.close();
    if (frames < 10) { say('I heard almost nothing — try again, closer to the microphone.'); return null; }
    const vec = Array.from(acc).map(x => x / frames);
    const max = Math.max(...vec) || 1;
    return vec.map(x => x / max);                  // normalised spectral fingerprint
  }

  async function enrolVoice() {
    $('#id-panel').hidden = false;
    for (let i = 1; i <= 3; i++) {
      say(`voice sample ${i}/3 — say: "Zero five four M four, this is my voice."`);
      const v = await voiceVector(3);
      if (!v) { i--; continue; }
      await api('/api/identity/enrol', {kind: 'voice', vector: v});
      await new Promise(r => setTimeout(r, 600));
    }
    say('✅ voice enrolled, sir.'); refreshCounts();
  }

  async function verifyVoice() {
    $('#id-panel').hidden = false;
    const v = await voiceVector(3);
    if (!v) return null;
    const res = await api('/api/identity/verify', {kind: 'voice', vector: v});
    say((res.known ? '✅ ' : '⚠️ ') + res.message + ` (score ${res.score})`);
    return res;
  }

  /* ---------- greet on camera use ---------- */
  async function greetIfOwner() {
    if (Date.now() - ID.lastGreet < 300000) return;
    const st = await api('/api/identity');
    if (!st.face_samples) return;
    ID.lastGreet = Date.now();
    const res = await verifyFace(true);
    if (res && res.known && window.speak) window.speak(`Welcome back, ${st.name}.`);
  }

  async function refreshCounts() {
    try {
      const st = await api('/api/identity');
      const el = $('#id-counts');
      if (el) el.textContent = `face: ${st.face_samples} · voice: ${st.voice_samples}` +
        (st.name && st.name !== 'sir' ? ` · knows you as ${st.name}` : '');
    } catch (_) {}
  }

  document.addEventListener('DOMContentLoaded', () => {
    const bind = (id, fn) => { const b = $(id); if (b) b.onclick = fn; };
    bind('#id-enrol-face', enrolFace);
    bind('#id-verify-face', () => verifyFace(false));
    bind('#id-enrol-voice', enrolVoice);
    bind('#id-verify-voice', verifyVoice);
    bind('#id-close', () => { stopCamera(); $('#id-panel').hidden = true; });
    refreshCounts();
  });
  window.Identity = {enrolFace, verifyFace, enrolVoice, verifyVoice, greetIfOwner};
})();
