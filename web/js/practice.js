/* 练习页：变速不变调 / A-B 循环 / 录音 / 三种 MP3 保存 / 滚动歌词 */
const PracticeView = (() => {
  const $ = id => document.getElementById(id);
  const audio = $('player');
  audio.preservesPitch = true;
  audio.mozPreservesPitch = true;
  audio.webkitPreservesPitch = true;

  let m = null, lines = [], activeIdx = -1, rafId = 0;
  let sepPoll = null, pollMisses = 0;
  let aT = null, bT = null, savedRate = 1;
  let mediaRec = null, micStream = null, recBlob = null, recBuf = null, recStart = 0, loopWasOn = false;
  const bufCache = new Map();
  let dead = false;

  function esc(s) {
    return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }
  function safeName(s) { return String(s || 'song').replace(/[\\/:*?"<>|]+/g, '_').slice(0, 80); }

  async function enter(id) {
    dead = false;
    lines = []; activeIdx = -1; aT = bT = null; recBlob = null; recBuf = null;
    bufCache.clear();
    resetUi();
    try {
      m = await API.getSong(id);
    } catch (e) { $('s-title').textContent = '加载失败：' + e.message; return; }
    API.touch(id).catch(() => {});
    document.title = `${m.title || '练唱'} · 唱练`;
    $('s-title').textContent = m.title || m.source;
    $('s-artist').textContent = [m.artist, m.album].filter(Boolean).join(' · ');

    // 音轨可用性
    document.querySelectorAll('#stem-switch button').forEach(b => {
      b.disabled = (b.dataset.stem !== 'source') && !m[b.dataset.stem];
    });
    setStem(m.instrumental ? 'instrumental' : 'source');

    $('btn-save-voc').disabled = true;
    $('btn-save-mix').disabled = true;
    const sepReady = !!m.instrumental;
    // 未分离时按钮保持可点：点击跳到新建页对该项目重新分离
    $('btn-save-inst').disabled = false;
    $('btn-save-inst').textContent = sepReady ? '⬇ 保存伴奏 (MP3)' : '⟳ 重新分离人声 / 伴奏';
    $('rec-hint').textContent = sepReady ? '' : '人声分离未完成，点上方「重新分离」重试';

    loadLyrics();
    tick();
    watchSeparation();
  }

  function teardown() {
    dead = true;
    cancelAnimationFrame(rafId);
    clearInterval(sepPoll); sepPoll = null;
    audio.pause(); audio.removeAttribute('src'); audio.load();
    stopMic();
    document.title = '唱练 · 本地练歌工作室';
  }

  /* 未分离但有任务在后台跑：练习页自己轮询，完成后自动刷新（不依赖新建页） */
  function watchSeparation() {
    clearInterval(sepPoll); sepPoll = null; pollMisses = 0;
    if (m.instrumental || !m.sep_job) return;
    const btn = $('btn-save-inst');
    btn.disabled = true;
    let dots = 0;
    sepPoll = setInterval(async () => {
      if (dead) { clearInterval(sepPoll); return; }
      let j;
      try { j = await API.job(m.sep_job); pollMisses = 0; }
      catch (e) {
        // 服务重启后任务记录丢失：连续 3 次 404 就放弃（wav 恢复可走重新分离按钮）
        if (++pollMisses >= 3) {
          clearInterval(sepPoll); sepPoll = null;
          btn.disabled = false; btn.textContent = '⟳ 重新分离人声 / 伴奏';
          $('rec-hint').textContent = '上次任务状态已丢失，点上方按钮可直接恢复或重试';
        }
        return;
      }
      if (j.status === 'queued') { btn.textContent = '排队等待分离…'; return; }
      if (j.status === 'running') {
        dots = (dots + 1) % 4;
        btn.textContent = '分离进行中' + '·'.repeat(dots + 1) +
                          '（已用 ' + Math.round(j.elapsed || 0) + 's）';
        return;
      }
      clearInterval(sepPoll); sepPoll = null;
      if (j.status === 'done') { m = await API.getSong(m.id); enter(m.id); }
      else if (j.status === 'error') {
        btn.disabled = false;
        btn.textContent = '⟳ 分离失败，点击重试';
        $('rec-hint').textContent = '人声分离失败：' + (j.error || '').slice(0, 80);
      }
    }, 2000);
  }

  function resetUi() {
    $('btn-play').textContent = '▶';
    $('seek').value = 0;
    $('speed').value = 100; $('speed-val').textContent = '100%';
    audio.playbackRate = 1;
    $('ab-info').textContent = '';
    $('lyrics').innerHTML = '<p class="dim">歌词加载中…</p>';
  }

  /* ---------- 音轨切换 ----------
     后端文件接口按 kind 取：/api/files/{id}/source|instrumental|vocals */
  function setStem(stem) {
    document.querySelectorAll('#stem-switch button').forEach(b =>
      b.classList.toggle('on', b.dataset.stem === stem));
    const wasPlaying = !audio.paused;
    const t = audio.currentTime;
    audio.src = API.fileUrl(m.id, stem);
    if (isFinite(t)) audio.currentTime = t;
    if (wasPlaying) audio.play().catch(() => {});
  }
  document.getElementById('stem-switch').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (b && !b.disabled) setStem(b.dataset.stem);
  });

  /* ---------- 返回首页 ---------- */
  $('btn-back').onclick = () => { location.hash = '#/home'; };

  /* ---------- 播放 / 进度 / 循环 ---------- */
  $('btn-play').onclick = () => {
    if (audio.paused) audio.play(); else audio.pause();
  };
  audio.addEventListener('play', () => $('btn-play').textContent = '⏸');
  audio.addEventListener('pause', () => $('btn-play').textContent = '▶');
  audio.addEventListener('loadedmetadata', () => {
    $('t-dur').textContent = fmtTime(audio.duration);
  });
  $('seek').addEventListener('input', () => {
    if (isFinite(audio.duration)) audio.currentTime = ($('seek').value / 1000) * audio.duration;
  });

  $('btn-a').onclick = () => { aT = audio.currentTime; bT = null; renderAb(); };
  $('btn-b').onclick = () => {
    if (aT == null) { aT = 0; }
    bT = Math.max(aT + 0.3, audio.currentTime); renderAb();
  };
  $('btn-clear-ab').onclick = () => { aT = bT = null; renderAb(); };
  function renderAb() {
    $('ab-info').textContent = aT != null
      ? `循环 ${fmtTime(aT)} → ${bT != null ? fmtTime(bT) : '…'}` : '';
  }

  /* ---------- 变速（不变调） ---------- */
  $('speed').addEventListener('input', e => {
    const r = e.target.value / 100;
    audio.playbackRate = r;
    $('speed-val').textContent = e.target.value + '%';
  });
  $('speed-reset').onclick = () => {
    $('speed').value = 100; $('speed-val').textContent = '100%'; audio.playbackRate = 1;
  };

  /* ---------- 主循环 ---------- */
  function tick() {
    if (dead) return;
    if (isFinite(audio.duration)) {
      $('t-cur').textContent = fmtTime(audio.currentTime);
      if (document.activeElement !== $('seek'))
        $('seek').value = (audio.currentTime / audio.duration) * 1000;
      if (!audio.paused && aT != null && bT != null && audio.currentTime >= bT) {
        audio.currentTime = aT;
      }
    }
    syncLyric();
    rafId = requestAnimationFrame(tick);
  }

  /* ---------- 歌词 ---------- */
  function parseLrc(text) {
    const out = [];
    for (const raw of text.split(/\r?\n/)) {
      const tags = [...raw.matchAll(/\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g)];
      if (!tags.length) continue;
      const body = raw.slice(tags[tags.length - 1].index + tags[tags.length - 1][0].length).trim();
      for (const tg of tags) {
        const frac = tg[3] ? +(tg[3] + '00').slice(0, 3) / 1000 : 0;
        out.push({ t: +tg[1] * 60 + +tg[2] + frac, text: body });
      }
    }
    return out.sort((x, y) => x.t - y.t);
  }

  /** 漢字《かんじ》|romaji <翻译> → HTML */
  function renderBody(text) {
    let rom = '';
    const bar = text.indexOf('|');
    if (bar >= 0) { rom = text.slice(bar + 1).replace(/<[^>]*>$/, '').trim(); text = text.slice(0, bar); }
    text = text.replace(/<[^>]*>$/, '').trim();
    // 普通片段与「汉字《注音》」片段交替渲染为 ruby
    let html = '';
    const parts = text.split(/([^《\s]+《[^》]*》)/g).filter(Boolean);
    for (const p of parts) {
      const mm2 = p.match(/^([^《]+)《([^》]*)》$/);
      if (mm2) html += `<ruby>${esc(mm2[1])}<rt>${esc(mm2[2])}</rt></ruby>`;
      else html += esc(p);
    }
    if (rom) html += `<span class="rom">${esc(rom)}</span>`;
    return html || '&nbsp;';
  }

  async function loadLyrics() {
    let text = '', kind = null;
    try {
      if (m.lyrics_annotated) { text = await API.lyrics(m.id, 'annotated'); kind = 'annotated'; }
      else { text = await API.lyrics(m.id); kind = 'plain'; }
    } catch (e) {
      try { text = await API.lyrics(m.id); kind = 'plain'; } catch (e2) {}
    }
    if (!text.trim()) {
      $('lyrics').innerHTML = '<p class="dim">暂无歌词，可点右上角“编辑歌词”手动粘贴 LRC。</p>';
      $('lyric-source').textContent = '';
      return;
    }
    lines = parseLrc(text);
    $('lyric-source').textContent = (kind === 'annotated' ? '带假名注音 · ' : '') + (m.lyrics_source || '本地歌词');
    const box = $('lyrics');
    box.innerHTML = lines.map((l, i) =>
      `<div class="lrc-line" data-i="${i}">${renderBody(l.text)}</div>`).join('');
    box.querySelectorAll('.lrc-line').forEach(el =>
      el.addEventListener('click', () => {
        const i = +el.dataset.i;
        audio.currentTime = lines[i].t;
      }));
  }

  function syncLyric() {
    if (!lines.length) return;
    const t = audio.currentTime;
    let lo = 0, hi = lines.length - 1, idx = -1;
    while (lo <= hi) { const md = (lo + hi) >> 1; if (lines[md].t <= t) { idx = md; lo = md + 1; } else hi = md - 1; }
    if (idx !== activeIdx) {
      activeIdx = idx;
      const els = $('lyrics').children;
      for (let i = 0; i < els.length; i++) els[i].classList.toggle('active', i === idx);
      const cur = els[idx];
      if (cur) cur.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  /* ---------- 歌词编辑 ---------- */
  $('btn-match-lyric').onclick = async () => {
    $('btn-match-lyric').disabled = true;
    try {
      const r = await API.matchLyrics(m.id, m.title, m.artist, m.album, Math.round(m.duration));
      if (r.source) {
        try { await API.annotate(m.id); } catch (e) {}
      } else alert('所有在线歌词库均未命中，可手动粘贴 LRC。');
      m = await API.getSong(m.id); loadLyrics();
    } catch (e) { alert('匹配失败：' + e.message); }
    $('btn-match-lyric').disabled = false;
  };

  const modal = $('modal');
  $('btn-edit-lyric').onclick = async () => {
    let text = '';
    try { text = m.lyrics_annotated ? await API.lyrics(m.id, 'annotated') : await API.lyrics(m.id); } catch (e) {}
    $('lyric-editor').value = text || `[00:00.00]在此粘贴 LRC 歌词\n`;
    modal.hidden = false;
  };
  $('me-cancel').onclick = () => modal.hidden = true;
  modal.addEventListener('click', e => { if (e.target === modal) modal.hidden = true; });
  $('me-save-direct').onclick = async () => {
    await API.saveLyrics(m.id, $('lyric-editor').value);
    modal.hidden = true;
    m = await API.getSong(m.id); loadLyrics();
  };
  $('me-save-raw').onclick = async () => {
    await API.saveLyrics(m.id, $('lyric-editor').value);
    try { await API.annotate(m.id); } catch (e) {}
    modal.hidden = true;
    m = await API.getSong(m.id); loadLyrics();
  };

  /* ---------- 录音 ---------- */
  $('btn-record').onclick = () => mediaRec && mediaRec.state === 'recording' ? stopRecord() : startRecord();

  async function startRecord() {
    if (!m.instrumental) { alert('请先完成人声分离再录音。'); return; }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) { alert('无法使用麦克风：' + e.message); return; }
    // 录音在原速时间轴对齐：录音期间强制 1.0×，并暂停 A-B 跳转
    savedRate = audio.playbackRate;
    if (audio.playbackRate !== 1) {
      audio.playbackRate = 1; $('speed').value = 100; $('speed-val').textContent = '100%';
    }
    loopWasOn = aT != null && bT != null;
    if (loopWasOn) { aT = bT = null; renderAb(); }

    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
    mediaRec = new MediaRecorder(micStream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    mediaRec.ondataavailable = e => e.data.size && chunks.push(e.data);
    mediaRec.onstop = async () => {
      recBlob = new Blob(chunks, { type: mediaRec.mimeType || 'audio/webm' });
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      recBuf = await ac.decodeAudioData(await recBlob.arrayBuffer());
      $('btn-save-voc').disabled = false;
      $('btn-save-mix').disabled = false;
      stopMic();
      // 恢复变速与循环
      audio.playbackRate = savedRate;
      $('speed').value = Math.round(savedRate * 100);
      $('speed-val').textContent = Math.round(savedRate * 100) + '%';
      // 录音期间临时关闭的 A-B 循环保持清除状态，避免旧点跨越录音段
      aT = bT = null; renderAb();
    };
    recStart = audio.currentTime;
    mediaRec.start(250);
    if (audio.paused) audio.play();
    $('btn-record').classList.add('rec');
    $('btn-record').textContent = '■ 停止录音';
    $('rec-hint').textContent = '录音中（原速）…';
  }
  async function stopRecord() {
    if (mediaRec && mediaRec.state !== 'inactive') mediaRec.stop();
    $('btn-record').classList.remove('rec');
    $('btn-record').textContent = '● 开始录音';
    $('rec-hint').textContent = '录音完成，可保存。';
  }
  function stopMic() {
    micStream?.getTracks().forEach(t => t.stop());
    micStream = null;
  }

  /* ---------- 解码缓存 ---------- */
  async function decoded(fileName) {
    if (!bufCache.has(fileName)) {
      const { ctx, buf } = await MP3.decodeUrl(API.fileUrl(m.id, fileName));
      bufCache.set(fileName, { ctx, buf });
    }
    return bufCache.get(fileName);
  }

  async function busyEncode(btn, handle, name, fn) {
    const old = btn.textContent;
    btn.disabled = true; btn.textContent = '正在生成 MP3…';
    try {
      const blob = await fn();        // 解码/编码（耗时）
      await MP3.write(handle, blob, name);
    } catch (e) {
      if (e?.name !== 'AbortError') alert('保存失败：' + e.message);
    } finally { btn.textContent = old; btn.disabled = false; }
  }

  /** 在点击手势内立即弹出“另存为”；取消或失败返回 undefined（失败会提示） */
  async function pickHandle(name) {
    try { return await MP3.pickSave(name); }
    catch (e) {
      if (e?.name === 'AbortError') return undefined;  // 用户取消，静默
      alert('无法打开保存对话框：' + e.message);
      return undefined;
    }
  }

  /* 保存伴奏（原速 MP3） */
  $('btn-save-inst').onclick = async e => {
    if (!m.instrumental) {
      location.hash = `#/new?resep=${encodeURIComponent(m.id)}`;
      return;
    }
    const name = `${safeName(m.title)} - 伴奏.mp3`;
    const handle = await pickHandle(name);
    if (handle === undefined) return;
    await busyEncode(e.currentTarget, handle, name, async () => {
      const { buf } = await decoded('instrumental');
      return MP3.encode(buf);
    });
  };

  /* 保存录音 */
  $('btn-save-voc').onclick = async e => {
    if (!recBuf) return;
    const name = `${safeName(m.title)} - 我的录音.mp3`;
    const handle = await pickHandle(name);
    if (handle === undefined) return;
    await busyEncode(e.currentTarget, handle, name, () =>
      Promise.resolve(MP3.encode(recBuf)));
  };

  /* 伴奏 + 录音混音（原速对齐） */
  $('btn-save-mix').onclick = async e => {
    if (!recBuf) return;
    const name = `${safeName(m.title)} - 伴奏+录音.mp3`;
    const handle = await pickHandle(name);
    if (handle === undefined) return;
    await busyEncode(e.currentTarget, handle, name, async () => {
      const { buf } = await decoded('instrumental');
      const sr = 44100;
      const dur = Math.max(buf.duration, recStart + recBuf.duration) + 0.5;
      const oc = new OfflineAudioContext(2, Math.ceil(dur * sr), sr);
      const bs = oc.createBufferSource(); bs.buffer = buf; bs.connect(oc.destination);
      const vs = oc.createBufferSource(); vs.buffer = recBuf;
      const vg = oc.createGain(); vg.gain.value = 1.15;
      vs.connect(vg); vg.connect(oc.destination);
      bs.start(0); vs.start(recStart);
      const mix = await oc.startRendering();
      return MP3.encode(mix);
    });
  };

  return { enter, teardown };
})();
