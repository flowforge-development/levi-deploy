"""Sefaria on-demand fetch + cache.

Adds Jewish commentary (Rashi, Ibn Ezra, Ramban) and can fetch Targum on
demand.  Results are cached in the same SQLite database, so the agent can
use them offline after the first fetch.

This uses Sefaria's public API.  Be polite: one request at a time, no bulk
crawling.  `preload` is deliberately limited to a chapter at a time.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import db
from .config import parse_ref, resolve_book

BASE = "https://www.sefaria.org/api/texts/"
UA = "Levi-Monster/0.1 (Bible study retrieval; contact: local user)"

# Sefaria's canonical titles for Tanakh books.
SEFARIA_BOOK = {
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
    "Numbers": "Numbers", "Deuteronomy": "Deuteronomy", "Joshua": "Joshua",
    "Judges": "Judges", "1Samuel": "I_Samuel", "2Samuel": "II_Samuel",
    "1Kings": "I_Kings", "2Kings": "II_Kings", "Isaiah": "Isaiah",
    "Jeremiah": "Jeremiah", "Ezekiel": "Ezekiel", "Hosea": "Hosea",
    "Joel": "Joel", "Amos": "Amos", "Obadiah": "Obadiah", "Jonah": "Jonah",
    "Micah": "Micah", "Nahum": "Nahum", "Habakkuk": "Habakkuk",
    "Zephaniah": "Zephaniah", "Haggai": "Haggai", "Zechariah": "Zechariah",
    "Malachi": "Malachi", "Psalms": "Psalms", "Proverbs": "Proverbs",
    "Job": "Job", "SongofSolomon": "Song_of_Songs", "Ruth": "Ruth",
    "Lamentations": "Lamentations", "Ecclesiastes": "Ecclesiastes",
    "Esther": "Esther", "Daniel": "Daniel", "Ezra": "Ezra",
    "Nehemiah": "Nehemiah", "1Chronicles": "I_Chronicles",
    "2Chronicles": "II_Chronicles",
}

TARGUM = {
    "Genesis": "Targum_Onkelos_Genesis",
    "Exodus": "Targum_Onkelos_Exodus",
    "Leviticus": "Targum_Onkelos_Leviticus",
    "Numbers": "Targum_Onkelos_Numbers",
    "Deuteronomy": "Targum_Onkelos_Deuteronomy",
}

COMMENTATORS = {
    "rashi": ("Rashi", "Rashi_on_{book}"),
    "ibn_ezra": ("Ibn Ezra", "Ibn_Ezra_on_{book}"),
    "ramban": ("Ramban", "Ramban_on_{book}"),
}


def _get(path: str, timeout: int = 30) -> dict:
    url = BASE + urllib.parse.quote(path, safe="._") + "?context=0"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _clean(s) -> str:
    if isinstance(s, list):
        s = " ".join(_clean(x) for x in s)
    if not isinstance(s, str):
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _cache_commentary(conn, verse_id, author, work, he, en, source="Sefaria"):
    text = ""
    if he:
        text += "[Hebrew/Aramaic]\n" + _clean(he)
    if en:
        text += ("\n\n[English]\n" if text else "") + _clean(en)
    if not text:
        return 0
    conn.execute(
        "INSERT INTO commentary(verse_id,author,work,text,source) VALUES(?,?,?,?,?)",
        (verse_id, author, work, text, source))
    return 1


def fetch_verse(ref: str, commentators=("rashi", "ibn_ezra", "ramban"),
                refresh: bool = False, conn=None) -> dict:
    """Fetch commentary for one verse and cache it.  Returns status dict."""
    p = parse_ref(ref)
    if not p or p["verse"] is None:
        return {"error": f"cannot parse reference: {ref}"}
    book = p["book"]
    if book not in SEFARIA_BOOK:
        return {"error": f"Sefaria coverage is Tanakh only; no entry for {book}"}
    own = conn is None
    conn = conn or db.connect()
    vid = f'{book}.{p["chapter"]}.{p["verse"]}'
    out = {"ref": ref, "verse_id": vid, "fetched": {}, "cached": []}
    try:
        if not refresh:
            existing = conn.execute(
                "SELECT author,work FROM commentary WHERE verse_id=? AND source='Sefaria'",
                (vid,)).fetchall()
            if existing:
                out["cached"] = [f"{r[0]} — {r[1]}" for r in existing]
                if len(existing) >= len(commentators):
                    return out
        for key in commentators:
            if key not in COMMENTATORS:
                continue
            author, pattern = COMMENTATORS[key]
            title = pattern.format(book=SEFARIA_BOOK[book])
            path = f"{title}.{p['chapter']}.{p['verse']}"
            try:
                data = _get(path)
                n = _cache_commentary(conn, vid, author, title.replace("_", " "), data.get("he"), data.get("text"))
                out["fetched"][key] = n
                conn.commit()
            except Exception as exc:
                out["fetched"][key] = f"error: {exc}"
            time.sleep(0.2)
    finally:
        if own:
            conn.close()
    return out


def fetch_targum_chapter(book: str, chapter: int, refresh: bool = False, conn=None) -> dict:
    """Fetch a chapter of Targum Onkelos and cache verse rows."""
    b = resolve_book(book)
    if b not in TARGUM:
        return {"error": f"Targum Onkelos is cached for the Torah; {book} not available here"}
    own = conn is None
    conn = conn or db.connect()
    out = {"book": b, "chapter": chapter, "verses": 0}
    try:
        if not refresh:
            n = conn.execute(
                "SELECT COUNT(*) FROM ancient_versions WHERE version='Targum Onkelos (Sefaria)' "
                "AND verse_id LIKE ?", (f"{b}.{chapter}.%",)).fetchone()[0]
            if n:
                out["verses"] = n
                out["cached"] = True
                return out
        data = _get(f"{TARGUM[b]}.{chapter}")
        he = data.get("he") or []
        en = data.get("text") or []
        rows, crows = [], []
        for i, txt in enumerate(he):
            if not txt:
                continue
            vid = f"{b}.{chapter}.{i+1}"
            rows.append((vid, "Targum Onkelos (Sefaria)", _clean(txt), "Sefaria"))
            if i < len(en) and en[i]:
                crows.append((vid, "Targum Onkelos", "Targum Onkelos (English)", _clean(en[i]), "Sefaria"))
        conn.executemany("INSERT OR REPLACE INTO ancient_versions(verse_id,version,text,source) VALUES(?,?,?,?)", rows)
        conn.executemany("INSERT INTO commentary(verse_id,author,work,text,source) VALUES(?,?,?,?,?)", crows)
        conn.commit()
        out["verses"] = len(rows)
        return out
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if own:
            conn.close()


def preload_torah(conn=None, delay: float = 0.2) -> dict:
    """Fetch Targum Onkelos for the whole Torah.  ~187 requests."""
    from .config import CHAPTER_COUNTS
    own = conn is None
    conn = conn or db.connect()
    total = 0
    try:
        for book in ("Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy"):
            for ch in range(1, CHAPTER_COUNTS[book] + 1):
                r = fetch_targum_chapter(book, ch, conn=conn)
                total += r.get("verses", 0)
                time.sleep(delay)
        return {"verses": total}
    finally:
        if own:
            conn.close()


def cached_commentary(ref: str, conn=None) -> list[dict]:
    p = parse_ref(ref)
    if not p or p["verse"] is None:
        return []
    own = conn is None
    conn = conn or db.connect()
    try:
        vid = f'{p["book"]}.{p["chapter"]}.{p["verse"]}'
        return [dict(r) for r in conn.execute(
            "SELECT author,work,text FROM commentary WHERE verse_id=? AND source='Sefaria' ORDER BY author",
            (vid,)).fetchall()]
    finally:
        if own:
            conn.close()
