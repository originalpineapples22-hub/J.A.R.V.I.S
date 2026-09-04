/* Hologram Mode — webcam hand tracking with a glowing orb between the hands.
   Uses MediaPipe Tasks Vision (HandLandmarker), loaded on demand from CDN. */
(function () {
  const $ = s => document.querySelector(s);
  const holo = {open:false, landmarker:null, raf:0, stream:null, orb:{x:.5,y:.5,r:60,tr:60,energy:0}, particles:[], lastPinch:0};

  function status(t){ const el = $('#holo-status'); if (el) el.textContent = t; }

  async function open() {
    if (!window.TOKEN && !localStorage.getItem('jarvis_token')) { alert('Link this device first, sir.'); return; }
    $('#holo').classList.remove('hidden'); holo.open = true;
    if ($('#holo-name') && window.AI_NAME) $('#holo-name').textContent = window.AI_NAME;
    try {
      status('starting camera…');
      holo.stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:'user', width:1280, height:720}, audio:false});
      const v = $('#holo-cam'); v.srcObject = holo.stream; await v.play();
      status('loading vision model…');
      if (!holo.landmarker) {
        const vision = await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs');
        const fileset = await vision.FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
        holo.landmarker = await vision.HandLandmarker.createFromOptions(fileset, {
          baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'},
          numHands:2, runningMode:'VIDEO'
        });
      }
      status('');
      resize(); window.addEventListener('resize', resize);
      loop();
    } catch (e) {
      status('Camera or model failed: ' + e.message + ' — allow camera access and use Chrome/Safari.');
    }
  }
  function close() {
    holo.open = false; $('#holo').classList.add('hidden');
    cancelAnimationFrame(holo.raf);
    if (holo.stream) { holo.stream.getTracks().forEach(t => t.stop()); holo.stream = null; }
  }
  let cv, cx;
  function resize(){ cv = $('#holo-canvas'); cv.width = cv.clientWidth; cv.height = cv.clientHeight; cx = cv.getContext('2d'); }

  function loop() {
    if (!holo.open) return;
    holo.raf = requestAnimationFrame(loop);
    const v = $('#holo-cam');
    if (!cx || v.readyState < 2) return;
    let hands = [];
    try { const res = holo.landmarker.detectForVideo(v, performance.now()); hands = res.landmarks || []; } catch (_) {}
    cx.clearRect(0, 0, cv.width, cv.height);
    const W = cv.width, H = cv.height, mx = x => (1 - x) * W, my = y => y * H; // mirror X to match the flipped video

    // draw faint skeletons
    cx.lineWidth = 2;
    for (const hand of hands) {
      cx.strokeStyle = 'rgba(56,230,255,.35)';
      const links = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
      for (const [a,b] of links){ cx.beginPath(); cx.moveTo(mx(hand[a].x),my(hand[a].y)); cx.lineTo(mx(hand[b].x),my(hand[b].y)); cx.stroke(); }
      for (const p of hand){ cx.fillStyle='rgba(120,240,255,.6)'; cx.beginPath(); cx.arc(mx(p.x),my(p.y),3,0,7); cx.fill(); }
    }

    // target orb position/size
    let tx=.5, ty=.45, tr=70, pinch=false;
    if (hands.length >= 2) {
      const c0 = hands[0][9], c1 = hands[1][9]; // palm centres
      tx = (c0.x + c1.x)/2; ty = (c0.y + c1.y)/2;
      const d = Math.hypot((c0.x-c1.x)*W, (c0.y-c1.y)*H);
      tr = Math.max(40, Math.min(d*0.42, W*0.28));
    } else if (hands.length === 1) {
      const h = hands[0];
      tx = h[9].x; ty = h[9].y - 0.12;
      const pd = Math.hypot((h[4].x-h[8].x)*W, (h[4].y-h[8].y)*H); // thumb-index distance
      tr = Math.max(40, Math.min(pd*1.1, 180));
      pinch = pd < 45;
    }
    // smooth
    const o = holo.orb;
    o.x += ((1-tx) - o.x) * 0.25; o.y += (ty - o.y) * 0.25; o.tr = tr; o.r += (o.tr - o.r) * 0.2;
    o.energy += ((pinch ? 1 : 0.35) - o.energy) * 0.15;
    if (pinch && performance.now() - holo.lastPinch > 700) { holo.lastPinch = performance.now(); burst(o.x*W, o.y*H); if (window.speak) window.speak('At your command, sir.'); }

    drawOrb(o.x*W, o.y*H, o.r, o.energy, hands.length===0);
    updateBurst();
  }

  function drawOrb(x, y, r, energy, idle) {
    const pulse = 1 + Math.sin(performance.now()/ (idle?600:200)) * 0.06 * (1+energy);
    r *= pulse;
    let g = cx.createRadialGradient(x - r*0.25, y - r*0.25, r*0.1, x, y, r);
    g.addColorStop(0, 'rgba(255,255,255,'+(0.9)+')');
    g.addColorStop(0.35, 'rgba(80,220,255,'+(0.85)+')');
    g.addColorStop(0.75, 'rgba(22,103,214,'+(0.5+0.3*energy)+')');
    g.addColorStop(1, 'rgba(20,60,160,0)');
    cx.save(); cx.globalCompositeOperation = 'lighter';
    cx.fillStyle = g; cx.beginPath(); cx.arc(x, y, r*1.6, 0, 7); cx.fill();
    // orbit rings
    cx.strokeStyle = 'rgba(120,240,255,'+(0.5+0.3*energy)+')'; cx.lineWidth = 2;
    for (let i=0;i<3;i++){ const rot = performance.now()/1000*(i%2?-1:1)*(0.4+i*0.2); const rr = r*(1.1+i*0.35);
      cx.beginPath(); cx.ellipse(x, y, rr, rr*0.36, rot, 0, 7); cx.stroke(); }
    cx.restore();
  }

  function burst(x,y){ for(let i=0;i<40;i++){ const a=Math.random()*7, s=2+Math.random()*6; holo.particles.push({x,y,vx:Math.cos(a)*s,vy:Math.sin(a)*s,life:1}); } }
  function updateBurst(){ cx.save(); cx.globalCompositeOperation='lighter'; for(const p of holo.particles){ p.x+=p.vx; p.y+=p.vy; p.vx*=.94; p.vy*=.94; p.life-=0.03; cx.fillStyle='rgba(150,240,255,'+Math.max(p.life,0)+')'; cx.beginPath(); cx.arc(p.x,p.y,2.5,0,7); cx.fill(); } holo.particles=holo.particles.filter(p=>p.life>0); cx.restore(); }

  document.addEventListener('DOMContentLoaded', () => {
    const b = $('#qc-holo'); if (b) b.onclick = open;
    const e = $('#holo-end'); if (e) e.onclick = close;
    const t = $('#holo-talk'); if (t) t.onclick = () => { const m = $('#mic'); if (m) m.click(); };
  });
  window.openHolo = open;
})();
