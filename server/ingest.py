"""入库管线：
1) 平台加密缓存（ncm/qmc/kgm/kgma/vpr/kwm，OpenYYY 同类格式）→ MIT music_unlock 解密；
2) 浏览器原生可播容器（mp3/flac/ogg/m4a/aac/wav）→ 原样保留；
3) 其它容器（ape/wma/aiff/opus…）→ ffmpeg 转 mp3。
"""
from __future__ import annotations
import os, sys, json, time, shutil, logging

log = logging.getLogger("ingest")

import paths
VENDOR = paths.VENDOR_DIR
sys.path.insert(0, VENDOR)
from music_unlock.formats import pick_decoder, supported_extensions  # noqa: E402
from music_unlock.errors import UnsupportedError  # noqa: E402

import ffmpegutil  # noqa: E402

try:
    from mutagen import File as MutagenFile  # noqa: E402
except Exception:
    MutagenFile = None

# 浏览器 <audio> 普遍支持的容器
NATIVE_EXTS = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wav", ".webm", ".mp4"}
ENCRYPTED_EXTS = set(supported_extensions())


def _read_tags(path: str) -> dict:
    tags = {"title": "", "artist": "", "album": ""}
    if not MutagenFile:
        return tags
    try:
        mf = MutagenFile(path, easy=True)
        if mf and mf.tags:
            for k in ("title", "artist", "album"):
                v = mf.tags.get(k)
                if v:
                    tags[k] = " / ".join(v) if isinstance(v, list) else str(v)
    except Exception:
        pass
    return tags


def process(upload_path: str, filename: str, song_dir: str) -> dict:
    """返回 manifest 片段：source/format/tags/duration/source_kind。"""
    os.makedirs(song_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    stem = os.path.splitext(os.path.split(filename)[1])[0]
    result = {"original_name": filename, "tags": {}, "duration": None}

    try_decrypt = ext in ENCRYPTED_EXTS
    if not try_decrypt:
        # 魔数嗅探兜底
        with open(upload_path, "rb") as f:
            head = f.read(16)
        if head[:8] == b"CTENFDAM":
            try_decrypt = True

    if try_decrypt:
        log.info("检测到加密云格式 %s，尝试本地解密", ext)
        from pathlib import Path
        try:
            dec = pick_decoder(Path(upload_path)).decode(Path(upload_path), __import__(
                "music_unlock.formats.base", fromlist=["DecodeOptions"]).DecodeOptions())
        except UnsupportedError:
            dec = None
        if dec is not None and dec.container not in ("bin", ""):
            raw = os.path.join(song_dir, "_decrypted." + dec.suggested_extension)
            with open(raw, "wb") as f:
                f.write(dec.payload)
            result["source_kind"] = "decrypted:" + (dec.source or ext.lstrip("."))
            result["tags"] = {**_read_tags(raw), **{k: v for k, v in (dec.tags or {}).items() if v}}
            final = _finalize(raw, song_dir)
            result.update(final)
            result["duration"] = ffmpegutil.duration(os.path.join(song_dir, result["source"]))
            return result
        log.warning("解密失败或容器未知，回退 ffmpeg 转码")

    # 普通音频：先 ffprobe 判断是否真的能读
    dur = ffmpegutil.duration(upload_path)
    if dur is None:
        raise ValueError("文件不是可识别的音频（ffprobe 无法解析），也不是支持的加密云格式")

    if ext in NATIVE_EXTS:
        dst = os.path.join(song_dir, "source" + (ext if ext != ".oga" else ".ogg"))
        shutil.copyfile(upload_path, dst)
        result["source"] = os.path.basename(dst)
        result["format"] = ext.lstrip(".")
        result["source_kind"] = "native"
    else:
        # ape/wma/aiff/opus 等 → mp3
        dst = os.path.join(song_dir, "source.mp3")
        ffmpegutil.to_mp3(upload_path, dst)
        result["source"] = "source.mp3"
        result["format"] = "mp3"
        result["source_kind"] = "transcoded:" + ext.lstrip(".")
    result["tags"] = _read_tags(os.path.join(song_dir, result["source"]))
    if not result["tags"].get("title"):
        result["tags"]["title"] = stem
    result["duration"] = ffmpegutil.duration(os.path.join(song_dir, result["source"]))
    return result


def _finalize(raw: str, song_dir: str) -> dict:
    """解密产物若浏览器不能直接播则转 mp3，否则改名为 source.*。"""
    ext = os.path.splitext(raw)[1].lower()
    if ext in NATIVE_EXTS:
        final = os.path.join(song_dir, "source" + ext)
        if os.path.abspath(raw) != os.path.abspath(final):
            shutil.move(raw, final)
        return {"source": os.path.basename(final), "format": ext.lstrip(".")}
    final = os.path.join(song_dir, "source.mp3")
    ffmpegutil.to_mp3(raw, final)
    os.remove(raw)
    return {"source": "source.mp3", "format": "mp3"}
