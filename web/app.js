/* J.A.R.V.I.S. Command Center — single-screen client */
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const store = {get: k => { try { return localStorage.getItem(k); } catch (_) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} }};
let TOKEN = store.get('jarvis_token') || ''; window.TOKEN = TOKEN;
const H = () => ({'Content-Type': 'application/json', 'X-JARVIS-TOKEN': TOKEN});
const api = async (path, opts = {}) => { const r = await fetch(path, Object.assign({headers: H()}, opts)); if (r.status === 401) { openSettings('Enter your access token to authenticate.'); throw new Error('unauthorized'); } return r.json(); };

/* ---------------- clock */
setInterval(() => { const d = new Date(); $('#time').textContent = d.toLocaleTimeString('en-GB'); $('#date').textContent = d.toLocaleDateString('en-GB', {weekday: 'long', day: '2-digit', month: 'long', year: 'numeric'}); }, 1000);

/* ---------------- speech out */
window.speak = function(t){ return speak(t); };
function speak(text) {
  if (!('speechSynthesis' in window) || !text) return;
  const clean = text.replace(/```[\s\S]*?```/g, ' code omitted ').replace(/[*_#`>\[\]|]/g, '').slice(0, 600);
  const u = new SpeechSynthesisUtterance(clean); u.rate = 1.02; u.pitch = 0.95;
  const vs = speechSynthesis.getVoices();
  u.voice = vs.find(v => /en-GB/i.test(v.lang) && /daniel|george|ryan|male/i.test(v.name)) || vs.find(v => /en-GB/i.test(v.lang)) || vs.find(v => /^en/i.test(v.lang)) || null;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}

/* ---------------- chat */
const chat = $('#chat'), hero = $('#hero');
function addMsg(role, text) { const d = document.createElement('div'); d.className = 'msg ' + role; d.textContent = text; chat.appendChild(d); chat.scrollTop = chat.scrollHeight; hero.classList.add('chatting'); return d; }
function render(el, text) { el.innerHTML = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/```(\w+)?\n([\s\S]*?)```/g, (m, l, c) => `<pre>${c}</pre>`).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>'); }
let ws, wsReady = false, current = null, busy = false;
function connect() {
  if (!TOKEN) return;
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/chat?token=' + encodeURIComponent(TOKEN));
  ws.onopen = () => { wsReady = true; $('#c-core').textContent = 'Active'; };
  ws.onclose = () => { wsReady = false; $('#c-core').textContent = 'Reconnecting…'; setTimeout(connect, 2500); };
  ws.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'token') { if (!current) current = addMsg('jarvis', ''); current._raw = (current._raw || '') + ev.text; render(current, current._raw); chat.scrollTop = chat.scrollHeight; if (call.open){ callBuf += ev.text; $('#call-caption').textContent = callBuf.slice(-240); } }
    else if (ev.type === 'tool') { addMsg('tool', `⚙ ${ev.name} ${JSON.stringify(ev.args).slice(0, 120)}`); markAgent(ev.name); }
    else if (ev.type === 'final') { if (!current) current = addMsg('jarvis', ''); render(current, ev.text); speak(ev.text); current = null; busy = false; $('#voice-state').textContent = 'Tap to talk'; refresh();
      if (call.open){ callWaiting=false; call.speaking=true; $('#orb').classList.add('speaking'); $('#call-status').textContent='speaking'; $('#call-caption').textContent = ev.text; callSpeak(ev.text); } }
    else if (ev.type === 'error') { addMsg('jarvis', '⚠ ' + ev.text); current = null; busy = false; }
  };
}
function send(text) {
  text = (text || '').trim(); if (!text || !wsReady) { if (!wsReady) openSettings('Not connected — check your access token and server.'); return; }
  addMsg('user', text); busy = true; $('#voice-state').textContent = 'Processing…'; current = null;
  ws.send(JSON.stringify({text, channel: 'web'}));
}
$('#composer').addEventListener('submit', e => { e.preventDefault(); send($('#prompt').value); $('#prompt').value = ''; });
$('#search').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.value.trim()) { send(e.target.value); e.target.value = ''; } });
$$('.quick button[data-cmd]').forEach(b => b.onclick = () => send(b.dataset.cmd));
$('#qc-learn').onclick = async () => { const t = prompt('Topic to master (e.g. Rust, Docker, React):'); if (t) { await api('/api/learn', {method: 'POST', body: JSON.stringify({topic: t})}); addMsg('jarvis', `Study session for ${t} started, sir. I'll notify you when it's complete.`); refresh(); } };
$('#qc-voice').onclick = () => $('#mic').click();
$('#qc-files').onclick = openFiles;

/* ---------------- speech in (tap to talk + optional always-listen with wake word) */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, always = false, listening = false;
function setupRec(continuous) {
  if (!SR) { $('#voice-state').textContent = 'Voice input unsupported here'; return null; }
  const r = new SR(); r.lang = 'en-US'; r.continuous = continuous; r.interimResults = false;
  r.onstart = () => { listening = true; $('#mic').classList.add('live'); $('#wave').classList.add('live'); $('#voice-state').textContent = continuous ? 'Listening — say "Jarvis, …"' : 'Listening…'; };
  r.onend = () => { listening = false; $('#mic').classList.remove('live'); $('#wave').classList.remove('live'); if (always) setTimeout(() => { try { r.start(); } catch (_) {} }, 300); else $('#voice-state').textContent = 'Tap to talk'; };
  r.onerror = e => { if (e.error === 'not-allowed') $('#voice-state').textContent = 'Mic blocked — allow microphone for this site'; };
  r.onresult = e => {
    const heard = e.results[e.results.length - 1][0].transcript.trim();
    if (!continuous) { send(heard); return; }
    const m = heard.match(/\b(jarvis|javis|jervis|travis|darvis)\b[\s,.!?]*(.*)/i);
    if (!m) return;
    const cmd = (m[2] || '').trim();
    if (!cmd) { speak('Yes, sir?'); return; }
    if (!busy) { speechSynthesis.cancel(); send(cmd); }
  };
  return r;
}
$('#mic').onclick = () => { if (always) return; if (listening) { rec && rec.stop(); return; } speechSynthesis.cancel(); rec = setupRec(false); try { rec && rec.start(); } catch (_) {} };


/* ---------------- dashboard refresh */
const agentEls = {}; let sparkHist = [];
function markAgent(tool) { const map = {web_search: 'Research Agent', youtube_transcript: 'Browser Agent', fetch_url: 'Browser Agent', create_file: 'Coding Agent', remember: 'Memory Agent', recall: 'Memory Agent', knowledge_lookup: 'Memory Agent', study_topic: 'Research Agent', add_task: 'Task Agent', set_reminder: 'Task Agent', list_tasks: 'Task Agent', complete_task: 'Task Agent'}; const a = map[tool] || 'System Agent'; const el = agentEls[a]; if (el) { el.classList.add('active'); el.querySelector('span').textContent = '● Active'; setTimeout(() => { el.classList.remove('active'); el.querySelector('span').textContent = '● Standby'; }, 6000); } }
function ring(k, v) { const el = document.querySelector(`.ring[data-k="${k}"]`); el.querySelector('.fg').style.strokeDashoffset = 213.6 - 213.6 * Math.min(v, 100) / 100; el.querySelector('b').textContent = Math.round(v) + '%'; el.querySelector('.fg').style.stroke = v > 85 ? 'var(--bad)' : v > 65 ? 'var(--warn)' : 'var(--cyan)'; }
async function refresh() {
  if (!TOKEN) return;
  let s; try { s = await api('/api/status'); } catch (_) { return; }
  $('#ver').textContent = 'v' + s.version; if (s.name) setName(s.name);
  ring('cpu', s.system.cpu); ring('ram', s.system.ram); ring('disk', s.system.disk);
  const stressed = s.system.cpu > 90 || s.system.ram > 90; $('#sys-word').textContent = stressed ? 'STRESSED' : 'OPTIMAL'; $('#sys-dot').style.background = stressed ? 'var(--warn)' : 'var(--ok)'; $('#c-sys').textContent = stressed ? 'Under load' : 'Optimal';
  $('#c-mem').textContent = `${s.memory.memories} memories · ${(s.rag && s.rag.available) ? 'semantic' : 'keyword'}`;
  $('#m-memories').textContent = s.memory.memories; $('#m-tasks').textContent = s.memory.tasks_open; $('#m-files').textContent = (s.files||[]).length; $('#m-turns').textContent = s.memory.messages;
  $('#nav-tasks').textContent = s.memory.tasks_open; $('#nav-convos').textContent = s.memory.messages; $('#nav-tools').textContent = s.agents.reduce((n, a) => n + a.tools.length, 0);
  sparkHist.push(s.memory.memories); if (sparkHist.length > 40) sparkHist.shift();
  const mx = Math.max(...sparkHist, 1), mn = Math.min(...sparkHist); $('#spark-line').setAttribute('points', sparkHist.map((v, i) => `${i * 200 / Math.max(sparkHist.length - 1, 1)},${58 - (v - mn) / Math.max(mx - mn, 1) * 50}`).join(' '));
  const learning = Object.entries(s.learning || {}); $('#c-agents').textContent = learning.length ? `${learning.length} studying (${learning.map(([t, v]) => `${t} ${v.done}/${v.total}`).join(', ')})` : `${s.agents.length} agents · standby`;
  $('#feed-list').innerHTML = s.events.map(e => `<li><i>${{learn: '📚', task: '☑', reminder: '⏰', file: '📦', alert: '⚠', briefing: '☀', system: '◎'}[e.kind] || '•'}</i><div>${e.text}<small>${e.ts}</small></div></li>`).join('') || '<li class="muted">Quiet for now.</li>';
  $('#agent-grid').innerHTML = ''; for (const a of s.agents) { const d = document.createElement('div'); d.className = 'agent'; d.innerHTML = `<b>${a.name}</b><span>● Standby</span>`; d.title = a.tools.join(', '); $('#agent-grid').appendChild(d); agentEls[a.name] = d; }
  $('#tl-list').innerHTML = [...s.reminders.map(r => `<li><span class="t">${r.when_ts.slice(5, 16)}</span>⏰ ${r.text}</li>`), ...s.tasks.map(t => `<li><span class="t">${t.due ? t.due.slice(5, 16) : 'open'}</span>${t.title}<button onclick="doneTask(${t.id})">done</button></li>`)].join('') || '<li class="muted">Nothing scheduled, sir.</li>';
  const p = s.providers || {}; const pool = p.pool || [];
  $('#llm-grid').innerHTML = pool.map(v => `<div class="llm ${v.connected ? 'on' : ''} ${p.active === v.id ? 'active' : ''}">
      <b>${v.name}</b><span>${v.cooldown ? 'cooling ' + v.cooldown + 's' : v.connected ? 'Connected' + (v.model ? ' · ' + v.model : '') : 'Free — not linked'}</span></div>`).join('');
  $('#llm-count').textContent = pool.filter(v => v.connected).length + ' Connected';
  $('#c-llm').textContent = `${p.tier || '—'} · ${p.model || p.active || 'none'}`;
  $('#c-voice').textContent = s.pc_online ? 'Browser + PC ear' : 'Browser';
  if (s.curriculum) { const cu = s.curriculum; const el = $('#c-study');
    if (el) el.textContent = cu.current ? `studying ${cu.current} · ${cu.learned}/${cu.total}` : `${cu.learned}/${cu.total} mastered (${cu.percent}%)`; }
  if (s.capability) { const cap = s.capability; $('#c-iq').textContent = `${cap.index}/1000 · ${cap.active_count}/${cap.total_count} systems`; window.CAP = cap; }
}
async function doneTask(id) { await api(`/api/tasks/${id}/done`, {method: 'POST'}); refresh(); }
$('#task-form').addEventListener('submit', async e => { e.preventDefault(); const v = $('#task-input').value.trim(); if (!v) return; await api('/api/tasks', {method: 'POST', body: JSON.stringify({title: v})}); $('#task-input').value = ''; refresh(); });
$$('#nav a, a.more[data-target]').forEach(a => a.onclick = () => { $$('#nav a').forEach(x => x.classList.remove('active')); a.classList.add('active'); const t = document.getElementById(a.dataset.target); if (t) { t.scrollIntoView({behavior: 'smooth', block: 'start'}); t.style.boxShadow = '0 0 30px rgba(56,230,255,.5)'; setTimeout(() => t.style.boxShadow = '', 1200); } });

/* ---------------- settings */
const modal = $('#modal');
function openSettings(msg) { modal.classList.remove('hidden'); $('#s-msg').textContent = msg || ''; $('#s-token').value = TOKEN; if (TOKEN) loadSettings(); }
async function loadSettings() { try { const s = await api('/api/settings'); $('#s-name').value = s.operator_name; $('#s-ai-name').value = s.assistant_name || ''; $('#s-ai-style').value = s.assistant_style || ''; $('#s-provider').value = s.provider; $('#s-groq').value = s.groq_api_key; $('#s-oai-url').value = s.openai_base_url; $('#s-oai-key').value = s.openai_api_key; $('#s-oai-model').value = s.openai_model; $('#s-ollama').value = s.ollama_url; $('#s-ollama-model').value = s.ollama_model; $('#s-tz').value = s.timezone; $('#s-brief').value = s.briefing_hour;
    $('#s-github').value = s.github_models_key || ''; $('#s-gemini').value = s.gemini_key || '';
    $('#s-cerebras').value = s.cerebras_key || ''; $('#s-openrouter').value = s.openrouter_key || '';
    $('#s-mistral').value = s.mistral_key || '';
    $('#s-tavily').value = s.tavily_key || ''; $('#s-wolfram').value = s.wolfram_appid || '';
    $('#s-eleven').value = s.elevenlabs_key || ''; $('#s-eleven-voice').value = s.elevenlabs_voice || '';
    $('#s-ha-url').value = s.homeassistant_url || ''; $('#s-ha-token').value = s.homeassistant_token || '';
    $('#s-hooks').value = s.webhooks || '{}'; const sel = $('#s-groq-model'); sel.innerHTML = '<option value="">Auto (best available)</option>' + (s.groq_models || []).map(m => `<option ${m === s.groq_model ? 'selected' : ''}>${m}</option>`).join(''); } catch (_) {} }
$('#btn-settings').onclick = () => openSettings(); $('#modal-close').onclick = () => modal.classList.add('hidden');
$('#s-save').onclick = async () => { TOKEN = $('#s-token').value.trim(); store.set('jarvis_token', TOKEN); window.TOKEN = TOKEN;
  try { await api('/api/settings', {method: 'POST', body: JSON.stringify({operator_name: $('#s-name').value, assistant_name: $('#s-ai-name').value, assistant_style: $('#s-ai-style').value, provider: $('#s-provider').value, groq_api_key: $('#s-groq').value, groq_model: $('#s-groq-model').value, openai_base_url: $('#s-oai-url').value, openai_api_key: $('#s-oai-key').value, openai_model: $('#s-oai-model').value, ollama_url: $('#s-ollama').value, ollama_model: $('#s-ollama-model').value, timezone: $('#s-tz').value, briefing_hour: parseInt($('#s-brief').value || '8'),
      github_models_key: $('#s-github').value, gemini_key: $('#s-gemini').value,
      cerebras_key: $('#s-cerebras').value, openrouter_key: $('#s-openrouter').value,
      mistral_key: $('#s-mistral').value, tavily_key: $('#s-tavily').value, wolfram_appid: $('#s-wolfram').value,
      elevenlabs_key: $('#s-eleven').value, elevenlabs_voice: $('#s-eleven-voice').value,
      homeassistant_url: $('#s-ha-url').value, homeassistant_token: $('#s-ha-token').value,
      webhooks: $('#s-hooks').value})}); $('#s-msg').textContent = 'Saved. All systems online, sir.'; if (!wsReady) connect(); refresh(); setTimeout(() => modal.classList.add('hidden'), 800); } catch (e) { $('#s-msg').textContent = 'Could not save — check the token.'; } };

/* ---------------- push notifications (iPhone: install to Home Screen first) */
async function enablePush() {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) { $('#s-msg').textContent = 'Notifications need the app installed to your Home Screen (Share → Add to Home Screen).'; return; }
    const reg = await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready;
    const perm = await Notification.requestPermission(); if (perm !== 'granted') { $('#s-msg').textContent = 'Notification permission denied.'; return; }
    const {public: key} = await api('/api/push/vapid');
    const raw = atob(key.replace(/-/g, '+').replace(/_/g, '/').padEnd(key.length + (4 - key.length % 4) % 4, '='));
    const sub = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, c => c.charCodeAt(0))});
    await api('/api/push/subscribe', {method: 'POST', body: JSON.stringify(sub.toJSON())});
    $('#s-msg').textContent = 'This device will now receive J.A.R.V.I.S. notifications.';
  } catch (e) { $('#s-msg').textContent = 'Push setup failed: ' + e.message; }
}
$('#s-push').onclick = enablePush; $('#btn-notify').onclick = () => { openSettings(); enablePush(); };
$('#s-push-test').onclick = async () => { const r = await api('/api/push/test', {method: 'POST'}); $('#s-msg').textContent = `Sent to ${r.sent} device(s).`; };

/* ---------------- drawers: knowledge & files */
const drawer = $('#drawer'); $('#drawer-close').onclick = () => drawer.classList.add('hidden');
$('#btn-providers').onclick = () => openSettings();
async function openFiles() { const s = await api('/api/status'); $('#drawer-title').textContent = 'FABRICATED FILES'; $('#drawer-body').innerHTML = s.files.map(f => `<div class="lesson"><b>${f.name}</b> · ${f.size} bytes <a class="more" style="display:inline" href="/api/files/${encodeURIComponent(f.name)}?token=${encodeURIComponent(TOKEN)}">⬇ download</a></div>`).join('') || '<div class="muted">No files yet — ask J.A.R.V.I.S. to make one.</div>'; drawer.classList.remove('hidden'); }


/* ---------------- identity */
function setName(n){
  const spaced = n.split('').join(n.includes('.') ? '' : ' ');
  const el = id => document.getElementById(id);
  if (el('hero-name')) el('hero-name').textContent = n.includes('.') ? n : n.toUpperCase().split('').join(' ');
  if (el('brand-name')) el('brand-name').textContent = n;
  if (el('call-name')) el('call-name').textContent = n;
  document.title = n + ' Command Center';
  window.AI_NAME = n;
}
window.AI_NAME = '0.5.4.M.4';

/* ---------------- CALL MODE: full-screen reactive-orb voice call */
const call = {open:false, rec:null, listening:false, speaking:false, muted:false, audioCtx:null, analyser:null, raf:0};
function openCall(){
  if (!TOKEN){ openSettings('Link this device first, sir.'); return; }
  if (!SR){ alert('Voice calls need Chrome, Edge or Safari.'); return; }
  $('#call').classList.remove('hidden'); call.open = true;
  $('#call-status').textContent = 'listening';
  $('#call-caption').innerHTML = `<span class="you">Say something — ${window.AI_NAME} is listening…</span>`;
  startOrbMic();
  if (window.Listener && window.Listener.on) { $('#call-status').textContent = 'listening'; } else { callListen(); }
  speak('Online, sir. How may I help?');
}
function endCall(){
  call.open = false; $('#call').classList.add('hidden');
  try{ call.rec && (call.rec.onend = null, call.rec.stop()); }catch(_){}
  cancelAnimationFrame(call.raf);
  if (call.audioCtx){ try{ call.audioCtx.close(); }catch(_){} call.audioCtx = null; }
  speechSynthesis.cancel();
}
$('#qc-call') && ($('#qc-call').onclick = openCall);
window.openCall = openCall; window.endCall = endCall;
window.callSubmit = function(t){ if (!call.open) openCall(); callSend(t); };
$('#call-end').onclick = endCall;
$('#call-mute').onclick = () => { call.muted = !call.muted; $('#call-mute').classList.toggle('muted', call.muted); $('#call-mute').textContent = call.muted ? '🔇' : '🎙️'; };

async function startOrbMic(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    call.audioCtx = new (window.AudioContext||window.webkitAudioContext)();
    const src = call.audioCtx.createMediaStreamSource(stream);
    call.analyser = call.audioCtx.createAnalyser(); call.analyser.fftSize = 128;
    src.connect(call.analyser);
    const data = new Uint8Array(call.analyser.frequencyBinCount);
    const orb = $('#orb'), cv = $('#orb-viz'), cx = cv.getContext('2d');
    const draw = () => {
      call.raf = requestAnimationFrame(draw);
      call.analyser.getByteFrequencyData(data);
      let sum = 0; for (const v of data) sum += v; const amp = sum / data.length / 255; // 0..1
      const level = call.speaking ? 0.55 + 0.45*Math.abs(Math.sin(Date.now()/120)) : amp;
      orb.style.transform = `scale(${1 + level*0.28})`;
      // frequency ring
      cx.clearRect(0,0,cv.width,cv.height); const cxp=cv.width/2, cyp=cv.height/2, R=cv.width*0.34;
      cx.strokeStyle = call.speaking ? 'rgba(120,240,255,.9)' : 'rgba(56,230,255,.55)'; cx.lineWidth=3; cx.beginPath();
      const N=data.length;
      for (let i=0;i<=N;i++){ const a=i/N*Math.PI*2; const r=R+(data[i%N]/255)*R*0.6*(call.speaking?1.1:1); const x=cxp+Math.cos(a)*r, y=cyp+Math.sin(a)*r; i?cx.lineTo(x,y):cx.moveTo(x,y);}
      cx.stroke();
    };
    draw();
  }catch(e){ $('#call-status').textContent = 'mic blocked'; }
}
function callListen(){
  if (!call.open) return;
  const r = new SR(); call.rec = r; r.lang='en-US'; r.interimResults=true; r.continuous=false;
  r.onstart = () => { call.listening=true; if(!call.speaking) $('#call-status').textContent='listening'; };
  r.onresult = e => {
    let txt=''; for (const res of e.results) txt += res[0].transcript;
    $('#call-caption').innerHTML = `<span class="you">${txt}</span>`;
    if (e.results[e.results.length-1].isFinal && txt.trim() && !call.muted){ callSend(txt.trim()); }
  };
  r.onerror = () => {};
  r.onend = () => { call.listening=false; if (call.open && !call.speaking) setTimeout(callListen, 200); };
  try{ r.start(); }catch(_){ setTimeout(callListen, 400); }
}
let callWaiting=false;
function callSend(text){
  if (callWaiting || !wsReady) return; callWaiting=true;
  try{ call.rec.onend=null; call.rec.stop(); }catch(_){}
  $('#call-status').textContent='thinking'; speechSynthesis.cancel();
  callBuf=''; callTarget=$('#call-caption'); ws.send(JSON.stringify({text, channel:'call'}));
}
let callBuf='', callTarget=null;


function callSpeak(text){
  if (!('speechSynthesis' in window)){ callDone(); return; }
  const clean = text.replace(/```[\s\S]*?```/g,' code omitted ').replace(/[*_#`>\[\]|]/g,'').slice(0,600);
  const u = new SpeechSynthesisUtterance(clean); u.rate=1.03; u.pitch=0.9;
  const vs = speechSynthesis.getVoices();
  u.voice = vs.find(v=>/en-GB/i.test(v.lang)&&/daniel|george|ryan|male/i.test(v.name)) || vs.find(v=>/en-GB/i.test(v.lang)) || vs.find(v=>/^en/i.test(v.lang)) || null;
  u.onend = callDone; u.onerror = callDone;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}
function callDone(){ call.speaking=false; $('#orb').classList.remove('speaking'); if (call.open){ $('#call-status').textContent='listening'; callListen(); } }


$('#qc-connectors') && ($('#qc-connectors').onclick = async () => {
  const cap = await api('/api/connectors');
  const pct = Math.round(cap.index / 10);
  let html = `<div class="lesson"><b style="font-size:1.3em">Capability Index ${cap.index} / 1000</b>
    <div class="bar" style="height:10px;border:1px solid var(--line2);border-radius:5px;margin:8px 0;overflow:hidden">
      <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,var(--acc),var(--cyan))"></div></div>
    <small class="muted">Brain: ${cap.brain.model} — ${cap.brain.points}/${cap.brain.max} pts. A frontier model is the single biggest gain available.</small></div>`;
  html += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0">' + Object.entries(cap.dimensions).map(([d, v]) => {
    const p = Math.round(v.earned / v.max * 100);
    return `<div class="lesson" style="flex:1 1 150px;margin:0"><b>${d}</b> <span class="skill" style="float:right">${v.earned}/${v.max}</span>
      <div class="bar" style="height:6px;border:1px solid var(--line);border-radius:3px;margin-top:6px;overflow:hidden">
      <div style="height:100%;width:${p}%;background:${p>75?'var(--ok)':p>40?'var(--cyan)':'var(--warn)'}"></div></div></div>`;
  }).join('') + '</div>';
  const cats = {};
  cap.connectors.forEach(c => { (cats[c.category] = cats[c.category] || []).push(c); });
  const lbl = {live:'ready', agent:'needs PC agent', oauth:'needs sign-in', key:'needs key'};
  for (const [cat, list] of Object.entries(cats)) {
    html += `<div style="margin:10px 0 4px;color:#bfe3ff;font-family:Orbitron;font-size:11px;letter-spacing:2px">${cat.toUpperCase()}</div>`;
    html += '<div style="display:flex;flex-wrap:wrap;gap:6px">' + list.map(c =>
      `<div class="lesson" style="flex:1 1 210px;margin:0;border-color:${c.active?'var(--ok)':'var(--line)'}">
        <b>${c.name}</b> <span class="skill" style="float:right">+${c.iq}</span><br>
        <small class="muted">${c.note}</small><br>
        <span class="chip ${c.active?'':'off'}" style="margin-top:4px">${c.active?'● ACTIVE':'○ '+lbl[c.auth]}</span>
      </div>`).join('') + '</div>';
  }
  $('#drawer-title').textContent = 'CAPABILITY INDEX';
  $('#drawer-body').innerHTML = html; $('#drawer').classList.remove('hidden');
});

/* ---------------- boot */
(async () => {
  if ('serviceWorker' in navigator) { try { await navigator.serviceWorker.register('/sw.js'); } catch (_) {} }
  const q = new URLSearchParams(location.search); const shared = q.get('url') || q.get('text'); if (shared) { $('#prompt').value = `Tell me about this: ${shared}`; history.replaceState({}, '', '/'); }
  if (!TOKEN) openSettings('Welcome, sir. Paste the access token from your server to link this device.');
  else { connect(); try { (await api('/api/history?n=20')).forEach(m => { const d = addMsg(m.role === 'user' ? 'user' : 'jarvis', ''); render(d, m.content); }); } catch (_) {} }
  refresh(); setInterval(refresh, 4000);
})();
