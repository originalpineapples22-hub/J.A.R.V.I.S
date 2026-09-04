/* Always-on listener — records only real speech (energy VAD) and transcribes it
   with Whisper on the server, so it never invents words you didn't say.
   Wake word opens Call Mode; sleep phrase closes it. */
(function () {
  const $ = s => document.querySelector(s);
  const L = {
    on: false, ctx: null, analyser: null, rec: null, chunks: [], speaking: false,
    since: 0, silence: 0, raf: 0, stream: null, busy: false, floor: 0.012,
    wake: 'osama', sleep: 'all done sleep'
  };
  const TOKEN = () => window.TOKEN || localStorage.getItem('jarvis_token') || '';

  function norm(t) { return (t || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim(); }
  function hasWake(t) {
    const n = norm(t);
    // tolerate Whisper hearing "osama"/"o sama"/"usama"/"osamah"
    return /\b(o\s?sama|osamah|usama|ousama|asama)\b/.test(n) || n.includes(L.wake);
  }
  function stripWake(t) {
    const n = norm(t);
    const m = n.match(/\b(?:o\s?sama|osamah|usama|ousama|asama)\b[\s,.!?]*(.*)/);
    return (m ? m[1] : n).trim();
  }
  function hasSleep(t) {
    const n = norm(t);
    return n.includes('all done sleep') || n.includes('all done, sleep') || /\ball done\b.*\bsleep\b/.test(n) || n.includes('go to sleep') || n.includes('stand down');
  }
  function status(t) { const e = $('#listen-state'); if (e) e.textContent = t; }

  async function start() {
    if (L.on) return;
    try {
      L.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) { status('mic blocked'); return; }
    L.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = L.ctx.createMediaStreamSource(L.stream);
    L.analyser = L.ctx.createAnalyser(); L.analyser.fftSize = 512; src.connect(L.analyser);
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
               : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : '';
    L.mime = mime;
    L.on = true; document.body.classList.add('listening');
    status('listening'); loop();
  }
  function stop() {
    L.on = false; cancelAnimationFrame(L.raf);
    try { L.rec && L.rec.state === 'recording' && L.rec.stop(); } catch (_) {}
    if (L.stream) { L.stream.getTracks().forEach(t => t.stop()); L.stream = null; }
    if (L.ctx) { try { L.ctx.close(); } catch (_) {} L.ctx = null; }
    document.body.classList.remove('listening');
    status('off');
  }

  function beginClip() {
    if (L.rec && L.rec.state === 'recording') return;
    try {
      L.chunks = [];
      L.rec = new MediaRecorder(L.stream, L.mime ? { mimeType: L.mime } : undefined);
      L.rec.ondataavailable = e => e.data.size && L.chunks.push(e.data);
      L.rec.onstop = () => sendClip();
      L.rec.start();
      L.since = performance.now();
    } catch (_) {}
  }
  function endClip() { try { L.rec && L.rec.state === 'recording' && L.rec.stop(); } catch (_) {} }

  async function sendClip() {
    const dur = performance.now() - L.since;
    const blob = new Blob(L.chunks, { type: L.mime || 'audio/webm' });
    L.chunks = [];
    if (dur < 400 || blob.size < 3000 || L.busy) return;   // too short to be speech
    L.busy = true; status('…');
    try {
      const fd = new FormData(); fd.append('file', blob, 'clip.webm');
      const r = await fetch('/api/transcribe', { method: 'POST', headers: { 'X-JARVIS-TOKEN': TOKEN() }, body: fd });
      const { text } = await r.json();
      if (text) handle(text);
    } catch (_) {}
    L.busy = false; status(L.on ? 'listening' : 'off');
  }

  function handle(text) {
    const inCall = !$('#call').classList.contains('hidden');
    const cap = $('#listen-heard'); if (cap) cap.textContent = '“' + text + '”';
    if (hasSleep(text)) {
      if (window.speak) window.speak('Going to sleep, sir.');
      if (inCall && window.endCall) window.endCall();
      return;
    }
    if (inCall) { if (window.callSubmit) window.callSubmit(text); return; }
    if (hasWake(text)) {
      const cmd = stripWake(text);
      if (window.openCall) window.openCall();
      if (cmd) setTimeout(() => window.callSubmit && window.callSubmit(cmd), 400);
    }
  }

  function loop() {
    if (!L.on) return;
    L.raf = requestAnimationFrame(loop);
    const buf = new Uint8Array(L.analyser.fftSize);
    L.analyser.getByteTimeDomainData(buf);
    let sum = 0; for (const v of buf) { const x = (v - 128) / 128; sum += x * x; }
    const rms = Math.sqrt(sum / buf.length);
    const bar = $('#listen-bar'); if (bar) bar.style.width = Math.min(100, rms * 600) + '%';
    const speakingNow = rms > L.floor;
    const now = performance.now();
    if (speakingNow) {
      L.silence = now;
      if (!L.speaking) { L.speaking = true; beginClip(); }
      if (now - L.since > 14000) { endClip(); L.speaking = false; }   // hard cap
    } else if (L.speaking && now - L.silence > 900) {                  // 0.9s of quiet ends the clip
      L.speaking = false; endClip();
    }
  }

  window.Listener = { start, stop, get on() { return L.on; } };
  document.addEventListener('DOMContentLoaded', () => {
    const t = $('#always-listen');
    if (t) t.onchange = e => { e.target.checked ? start() : stop(); const c = $('#ear-chip'); if (c) { c.textContent = e.target.checked ? 'EAR ON' : 'EAR OFF'; c.classList.toggle('off', !e.target.checked); } };
  });
})();
