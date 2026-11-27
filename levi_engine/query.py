"""Query layer for the Levi Monster."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from . import db
from .config import (BOOK_BY_FULL, BOOK_CONTEXT, DB_PATH, parse_ref, ref_label,
                     resolve_book, strip_accents)

import threading

_tls = threading.local()

def conn():
    # One connection per thread: SQLite objects are not cross-thread; the API
    # serves concurrent readers, each handler thread gets its own connection.
    c = getattr(_tls, "conn", None)
    if c is None:
        c = db.connect(DB_PATH)
        _tls.conn = c
    return c


def _rows(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def _one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def _resolve(ref: str):
    p = parse_ref(ref)
    if not p:
        return None
    return p


def _verse_ids(p):
    if p["verse"] is None:
        return []
    return [f'{p["book"]}.{p["chapter"]}.{v}' for v in range(p["verse"], p["verse_end"] + 1)]


# ── Verse / translations ─────────────────────────────────────────────

def get_verse(ref: str, translation_list=None) -> dict | None:
    p = _resolve(ref)
    if not p or p["verse"] is None:
        return None
    vid = f'{p["book"]}.{p["chapter"]}.{p["verse"]}'
    v = _one("SELECT * FROM verses WHERE id=?", (vid,))
    if not v:
        return None
    v["reference"] = ref_label(v["book"], v["chapter"], v["verse"])
    translations = _rows(
        "SELECT translation,text FROM translations WHERE verse_id=? "
        "ORDER BY CASE translation WHEN 'KJV' THEN 0 WHEN 'ASV' THEN 1 WHEN 'NHEB' THEN 2 "
        "WHEN 'YLT' THEN 3 WHEN 'Darby' THEN 4 WHEN 'BBE' THEN 5 WHEN 'Webster' THEN 6 "
        "WHEN 'Geneva1599' THEN 7 WHEN 'Vulgate' THEN 8 ELSE 9 END", (vid,))
    if translation_list:
        wanted = {t.upper() for t in translation_list}
        translations = [t for t in translations if t["translation"].upper() in wanted]
    v["translations"] = translations
    v["words"] = get_words(vid)
    v["language_tags"] = _rows(
        "SELECT lang,scope,word_start,word_end,note FROM lang_tags WHERE verse_id=? ORDER BY lang", (vid,))
    v["variants"] = _rows("SELECT pos,reading,witness,kind,note FROM variants WHERE verse_id=? ORDER BY pos", (vid,))
    v["cross_refs"] = crossrefs(ref, limit=20)
    v["topics"] = _rows("SELECT topic,source,entry FROM topics WHERE verse_id=? ORDER BY topic LIMIT 30", (vid,))
    v["book_context"] = _one("SELECT * FROM book_context WHERE book=?", (v["book"],))
    v["lxx"] = get_lxx(v["book"], v["chapter"], v["verse"])
    v["purpose"] = _one("SELECT * FROM language_purpose WHERE verse_id=?", (vid,))
    v["ancient_versions"] = _rows(
        "SELECT version,text FROM ancient_versions WHERE verse_id=? ORDER BY version", (vid,))
    v["book_overlap"] = _rows(
        "SELECT related_book,score,basis FROM book_overlap WHERE book=? ORDER BY score DESC LIMIT 8",
        (v["book"],))
    return v


def multi(ref: str = "", caps: str = "", q: str = "", limit: int = 20) -> dict:
    """One API for everything: the verse reference is the signal.

    caps = comma list of: text, interlinear, context, language, purpose,
    chunks, crossref, ancient, search. Default: text + interlinear.
    A `q` search ignores caps and returns search results.
    """
    if q:
        return {"ref": ref, "search": search(q, limit=limit)}
    if not ref:
        raise ValueError("ref or q required")
    wanted = {c for c in (caps or "text,interlinear").split(",")}
    out: dict = {"ref": ref}
    if "text" in wanted:
        out["text"] = get_verse(ref)
    if "interlinear" in wanted:
        out["interlinear"] = interlinear(ref)
    if "context" in wanted:
        out["context"] = context(ref, user_id=None)
    if "language" in wanted:
        out["language"] = language(ref)
    if "purpose" in wanted:
        out["purpose"] = purpose(ref)
    if "chunks" in wanted:
        out["chunks"] = chunks(ref)
    if "crossref" in wanted:
        out["crossref"] = crossrefs(ref, limit=limit)
    if "ancient" in wanted:
        out["ancient"] = (get_verse(ref) or {}).get("ancient_versions", [])
    return out


def chunks(ref: str) -> list[dict]:
    p = _resolve(ref)
    if not p:
        return []
    if p["verse"] is None:
        return _rows(
            "SELECT id,book,chapter,verse_start,verse_end,kind,label,text FROM chunks "
            "WHERE book=? AND chapter=? ORDER BY verse_start", (p["book"], p["chapter"]))
    return _rows(
        "SELECT id,book,chapter,verse_start,verse_end,kind,label,text FROM chunks "
        "WHERE book=? AND chapter=? AND verse_start<=? AND verse_end>=? ORDER BY verse_start",
        (p["book"], p["chapter"], p["verse_end"], p["verse"]))


def get_chapter(book: str, chapter: int) -> dict:
    b = resolve_book(book)
    if not b:
        return {"error": f"unknown book: {book}"}
    verses = _rows("SELECT id,book,chapter,verse,kjv_text,hebrew,greek,lang,lang_note FROM verses WHERE book=? AND chapter=? ORDER BY verse", (b, chapter))
    return {"book": b, "chapter": chapter, "verses": verses,
            "book_context": _one("SELECT * FROM book_context WHERE book=?", (b,))}


def get_words(vid: str) -> list[dict]:
    words = _rows("SELECT * FROM words WHERE verse_id=? ORDER BY pos", (vid,))
    # attach best lexicon gloss/definition and domains
    for w in words:
        codes = [w.get("strongs"), w.get("strongs_base")]
        lex = None
        for code in codes:
            if not code:
                continue
            lex = _one("SELECT strongs,lemma,translit,gloss,definition,source FROM lexicon WHERE strongs=? ORDER BY CASE source WHEN 'TBESH' THEN 0 WHEN 'TBESG' THEN 0 WHEN 'SDBH' THEN 1 WHEN 'LSJ' THEN 2 ELSE 3 END LIMIT 1", (code,))
            if lex:
                break
        w["lexicon"] = lex or {}
        if w.get("strongs_base"):
            w["domains"] = [r["label"] for r in _rows(
                "SELECT DISTINCT label FROM domains WHERE strongs=? OR strongs LIKE ? LIMIT 12",
                (w["strongs"], w["strongs_base"] + "%"))]
        else:
            w["domains"] = []
        if w.get("lang") == "grc" and w.get("strongs_base"):
            w["aramaic"] = _rows(
                "SELECT aramaic,translit,gloss,confidence,note FROM aramaic_bridge WHERE greek_strong=?",
                (w["strongs_base"],))
    return words


def interlinear(ref: str) -> dict | None:
    p = _resolve(ref)
    if not p or p["verse"] is None:
        return None
    out = []
    for vid in _verse_ids(p):
        v = _one("SELECT id,book,chapter,verse,kjv_text,hebrew,greek,lang,lang_note FROM verses WHERE id=?", (vid,))
        if not v:
            continue
        v["words"] = get_words(vid)
        v["reference"] = ref_label(v["book"], v["chapter"], v["verse"])
        out.append(v)
    return {"verses": out}


# ── Lexicon ──────────────────────────────────────────────────────────

def normalize_strong(s: str) -> str:
    s = (s or "").strip().upper()
    m = re.match(r"^([HG])0*(\d+)", s)
    if not m:
        return s
    return f"{m.group(1)}{int(m.group(2)):04d}"


def word_lookup(query: str, limit: int = 30) -> dict:
    q = query.strip()
    strong = normalize_strong(q)
    lex = []
    if re.match(r"^[HG]\d{1,5}", strong):
        lex = _rows("SELECT * FROM lexicon WHERE strongs=? OR base=? ORDER BY CASE source WHEN 'TBESH' THEN 0 WHEN 'TBESG' THEN 0 WHEN 'SDBH' THEN 1 WHEN 'Strongs' THEN 2 ELSE 3 END",
                    (strong, strong))
    if not lex:
        # lemma exact, then accent-insensitive
        lex = _rows("SELECT * FROM lexicon WHERE lemma=? OR lower(lemma)=lower(?) LIMIT 50", (q, q))
    if not lex:
        target = strip_accents(q).lower()
        for row in conn().execute("SELECT * FROM lexicon WHERE lemma IS NOT NULL AND lemma<>''"):
            if strip_accents(row["lemma"]).lower() == target:
                lex.append(dict(row))
    bases = sorted({r.get("base") or r["strongs"] for r in lex if r.get("base") or r.get("strongs")})
    occ = []
    if bases:
        marks = ",".join("?" for _ in bases)
        occ = _rows(
            f"SELECT w.verse_id, v.book, v.chapter, v.verse, v.kjv_text, w.surface, w.translit, w.strongs, w.gloss "
            f"FROM words w JOIN verses v ON v.id=w.verse_id WHERE w.strongs_base IN ({marks}) "
            f"ORDER BY v.book, v.chapter, v.verse LIMIT ?", (*bases, limit))
    domains = []
    if bases:
        marks = ",".join("?" for _ in bases)
        domains = _rows(f"SELECT DISTINCT label,source FROM domains WHERE strongs IN ({marks}) OR strongs LIKE ? LIMIT 40",
                        (*bases, bases[0] + "%"))
    return {"query": query, "strongs": bases, "lexicon": lex, "occurrences": occ,
            "count": _count_occurrences(bases), "domains": domains}


def _count_occurrences(bases):
    if not bases:
        return 0
    marks = ",".join("?" for _ in bases)
    return conn().execute(f"SELECT COUNT(*) FROM words WHERE strongs_base IN ({marks})", bases).fetchone()[0]


def occurrences(strong: str, limit: int = 100) -> dict:
    s = normalize_strong(strong)
    rows = _rows(
        "SELECT w.verse_id,v.book,v.chapter,v.verse,v.kjv_text,w.surface,w.translit,w.morph,w.gloss "
        "FROM words w JOIN verses v ON v.id=w.verse_id WHERE w.strongs_base=? "
        "ORDER BY v.book,v.chapter,v.verse LIMIT ?", (s, limit))
    total = conn().execute("SELECT COUNT(*) FROM words WHERE strongs_base=?", (s,)).fetchone()[0]
    return {"strongs": s, "total": total, "occurrences": rows}


# ── Cross references / topics / commentary ───────────────────────────

def crossrefs(ref: str, limit: int = 30, min_votes: int = 0) -> list[dict]:
    p = _resolve(ref)
    if not p or p["verse"] is None:
        return []
    vid = f'{p["book"]}.{p["chapter"]}.{p["verse"]}'
    out = []
    for r in _rows(
        "SELECT x.to_id,x.votes,x.source,v.book,v.chapter,v.verse,v.kjv_text "
        "FROM cross_refs x LEFT JOIN verses v ON v.id=x.to_id "
        "WHERE x.from_id=? AND x.votes>=? ORDER BY x.votes DESC LIMIT ?", (vid, min_votes, limit)):
        out.append(r)
    # reverse links too
    for r in _rows(
        "SELECT x.from_id AS to_id,x.votes,x.source,v.book,v.chapter,v.verse,v.kjv_text "
        "FROM cross_refs x LEFT JOIN verses v ON v.id=x.from_id "
        "WHERE x.to_id=? AND x.votes>=? ORDER BY x.votes DESC LIMIT ?", (vid, min_votes, limit)):
        out.append(r)
    seen, dedup = set(), []
    for r in out:
        if r["to_id"] in seen:
            continue
        seen.add(r["to_id"]); dedup.append(r)
    dedup.sort(key=lambda x: -(x.get("votes") or 0))
    return dedup[:limit]


def topic_search(query: str, limit: int = 30) -> list[dict]:
    q = f"%{query}%"
    return _rows(
        "SELECT topic,verse_id,source,entry FROM topics WHERE topic LIKE ? "
        "ORDER BY topic LIMIT ?", (q, limit))


def topics_for(ref: str) -> list[dict]:
    p = _resolve(ref)
    if not p or p["verse"] is None:
        return []
    vid = f'{p["book"]}.{p["chapter"]}.{p["verse"]}'
    return _rows("SELECT topic,source,entry FROM topics WHERE verse_id=? ORDER BY topic", (vid,))


def commentary(ref: str, limit: int = 20) -> list[dict]:
    p = _resolve(ref)
    if not p or p["verse"] is None:
        return []
    vid = f'{p["book"]}.{p["chapter"]}.{p["verse"]}'
    rows = _rows("SELECT author,work,text FROM commentary WHERE verse_id=? ORDER BY author LIMIT ?", (vid, limit))
    # chapter intro fallback
    if not rows:
        rows = _rows("SELECT author,work,text FROM commentary WHERE verse_id=? ORDER BY author LIMIT ?",
                     (f'{p["book"]}.{p["chapter"]}.0', limit))
    return rows


def language(ref: str) -> dict | None:
    p = _resolve(ref)
    if not p or p["verse"] is None:
        return None
    vid = f'{p["book"]}.{p["chapter"]}.{p["verse"]}'
    v = _one("SELECT id,book,chapter,verse,lang,lang_note,hebrew,greek FROM verses WHERE id=?", (vid,))
    if not v:
        return None
    v["tags"] = _rows("SELECT lang,scope,word_start,word_end,note FROM lang_tags WHERE verse_id=? ORDER BY lang,word_start", (vid,))
    v["words"] = _rows("SELECT pos,lang,surface,translit,strongs,morph,gloss FROM words WHERE verse_id=? ORDER BY pos", (vid,))
    v["lxx"] = get_lxx(v["book"], v["chapter"], v["verse"])
    return v


def purpose(ref: str) -> dict | None:
    p = _resolve(ref)
    if not p:
        return None
    # A chapter/book reference is represented by its first verse.
    verse = p["verse"] if p["verse"] is not None else 1
    vid = f'{p["book"]}.{p["chapter"]}.{verse}'
    row = _one("SELECT * FROM language_purpose WHERE verse_id=?", (vid,))
    if row and p["verse"] is None:
        row["note"] = (row.get("note", "") + " (chapter-level representative)").strip()
    return row


def book_overlap(book: str, limit: int = 15) -> list[dict]:
    b = resolve_book(book)
    if not b:
        return []
    return _rows(
        "SELECT related_book,score,basis FROM book_overlap WHERE book=? "
        "ORDER BY score DESC LIMIT ?", (b, limit))


def character_search(query: str, limit: int = 20) -> list[dict]:
    q = f"%{query}%"
    return _rows(
        "SELECT name,strongs,description,refs FROM characters "
        "WHERE name LIKE ? OR description LIKE ? ORDER BY name LIMIT ?",
        (q, q, limit))


def get_lxx(book: str, chapter: int, verse: int) -> dict | None:
    b = BOOK_BY_FULL.get(book)
    if not b:
        return None
    lxx_ch = chapter
    lxx_v = verse
    note = "LXX versification may differ"
    if book == "Psalms":
        # Rahlfs follows the Greek Psalter numbering, which is usually one
        # chapter lower than the English/Masoretic numbering after Ps 10.
        if 11 <= chapter <= 113 or 117 <= chapter <= 146:
            lxx_ch = chapter - 1
            note = "Rahlfs Psalter numbering (usually MT chapter − 1)"
        elif chapter in (9, 10):
            lxx_ch = 9
            note = "Rahlfs joins MT Psalms 9–10 as LXX Psalm 9"
        elif chapter in (114, 115):
            lxx_ch = 113
            note = "Rahlfs joins MT Psalms 114–115 as LXX Psalm 113"
        elif chapter == 116:
            lxx_ch = 114 if verse <= 9 else 115
            lxx_v = verse if verse <= 9 else verse - 9
            note = "Rahlfs splits MT Psalm 116 across LXX Psalms 114–115"
        elif chapter == 147:
            lxx_ch = 146 if verse <= 11 else 147
            lxx_v = verse if verse <= 11 else verse - 11
            note = "Rahlfs splits MT Psalm 147 across LXX Psalms 146–147"
    row = _one(
        "SELECT l.text FROM lxx_verses l JOIN lxx_books b ON b.number=l.book_no "
        "WHERE b.code=? AND l.chapter=? AND l.verse=?", (b["short"], lxx_ch, lxx_v))
    if not row:
        return None
    return {"text": row["text"], "edition": "Rahlfs 1935", "note": note}


# ── Search ───────────────────────────────────────────────────────────

def _fts_query(q: str) -> str:
    q = q.strip()
    if not q:
        return '""'
    # allow explicit FTS syntax if user uses quotes/operators
    if any(x in q for x in ('"', " OR ", " AND ", " NOT ", " NEAR(")):
        return q
    terms = re.findall(r"[\w\u0590-\u05FF\u0370-\u03FF]+", q, re.UNICODE)
    if not terms:
        return '""'
    return " OR ".join(f'"{t}"' for t in terms[:24])


def search(query: str, limit: int = 20, testament: str = None, book: str = None,
           translation: str = None) -> list[dict]:
    b = resolve_book(book) if book else None
    if translation and translation.upper() != "KJV":
        like = "%" + query.replace("%", "") + "%"
        sql = ("SELECT verse_id AS id,v.book,v.chapter,v.verse,v.kjv_text,t.text AS matched_text "
               "FROM translations t JOIN verses v ON v.id=t.verse_id "
               "WHERE t.translation=? AND t.text LIKE ?")
        args = [translation, like]
        if testament:
            sql += " AND v.testament=?"; args.append(testament.upper())
        if b:
            sql += " AND v.book=?"; args.append(b)
        sql += " LIMIT ?"; args.append(limit)
        return _rows(sql, args)

    sql = ("SELECT f.id, v.book, v.chapter, v.verse, v.kjv_text, "
           "snippet(verses_fts, 2, '[', ']', '…', 18) AS snippet, bm25(verses_fts) AS rank "
           "FROM verses_fts f JOIN verses v ON v.id=f.id WHERE verses_fts MATCH ?")
    args = [_fts_query(query)]
    if testament:
        sql += " AND v.testament=?"; args.append(testament.upper())
    if b:
        sql += " AND v.book=?"; args.append(b)
    sql += " ORDER BY rank LIMIT ?"; args.append(limit)
    try:
        return _rows(sql, args)
    except sqlite3.OperationalError as exc:
        return [{"error": f"search syntax: {exc}"}]


def search_word(query: str, limit: int = 50) -> list[dict]:
    q = f"%{query}%"
    return _rows(
        "SELECT w.verse_id,v.book,v.chapter,v.verse,v.kjv_text,w.surface,w.translit,w.strongs,w.gloss "
        "FROM words w JOIN verses v ON v.id=w.verse_id "
        "WHERE w.surface LIKE ? OR w.translit LIKE ? OR w.lemma LIKE ? "
        "ORDER BY v.book,v.chapter,v.verse LIMIT ?", (q, q, q, limit))


# ── Context bundle for LLM ───────────────────────────────────────────

def context(ref: str, limit_xref: int = 15, commentary_limit: int = 6,
            sefirot_limit: int = 5, user_id: str | None = None) -> dict:
    v = get_verse(ref)
    if not v:
        return {"error": f"verse not found: {ref}"}
    v["cross_refs"] = v.get("cross_refs", [])[:limit_xref]
    v["commentary"] = commentary(ref, limit=commentary_limit)
    v["topics"] = v.get("topics", [])[:20]
    v["book_context"] = v.get("book_context") or {}
    return v


def context_markdown(ref: str, full: bool = False, user_id: str | None = None) -> str:
    """Render a layered study page.

    The default is intentionally quiet: glosses, not full dictionary dumps.
    ``full=True`` keeps the complete lexical evidence for an agent or a deep
    word study.  The layers stay in the same order either way.
    """
    v = context(ref, limit_xref=40 if full else 10,
                commentary_limit=20 if full else 3,
                sefirot_limit=8 if full else 5, user_id=user_id)
    if "error" in v:
        return v["error"]
    out = []
    out.append(f"# {v['reference']}\n")
    bc = v.get("book_context") or {}
    if bc:
        out.append("## Book context")
        out.append(f"- Author/tradition: {bc.get('author','')}")
        out.append(f"- Date: {bc.get('date','')}")
        out.append(f"- Genre: {bc.get('genre','')}")
        out.append(f"- Audience: {bc.get('audience','')}")
        out.append(f"- Purpose: {bc.get('purpose','')}")
        out.append(f"- Language register: {bc.get('register','')}")
        out.append(f"- Summary: {bc.get('summary','')}\n")
    out.append("## Translations")
    for t in v.get("translations", []):
        out.append(f"- **{t['translation']}**: {t['text']}")
    out.append("")
    out.append("## Original-language tokens")
    if not full:
        out.append("_Glosses only. Ask for full lexical detail when needed "
                   "(`context --full` in the CLI, or `full=true` in MCP)._")
        out.append("")
    for w in v.get("words", []):
        lex = w.get("lexicon") or {}
        dom = ", ".join(w.get("domains") or [])
        line = (f"- #{w.get('pos')} {w.get('surface','')} ({w.get('translit','')}) "
                f"[{w.get('strongs','')}] {w.get('morph','')} — {w.get('gloss','')}")
        if full and lex.get("definition"):
            line += f"\n  - lexicon: {lex['definition'][:1200]}"
        if full and dom:
            line += f"\n  - domains: {dom}"
        if w.get("aramaic"):
            for a in w["aramaic"]:
                line += f"\n  - Aramaic reconstruction: {a['aramaic']} ({a['translit']}) = {a['gloss']} [{a['confidence']}]"
        out.append(line)
    out.append("")
    purpose = v.get("purpose") or {}
    if purpose:
        out.append("## Language purpose / register")
        out.append(f"- Language: {purpose.get('language','')}")
        out.append(f"- Register: {purpose.get('purpose','')}")
        out.append(f"- Period: {purpose.get('period','')}")
        out.append(f"- Note: {purpose.get('note','')} ({purpose.get('confidence','')} confidence)\n")
    tags = v.get("language_tags") or []
    if tags:
        out.append("## Language tags")
        for t in tags:
            scope = t.get("scope") or ""
            rng = ""
            if t.get("word_start"):
                rng = f" words {t['word_start']}-{t.get('word_end') or ''}"
            out.append(f"- {t['lang']} ({scope}{rng}): {t.get('note','')}")
        out.append("")
    if v.get("lxx"):
        out.append("## Septuagint (Rahlfs)")
        out.append(f"> {v['lxx']['text']}\n")
    av = v.get("ancient_versions") or []
    if av:
        out.append("## Ancient versions (Syriac / Aramaic)")
        for a in av:
            out.append(f"- **{a['version']}**: {a['text']}")
        out.append("")
    variants = v.get("variants") or []
    if variants:
        out.append("## Textual / spelling variants")
        for x in variants[:12]:
            out.append(f"- token {x.get('pos')}: {x.get('kind')} — {x.get('reading','')[:300]}")
        out.append("")
    xr = v.get("cross_refs") or []
    if xr:
        out.append("## Cross references")
        for x in xr:
            out.append(f"- {x.get('book','')} {x.get('chapter','')}:{x.get('verse','')} "
                       f"(votes {x.get('votes',0)}) — {(x.get('kjv_text') or '')[:220]}")
        out.append("")
    tp = v.get("topics") or []
    if tp:
        out.append("## Topical index")
        for t in tp:
            out.append(f"- {t['topic']} ({t['source']}): {t.get('entry','')[:220]}")
        out.append("")
    cm = v.get("commentary") or []
    if cm:
        out.append("## Commentary")
        for c in cm:
            out.append(f"### {c['author']} — {c['work']}")
            limit = 4000 if full else 1200
            out.append(c["text"][:limit] + ("…" if len(c["text"]) > limit else ""))
            out.append("")
    if not full:
        out.append(f"_Full lexical detail is available with `context \"{v['reference']}\" --full` "
                   f"or `levi_context` with `full=true`._")
    return "\n".join(out)


def context_json(ref: str, full: bool = False, user_id: str | None = None) -> str:
    v = context(ref, limit_xref=40 if full else 15, commentary_limit=20 if full else 6,
                user_id=user_id)
    return json.dumps(v, ensure_ascii=False, indent=2, default=str)


STUDY_SYSTEM = (
    "You are Levi, a Bible-study retrieval-and-synthesis engine. Answer only from the "
    "provided sources. Distinguish what the text says, what the original languages add, "
    "what the historical/cultural context suggests, and what is later interpretation. "
    "Flag uncertainty. Do not invent citations."
)


def study_bundle(q: str = "", ref: str = "", limit: int = 6) -> dict:
    """Grounded sources plus a ready-to-use prompt for a client-side LLM."""
    limit = max(1, min(int(limit), 12))
    sources: list[dict] = []
    if ref:
        if get_verse(ref):
            sources.append({"ref": ref,
                            "context": context_markdown(ref, full=False, user_id=None)})
    elif q:
        for h in search(q, limit=limit):
            if "error" in h:
                continue
            r = ref_label(h["book"], h["chapter"], h["verse"])
            sources.append({"ref": r,
                            "context": context_markdown(r, full=False, user_id=None)})
    question = q or ref
    prompt = (
        f"{STUDY_SYSTEM}\n\nQUESTION: {question}\n\nSOURCES:\n"
        + "\n\n---\n\n".join(s["context"] for s in sources)
    )
    return {"query": q, "ref": ref or None, "count": len(sources),
            "sources": sources, "prompt": prompt}


# ── Stats / misc ─────────────────────────────────────────────────────

def stats() -> dict:
    s = db.stats(conn())
    try:
        s["verses_fts"] = conn().execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0]
    except Exception:
        pass
    s["database"] = str(DB_PATH)
    s["size_mb"] = round(Path(DB_PATH).stat().st_size / 1e6, 1) if Path(DB_PATH).exists() else 0
    return s


def overview(recent_limit: int = 5, review_limit: int = 5,
             user_id: str | None = None) -> dict:
    """A calm, first-look dashboard for a person or an agent."""
    if not Path(DB_PATH).exists():
        return {
            "ok": False,
            "name": "Levi Monster",
            "error": f"database not found: {DB_PATH}",
            "next": ["bin/levi build --reset", "bin/levi doctor"],
        }
    s = stats()
    uid = None
    current = {"id": None, "note": "personal brain lives in Ritual now"}
    try:
        health = doctor()
    except Exception as exc:
        health = {"ok": False, "summary": f"health check failed: {exc}", "checks": []}
    notebook = {"note": "the brain lives in Ritual"}
    recent = []
    recent_threads = []
    review_queue = {"notes": [], "count": 0, "note": "the brain lives in Ritual"}
    counts = {k: s.get(k, 0) for k in (
        "verses", "words", "translations", "cross_refs", "commentary",
        "ancient_versions",
    )}
    return {
        "ok": bool(health.get("ok")),
        "name": "Levi Monster",
        "tagline": "The Scripture beating heart. The brain lives in Ritual.",
        "user": current,
        "database": {"path": str(DB_PATH), "size_mb": s.get("size_mb", 0)},
        "counts": counts,
        "health": health,
        "next": [
            "bin/levi context \"John 1:1\"",
            "bin/levi interlinear \"John 3:16\"",
            "bin/levi backup",
        ],
    }


def doctor() -> dict:
    """Check the database and its major channels for obvious breakage."""
    import os
    checks = []

    def add(name, ok, detail, level="error"):
        checks.append({"check": name, "ok": bool(ok), "level": level if not ok else "ok",
                       "detail": str(detail)})

    path = Path(DB_PATH)
    if not path.exists():
        return {"ok": False, "checks": [
            {"check": "database", "ok": False, "level": "error",
             "detail": f"missing database: {path}"}], "summary": "database missing"}

    s = stats()
    add("database", True, f"{s['database']} ({s['size_mb']} MB)")
    try:
        quick = conn().execute("PRAGMA quick_check").fetchone()[0]
        add("sqlite_integrity", quick == "ok", quick)
    except Exception as exc:
        add("sqlite_integrity", False, f"query failed: {exc}")
    add("verses", s.get("verses") == 31102, f"{s.get('verses',0):,} / 31,102")
    add("original_words", s.get("words", 0) > 400000, f"{s.get('words',0):,} token rows")
    add("translations", s.get("translations", 0) > 250000, f"{s.get('translations',0):,} rows")
    add("cross_refs", s.get("cross_refs", 0) > 200000, f"{s.get('cross_refs',0):,} links")
    add("commentary", s.get("commentary", 0) > 1000, f"{s.get('commentary',0):,} entries")
    add("verses_fts", s.get("verses_fts", 0) == s.get("verses"), f"{s.get('verses_fts',0):,} indexed")
    try:
        missing = conn().execute(
            "SELECT COUNT(*) FROM verses WHERE id NOT IN (SELECT DISTINCT verse_id FROM words)"
        ).fetchone()[0]
        add("language_coverage", missing <= 10, f"{missing} translation-only verses", "warn")
    except Exception as exc:
        add("language_coverage", False, f"query failed: {exc}", "warn")
    add("sefirot_links", s.get("sefirot_links", 0) > 0,
        f"{s.get('sefirot_links',0):,} personal links", "warn")
    add("sefirot_fts", s.get("sefirot_fts", 0) == s.get("sefirot_nodes", 0),
        f"{s.get('sefirot_fts',0):,} indexed / {s.get('sefirot_nodes',0):,} active notes", "warn")
    try:
        orphan = conn().execute(
            "SELECT COUNT(*) FROM sefirot_links l "
            "LEFT JOIN sefirot_nodes n ON n.id=l.from_node "
            "LEFT JOIN sefirot_nodes t ON t.id=l.to_node "
            "WHERE n.id IS NULL OR (l.to_node IS NOT NULL AND t.id IS NULL)"
        ).fetchone()[0]
        add("sefirot_integrity", orphan == 0, f"{orphan} orphan links")
    except Exception as exc:
        add("sefirot_integrity", False, f"query failed: {exc}", "warn")
    try:
        orphan_refs = conn().execute(
            "SELECT COUNT(*) FROM sefirot_ref_index i "
            "LEFT JOIN sefirot_nodes s ON s.id=i.section_id "
            "LEFT JOIN sefirot_nodes t ON t.id=i.thread_id "
            "WHERE s.id IS NULL OR t.id IS NULL"
        ).fetchone()[0]
        add("sefirot_ref_integrity", orphan_refs == 0,
            f"{orphan_refs} orphan reference-index rows", "warn")
    except Exception as exc:
        add("sefirot_ref_integrity", False, f"query failed: {exc}", "warn")
    try:
        n_sources = conn().execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
        add("source_registry", n_sources > 0, f"{n_sources} sources")
    except Exception as exc:
        add("source_registry", False, f"query failed: {exc}", "warn")
    try:
        from . import users
        reg = users.ensure_registry()
        current = users.resolve_user(registry=reg)
        add("users_registry", True,
            f"{len(reg['users'])} local user(s); default={reg['default_user']}; "
            f"current={current['display_name']} ({current['id']}) via {current['resolved_by']}")
        notebook = Path(current["notebook"])
        add("user_notebook", notebook.exists(), str(notebook), "warn")
        cols = {row[1] for row in conn().execute("PRAGMA table_info(sefirot_nodes)")}
        add("sefirot_user_scope", "user_id" in cols,
            "sefirot_nodes.user_id present" if "user_id" in cols else "missing user_id column")
        if "user_id" in cols:
            indexed = conn().execute(
                "SELECT COUNT(*) FROM sefirot_nodes WHERE user_id=? AND archived=0",
                (current["id"],),
            ).fetchone()[0]
            add("user_notebook_index", indexed > 0,
                f"{indexed} active entries owned by {current['id']}", "warn")
    except Exception as exc:
        add("users_registry", False, f"user identity check failed: {exc}", "warn")
    errors = [c for c in checks if not c["ok"] and c["level"] == "error"]
    warns = [c for c in checks if not c["ok"] and c["level"] == "warn"]
    summary = f"{len(checks) - len(errors) - len(warns)} ok, {len(warns)} warnings, {len(errors)} errors"
    return {"ok": not errors, "dsn": os.environ.get("LEVI_DB_PATH", str(DB_PATH)),
            "checks": checks, "summary": summary}


def sources() -> list[dict]:
    return _rows("SELECT * FROM source_registry ORDER BY kind,name")


def books() -> list[dict]:
    return _rows("SELECT * FROM book_context ORDER BY rowid")


def random_verse() -> dict | None:
    r = _one("SELECT book,chapter,verse FROM verses ORDER BY RANDOM() LIMIT 1")
    if not r:
        return None
    return get_verse(ref_label(r["book"], r["chapter"], r["verse"]))


def add_note(ref: str, body: str, tag: str = "") -> dict:
    p = _resolve(ref)
    if not p:
        return {"error": f"cannot parse reference: {ref}"}
    cur = conn().execute("INSERT INTO notes(ref,tag,body) VALUES(?,?,?)", (ref, tag, body))
    conn().commit()
    return {"id": cur.lastrowid, "ref": ref, "tag": tag, "body": body}


def list_notes(ref: str = None, limit: int = 50) -> list[dict]:
    if ref:
        return _rows("SELECT id,ref,tag,body,created FROM notes WHERE ref LIKE ? ORDER BY id DESC LIMIT ?",
                     (f"%{ref}%", limit))
    return _rows("SELECT id,ref,tag,body,created FROM notes ORDER BY id DESC LIMIT ?", (limit,))


# ── Semantic search v2 — originals-only word/lemma vectors ─────────────
# Index: the ORIGINAL VDB build, shipped from the HOST (wordindex.db:
# 58,645 words + 13,850 lemmas, BAAI/bge-m3 fp32, deduped, wvec table).
# Query in the same space, then resolve hits to verses through Strong's
# numbers -> the main interlinear words.strongs_base (indexed). The v1
# verse-vector index (verse_vectors.db) is retired.
# Query vectors: an HTTP embeddings endpoint using the SAME model
# (LEVI_EMBED_URL / LEVI_EMBED_MODEL / LEVI_EMBED_KEY, OpenAI-compatible),
# with local SentenceTransformer as fallback on bigger boxes.
_semantic_cache = None


def _embed_query(q: str):
    url = os.environ.get("LEVI_EMBED_URL", "")
    import urllib.request

    if url:
        model = os.environ.get("LEVI_EMBED_MODEL", "BAAI/bge-m3")
        key = os.environ.get("LEVI_EMBED_KEY", "")
        payload = json.dumps({"model": model, "input": [q]}).encode()
        req = urllib.request.Request(
            url.rstrip("/") + "/embeddings", data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"} if key else {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        vec = data["data"][0]["embedding"]
        import numpy as np

        v = np.asarray(vec, dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n else v

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(os.environ.get("LEVI_EMBED_MODEL", "BAAI/bge-m3"))
    return model.encode([q], normalize_embeddings=True)[0].astype("float32")


def _semantic():
    global _semantic_cache
    if _semantic_cache is not None:
        return _semantic_cache
    import numpy as np

    vec_path = os.environ.get("LEVI_VEC_PATH", "wordindex.db")
    try:
        vdb = sqlite3.connect(f"file:{vec_path}?mode=ro", uri=True)
        rows = vdb.execute(
            "SELECT vdb_id, lang, surface, strongs, vec FROM wvec WHERE surface IS NOT NULL"
        ).fetchall()
        if not rows:
            raise RuntimeError("no vectors")
        M = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
        norms = np.linalg.norm(M, axis=1, keepdims=True)
        norms[norms == 0] = 1e-8
        M = M / norms
    except Exception as exc:
        print(f"[levi] semantic index unavailable: {exc}")
        _semantic_cache = None
        return None
    _semantic_cache = (rows, M)
    return _semantic_cache


def _strongs_bases(lang: str, strongs_csv: str) -> list:
    # VDB strongs are bare numbers ("976"); the main DB indexes the
    # zero-padded, prefixed form ("G0976" / "H7225").
    bases = []
    for num in (strongs_csv or "").split(","):
        num = num.strip()
        if not num.isdigit():
            continue
        bases.append(("G" if lang == "grc" else "H") + f"{int(num):04d}")
    return bases


def semantic_search(q: str, limit: int = 15, testament: str = None, book: str = None) -> dict:
    q = (q or "").strip()
    if not q:
        return {"error": "q required", "results": []}
    import numpy as np

    parts = _semantic()
    b = resolve_book(book) if book else None
    limit = max(1, min(int(limit or 15), 50))
    if parts is None:
        return {"error": "semantic index unavailable", "results": []}
    rows, M = parts
    try:
        qv = _embed_query(q)
    except Exception as exc:
        print(f"[levi] query embedding failed: {exc}")
        return {"error": f"query embedding failed: {exc}", "results": []}
    scores = M @ qv
    idx = np.argsort(-scores)[:80]
    # hits are deduped ORIGINALS-ONLY words; resolve them to verses through
    # Strong's -> the main interlinear (words.strongs_base, indexed).
    verse_best, verse_hits = {}, {}
    for i in idx:
        vdb_id, lang, surface, strongs_csv, _vec = rows[i]
        bases = _strongs_bases(lang, strongs_csv)
        if not bases:
            continue
        s = float(scores[i])
        for base in bases:
            for (vid,) in conn().execute("SELECT DISTINCT verse_id FROM words WHERE strongs_base=? LIMIT 150", (base,)):
                if vid not in verse_best or s > verse_best[vid]:
                    verse_best[vid] = s
                verse_hits[vid] = verse_hits.get(vid, 0) + 1
    ranked = sorted(verse_best.items(), key=lambda t: -(t[1] + 0.02 * min(verse_hits.get(t[0], 1), 5)))[: limit * 3]
    out, seen = [], set()
    for vid, s in ranked:
        v = _one("SELECT book, chapter, verse, kjv_text, testament FROM verses WHERE id=?", (vid,))
        if not v or vid in seen:
            continue
        if b and v["book"] != b:
            continue
        if testament and v["testament"] != testament.upper():
            continue
        seen.add(vid)
        out.append({
            "ref": f'{v["book"]} {v["chapter"]}:{v["verse"]}',
            "book": v["book"], "chapter": v["chapter"], "verse": v["verse"],
            "kjv_text": v["kjv_text"],
            "score": round(s, 4),
        })
        if len(out) >= limit:
            break
    return {"query": q, "results": out, "index": "originals-words",
            "vectors": len(rows), "lang": "heb+grc"}


# ── Graph-neighbor search: the brain's own 3D space ────────────────────
_graph3d_cache = None


def _graph3d():
    global _graph3d_cache
    if _graph3d_cache is not None:
        return _graph3d_cache
    path = os.environ.get("LEVI_GRAPH3D_PATH", "graph3d.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
            coords = {c["id"]: (c["x"], c["y"], c["z"]) for c in data.get("chapters", [])}
        if not coords:
            raise RuntimeError("no chapters")
    except Exception as exc:
        print(f"[levi] graph3d unavailable: {exc}")
        _graph3d_cache = None
        return None
    _graph3d_cache = (coords, list(coords.keys()))
    return _graph3d_cache


def graph_neighbors(ref: str = None, q: str = None, limit: int = 10) -> dict:
    g = _graph3d()
    if g is None:
        return {"error": "graph index unavailable", "results": []}
    coords, cids = g
    limit = max(1, min(int(limit or 10), 40))

    seeds = set()
    if ref:
        p = parse_ref(ref)
        if p and p.get("chapter"):
            seeds.add(f'{p["book"]}.{p["chapter"]}')
    if q:
        for r in search((q or "").strip(), limit=6):
            if "book" in r and "chapter" in r:
                seeds.add(f'{r["book"]}.{r["chapter"]}')
    if not seeds:
        return {"error": "ref or q required", "results": []}

    best = {}
    for seed in seeds:
        base = coords.get(seed)
        if base is None:
            continue
        sx, sy, sz = base
        for cid in cids:
            if cid == seed:
                continue
            x, y, z = coords[cid]
            d2 = (x - sx) ** 2 + (y - sy) ** 2 + (z - sz) ** 2
            if cid not in best or d2 < best[cid][0]:
                best[cid] = (d2,)
    ordered = sorted(best.items(), key=lambda t: t[1][0])[:limit]
    out = []
    for cid, (d2,) in ordered:
        book, chapter = cid.rsplit(".", 1)
        out.append({
            "book": book,
            "chapter": int(chapter),
            "ref": f"{book} {chapter}",
            "distance": round(float(d2) ** 0.5, 4),
        })
    return {"ref": ref, "q": q, "results": out}

