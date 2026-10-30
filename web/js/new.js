/* 新建项目：识别格式 → 自动 UVR 分离 + 自动歌词注音（并行）
   也支持 #/new?resep=<id>：对已存在项目重新分离（练习页入口） */
const NewView = (() => {
  const $ = id => document.getElementById(id);
  let busy = false;
  let resepId = null;

  function setStep(id, state) {
    const el = $(id);
    el.classList.remove('run', 'done', 'err');
    if (state) el.classList.add(state);
  }
  function setBar(id, ratio) {
    $(id).style.width = Math.round(Math.min(1, ratio) * 100) + '%';
  }

  function enter() {
    if (busy) return;
    resepId = new URLSearchParams((location.hash.split('?')[1]) || '').get('resep');
    $('dropzone').hidden = !!resepId;
    $('pipeline').hidden = true;
    $('ingest-info').hidden = true;
    $('pl-error').hidden = true;
    $('pl-error').textContent = '';
    $('file-input').value = '';
    setBar('bar-upload', 0); setBar('bar-sep', 0);
    $('bar-sep').classList.remove('indeterminate');
    $('pct-upload').textContent = '0%';
    $('pct-sep').textContent = '排队中';
    $('sep-label').textContent = '准备分离人声 / 伴奏';
    if (resepId) startResep(resepId);
  }

  const dz = $('dropzone');
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('drag');
    if (e.dataTransfer.files[0]) start(e.dataTransfer.files[0]);
  });
  $('file-input').addEventListener('change', e => e.target.files[0] && start(e.target.files[0]));

  async function start(file) {
    if (busy) return;
    busy = true;
    try {
      $('pipeline').hidden = false;
      $('pl-error').hidden = true;
      setStep('pl-upload', 'run'); setStep('pl-sep', ''); setStep('pl-lyric', '');
      $('lyric-status').textContent = '等待中';

      const ing = await API.upload(file, p => {
        setBar('bar-upload', p);
        $('pct-upload').textContent = Math.round(p * 100) + '%';
      });
      setBar('bar-upload', 1); setStep('pl-upload', 'done');

      const m = await API.getSong(ing.id);
      const kindTxt = m.source_kind === 'native'
        ? (m.source.split('.').pop() || '音频').toUpperCase() + ' 原始格式'
        : (m.source_kind.split(':')[1] || '').toUpperCase() + ' 加密缓存 · 已解密';
      $('ingest-info').hidden = false;
      $('ii-name').textContent = `${m.title || file.name} · ${fmtTime(m.duration)}`;
      const chip = $('ii-kind');
      chip.textContent = kindTxt;
      chip.className = 'chip ok';
      $('ii-tags').textContent = [m.artist, m.album].filter(Boolean).join(' · ') || file.name;

      // 两条流水线并行：UVR 分离 / 歌词匹配+注音
      const sepP = runSeparation(m);
      const lyrP = runLyrics(m);
      const [sepOk, lyrOk] = await Promise.allSettled([sepP, lyrP]);

      if (sepOk.status === 'rejected') {
        setStep('pl-sep', 'err');
        $('pl-error').hidden = false;
        $('pl-error').textContent = '分离失败：' + sepOk.reason.message + '（项目已创建，可稍后在练习页重试）';
      } else {
        setStep('pl-sep', 'done'); $('pct-sep').textContent = '完成';
      }
      if (lyrOk.status === 'rejected') {
        $('lyric-status').textContent = '未获取：' + lyrOk.reason.message;
      } else {
        $('lyric-status').textContent = lyrOk.value;
      }
      setStep('pl-lyric', lyrOk.status === 'fulfilled' && lyrOk.value.startsWith('✓') ? 'done' : 'err');

      await new Promise(r => setTimeout(r, sepOk.status === 'fulfilled' ? 700 : 2600));
      location.hash = `#/song?id=${encodeURIComponent(m.id)}`;
    } catch (err) {
      setStep('pl-upload', 'err');
      $('pl-error').hidden = false;
      $('pl-error').textContent = err.message;
    } finally {
      busy = false;
    }
  }

  async function runSeparation(m) {
    setStep('pl-sep', 'run');
    const r = await API.separate(m.id);
    // 已经分离过（含服务重启后从盘上恢复）：直接完成
    if (r.already) { setBar('bar-sep', 1); $('pct-sep').textContent = '已完成'; return true; }
    const job_id = r.job_id;
    const t0 = Date.now();
    const bar = $('bar-sep');
    while (true) {
      await new Promise(r => setTimeout(r, 1200));
      const j = await API.job(job_id);
      const el = Math.round((Date.now() - t0) / 1000);
      $('sep-label').textContent =
        j.stage === 'wav' ? '转码为无损波形…' :
        j.stage === 'model' ? '加载分离模型…' :
        j.stage === 'separate' ? 'UVR 分离人声 / 伴奏（CPU 耗时约为歌曲时长的 0.5–1.5 倍，可切走等待）' :
        '排队中…';
      if (j.stage === 'separate') {
        // 不确定进度：滑动动画条 + 已用时间，不再用假百分比
        bar.classList.add('indeterminate');
        $('pct-sep').textContent = '已用 ' + fmtTime(el);
      } else {
        bar.classList.remove('indeterminate');
        setBar('bar-sep', 0.08);
        $('pct-sep').textContent = el + 's';
      }
      if (j.status === 'done') {
        bar.classList.remove('indeterminate');
        setBar('bar-sep', 1); $('pct-sep').textContent = '完成';
        return true;
      }
      if (j.status === 'error') {
        bar.classList.remove('indeterminate');
        throw new Error(j.error || '分离任务出错');
      }
    }
  }

  /* 对已有项目重新分离（练习页「重新分离」入口，不重新上传） */
  async function startResep(id) {
    busy = true;
    try {
      $('pipeline').hidden = false;
      setStep('pl-upload', 'done'); setBar('bar-upload', 1); $('pct-upload').textContent = '已存在';
      let m;
      try { m = await API.getSong(id); }
      catch (e) { throw new Error('项目不存在：' + e.message); }
      $('ingest-info').hidden = false;
      $('ii-name').textContent = `${m.title || m.source} · ${fmtTime(m.duration)}`;
      const chip = $('ii-kind'); chip.textContent = '重新分离'; chip.className = 'chip ok';
      $('ii-tags').textContent = [m.artist, m.album].filter(Boolean).join(' · ') || '';
      setStep('pl-lyric', (m.lyrics_annotated || m.lyrics) ? 'done' : 'err');
      $('lyric-status').textContent = m.lyrics_annotated ? '已有注音歌词，已保留'
        : m.lyrics ? '已有歌词，已保留（可稍后重新注音）'
        : '本次不处理歌词，可稍后在练习页匹配';
      try {
        await runSeparation(m);
        setStep('pl-sep', 'done'); $('pct-sep').textContent = '完成';
        await new Promise(r => setTimeout(r, 700));
        location.hash = `#/song?id=${encodeURIComponent(id)}`;
      } catch (err) {
        setStep('pl-sep', 'err');
        const box = $('pl-error');
        box.hidden = false;
        box.textContent = '分离失败：' + err.message + '　';
        const b = document.createElement('button');
        b.className = 'gbtn tiny'; b.textContent = '返回练习页';
        b.onclick = () => { location.hash = `#/song?id=${encodeURIComponent(id)}`; };
        box.appendChild(b);
      }
    } catch (err) {
      $('pl-error').hidden = false;
      $('pl-error').textContent = err.message;
    } finally {
      busy = false;
    }
  }

  async function runLyrics(m) {
    setStep('pl-lyric', 'run');
    $('lyric-status').textContent = '在线歌词库匹配中…';
    const r = await API.matchLyrics(m.id, m.title, m.artist, m.album, Math.round(m.duration));
    if (!r.source) throw new Error('未找到歌词，可在练习页手动编辑');
    $('lyric-status').textContent = '已匹配，正在生成日语假名注音…';
    let note = `✓ ${r.source}`;
    try {
      const a = await API.annotate(m.id);
      note += ` · 注音 ${a.annotated_lines} 行`;
    } catch (e) { note += ' · 注音跳过（非日语或服务不可用）'; }
    return note;
  }

  return { enter };
})();
