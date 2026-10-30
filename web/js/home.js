/* 首页：新建入口 + 最近项目 */
const HomeView = (() => {
  const elGrid = document.getElementById('project-grid');
  const elEmpty = document.getElementById('home-empty');

  function esc(s) {
    return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function kindBadge(m) {
    if (m.source_kind === 'native') return '<span class="badge">原始音频</span>';
    if (m.source_kind?.startsWith('decrypted')) return `<span class="badge">${esc(m.source_kind.split(':')[1].toUpperCase())} 已解密</span>`;
    return '';
  }

  async function refresh() {
    const list = await API.listSongs();
    elGrid.innerHTML = '';
    elEmpty.hidden = list.length > 0;
    for (const m of list) {
      const card = document.createElement('div');
      card.className = 'p-card glass';
      card.innerHTML = `
        <button class="pc-del" title="删除项目">✕</button>
        <div class="pc-name">${esc(m.title || m.source)}</div>
        <div class="pc-meta">${esc(m.artist || '未知歌手')}${m.album ? ' · ' + esc(m.album) : ''} · ${fmtTime(m.duration)}</div>
        <div class="badges">
          ${kindBadge(m)}
          ${m.instrumental ? '<span class="badge ok">已分离</span>' : '<span class="badge warn">未分离</span>'}
          ${m.lyrics_source ? '<span class="badge ok">歌词</span>' : '<span class="badge warn">无歌词</span>'}
          ${m.lyrics_annotated ? '<span class="badge ok">假名注音</span>' : ''}
        </div>`;
      card.addEventListener('click', e => {
        if (e.target.classList.contains('pc-del')) return;
        location.hash = `#/song?id=${encodeURIComponent(m.id)}`;
      });
      card.querySelector('.pc-del').addEventListener('click', async e => {
        e.stopPropagation();
        if (!confirm(`删除项目「${m.title || m.source}」？其音频、分离与歌词文件都会被删除。`)) return;
        await API.deleteSong(m.id);
        refresh();
      });
      elGrid.appendChild(card);
    }
  }

  return { refresh };
})();
