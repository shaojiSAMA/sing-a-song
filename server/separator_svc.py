"""UVR5 人声/伴奏分离（audio-separator，ONNX 后端，CPU）。
单工作线程串行跑，避免并发爆内存。
"""
from __future__ import annotations
import os, time, json, uuid, queue, threading, traceback, logging

import ffmpegutil, paths

# audio-separator 构造时会用裸名 "ffmpeg" 自检，把资源 bin 前置到 PATH
paths.ensure_dirs()
if os.path.isdir(ffmpegutil.BIN):
    os.environ["PATH"] = ffmpegutil.BIN + os.pathsep + os.environ.get("PATH", "")

# CPU 核心很多时 onnxruntime 默认按全部逻辑核开线程池，小矩阵推理反而会
# 出现线程调度停顿（表现为进度随机卡死数分钟）。统一限制为少量线程。
ORT_THREADS = min(8, max(2, (os.cpu_count() or 8)))

def _patch_onnxruntime_threads(threads: int):
    """在 audio_separator import 之前给 onnxruntime 注入线程数。"""
    import onnxruntime as ort
    if getattr(ort.InferenceSession, "_changlian_patched", False):
        return
    OrigSession = ort.InferenceSession

    class _PatchedSession(OrigSession):
        _changlian_patched = True

        def __init__(self, path_or_bytes, sess_options=None, *args, **kwargs):
            if sess_options is None:
                sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = threads   # 单个算子内部并行
            sess_options.inter_op_num_threads = 1         # 算子间串行
            try:
                sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            except Exception:
                pass
            super().__init__(path_or_bytes, sess_options, *args, **kwargs)

    ort.InferenceSession = _PatchedSession


_patch_onnxruntime_threads(ORT_THREADS)
MODEL_DIR = paths.MODEL_DIR

log = logging.getLogger("separator")
MODEL = "UVR-MDX-NET-Inst_HQ_3.onnx"   # 经典 MDX-Net 人声分离模型，CPU 可用

_jobs: dict[str, dict] = {}
_q: queue.Queue = queue.Queue()
_lock = threading.Lock()


def _atomic_save_manifest(mp: str, m: dict):
    tmp = mp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    for i in range(6):
        try:
            os.replace(tmp, mp)
            return
        except PermissionError:
            time.sleep(0.25 * (i + 1))
    os.replace(tmp, mp)


def _backfill_manifest(sdir: str) -> bool:
    """分离完成后由 worker 直接回填 manifest（不依赖前端轮询）。"""
    mp = os.path.join(sdir, "manifest.json")
    if not os.path.exists(mp):
        return False
    try:
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
        if not m.get("instrumental"):
            m["instrumental"] = "instrumental.wav"
            m["vocals"] = "vocals.wav"
            _atomic_save_manifest(mp, m)
        return True
    except Exception:
        log.exception("manifest backfill failed")
        return False


def outputs_exist(sdir: str) -> bool:
    return (os.path.exists(os.path.join(sdir, "vocals.wav")) and
            os.path.exists(os.path.join(sdir, "instrumental.wav")))


def _run(job_id: str, sdir: str, source_file: str):
    job = _jobs[job_id]
    try:
        job["status"] = "running"; job["started_at"] = time.time()
        wav_in = os.path.join(sdir, "_sep_input.wav")
        ffmpegutil.to_wav(source_file, wav_in)
        job["stage"] = "model"
        import torch
        torch.set_num_threads(ORT_THREADS)
        try:
            torch.set_num_interop_threads(1)   # 仅首次调用生效
        except RuntimeError:
            pass
        from audio_separator.separator import Separator
        # output_dir 在构造时传入：模型实例的输出目录在 load_model 时固化
        sep = Separator(log_level=logging.WARNING, output_dir=sdir,
                        model_file_dir=MODEL_DIR, output_format="WAV")
        sep.load_model(MODEL)
        job["stage"] = "separate"
        with _lock:
            outs = sep.separate(wav_in, custom_output_names={
                "Vocals": "vocals", "Instrumental": "instrumental"})
        for expect in ("vocals.wav", "instrumental.wav"):
            p = os.path.join(sdir, expect)
            if not os.path.exists(p):
                raise RuntimeError(f"分离输出缺失 {expect}，实际输出: {outs}")
        try:
            os.remove(wav_in)
        except OSError:
            pass
        _backfill_manifest(sdir)   # 关键：完成即回填，前端断轮询也不丢状态
        job.update(status="done", finished_at=time.time(),
                   result={"instrumental": "instrumental.wav", "vocals": "vocals.wav"})
    except Exception as e:
        log.exception("separation failed")
        job.update(status="error", finished_at=time.time(),
                   error=str(e)[:600], tb=traceback.format_exc()[-1200:])


def _worker():
    while True:
        jid, song_dir, source = _q.get()
        _run(jid, song_dir, source)
        _q.task_done()


threading.Thread(target=_worker, daemon=True, name="uvr-worker").start()


def active_job_for(sdir: str) -> str | None:
    """该目录是否已有排队/运行中的任务（避免重复分离）。"""
    with _lock:
        for j in _jobs.values():
            if j.get("song_dir") == sdir and j["status"] in ("queued", "running"):
                return j["id"]
    return None


def enqueue(sdir: str, source_file: str) -> str:
    existing = active_job_for(sdir)
    if existing:
        return existing
    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"id": jid, "status": "queued", "stage": "queue",
                  "queued_at": time.time(), "song_dir": sdir}
    _q.put((jid, sdir, source_file))
    return jid


def status(jid: str) -> dict | None:
    j = _jobs.get(jid)
    if not j:
        return None
    out = {k: v for k, v in j.items() if k not in ("tb",)}
    if j["status"] == "running":
        out["elapsed"] = round(time.time() - j.get("started_at", time.time()), 1)
    return out
