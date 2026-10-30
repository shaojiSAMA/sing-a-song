/* WAV/AudioBuffer → MP3（lamejs），以及“选择任意目录保存” */
const MP3 = (() => {
  /** AudioBuffer 编码为 MP3 Blob，192kbps */
  function encode(buffer, kbps = 192) {
    const sr = buffer.sampleRate;
    const nch = Math.min(2, buffer.numberOfChannels);
    const enc = new lamejs.Mp3Encoder(nch, sr, kbps);
    const left = floatToInt16(buffer.getChannelData(0));
    const right = nch > 1 ? floatToInt16(buffer.getChannelData(1)) : left;
    const block = 1152;
    const parts = [];
    for (let i = 0; i < left.length; i += block) {
      const l = left.subarray(i, i + block);
      const r = right.subarray(i, i + block);
      const d = nch > 1 ? enc.encodeBuffer(l, r) : enc.encodeBuffer(l);
      if (d.length) parts.push(d);
    }
    const end = enc.flush();
    if (end.length) parts.push(end);
    return new Blob(parts, { type: 'audio/mpeg' });
  }

  function floatToInt16(f) {
    const out = new Int16Array(f.length);
    for (let i = 0; i < f.length; i++) {
      let s = Math.max(-1, Math.min(1, f[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  /**
   * 第一步：在用户点击手势内立刻弹出“另存为”，拿到目标句柄。
   * 必须在任何 await（解码/编码）之前调用，否则浏览器会以
   * "Must be handling a user gesture" 拒绝弹框。
   * 用户取消时抛出 AbortError。不支持 File System Access 的浏览器返回 null。
   */
  async function pickSave(suggestedName) {
    if (!window.showSaveFilePicker) return null;
    return window.showSaveFilePicker({
      suggestedName,
      types: [{ description: 'MP3 音频', accept: { 'audio/mpeg': ['.mp3'] } }],
    });
  }

  /** 第二步：编码完成后写入用户选定的文件；无句柄时退化为普通下载 */
  async function write(handle, blob, fallbackName) {
    if (handle) {
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = fallbackName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }
  }

  /** 把 url 拉取并解码为 AudioBuffer（带缓存） */
  async function decodeUrl(url) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const ab = await (await fetch(url)).arrayBuffer();
    const buf = await ctx.decodeAudioData(ab);
    return { ctx, buf };
  }

  return { encode, pickSave, write, decodeUrl };
})();
