"""歌词自动匹配（多源级联）：
1) LRCLIB（开放免费、无需 key；欧美/日系同人覆盖好）按 歌手/曲名/时长 匹配；
2) 网易云音乐公开接口（日语歌覆盖极广，取日文原文 LRC，注音由本地 MeCab 完成）；
3) QQ 音乐公开接口（日系版权与动画歌覆盖好）；
4) 本地歌词库（程序目录 lrcs：歌手 - 歌名.lrc，文件名模糊匹配）。
"""
from __future__ import annotations
import os, re, glob, base64, difflib, urllib.parse, urllib.request, json

import paths
LOCAL_DIR = paths.LRCS_DIR

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": CHROME_UA}
H_163 = {**HEADERS, "Referer": "https://music.163.com/"}
H_QQ = {**HEADERS, "Referer": "https://y.qq.com/"}


def _http_json(url: str, headers: dict, timeout: float = 12.0):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[\s\-_·.,\[\]【】（）()「」『』]+", "", s)
    s = re.sub(r"(feat\.?|ft\.?).*$", "", s)
    return s


def _looks_japanese(*texts: str) -> bool:
    """含平假名/片假名是日语的强信号（汉字无法区分中日）。"""
    return bool(re.search(r"[぀-ゟ゠-ヿ]", " ".join(t or "" for t in texts)))


# ---------------- LRC 清洗 ----------------
_ID_TAG = re.compile(r"^\[(ti|ar|al|by|offset|length|re|ve|au|la|id):", re.I)
# 创作人员/制作信息行（中日英），不应进入歌词与注音
_META_WORDS = (
    "作词", "作詞", "作曲", "编曲", "編曲", "制作人", "製作人", "出品", "发行", "發行",
    "和声", "合声", "和聲", "混音", "母带", "母帶", "录音", "錄音", "人声制作", "人聲製作",
    "吉他", "貝斯", "贝斯", "架子鼓", "键盘", "鍵盤", "弦乐", "弦樂", "鼓手",
    "声乐指导", "聲樂指導", "企划", "企劃", "监制", "監製", "op", "ed", "tvアニメ",
    "lyrics by", "lyrics:", "music by", "music:", "composed by", "compose:",
    "arranged by", "arranger", "arr:", "produced by", "producer",
    "vocal", "guitar", "bass", "drums", "drum", "keyboard", "keyboards", "piano",
    "strings", "mix", "mastered", "mastering",
)
_META_RE = re.compile(
    r"^\s*(?:[【\[]?\s*)"
    r"(?:" + "|".join(re.escape(w) for w in _META_WORDS) + r")"
    r"\s*[\]】]?\s*[:：>\-]?", re.I)


def _strip_meta(text: str) -> str:
    """剥掉 ID 标签行与创作信息行，保留有时间轴的正文；顺带去掉纯空白时间戳行。"""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if _ID_TAG.match(s):
            continue
        body = re.sub(r"^(\[\d{1,2}:\d{1,2}(?:[.:]\d{1,3})?\])+", "", s).strip()
        if body and _META_RE.match(body):
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def _kana_lines_ratio(text: str) -> float:
    bodies = [re.sub(r"^\[[^\]]*\]", "", ln).strip() for ln in text.splitlines()]
    bodies = [b for b in bodies if b]
    if not bodies:
        return 0.0
    return sum(1 for b in bodies if re.search(r"[぀-ゟ゠-ヿ]", b)) / len(bodies)


def _has_sync(text: str) -> bool:
    return bool(re.search(r"\[\d{1,2}:\d{2}[.:]\d{1,3}\]", text or ""))


# ---------------- 候选打分（标题/歌手/时长） ----------------
def _rank_candidates(cands: list[dict], title: str, artist: str,
                     duration: float | None) -> list[dict]:
    nt, na = _norm(title), _norm(artist)

    def score(c):
        cn, ca = _norm(c.get("name", "")), _norm(c.get("artist", ""))
        s = difflib.SequenceMatcher(None, nt, cn).ratio() * 5
        if nt and (nt in cn or cn in nt):
            s += 2
        if na and ca:
            if na in ca or ca in na:
                s += 4.5
            else:
                s += difflib.SequenceMatcher(None, na, ca).ratio() * 2.5
        d = c.get("duration")
        if duration and d:
            dd = abs(float(duration) - float(d))
            s += 4 if dd <= 3 else 2.5 if dd <= 8 else max(-6, 2 - dd / 4)
        if re.search(r"(live|现场|現場|伴奏|inst\.?\s*$|karaoke|cover|翻唱|翻奏|remix|节目|節目)",
                     c.get("name", ""), re.I):
            s -= 3
        return s

    return sorted(cands, key=score, reverse=True)


# ---------------- LRCLIB ----------------
def _lrc_quality(text: str) -> float:
    """歌词正文质量分：日文纯歌词优先，惩罚行内英文翻译（LRCLIB 常用 ^ 衔接）。"""
    if not text:
        return -100
    bodies = [re.sub(r"^\[[^\]]*\]", "", ln).strip() for ln in text.splitlines()]
    bodies = [b for b in bodies if b]
    if not bodies:
        return -100
    sc = 0.0
    for b in bodies:
        if "^" in b: sc -= 8
        jp = len(re.findall(r"[぀-ヿ一-鿿]", b))
        en = len(re.findall(r"[A-Za-z]", b))
        if jp: sc += 1
        if en > 4 and jp and en / max(1, jp + en) > 0.35: sc -= 4
        if jp == 0 and en > 4: sc -= 2
    return sc


def _clean_lrclib(text: str) -> str:
    out = []
    for ln in text.splitlines():
        if "^" in ln:
            head, _, tail = ln.partition("^")
            if head.count("[") == tail.count("]"):
                ln = head.rstrip()
        out.append(ln)
    return _strip_meta("\n".join(out))


def _pick_lrclib(records: list[dict], duration: float | None) -> dict | None:
    if not records:
        return None
    def score(it):
        sc = 0
        text = it.get("syncedLyrics") or it.get("plainLyrics") or ""
        if it.get("syncedLyrics"): sc += 10
        if it.get("instrumental"): sc -= 50
        sc += _lrc_quality(text)
        if duration and it.get("duration"):
            sc -= min(10, abs(float(it["duration"]) - duration) / 3)
        return sc
    return sorted(records, key=score, reverse=True)[0]


def match_lrclib(title: str, artist: str, duration: float | None) -> dict | None:
    title, artist = (title or "").strip(), (artist or "").strip()
    if not title:
        return None
    try:
        recs, seen = [], set()
        def push(it):
            if it and it.get("id") not in seen:
                seen.add(it["id"]); recs.append(it)
        q = urllib.parse.urlencode({"artist_name": artist, "track_name": title,
                                    **({"duration": round(duration)} if duration else {})})
        try:
            push(_http_json(f"https://lrclib.net/api/get?{q}", HEADERS))
        except Exception:
            pass
        q = urllib.parse.urlencode({"track_name": title})
        try:
            for it in _http_json(f"https://lrclib.net/api/search?{q}", HEADERS) or []:
                push(it)
        except Exception:
            pass
        if artist:
            na = _norm(artist)
            filtered = [r for r in recs if na in _norm(r.get("artistName", "")) or
                        _norm(r.get("artistName", "")) in na]
            if filtered:
                recs = filtered
        it = _pick_lrclib(recs, duration)
        if it and (it.get("syncedLyrics") or it.get("plainLyrics")):
            synced = bool(it.get("syncedLyrics"))
            lrc = it.get("syncedLyrics") or _plain_to_lrc(it.get("plainLyrics") or "")
            lrc = _clean_lrclib(lrc)
            # 日语歌却拿不到带假名的歌词（多半是英文/罗马音版本），让给后续日语源
            if _looks_japanese(title, artist) and _kana_lines_ratio(lrc) < 0.15:
                return None
            return {"lrc": lrc, "synced": synced,
                    "source": f"LRCLIB · {it.get('artistName','')} - {it.get('trackName','')}"}
    except Exception:
        return None
    return None


def _plain_to_lrc(text: str) -> str:
    out = []
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if line:
            out.append(f"[{(i*3)//60:02d}:{(i*3)%60:02}.00]{line}")
    return "\n".join(out)


# ---------------- 网易云音乐 ----------------
def match_netease(title: str, artist: str, duration: float | None) -> dict | None:
    if not title:
        return None
    try:
        kw = f"{artist} {title}".strip() if artist else title
        q = urllib.parse.urlencode({"s": kw, "type": 1, "limit": 12, "offset": 0})
        data = _http_json(f"https://music.163.com/api/search/get?{q}", H_163)
        songs = (data.get("result") or {}).get("songs") or []
        cands = [{
            "name": s.get("name", ""),
            "artist": ",".join(a.get("name", "") for a in s.get("artists", [])),
            "duration": (s.get("duration") or 0) / 1000.0,
            "id": s.get("id"),
        } for s in songs if s.get("id")]
        for c in _rank_candidates(cands, title, artist, duration)[:4]:
            try:
                d = _http_json(
                    f"https://music.163.com/api/song/lyric?id={c['id']}&lv=1&kv=1&tv=-1", H_163)
            except Exception:
                continue
            if d.get("nolyric") or d.get("uncollected"):
                continue
            lrc = ((d.get("lrc") or {}).get("lyric")) or ""
            if not lrc.strip():
                continue
            lrc = _strip_meta(lrc)
            if _looks_japanese(title, artist) and _kana_lines_ratio(lrc) < 0.15:
                continue
            return {"lrc": lrc, "synced": _has_sync(lrc),
                    "source": f"网易云 · {c['artist']} - {c['name']}"}
    except Exception:
        return None
    return None


# ---------------- QQ 音乐 ----------------
def _decode_qq_lyric(raw: str) -> str:
    raw = raw.strip()
    # nobase64=1 时是明文；否则为 base64（历史格式）
    if raw.startswith("[") or "\n[" in raw[:200]:
        return raw
    try:
        b = base64.b64decode(raw + "=" * (-len(raw) % 4))
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
    except Exception:
        pass
    return ""


def match_qq(title: str, artist: str, duration: float | None) -> dict | None:
    if not title:
        return None
    try:
        kw = f"{artist} {title}".strip() if artist else title
        q = urllib.parse.quote(kw)
        url = (f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w={q}"
               f"&format=json&p=1&n=12&g_tk=5381&inCharset=utf-8&outCharset=utf-8")
        data = _http_json(url, H_QQ)
        songs = (((data.get("data") or {}).get("song") or {}).get("list")) or []
        cands = [{
            "name": s.get("songname", ""),
            "artist": ",".join(a.get("name", "") for a in s.get("singer", [])),
            "duration": s.get("interval"),
            "mid": s.get("songmid"),
        } for s in songs if s.get("songmid")]
        for c in _rank_candidates(cands, title, artist, duration)[:4]:
            try:
                url = ("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
                       f"?songmid={c['mid']}&g_tk=5381&format=json&nobase64=1"
                       f"&inCharset=utf-8&outCharset=utf-8")
                d = _http_json(url, H_QQ)
            except Exception:
                continue
            lrc = _decode_qq_lyric(d.get("lyric") or "")
            if not lrc.strip():
                continue
            lrc = _strip_meta(lrc)
            if _looks_japanese(title, artist) and _kana_lines_ratio(lrc) < 0.15:
                continue
            return {"lrc": lrc, "synced": _has_sync(lrc),
                    "source": f"QQ音乐 · {c['artist']} - {c['name']}"}
    except Exception:
        return None
    return None


# ---------------- 本地歌词库 ----------------
def match_local(title: str, artist: str) -> dict | None:
    if not os.path.isdir(LOCAL_DIR):
        return None
    target = _norm((artist or "") + title)
    best, best_sc = None, 0
    for path in glob.glob(os.path.join(LOCAL_DIR, "*.lrc")):
        name = _norm(os.path.splitext(os.path.basename(path))[0])
        sc = difflib.SequenceMatcher(None, target, name).ratio()
        toks = sum(1 for t in (_norm(artist), _norm(title)) if t and t in name)
        sc += 0.15 * toks
        if sc > best_sc:
            best, best_sc = path, sc
    if best and best_sc >= 0.45:
        with open(best, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"lrc": _strip_meta(content), "synced": _has_sync(content),
                "source": "本地歌词库 · " + os.path.basename(best)}
    return None


# ---------------- 级联入口 ----------------
def match(title: str, artist: str, duration: float | None) -> dict | None:
    for fn in (
        lambda: match_lrclib(title, artist, duration),
        lambda: match_netease(title, artist, duration),
        lambda: match_qq(title, artist, duration),
        lambda: match_local(title, artist),
    ):
        hit = fn()
        if hit and hit.get("lrc", "").strip():
            return hit
    return None
