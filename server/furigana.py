"""日语汉字假名注音 + 罗马音（离线：fugashi + unidic-lite + cutlet）。
思路与 MisuzuMusic 的内联注音一致，读音由本地词典真实形态分析得到。
输出标记沿用《》： 夢《ゆめ》
"""
from __future__ import annotations
import os, re, threading

_tagger = None
_cutlet = None
_lock = threading.Lock()
KANJI = re.compile(r"[㐀-䶿一-鿿々ヿ]")


def _ensure():
    global _tagger, _cutlet
    if _tagger is None:
        import fugashi, unidic_lite, jaconv  # noqa: F401
        import paths
        paths.ensure_dirs()
        dic = unidic_lite.DICDIR
        # Windows 下 MeCab 默认找 c:\mecab\mecabrc；rc 放可写的运行时目录（封装后词典目录只读）
        rc = os.path.join(paths.RUNTIME_DIR, "mecabrc")
        if not os.path.exists(rc):
            with open(rc, "w", encoding="utf-8") as f:
                f.write("")
        dic = dic.replace("\\", "/")
        rc = rc.replace("\\", "/")
        args = f'-r "{rc}" -d "{dic}"'
        _tagger = fugashi.GenericTagger(args)
        import cutlet
        _cutlet = cutlet.Cutlet(mecab_args=args)
        _cutlet.use_foreign_spelling = False
    return _tagger, _cutlet


def annotate_line(text: str) -> tuple[str, str]:
    """返回 (带《注音》的日文, 罗马音)。无汉字的行不注音。"""
    tagger, kui = _ensure()
    with _lock:
        romaji = ""
        try:
            romaji = kui.romaji(text)
        except Exception:
            pass
        if not KANJI.search(text):
            return text, romaji
        import jaconv
        parts = []
        for w in tagger(text):
            surf = w.surface
            feat = w.feature
            # unidic-lite 特征为位置元组：索引 6=lForm, 9=pron（片假名）
            pron = feat[9] if len(feat) > 9 and feat[9] != "*" else ""
            if KANJI.search(surf) and pron:
                hira = jaconv.kata2hira(pron)
                parts.append(f"{surf}《{hira}》" if hira and hira != surf else surf)
            else:
                parts.append(surf)
        return "".join(parts), romaji


if __name__ == "__main__":
    for s in ["夢じゃない", "一緒に歌おう", "夜に駆ける", "光るとき", "君と夏の終わり"]:
        a, r = annotate_line(s)
        print(s, "=>", a, "|", r)
