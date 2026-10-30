"""路径中心：同时兼容开发态（python 源码运行）与封装态（PyInstaller frozen）。

- RES_DIR：只读资源目录（ffmpeg、网页、内置模型、vendor 库），封装后位于 _internal；
- HOME：可写的用户目录，封装后是 exe 同级目录，开发态是项目根。
所有用户数据（歌曲库、模型副本、歌词、运行时文件）都放在 HOME 下。
"""
from __future__ import annotations
import os, sys, shutil

FROZEN = bool(getattr(sys, "frozen", False))
_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SERVER_DIR)

if FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = os.path.abspath(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = RES_DIR = _PROJECT_ROOT

HOME = os.environ.get("SINGREN_HOME") or APP_DIR

BIN_DIR = os.path.join(RES_DIR, "bin")
WEB_DIR = os.path.join(RES_DIR, "web")
MODEL_RES_DIR = os.path.join(RES_DIR, "models")
# vendor/music_unlock：开发态在 server/vendor，封装时 add-data 到 RES/vendor
VENDOR_DIR = os.path.join(RES_DIR, "vendor") if FROZEN else os.path.join(_SERVER_DIR, "vendor")

MODEL_DIR = os.path.join(HOME, "models")
LIB_DIR = os.path.join(HOME, "library")
LRCS_DIR = os.path.join(HOME, "lrcs")
RUNTIME_DIR = os.path.join(HOME, "runtime")


def ensure_dirs() -> None:
    for d in (MODEL_DIR, LIB_DIR, LRCS_DIR, RUNTIME_DIR):
        os.makedirs(d, exist_ok=True)


def seed_models() -> None:
    """首次运行：把内置 UVR 模型复制到可写的 HOME/models（audio-separator 会写校验 json）。"""
    ensure_dirs()
    if not os.path.isdir(MODEL_RES_DIR):
        return
    for name in os.listdir(MODEL_RES_DIR):
        src, dst = os.path.join(MODEL_RES_DIR, name), os.path.join(MODEL_DIR, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
