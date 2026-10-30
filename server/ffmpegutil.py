"""ffmpeg / ffprobe 封装：可执行文件取自 E:\\singren\\bin，其次 PATH。"""
from __future__ import annotations
import os, shutil, subprocess, json, sys

import paths
BIN = paths.BIN_DIR


def _exe(name: str) -> str:
    p = os.path.join(BIN, name + (".exe" if os.name == "nt" else ""))
    return p if os.path.exists(p) else (shutil.which(name) or name)


FFMPEG = _exe("ffmpeg")
FFPROBE = _exe("ffprobe")


def available() -> bool:
    try:
        r = subprocess.run([FFMPEG, "-version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="ignore")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-1500:])
    return p.returncode, p.stderr[-400:]


def duration(path: str) -> float | None:
    try:
        p = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "json", path], capture_output=True, text=True, timeout=60)
        return float(json.loads(p.stdout)["format"]["duration"])
    except Exception:
        return None


def to_wav(src: str, dst: str, sr: int = 44100) -> str:
    """统一转 16bit 立体声 wav，供分离模型使用。"""
    run([FFMPEG, "-y", "-i", src, "-ac", "2", "-ar", str(sr),
         "-c:a", "pcm_s16le", dst], timeout=1200)
    return dst


def to_mp3(src: str, dst: str, bitrate: str = "320k") -> str:
    """浏览器不友好的容器（ape/wma/aiff 等）统一转 mp3。"""
    run([FFMPEG, "-y", "-i", src, "-c:a", "libmp3lame", "-b:a", bitrate, dst], timeout=1200)
    return dst
