"""Levi thought-watcher.

Resolve a fragment of generated text into the DB entities it names:
verse references in any form ("John 3:16", "Jn 3.16", "1 Cor 13:4-7",
"Genesis 1"), Strong's codes (H7225 / G4102), original Hebrew/Greek words
and runs (matched against the pericope chunk n-gram index), and
transliterations (hesed, charis). Every hit is a synapse pulse candidate
for the brain animator.

Data sources:
  watcher.db  — exported from the VDB chunk_phrases (LEVI_WATCHER_PATH)
  main DB     — transliteration index built at startup from words.translit
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from array import array
from collections import defaultdict

from .config import DB_PATH, parse_ref

# Verse refs: book names (1-2 words) + digits, dotted or coloned, ranges.
REF_RE = re.compile(
    r"\b(?:[1-3]\s+)?[A-Za-z]+[.\s]+\d{1,3}"
    r"(?:(?:[:.])\d{1,3})?(?:\s*[–—-]\s*\d{1,3})?\b"
)
STRONG_RE = re.compile(r"\b([HGhg])\s?(\d{1,4})\b")
TOKEN_RE = re.compile(r"[^\s,;:.!?\"'()\[\]{}«»—–-]+")
_GRC = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_HEB = re.compile(r"[\u0590-\u05ff]")
_LATIN = re.compile(r"[A-Za-z]")
_HEB_POINTS = re.compile(r"[\u0591-\u05c7\u05bd]")


def _norm_grc(s: str) -> str:
    """Unaccent Greek for index lookup (norm_text in the VDB is unaccented)."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("\u03c2", "\u03c3")  # final sigma -> base sigma


def _norm_heb(s: str) -> str:
    """Strip Hebrew points/cantillation for index lookup."""
    return _HEB_POINTS.sub("", s)


def _label(vid: str) -> str:
    b, ch, vs = vid.split(".")
    return f"{b} {ch}:{vs}"


class _Watcher:
    def __init__(self):
        self._ready = False
        self._g = None
        self._verses = []
        self._translit = {}
        self._lock = False

    def _load(self):
        import sqlite3

        t0 = time.time()
        wpath = os.environ.get("LEVI_WATCHER_PATH", "watcher.db")
        self._g = sqlite3.connect(f"file:{wpath}?mode=ro", uri=True)
        self._verses = [r[0] for r in self._g.execute("SELECT id FROM verses ORDER BY idx")]
        trans = defaultdict(list)
        mdb = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        n = 0
        for word, sb, vid in mdb.execute(
            "SELECT translit, strongs_base, verse_id FROM words WHERE translit<>''"
        ):
            k = _norm_grc(word)
            if len(k) < 3:
                continue
            e = trans[k]
            if len(e) < 12:
                e.append((vid, sb))
            n += 1
        mdb.close()
        # Only keep translits that are distinctive (2-400 occurrences).
        self._translit = {k: v for k, v in trans.items() if 2 <= len(v) <= 400}
        ngrams = self._g.execute("SELECT COUNT(*) FROM grams").fetchone()[0]
        self._ready = True
        print(
            f"[levi] watcher loaded: grams={ngrams:,} verses={len(self._verses):,} "
            f"translits={len(self._translit):,} ({time.time() - t0:.1f}s)"
        )

    def match(self, text: str, cap: int = 40) -> dict:
        if not self._ready:
            self._load()
        text = (text or "")[:4000]
        verses, seen_v = [], set()
        strongs, words, grams_out = [], [], []

        def add_vid(vid: str):
            if len(verses) >= cap:
                return
            lab = _label(vid)
            if lab not in seen_v:
                seen_v.add(lab)
                verses.append(lab)

        # ── 1. verse refs in any spelling ──────────────────────────────
        for m in REF_RE.finditer(text):
            if len(verses) >= cap:
                break
            cand = m.group(0)
            # recover a numeral that a preceding false match swallowed
            # ("…and 1 Cor 13:4-7" often scans as "and 1" + "Cor 13:4-7").
            prefix = text[: m.start()]
            pm = re.search(r"\b([1-3])\s*$", prefix)
            if pm:
                cand = pm.group(1) + " " + cand
            try:
                r = parse_ref(cand)
            except Exception:
                continue
            if not r or not r.get("book"):
                continue
            lo = r.get("verse") or 1
            hi = min(r.get("verse_end") or lo, lo + 8)
            for vv in range(lo, hi + 1):
                if len(verses) >= cap:
                    break
                add_vid(f"{r['book']}.{r['chapter']}.{vv}")

        # ── 2. original-language tokens -> pericope gram index ──────────
        if True:
            orig = []
            for tok in TOKEN_RE.findall(text):
                if _GRC.search(tok) and not _LATIN.search(tok):
                    orig.append(("g", _norm_grc(tok)))
                elif _HEB.search(tok):
                    orig.append(("h", _norm_heb(tok)))
            seen_grams = set()
            for i, (_script, _t) in enumerate(orig):
                run = [orig[i][1]]
                j = i + 1
                while j < len(orig) and orig[j][0] == _script and len(run) < 6:
                    run.append(orig[j][1])
                    j += 1
                for n in (2, 1):
                    for k in range(len(run) - n + 1):
                        g = " ".join(run[k : k + n])
                        if g in seen_grams:
                            continue
                        seen_grams.add(g)
                        row = self._g.execute(
                            "SELECT vids FROM grams WHERE g=?", (g,)
                        ).fetchone()
                        if not row:
                            continue
                        idxs = array("H")
                        idxs.frombytes(row[0])
                        refs = []
                        for vi in list(idxs[:10]):
                            vid = self._verses[vi]
                            refs.append(_label(vid))
                            add_vid(vid)
                        if refs:
                            grams_out.append({"g": g, "refs": refs[:8]})

        # ── 3. transliterations (hesed, charis, ruach …) ────────────────
        for tok in TOKEN_RE.findall(text):
            if len(tok) < 3 or not _LATIN.match(tok):
                continue
            hits = self._translit.get(_norm_grc(tok))
            if not hits:
                continue
            words.append(tok)
            for vid, sb in hits[:8]:
                if sb:
                    strongs.append(sb)
                add_vid(vid)

        # ── 4. Strong's codes written out ───────────────────────────────
        for m in STRONG_RE.finditer(text):
            code = f"{m.group(1).upper()}{int(m.group(2)):04d}"
            if code not in strongs:
                strongs.append(code)

        return {
            "verses": verses[:cap],
            "strongs": sorted(set(strongs))[:8],
            "words": sorted(set(words))[:12],
            "grams": grams_out[:6],
        }


_watcher = None


def watch_text(text: str, cap: int = 40) -> dict:
    global _watcher
    if _watcher is None:
        _watcher = _Watcher()
    try:
        return _watcher.match(text, cap=cap)
    except Exception as exc:  # never let the watcher break a generation
        print(f"[levi] watcher error: {exc}")
        return {"verses": [], "strongs": [], "words": [], "grams": []}
