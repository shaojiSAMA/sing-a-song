# -*- mode: python ; coding: utf-8 -*-
"""唱练发行包构建：pyinstaller --noconfirm build.spec"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block = (
    "matplotlib", "pandas", "tkinter", "pytest", "IPython", "jupyter",
    # PIL/torchvision/torchgen/functorch 均为运行时依赖，不能排除
)

datas, binaries, hiddenimports = [], [], []
for pkg in [
    "audio_separator", "onnxruntime", "unidic_lite", "cutlet", "fugashi", "jaconv",
    "onnx2torch", "rotary_embedding_torch", "soundfile", "librosa", "lazy_loader",
    "scipy", "pydub", "torchvision", "PIL",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

for pkg in ["uvicorn", "anyio", "starlette", "fastapi", "pydantic", "pydantic_core",
            "torchgen", "functorch"]:
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

hiddenimports += [
    "multipart", "multipart.multipart",
    "Crypto", "Crypto.Cipher.AES", "Crypto.Util.Padding",
    "mutagen", "audioread",
    # 本项目扁平模块（位于 server/，pathex 已加入）
    "app", "ingest", "ffmpegutil", "lyrics", "furigana", "separator_svc", "paths",
]

# 只读资源：网页、ffmpeg、内置模型、music_unlock 解密库
for src, dst in [("web", "web"), ("bin", "bin"), ("models", "models"),
                 (os.path.join("server", "vendor"), "vendor")]:
    datas.append((src, dst))

a = Analysis(
    ["launcher.py"],
    pathex=[os.path.abspath("server")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=list(block),
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts,
    exclude_binaries=True,
    name="唱练",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name="唱练",
)
