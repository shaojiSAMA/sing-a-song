/* 后端 API 封装 */
const API = (() => {
  const base = location.origin.startsWith('http') ? '' : 'http://127.0.0.1:8178';

  async function json(path, opts) {
    const r = await fetch(base + path, { cache: 'no-store', ...opts });
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { msg = (await r.json()).detail || msg; } catch (e) {}
      throw new Error(msg);
    }
    return r.headers.get('content-type')?.includes('application/json') ? r.json() : r.text();
  }

  /** 带真实上传进度的 multipart 上传 */
  function upload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', base + '/api/ingest');
      xhr.upload.onprogress = e => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
        else { try { reject(new Error(JSON.parse(xhr.responseText).detail)); } catch (e) { reject(new Error('HTTP ' + xhr.status)); } }
      };
      xhr.onerror = () => reject(new Error('上传失败：后端服务是否已启动？'));
      const fd = new FormData();
      fd.append('file', file);
      xhr.send(fd);
    });
  }

  return {
    base,
    listSongs: () => json('/api/songs'),
    getSong: id => json('/api/songs/' + id),
    deleteSong: id => json('/api/songs/' + id, { method: 'DELETE' }),
    touch: id => json(`/api/songs/${id}/touch`, { method: 'POST' }),
    upload,
    separate: id => json(`/api/songs/${id}/separate`, { method: 'POST' }),
    job: jid => json('/api/jobs/' + jid),
    lyrics: (id, kind) => json(`/api/songs/${id}/lyrics${kind ? '?annotated=1' : ''}`),
    matchLyrics: (id, title, artist, album, dur) =>
      json(`/api/songs/${id}/lyrics/auto`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, artist, album, duration: dur })
      }),
    annotate: id => json(`/api/songs/${id}/lyrics/annotate`, { method: 'POST' }),
    saveLyrics: async (id, content) => {
      const fd = new FormData();
      fd.append('content', content);
      return json(`/api/songs/${id}/lyrics`, { method: 'PUT', body: fd });
    },
    fileUrl: (id, name) => `${base}/api/files/${id}/${name}`,
  };
})();

const fmtTime = s => {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60), x = Math.floor(s % 60);
  return `${m}:${String(x).padStart(2, '0')}`;
};
