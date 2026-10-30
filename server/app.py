"""唱练 · 本地后端（仅监听 127.0.0.1）
/  静态网页；/api/* 格式转换入库、UVR 分离、歌词匹配、假名注音。
"""
from __future__ import annotations
import os, sys, json, time, uuid, shutil, tempfile, threading, logging, re

# 必须在 import torch / onnxruntime 等原生数值库之前设置：
# CPU 推理在线程中运行时，OpenMP/MKL 线程池在第二次推理可能死锁（表现为进度卡死）
_THREADS = str(min(4, os.cpu_count() or 4))
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_k, _THREADS)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import ffmpegutil, ingest, lyrics as lyrics_svc, separator_svc
import furigana as furi_svc

import paths
paths.ensure_dirs()
ROOT = paths.HOME
WEB = paths.WEB_DIR
LIB = paths.LIB_DIR

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("api")

app = FastAPI(title="changlian-local")


# ---------------- manifest 管理 ----------------
def song_dir(sid: str) -> str:
    d = os.path.join(LIB, sid)
    if not os.path.isdir(d):
        raise HTTPException(404, "歌曲不存在")
    return d


def load_manifest(sid: str) -> dict:
    d = song_dir(sid)
    mp = os.path.join(d, "manifest.json")
    if not os.path.exists(mp):
        raise HTTPException(404, "manifest 丢失")
    with open(mp, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(sid: str, m: dict):
    # 原子写：先写临时文件再替换，避免多线程/异常退出时留下 0 字节 manifest。
    # Windows 上杀软/索引器可能瞬时占用文件导致 WinError 5，做几次重试。
    p = os.path.join(song_dir(sid), "manifest.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    for i in range(6):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.25 * (i + 1))
    try:
        os.replace(tmp, p)
    except OSError:
        with open(p, "w", encoding="utf-8") as f:  # 最终兜底：直接覆写
            json.dump(m, f, ensure_ascii=False, indent=2)
        try:
            os.remove(tmp)
        except OSError:
            pass


def public_manifest(m: dict) -> dict:
    out = dict(m)
    out["title"] = m.get("title") or m.get("name")
    out["files"] = {}
    for k in ("source", "instrumental", "vocals"):
        if m.get(k):
            out["files"][k] = f"/api/files/{m['id']}/{k}"
    return out


# ---------------- 基础接口 ----------------
@app.get("/api/health")
def health():
    return {"ok": True, "ffmpeg": ffmpegutil.available(),
            "encrypted_exts": sorted(ingest.ENCRYPTED_EXTS)}


@app.get("/api/songs")
def list_songs():
    items = []
    for sid in sorted(os.listdir(LIB), reverse=True):
        mp = os.path.join(LIB, sid, "manifest.json")
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    items.append(public_manifest(json.load(f)))
            except Exception:
                pass
    items.sort(key=lambda m: m.get("last_opened") or m.get("created_at", 0), reverse=True)
    return items


@app.get("/api/songs/{sid}")
def get_song(sid: str):
    return public_manifest(load_manifest(sid))


@app.post("/api/songs/{sid}/touch")
def touch_song(sid: str):
    m = load_manifest(sid)
    m["last_opened"] = time.time()
    save_manifest(sid, m)
    return {"ok": True}


@app.post("/api/ingest")
async def ingest_file(file: UploadFile = File(...)):
    sid = time.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8]
    d = os.path.join(LIB, sid)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "_upload" + os.path.splitext(file.filename or "")[1].lower())
    with open(tmp, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size = os.path.getsize(tmp)
    try:
        info = ingest.process(tmp, file.filename or "audio", d)
    except Exception as e:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, f"入库失败：{e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    tags = info.get("tags") or {}
    m = {
        "id": sid,
        "name": tags.get("title") or os.path.splitext(file.filename or "未命名")[0],
        "artist": tags.get("artist", ""),
        "album": tags.get("album", ""),
        "created_at": time.time(),
        "size": size,
        "duration": info.get("duration"),
        "last_opened": time.time(),
        "source": info["source"],
        "format": info.get("format"),
        "source_kind": info.get("source_kind", "native"),
        "instrumental": None, "vocals": None,
        "lyrics": None, "lyrics_annotated": None, "lyrics_source": None,
        "sep_job": None,
    }
    save_manifest(sid, m)
    return public_manifest(m)


@app.get("/api/files/{sid}/{kind}")
def get_file(sid: str, kind: str):
    m = load_manifest(sid)
    key = {"source": m["source"], "instrumental": m.get("instrumental"),
           "vocals": m.get("vocals")}.get(kind)
    if not key:
        raise HTTPException(404, "文件不存在")
    p = os.path.join(song_dir(sid), key)
    media = "audio/wav" if key.endswith(".wav") else "audio/mpeg" if key.endswith(".mp3") else "audio/flac"
    return FileResponse(p, media_type=media)


@app.delete("/api/songs/{sid}")
def delete_song(sid: str):
    shutil.rmtree(song_dir(sid), ignore_errors=True)
    return {"ok": True}


# ---------------- 人声分离 ----------------
@app.post("/api/songs/{sid}/separate")
def separate(sid: str):
    m = load_manifest(sid)
    d = song_dir(sid)
    if m.get("instrumental"):
        return {"job_id": m.get("sep_job"), "already": True}
    # wav 已在盘上但 manifest 没标记（上次跑完后状态丢失）：直接恢复，不再分离
    if separator_svc.outputs_exist(d):
        m["instrumental"] = "instrumental.wav"
        m["vocals"] = "vocals.wav"
        save_manifest(sid, m)
        return {"job_id": m.get("sep_job"), "already": True, "recovered": True}
    jid = separator_svc.enqueue(d, os.path.join(d, m["source"]))
    m["sep_job"] = jid
    save_manifest(sid, m)
    return {"job_id": jid}


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    j = separator_svc.status(jid)
    if not j:
        raise HTTPException(404)
    if j["status"] == "done":
        # 回填到对应歌曲
        for sid in os.listdir(LIB):
            mp = os.path.join(LIB, sid, "manifest.json")
            if not os.path.exists(mp):
                continue
            with open(mp, encoding="utf-8") as f:
                mm = json.load(f)
            if mm.get("sep_job") == jid and not mm.get("instrumental"):
                mm["instrumental"] = "instrumental.wav"
                mm["vocals"] = "vocals.wav"
                save_manifest(sid, mm)
    return j


# ---------------- 歌词 ----------------
@app.post("/api/songs/{sid}/lyrics/auto")
def auto_lyrics(sid: str):
    m = load_manifest(sid)
    hit = lyrics_svc.match(m.get("name", ""), m.get("artist", ""), m.get("duration"))
    if not hit:
        raise HTTPException(404, f"所有在线歌词库（LRCLIB / 网易云 / QQ音乐）均未命中，"
                                 f"可把 *.lrc 放入程序目录下的 lrcs 文件夹：{paths.LRCS_DIR}，或在练习页手动粘贴")
    with open(os.path.join(song_dir(sid), "lyrics.lrc"), "w", encoding="utf-8") as f:
        f.write(hit["lrc"])
    m["lyrics"] = "lyrics.lrc"
    m["lyrics_annotated"] = None
    m["lyrics_source"] = hit["source"] + ("（时间轴）" if hit["synced"] else "（无时间轴）")
    save_manifest(sid, m)
    return {"ok": True, "source": m["lyrics_source"], "lrc": hit["lrc"]}


@app.get("/api/songs/{sid}/lyrics")
def get_lyrics(sid: str, annotated: int = 0):
    m = load_manifest(sid)
    key = "lyrics_annotated" if annotated else "lyrics"
    if not m.get(key):
        raise HTTPException(404, "暂无歌词")
    p = os.path.join(song_dir(sid), m[key])
    return FileResponse(p, media_type="text/plain; charset=utf-8")


@app.post("/api/songs/{sid}/lyrics")
async def save_lyrics(sid: str, content: str = Form(...)):
    m = load_manifest(sid)
    with open(os.path.join(song_dir(sid), "lyrics.lrc"), "w", encoding="utf-8") as f:
        f.write(content)
    m["lyrics"] = "lyrics.lrc"
    m["lyrics_annotated"] = None
    m["lyrics_source"] = "手动编辑"
    save_manifest(sid, m)
    return {"ok": True}


@app.post("/api/songs/{sid}/lyrics/annotate")
def annotate_lyrics(sid: str):
    m = load_manifest(sid)
    if not m.get("lyrics"):
        raise HTTPException(400, "请先匹配或粘贴歌词")
    src = os.path.join(song_dir(sid), m["lyrics"])
    with open(src, encoding="utf-8") as f:
        raw = f.read()
    out_lines, n = [], 0
    for line in raw.splitlines():
        mt = re.match(r"^((?:\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\])+)(.*)$", line)
        if not mt:
            out_lines.append(line)
            continue
        tags, body = mt.group(1), mt.group(2).strip()
        if not body:
            out_lines.append(tags)
            continue
        trans = ""
        mm = re.search(r"\s<([^>]*)>$", body)
        if mm:
            trans, body = mm.group(1), body[:mm.start()].strip()
        marked, romaji = furi_svc.annotate_line(body)
        if marked != body:
            n += 1
        suffix = f"|{romaji}" if romaji else ""
        if trans:
            suffix += f" <{trans}>"
        out_lines.append(f"{tags}{marked}{suffix}")
    dst = os.path.join(song_dir(sid), "lyrics.furi.lrc")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    m["lyrics_annotated"] = "lyrics.furi.lrc"
    save_manifest(sid, m)
    return {"ok": True, "annotated_lines": n}


# ---------------- 静态页面（挂在最后，避免覆盖 /api） ----------------
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8178, log_level="warning")
