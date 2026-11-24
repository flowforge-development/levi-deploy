"""Levi Monster ingestion pipeline.

Builds one SQLite database from many public-domain / openly licensed channels.
Run:  python3 -m levi_engine.ingest [--reset] [--only translations,stepbible,...]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

from . import db
from .config import (
    BOOKS, BOOK_BY_FULL, BOOK_CONTEXT, DATA_DIR, SRC_DIR, DB_PATH,
    ARAMAIC_BRIDGE, LANG_EVENTS, SOURCES, resolve_book,
)

# Extra abbreviated book names used by Nave / Torrey / cross-reference files.
_ABBREV = {
    "ge": "Genesis", "gen": "Genesis", "ex": "Exodus", "exo": "Exodus", "exod": "Exodus",
    "le": "Leviticus", "lev": "Leviticus", "nu": "Numbers", "num": "Numbers",
    "de": "Deuteronomy", "deu": "Deuteronomy", "jos": "Joshua", "josh": "Joshua",
    "jg": "Judges", "jdg": "Judges", "judg": "Judges", "ru": "Ruth", "rut": "Ruth",
    "1sa": "1Samuel", "2sa": "2Samuel", "1ki": "1Kings", "2ki": "2Kings",
    "1ch": "1Chronicles", "2ch": "2Chronicles", "ezr": "Ezra", "ne": "Nehemiah",
    "neh": "Nehemiah", "es": "Esther", "est": "Esther", "job": "Job",
    "ps": "Psalms", "psa": "Psalms", "psalm": "Psalms", "pr": "Proverbs",
    "pro": "Proverbs", "ec": "Ecclesiastes", "ecc": "Ecclesiastes",
    "so": "SongofSolomon", "song": "SongofSolomon", "sng": "SongofSolomon",
    "isa": "Isaiah", "jer": "Jeremiah", "la": "Lamentations", "lam": "Lamentations",
    "eze": "Ezekiel", "ezek": "Ezekiel", "da": "Daniel", "dan": "Daniel",
    "ho": "Hosea", "hos": "Hosea", "joe": "Joel", "jol": "Joel", "am": "Amos",
    "amo": "Amos", "ob": "Obadiah", "oba": "Obadiah", "jon": "Jonah",
    "mic": "Micah", "na": "Nahum", "nah": "Nahum", "nam": "Nahum", "hab": "Habakkuk",
    "zep": "Zephaniah", "zeph": "Zephaniah", "hag": "Haggai",
    "zec": "Zechariah", "zech": "Zechariah", "mal": "Malachi",
    "mt": "Matthew", "mat": "Matthew", "mr": "Mark", "mar": "Mark", "mrk": "Mark",
    "lu": "Luke", "luk": "Luke", "joh": "John", "jn": "John", "jhn": "John",
    "ac": "Acts", "act": "Acts", "ro": "Romans", "rom": "Romans",
    "1co": "1Corinthians", "2co": "2Corinthians", "ga": "Galatians", "gal": "Galatians",
    "eph": "Ephesians", "php": "Philippians", "phil": "Philippians",
    "col": "Colossians", "1th": "1Thessalonians", "2th": "2Thessalonians",
    "1ti": "1Timothy", "2ti": "2Timothy", "tit": "Titus", "phm": "Philemon",
    "phlm": "Philemon", "heb": "Hebrews", "jas": "James", "1pe": "1Peter",
    "2pe": "2Peter", "1jo": "1John", "2jo": "2John", "3jo": "3John",
    "1jn": "1John", "2jn": "2John", "3jn": "3John", "jude": "Jude",
    "re": "Revelation", "rev": "Revelation",
}

def _book(name: str) -> str | None:
    key = re.sub(r"[\s._\-]+", "", name or "").lower()
    if key in _ABBREV:
        return _ABBREV[key]
    return resolve_book(name)


def _osis_to_full(ref: str) -> str | None:
    """Gen.1.1 / 1Cor.13.4 / Ps.23.1 -> Genesis.1.1."""
    ref = ref.strip().replace(" ", "")
    m = re.match(r"^(.+?)\.(\d+)\.(\d+)$", ref)
    if not m:
        return None
    b = _book(m.group(1))
    if not b:
        return None
    return f"{b}.{int(m.group(2))}.{int(m.group(3))}"


def _clean(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ── Translations ─────────────────────────────────────────────────────

_TRANSLATION_FILES = [
    ("KJV", "KJV.db"), ("ASV", "ASV.db"), ("NHEB", "NHEB.db"),
    ("YLT", "YLT.db"), ("Darby", "Darby.db"), ("BBE", "BBE.db"),
    ("Webster", "Webster.db"), ("Geneva1599", "Geneva1599.db"),
    ("Vulgate", "Vulgate.db"),
]

def ingest_translations(conn):
    print("→ translations", flush=True)
    seen_books = set()
    total = 0
    for label, fname in _TRANSLATION_FILES:
        path = SRC_DIR / "scrollmapper" / fname
        if not path.exists():
            print(f"  ! missing {path.name}")
            continue
        src = sqlite3.connect(str(path))
        t = label
        books = {r[0]: r[1] for r in src.execute(f"SELECT id,name FROM {t}_books")}
        rows = src.execute(f"SELECT book_id,chapter,verse,text FROM {t}_verses").fetchall()
        src.close()
        # Each scrollmapper DB repeats the canon several times. Keep first copy per book.
        seen_in_file = set()
        batch = []
        for bid, ch, vs, text in rows:
            bname = books.get(bid)
            if not bname:
                continue
            full = _book(bname)
            if not full:
                continue
            if full in seen_in_file:
                continue
            if full not in seen_books:
                # first translation establishes verse skeleton
                pass
            key = (full, int(ch), int(vs))
            if key in seen_in_file:
                continue
            seen_in_file.add(key)
            vid = f"{full}.{int(ch)}.{int(vs)}"
            text = (text or "").strip()
            if label == "KJV":
                conn.execute(
                    "INSERT OR IGNORE INTO verses(id,osis,book,chapter,verse,testament,kjv_text) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (vid, f"{BOOK_BY_FULL[full]['short']}.{int(ch)}.{int(vs)}", full,
                     int(ch), int(vs), BOOK_BY_FULL[full]["testament"], text))
            batch.append((vid, label, text))
            total += 1
            if len(batch) >= 20000:
                conn.executemany("INSERT OR REPLACE INTO translations(verse_id,translation,text) VALUES(?,?,?)", batch)
                batch = []
        if batch:
            conn.executemany("INSERT OR REPLACE INTO translations(verse_id,translation,text) VALUES(?,?,?)", batch)
        for b in seen_in_file:
            seen_books.add(b[0] if isinstance(b, tuple) else b)
        conn.commit()
        print(f"  {label}: {len(seen_in_file)} verse rows")
    # fill remaining verse skeleton rows (LXX-only books not included)
    conn.execute("UPDATE verses SET text = kjv_text WHERE text IS NULL")
    conn.commit()
    print(f"  total translation rows: {total}")


# ── STEPBible original-language tokens ───────────────────────────────

_STRONG_RX = re.compile(r"[HG]\d+[A-Z]?")

def _extract_strong(field: str) -> tuple[str, str]:
    """Return (display_code, base_code) from a dStrong field."""
    if not field:
        return "", ""
    # Prefer the root inside curly braces.
    roots = re.findall(r"\{([HG]\d+[A-Z]?)\}", field)
    code = roots[0] if roots else ""
    if not code:
        m = _STRONG_RX.search(field)
        code = m.group(0) if m else ""
    base = re.match(r"[HG]\d+", code).group(0) if code else ""
    return code, base


def _step_rows(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or "#" not in line:
            continue
        # Ref format: English_ref(Hebrew_ref)#word=type.  The main ref is the
        # English/NRSV-style verse, which is what we align to KJV.  Psalm
        # titles use verse 0; they are folded onto verse 1 with negative
        # token positions so they sort before the verse proper.
        m = re.match(
            r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)"
            r"(?:\((\d+)\.(\d+)\))?"
            r"#(\d+)=([A-Za-z()]+)\t", line)
        if not m:
            continue
        book = m.group(1)
        ch = int(m.group(2))
        vs = int(m.group(3))
        is_title = (vs == 0)
        if is_title:
            vs = 1
        yield f"{book}.{ch}.{vs}", int(m.group(6)), m.group(7), line.split("\t"), is_title


def ingest_stepbible(conn):
    print("→ STEPBible TAHOT/TAGNT", flush=True)
    step = SRC_DIR / "stepbible"
    verse_text = defaultdict(list)
    verse_words = defaultdict(list)
    batch = []
    nwords = 0
    files = sorted(step.glob("TAHOT*.txt")) + sorted(step.glob("TAGNT*.txt"))
    for path in files:
        print(f"  {path.name[:28]}…", flush=True)
        for osis, pos, wtype, cols, is_title in _step_rows(path):
            vid = _osis_to_full(osis)
            if not vid:
                continue
            if is_title:
                pos = -1000 + pos
            is_hebrew = "TAHOT" in path.name
            if is_hebrew:
                surface = (cols[1] if len(cols) > 1 else "").replace("/", "").strip()
                translit = (cols[2] if len(cols) > 2 else "").strip()
                gloss = _clean(cols[3] if len(cols) > 3 else "")
                strong_field = cols[4] if len(cols) > 4 else ""
                morph = (cols[5] if len(cols) > 5 else "").strip()
                meaning_var = _clean(cols[6] if len(cols) > 6 else "")
                spelling_var = _clean(cols[7] if len(cols) > 7 else "")
                root_field = cols[8] if len(cols) > 8 else ""
            else:
                raw = cols[1] if len(cols) > 1 else ""
                m = re.match(r"^(.*?)(?:\s*\(([^)]*)\))?$", raw)
                surface = (m.group(1) if m else raw).strip()
                translit = (m.group(2) if m and m.group(2) else "").strip()
                gloss = _clean(cols[2] if len(cols) > 2 else "")
                strong_field = cols[3] if len(cols) > 3 else ""
                morph = ""
                if "=" in strong_field:
                    strong_field, morph = strong_field.split("=", 1)
                meaning_var = _clean(cols[6] if len(cols) > 6 else "")
                spelling_var = _clean(cols[7] if len(cols) > 7 else "")
                root_field = cols[11] if len(cols) > 11 else ""
            code, base = _extract_strong(strong_field)
            root_code, _ = _extract_strong(root_field)
            lang = "grc"
            if is_hebrew:
                lang = "arc" if morph[:1].upper() == "A" else "heb"
            variant = " | ".join(x for x in (meaning_var, spelling_var) if x)
            if wtype not in ("L", "NKO"):
                variant = (variant + f" | type={wtype}").strip(" |")
            lemma = ""
            if not is_hebrew and "=" in (cols[4] if len(cols) > 4 else ""):
                lemma = cols[4].split("=", 1)[0].strip()
            if surface or code:
                batch.append((vid, pos, lang, surface, translit, lemma, code, base,
                              morph, gloss, root_code, variant, "STEPBible"))
                verse_text[vid].append((lang, surface))
                verse_words[vid].append((lang, surface, code, base, gloss, morph))
                nwords += 1
            if len(batch) >= 20000:
                conn.executemany(
                    "INSERT INTO words(verse_id,pos,lang,surface,translit,lemma,strongs,strongs_base,morph,gloss,root,variant,source) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                conn.commit()
                batch = []
    if batch:
        conn.executemany(
            "INSERT INTO words(verse_id,pos,lang,surface,translit,lemma,strongs,strongs_base,morph,gloss,root,variant,source) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
    conn.commit()

    # Reconstruct plain text and old-style enriched text per verse.
    updates = []
    for vid, parts in verse_text.items():
        heb = " ".join(s for l, s in parts if l in ("heb", "arc"))
        grc = " ".join(s for l, s in parts if l == "grc")
        original = " ".join(s for l, s in parts)
        enriched = "[" + vid + "] " + " | ".join(
            f"{s} [{c}] ({g})".strip() for l, s, c, b, g, m in verse_words[vid] if s
        )
        langs = {l for l, _ in parts}
        lang = "mixed" if len(langs) > 1 else next(iter(langs), None)
        note = ""
        if "heb" in langs and "arc" in langs:
            note = "Hebrew/Aramaic mixed verse (word-level tags available)"
        updates.append((heb, grc, enriched, len(parts), lang, note, vid))
        if len(updates) >= 10000:
            conn.executemany("UPDATE verses SET hebrew=?,greek=?,text=?,word_count=?,lang=?,lang_note=? WHERE id=?", updates)
            conn.commit(); updates = []
    if updates:
        conn.executemany("UPDATE verses SET hebrew=?,greek=?,text=?,word_count=?,lang=?,lang_note=? WHERE id=?", updates)
    conn.commit()
    print(f"  {nwords} word tokens across {len(verse_text)} verses")


# ── Lexicons and semantic domains ────────────────────────────────────

def _parse_strongs_js(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return {}


def _sdbh_defs(entry: dict):
    defs, domains = [], []
    for bf in entry.get("BaseForms", []) or []:
        for meaning in bf.get("LEXMeanings", []) or []:
            for dom in meaning.get("LEXDomains", []) or []:
                d = dom.get("Domain")
                if d and d not in domains:
                    domains.append(d)
            for sense in meaning.get("LEXSenses", []) or []:
                sd = sense.get("DefinitionShort") or ""
                if not sd:
                    gl = sense.get("Glosses") or []
                    sd = ", ".join(gl)
                if sd and sd not in defs:
                    defs.append(sd)
    return "; ".join(defs[:4]), domains


def ingest_lexicons(conn):
    print("→ lexicons / domains", flush=True)
    conn.execute("DELETE FROM lexicon")
    conn.execute("DELETE FROM domains")
    # Strong's dictionaries
    for lang, path in (("heb", DATA_DIR / "strongs/hebrew/strongs-hebrew-dictionary.js"),
                       ("grc", DATA_DIR / "strongs/greek/strongs-greek-dictionary.js")):
        data = _parse_strongs_js(path)
        rows = []
        for key, entry in data.items():
            prefix = key[0]
            num = key[1:]
            code = f"{prefix}{num.zfill(4)}"
            rows.append((code, code, lang, entry.get("lemma", ""), entry.get("translit", ""),
                         "", entry.get("kjv_def", "") or entry.get("strongs_def", ""),
                         _clean(entry.get("strongs_def", "") or entry.get("derivation", "")),
                         "Strongs"))
        conn.executemany("INSERT OR REPLACE INTO lexicon(strongs,base,lang,lemma,translit,morph,gloss,definition,source) VALUES(?,?,?,?,?,?,?,?,?)", rows)
        print(f"  Strong's {lang}: {len(rows)}")
    # STEPBible brief lexicons
    for lang, pattern in (("heb", "TBESH*.txt"), ("grc", "TBESG*.txt")):
        for path in (SRC_DIR / "stepbible").glob(pattern):
            rows = []
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.startswith(("H0", "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9",
                                        "G0", "G1", "G2", "G3", "G4", "G5")):
                    continue
                cols = line.split("\t")
                if len(cols) < 6:
                    continue
                # TBESH/TBESG: eStrong, dStrong (extended), uStrong, lemma,
                # translit, morph, gloss, definition.  Key by the extended
                # Strong's code so H0430G/H0430H do not overwrite each other.
                e = cols[0].strip()
                em = re.match(r"^([HG]\d+)", e)
                if not em:
                    continue
                base = em.group(1)
                strong = base
                if len(cols) > 1:
                    dm = re.match(r"^([HG]\d+[A-Z]?)", cols[1].strip())
                    if dm:
                        strong = dm.group(1)
                lemma = cols[3].strip() if len(cols) > 3 else ""
                translit = cols[4].strip() if len(cols) > 4 else ""
                morph = cols[5].strip() if len(cols) > 5 else ""
                gloss = _clean(cols[6]) if len(cols) > 6 else ""
                definition = _clean(cols[7]) if len(cols) > 7 else ""
                rows.append((strong, base, lang, lemma, translit, morph, gloss, definition, path.name[:5]))
            if rows:
                conn.executemany("INSERT OR REPLACE INTO lexicon(strongs,base,lang,lemma,translit,morph,gloss,definition,source) VALUES(?,?,?,?,?,?,?,?,?)", rows)
                print(f"  {path.name[:5]}: {len(rows)}")
    # SDBH / SDBG
    for lang, path in (
        ("heb", DATA_DIR / "sdbh/dictionaries/hebrew/JSON/UBSHebrewDic-v0.9.2-en.JSON"),
        ("grc", DATA_DIR / "sdbh/dictionaries/greek/JSON/UBSGreekNTDic-v1.1-en.JSON"),
    ):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        lrows, drows = [], []
        for entry in data:
            lemma = entry.get("Lemma", "")
            defs, domains = _sdbh_defs(entry)
            for code in entry.get("StrongCodes", []) or []:
                base = re.match(r"^[HG]\d+", code).group(0) if re.match(r"^[HG]\d+", code) else code
                lrows.append((code, base, lang, lemma, "", "", "", defs, "SDBH"))
                for d in domains:
                    drows.append((code, "", d, "SDBH"))
        conn.executemany("INSERT OR REPLACE INTO lexicon(strongs,base,lang,lemma,translit,morph,gloss,definition,source) VALUES(?,?,?,?,?,?,?,?,?)", lrows)
        conn.executemany("INSERT INTO domains(strongs,code,label,source) VALUES(?,?,?,?)", drows)
        print(f"  SDBH {lang}: {len(lrows)} entries, {len(drows)} domain links")
    # SAHD cultural tags
    sahd = DATA_DIR / "sahd/sahd_tags.json"
    if sahd.exists():
        try:
            entries = json.loads(sahd.read_text(encoding="utf-8"))
            drows = []
            for e in entries:
                heb = e.get("hebrew", "")
                for f in e.get("semantic_fields", []) or []:
                    drows.append(("", "", f"{heb} → {f}", "SAHD"))
            conn.executemany("INSERT INTO domains(strongs,code,label,source) VALUES(?,?,?,?)", drows)
            print(f"  SAHD tags: {len(drows)}")
        except Exception as exc:
            print(f"  ! SAHD: {exc}")
    # LSJ (optional, large): keys and short glosses
    for path in (SRC_DIR / "stepbible").glob("TFLSJ*.txt"):
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.startswith(("G0", "G1", "G2", "G3", "G4", "G5")):
                continue
            cols = line.split("\t")
            if len(cols) < 4:
                continue
            strong = cols[0].strip()
            if not re.match(r"^[HG]\d+", strong):
                continue
            base = re.match(r"^[HG]\d+", strong).group(0)
            lemma = cols[1].strip() if len(cols) > 1 else ""
            gloss = _clean(cols[3] if len(cols) > 3 else "")
            definition = _clean("\t".join(cols[4:]) if len(cols) > 4 else "")
            rows.append((strong, base, "grc", lemma, "", "", gloss, definition, "LSJ"))
        if rows:
            conn.executemany("INSERT OR IGNORE INTO lexicon(strongs,base,lang,lemma,translit,morph,gloss,definition,source) VALUES(?,?,?,?,?,?,?,?,?)", rows)
            print(f"  LSJ: {len(rows)}")
    conn.commit()


# ── Cross references ─────────────────────────────────────────────────

def ingest_enrich_words(conn):
    print("→ enrich words", flush=True)
    conn.execute(
        "UPDATE words SET lemma=COALESCE((SELECT l.lemma FROM lexicon l "
        "WHERE l.strongs=words.strongs AND l.lemma<>'' LIMIT 1), lemma) "
        "WHERE (lemma IS NULL OR lemma='') AND lang IN ('heb','arc')")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM words WHERE lemma IS NOT NULL AND lemma<>''").fetchone()[0]
    print(f"  {n} words with lemma")


def ingest_crossrefs(conn):
    print("→ cross references", flush=True)
    path = SRC_DIR / "xrefs/cross_references.txt"
    if not path.exists():
        print("  ! missing cross_references.txt"); return
    rows = []
    with path.open(encoding="utf-8", errors="replace") as f:
        next(f, None)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            a = _osis_to_full(parts[0])
            b = _osis_to_full(parts[1])
            if not a or not b:
                continue
            try:
                votes = int(parts[2])
            except ValueError:
                votes = 0
            rows.append((a, b, votes, "OpenBible"))
            if len(rows) >= 50000:
                conn.executemany("INSERT OR REPLACE INTO cross_refs(from_id,to_id,votes,source) VALUES(?,?,?,?)", rows)
                conn.commit(); rows = []
    if rows:
        conn.executemany("INSERT OR REPLACE INTO cross_refs(from_id,to_id,votes,source) VALUES(?,?,?,?)", rows)
    conn.commit()
    print(f"  {conn.execute('SELECT COUNT(*) FROM cross_refs').fetchone()[0]} links")


# ── LXX ──────────────────────────────────────────────────────────────

def _strip_strong_tags(s: str) -> str:
    s = re.sub(r"<S>\d+</S>", "", s or "")
    s = re.sub(r"<m>[^<]*</m>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()

def ingest_lxx(conn):
    print("→ Septuagint", flush=True)
    path = SRC_DIR / "lxx/LXX1.SQLite3"
    if not path.exists():
        print("  ! missing LXX"); return
    src = sqlite3.connect(str(path))
    books = src.execute("SELECT book_number,short_name,long_name FROM books").fetchall()
    conn.executemany("INSERT OR REPLACE INTO lxx_books(number,code,name) VALUES(?,?,?)", books)
    rows = []
    for book_no, ch, vs, text in src.execute("SELECT book_number,chapter,verse,text FROM verses"):
        rows.append((book_no, ch, vs, _strip_strong_tags(text)))
        if len(rows) >= 20000:
            conn.executemany("INSERT OR REPLACE INTO lxx_verses(book_no,chapter,verse,text) VALUES(?,?,?,?)", rows)
            conn.commit(); rows = []
    if rows:
        conn.executemany("INSERT OR REPLACE INTO lxx_verses(book_no,chapter,verse,text) VALUES(?,?,?,?)", rows)
    conn.commit()
    src.close()
    print(f"  {conn.execute('SELECT COUNT(*) FROM lxx_verses').fetchone()[0]} verses")


# ── Topical index (Nave / Torrey) ────────────────────────────────────

_BOOK_TOKEN = re.compile(r"^(?:[1-3]\s*)?[A-Za-z]{2,}\.?$")

def _expand_ref_group(group: str):
    """Expand '1Ch 6:2,3; 23:13' into full verse ids."""
    ids = []
    current_book = None
    for seg in group.split(";"):
        seg = seg.strip().rstrip(".")
        if not seg:
            continue
        m = re.match(r"^((?:[1-3]\s*)?[A-Za-z]{2,})\.?\s+(\d+)(?::(.*))?$", seg)
        if m:
            current_book = _book(m.group(1))
            ch = int(m.group(2))
            vpart = m.group(3)
        else:
            m2 = re.match(r"^(\d+):(.*)$", seg)
            if m2 and current_book:
                ch = int(m2.group(1)); vpart = m2.group(2)
            else:
                continue
        if not current_book:
            continue
        if not vpart:
            # whole chapter: cap at 200 verses
            for v in range(1, 201):
                ids.append(f"{current_book}.{ch}.{v}")
            continue
        for piece in vpart.split(","):
            piece = piece.strip()
            mr = re.match(r"^(\d+)(?:[-–](\d+))?$", piece)
            if not mr:
                continue
            a = int(mr.group(1)); b = int(mr.group(2)) if mr.group(2) else a
            for v in range(a, min(b, a + 200) + 1):
                ids.append(f"{current_book}.{ch}.{v}")
    return ids

def ingest_topics(conn):
    print("→ topical indexes", flush=True)
    for source, fname in (("Nave", "nave-entries.jsonl"), ("Torrey", "torrey-entries.jsonl")):
        path = SRC_DIR / "commentary" / fname
        if not path.exists():
            continue
        rows = []
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                topic = (e.get("sourceTopic") or "").strip()
                entry = (e.get("rawText") or "").strip()
                for g in e.get("refGroups", []) or []:
                    for vid in _expand_ref_group(g):
                        rows.append((topic, vid, source, entry))
                if len(rows) >= 50000:
                    conn.executemany("INSERT OR IGNORE INTO topics(topic,verse_id,source,entry) VALUES(?,?,?,?)", rows)
                    conn.commit(); rows = []
        if rows:
            conn.executemany("INSERT OR IGNORE INTO topics(topic,verse_id,source,entry) VALUES(?,?,?,?)", rows)
        conn.commit()
        print(f"  {source}: {conn.execute('SELECT COUNT(*) FROM topics WHERE source=?',(source,)).fetchone()[0]} links")


# ── Commentary (Calvin / F. B. Meyer) ────────────────────────────────

_CALVIN_BOOKS = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
    "1SA": "1Samuel", "2SA": "2Samuel", "1KI": "1Kings", "2KI": "2Kings",
    "1CH": "1Chronicles", "2CH": "2Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
    "EST": "Esther", "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "SongofSolomon", "ISA": "Isaiah", "JER": "Jeremiah",
    "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea",
    "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah", "MIC": "Micah",
    "NAM": "Nahum", "HAB": "Habakkuk", "ZEP": "Zephaniah", "HAG": "Haggai",
    "ZEC": "Zechariah", "MAL": "Malachi", "MAT": "Matthew", "MRK": "Mark",
    "LUK": "Luke", "JHN": "John", "ACT": "Acts", "ROM": "Romans",
    "1CO": "1Corinthians", "2CO": "2Corinthians", "GAL": "Galatians",
    "EPH": "Ephesians", "PHP": "Philippians", "COL": "Colossians",
    "1TH": "1Thessalonians", "2TH": "2Thessalonians", "1TI": "1Timothy",
    "2TI": "2Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAS": "James", "1PE": "1Peter", "2PE": "2Peter", "1JN": "1John",
    "2JN": "2John", "3JN": "3John", "JUD": "Jude", "REV": "Revelation",
}

def _flatten_content(content) -> str:
    out = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("text"):
                    out.append(str(item["text"]))
                elif item.get("content"):
                    out.append(_flatten_content(item["content"]))
            elif isinstance(item, str):
                out.append(item)
    elif isinstance(content, str):
        out.append(content)
    return _clean(" ".join(out))

def ingest_commentary(conn):
    print("→ commentary", flush=True)
    base = SRC_DIR / "commentary/pillar/c"
    for author in ("calvin", "fbmeyer"):
        root = base / author
        if not root.exists():
            continue
        n = 0
        for bookdir in sorted(root.iterdir()):
            if not bookdir.is_dir():
                continue
            book = _CALVIN_BOOKS.get(bookdir.name.upper())
            if not book:
                continue
            for jf in sorted(bookdir.glob("*.json")):
                try:
                    d = json.loads(jf.read_text(encoding="utf-8"))
                except Exception:
                    continue
                ch = d.get("chapter") or {}
                chap_no = ch.get("number") or int(jf.stem)
                for item in ch.get("content", []) or []:
                    if item.get("type") == "verse":
                        vs = int(item.get("number") or 0)
                        text = _flatten_content(item.get("content"))
                        if text:
                            vid = f"{book}.{int(chap_no)}.{vs}"
                            conn.execute(
                                "INSERT INTO commentary(verse_id,author,work,text,source) VALUES(?,?,?,?,?)",
                                (vid, author, "Calvin" if author == "calvin" else "F. B. Meyer", text, "pillar"))
                            n += 1
                    elif item.get("type") == "chapter":
                        text = _flatten_content(item.get("content"))
                        if text:
                            vid = f"{book}.{int(chap_no)}.0"
                            conn.execute(
                                "INSERT INTO commentary(verse_id,author,work,text,source) VALUES(?,?,?,?,?)",
                                (vid, author, "Calvin" if author == "calvin" else "F. B. Meyer", text, "pillar"))
                            n += 1
                if n % 2000 < 5:
                    conn.commit()
        conn.commit()
        print(f"  {author}: {n} entries")


# ── Language tags ────────────────────────────────────────────────────

def ingest_language(conn):
    print("→ language tags", flush=True)
    rows = []
    # Word-level Aramaic runs
    cur = conn.execute("SELECT verse_id, lang, MIN(pos), MAX(pos), COUNT(*) FROM words WHERE lang IN ('heb','arc') GROUP BY verse_id,lang")
    per_verse = defaultdict(dict)
    for vid, lang, mn, mx, n in cur:
        per_verse[vid][lang] = (mn, mx, n)
    for vid, d in per_verse.items():
        if "arc" in d:
            mn, mx, n = d["arc"]
            total = sum(x[2] for x in d.values())
            note = "Aramaic portion" if "heb" in d else "Aramaic verse"
            rows.append((vid, "arc", "words", mn, mx, note))
            if "heb" in d:
                rows.append((vid, "mixed", "verse", None, None, "Hebrew and Aramaic in the same verse"))
    # Curated mixed-language events use OSIS refs.
    for osis, lang, scope, wr, note in LANG_EVENTS:
        vid = _osis_to_full(osis)
        if not vid:
            continue
        a, b = None, None
        if wr:
            m = re.match(r"^(\d+)-(\d*)$", wr)
            if m:
                a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else None
        rows.append((vid, lang, scope, a, b, note))
    conn.executemany("INSERT OR IGNORE INTO lang_tags(verse_id,lang,scope,word_start,word_end,note) VALUES(?,?,?,?,?,?)", rows)
    conn.commit()
    # Put curated notes on the verse record too.
    for osis, lang, scope, wr, note in LANG_EVENTS:
        vid = _osis_to_full(osis)
        if vid:
            conn.execute("UPDATE verses SET lang_note=? WHERE id=? AND (lang_note IS NULL OR lang_note='')",
                         (note, vid))
    conn.commit()
    print(f"  {len(rows)} language tags")


# ── Book context / bridge / chunks / places ──────────────────────────

def ingest_book_context(conn):
    print("→ book context", flush=True)
    rows = []
    for b in BOOKS:
        full = b["full"]
        c = BOOK_CONTEXT.get(full, {})
        primary = "heb" if b["testament"] == "OT" else "grc"
        rows.append((full, c.get("author", ""), c.get("date", ""), c.get("genre", ""),
                     c.get("audience", ""), c.get("purpose", ""), c.get("register", ""),
                     c.get("summary", ""), primary, "arc" if full in ("Daniel", "Ezra") else ""))
    conn.executemany("INSERT OR REPLACE INTO book_context(book,author,date,genre,audience,purpose,register,summary,lang_primary,lang_secondary) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  {len(rows)} books")


def ingest_aramaic_bridge(conn):
    print("→ Koine→Aramaic bridge", flush=True)
    conn.execute("DELETE FROM aramaic_bridge")
    conn.executemany(
        "INSERT INTO aramaic_bridge(greek_strong,greek_lemma,aramaic,translit,gloss,confidence,note) VALUES(?,?,?,?,?,?,?)",
        ARAMAIC_BRIDGE)
    conn.commit()
    print(f"  {len(ARAMAIC_BRIDGE)} entries")


def ingest_chunks(conn):
    print("→ chunks (sof pasuq / Greek clause units)", flush=True)
    rows = []
    for r in conn.execute("SELECT id,book,chapter,verse,kjv_text,hebrew,greek,lang FROM verses ORDER BY book,chapter,verse"):
        if r["hebrew"]:
            kind = "sof_pasuq"
            label = f'{r["book"]} {r["chapter"]}:{r["verse"]} — Masoretic verse (sof pasuq)'
            text = r["hebrew"]
        elif r["greek"]:
            kind = "greek_clause"
            label = f'{r["book"]} {r["chapter"]}:{r["verse"]} — Greek NT clause/period'
            text = r["greek"]
        else:
            kind = "verse"
            label = f'{r["book"]} {r["chapter"]}:{r["verse"]}'
            text = r["kjv_text"] or ""
        rows.append((r["id"], r["book"], r["chapter"], r["verse"], r["verse"], kind, label, text))
    conn.executemany("INSERT OR REPLACE INTO chunks(id,book,chapter,verse_start,verse_end,kind,label,text) VALUES(?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  {len(rows)} chunks")


def ingest_places(conn):
    print("→ proper names / places", flush=True)
    path = next((SRC_DIR / "stepbible").glob("TIPNR*.txt"), None)
    if not path:
        return
    conn.execute("DELETE FROM places")
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("$", "-", "#", "TIPNR", "Names", "Proper", "Lists", "Strong", "Spreadsheet", "JSON", "–", "\t")):
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        head = cols[0].strip()
        m = re.match(r"^([^@]+)@[^.]+\.\d+\.\d+(?:-[A-Za-z]+)?=([HG]\d+)", head)
        if not m:
            continue
        name = m.group(1).strip()
        strong = m.group(2)
        desc = _clean(cols[1]) if len(cols) > 1 else ""
        rows.append((name, strong, "person/place", desc, head))
        if len(rows) >= 5000:
            conn.executemany("INSERT INTO places(name,strongs,kind,description,refs) VALUES(?,?,?,?,?)", rows)
            rows = []
    if rows:
        conn.executemany("INSERT INTO places(name,strongs,kind,description,refs) VALUES(?,?,?,?,?)", rows)
    conn.commit()
    print(f"  {conn.execute('SELECT COUNT(*) FROM places').fetchone()[0]} names")


# ── Language purpose (register) ──────────────────────────────────────

_PURPOSE_OVERRIDES = [
    ("Genesis", 23, 23, "trade/administration", "land purchase transaction"),
    ("Genesis", 41, 41, "trade/administration", "Joseph's administrative rise"),
    ("Genesis", 47, 47, "trade/administration", "famine administration"),
    ("Exodus", 20, 24, "official", "covenant law code and legal assembly"),
    ("Exodus", 25, 31, "official", "tabernacle instructions"),
    ("Exodus", 35, 40, "official", "tabernacle construction"),
    ("Leviticus", 1, 27, "official", "priestly ritual legislation"),
    ("Numbers", 1, 10, "official", "census and camp organization"),
    ("Deuteronomy", 12, 26, "official", "covenant law code"),
    ("Joshua", 13, 22, "official", "land allotment records"),
    ("1Chronicles", 1, 9, "official", "genealogical records"),
    ("1Chronicles", 23, 29, "official", "temple administration"),
    ("1Kings", 4, 10, "trade/administration", "Solomon's administration and trade"),
    ("1Kings", 9, 10, "trade/administration", "trade and building projects"),
    ("2Kings", 12, 12, "trade/administration", "temple repair administration"),
    ("2Kings", 22, 23, "official", "covenant reform records"),
    ("2Chronicles", 1, 9, "trade/administration", "Solomon's administration and trade"),
    ("Ezra", 1, 10, "official", "Persian-era administrative records"),
    ("Nehemiah", 1, 13, "official", "administrative memoir and lists"),
    ("Esther", 1, 10, "official", "Persian court narrative"),
    ("Psalms", 1, 150, "liturgical", "psalter / temple prayer"),
    ("Proverbs", 1, 31, "common", "wisdom instruction"),
    ("Ecclesiastes", 1, 12, "common", "wisdom reflection"),
    ("Job", 1, 42, "common", "wisdom poetry"),
    ("SongofSolomon", 1, 8, "liturgical", "love poetry / possible wedding song"),
    ("Isaiah", 1, 66, "common", "prophetic oracle"),
    ("Jeremiah", 1, 52, "common", "prophetic oracle"),
    ("Lamentations", 1, 5, "liturgical", "communal lament"),
    ("Ezekiel", 1, 48, "common", "prophetic vision"),
    ("Ezekiel", 27, 27, "trade/administration", "Tyre trade lament"),
    ("Daniel", 1, 6, "official", "court narrative"),
    ("Daniel", 7, 12, "liturgical", "apocalyptic vision"),
    ("Hosea", 1, 14, "common", "prophetic oracle"),
    ("Joel", 1, 3, "liturgical", "prophetic liturgy"),
    ("Amos", 1, 9, "common", "prophetic oracle"),
    ("Obadiah", 1, 1, "common", "prophetic oracle"),
    ("Jonah", 1, 4, "common", "prophetic narrative"),
    ("Micah", 1, 7, "common", "prophetic oracle"),
    ("Nahum", 1, 3, "common", "prophetic oracle"),
    ("Habakkuk", 1, 3, "liturgical", "prophetic dialogue and psalm"),
    ("Zephaniah", 1, 3, "common", "prophetic oracle"),
    ("Haggai", 1, 2, "official", "temple rebuilding oracles"),
    ("Zechariah", 1, 14, "liturgical", "vision and temple oracles"),
    ("Malachi", 1, 4, "official", "covenant disputation"),
    ("Matthew", 5, 7, "liturgical", "Sermon on the Mount"),
    ("Matthew", 26, 28, "liturgical", "passion and resurrection narrative"),
    ("Mark", 14, 16, "liturgical", "passion and resurrection narrative"),
    ("Luke", 1, 2, "liturgical", "infancy narrative and songs"),
    ("Luke", 22, 24, "liturgical", "passion and resurrection narrative"),
    ("John", 13, 17, "liturgical", "farewell discourse and passion"),
    ("Acts", 1, 28, "official", "mission history and public speeches"),
    ("Romans", 1, 16, "official", "theological letter"),
    ("1Corinthians", 1, 16, "common", "pastoral letter"),
    ("2Corinthians", 1, 13, "common", "apostolic defense"),
    ("Galatians", 1, 6, "official", "polemical letter"),
    ("Ephesians", 1, 6, "liturgical", "theological meditation and blessing"),
    ("Philippians", 1, 4, "common", "friendship letter"),
    ("Colossians", 1, 4, "liturgical", "hymn and doctrinal correction"),
    ("1Thessalonians", 1, 5, "common", "pastoral letter"),
    ("2Thessalonians", 1, 3, "common", "pastoral correction"),
    ("1Timothy", 1, 6, "official", "church order manual"),
    ("2Timothy", 1, 4, "official", "farewell charge"),
    ("Titus", 1, 3, "official", "church order manual"),
    ("Philemon", 1, 1, "common", "personal appeal"),
    ("Hebrews", 1, 13, "liturgical", "sermon / homily"),
    ("James", 1, 5, "common", "wisdom instruction"),
    ("1Peter", 1, 5, "liturgical", "baptismal exhortation"),
    ("2Peter", 1, 3, "official", "testament and warning"),
    ("1John", 1, 5, "liturgical", "homily"),
    ("2John", 1, 1, "common", "short letter"),
    ("3John", 1, 1, "common", "short letter"),
    ("Jude", 1, 1, "liturgical", "polemic and doxology"),
    ("Revelation", 1, 22, "liturgical", "apocalyptic worship vision"),
    ("Revelation", 18, 18, "trade/administration", "commerce lament"),
]

def _purpose_for(book: str, chapter: int):
    matches = [(c2 - c1, purpose, note)
               for b, c1, c2, purpose, note in _PURPOSE_OVERRIDES
               if b == book and c1 <= chapter <= c2]
    if matches:
        _, purpose, note = min(matches, key=lambda x: x[0])
        return purpose, note
    reg = BOOK_CONTEXT.get(book, {}).get("register", "common")
    purpose = reg.split("+")[0].strip() or "common"
    return purpose, "default register for this book/genre"


def ingest_purpose(conn):
    print("→ language purpose / register", flush=True)
    conn.execute("DELETE FROM language_purpose")
    rows = []
    for r in conn.execute("SELECT id,book,chapter,verse,lang FROM verses ORDER BY book,chapter,verse"):
        purpose, note = _purpose_for(r["book"], r["chapter"])
        lang = {"heb": "Hebrew", "arc": "Aramaic", "grc": "Greek",
                "mixed": "Hebrew/Aramaic"}.get(r["lang"], r["lang"] or "")
        period = BOOK_CONTEXT.get(r["book"], {}).get("date", "")
        rows.append((r["id"], lang, purpose, period, "heuristic", note))
    conn.executemany("INSERT OR REPLACE INTO language_purpose(verse_id,language,purpose,period,confidence,note) VALUES(?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  {len(rows)} verses tagged")


def ingest_overlap(conn):
    print("→ book overlap graph", flush=True)
    conn.execute("DELETE FROM book_overlap")
    rows = []
    q = """
    SELECT va.book AS a, vb.book AS b, COUNT(*) AS score
    FROM cross_refs x
    JOIN verses va ON va.id = x.from_id
    JOIN verses vb ON vb.id = x.to_id
    WHERE va.book <> vb.book
    GROUP BY va.book, vb.book
    """
    for a, b, score in conn.execute(q):
        rows.append((a, b, int(score), "cross_refs"))
    # Top 12 per book
    by_book = defaultdict(list)
    for a, b, score, basis in rows:
        by_book[a].append((b, score, basis))
    top = []
    for a, lst in by_book.items():
        for b, score, basis in sorted(lst, key=lambda x: -x[1])[:12]:
            top.append((a, b, score, basis))
    conn.executemany("INSERT OR REPLACE INTO book_overlap(book,related_book,score,basis) VALUES(?,?,?,?)", top)
    conn.commit()
    print(f"  {len(top)} overlap edges")


def ingest_characters(conn):
    print("→ characters / prosopography", flush=True)
    path = next((SRC_DIR / "stepbible").glob("TIPNR*.txt"), None)
    if not path:
        return
    conn.execute("DELETE FROM characters")
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "@" not in line or line.startswith(("$", "-", "#", "TIPNR", "Names", "Proper", "Lists", "Strong", "Spreadsheet", "JSON", "–")):
            continue
        cols = line.split("\t")
        head = cols[0].strip()
        m = re.match(r"^([^@]+)@([^=\t]+)=([HG]\d+)", head)
        if not m:
            continue
        name, refs, strong = m.group(1).strip(), m.group(2).strip(), m.group(3)
        desc = _clean(cols[1]) if len(cols) > 1 else ""
        low = desc.lower()
        person_markers = ("man ", "woman", "king", "queen", "prophet", "priest", "levite",
                          "son of", "daughter", "brother", "father", "mother", "wife",
                          "husband", "servant", "apostle", "disciple", "living at the time of",
                          "high priest", "judge", "governor", "emperor", "pharaoh")
        place_markers = ("place", "city", "town", "region", "mountain", "river", "valley",
                         "land of", "country", "island", "sea", "lake", "well", "wilderness of",
                         "plain of", "hill", "mount ", "field", "altar", "gate", "wall",
                         "temple", "house", "pool", "garden", "road", "path", "spring",
                         "fountain", "cistern", "tomb", "cave", "rock", "district",
                         "territory", "coast", "border", "= near ", "= in ", "= on ")
        if any(w in low for w in person_markers):
            pass
        elif "=" in desc or len(desc) < 25:
            continue
        elif any(w in low for w in place_markers):
            continue
        rows.append((name, strong, desc, refs))
    conn.executemany("INSERT INTO characters(name,strongs,description,refs) VALUES(?,?,?,?)", rows)
    conn.commit()
    print(f"  {len(rows)} characters")


def ingest_ancient_versions(conn):
    print("→ Peshitta / Targums", flush=True)
    base = SRC_DIR / "aramaic"
    files = [
        ("Peshitta (OT)", base / "peshitta_ot.csv"),
        ("Peshitta (NT)", base / "peshitta_nt.csv"),
        ("Targum Onkelos", base / "targum_onkelos.csv"),
        ("Targum Jonathan", base / "targum_jonathan.csv"),
        ("Targum Writings", base / "targum_writings.csv"),
    ]
    conn.execute("DELETE FROM ancient_versions")
    total = 0
    for version, path in files:
        if not path.exists():
            print(f"  ! missing {path.name}")
            continue
        rows = []
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                book = _book(r.get("book", ""))
                try:
                    ch = int(r.get("chapter") or 0)
                    vs = int(r.get("verse") or 0)
                except ValueError:
                    continue
                if not book or not ch:
                    continue
                text = _clean(r.get("syriac") or r.get("text") or "")
                if not text:
                    continue
                rows.append((f"{book}.{ch}.{vs}", version, text, "aramaic-root-atlas"))
        conn.executemany("INSERT OR REPLACE INTO ancient_versions(verse_id,version,text,source) VALUES(?,?,?,?)", rows)
        conn.commit()
        total += len(rows)
        print(f"  {version}: {len(rows)} verses")
    print(f"  total: {total}")


def ingest_cognates(conn):
    print("→ Aramaic cognates", flush=True)
    path = SRC_DIR / "aramaic/cognates.json"
    if not path.exists():
        print("  ! missing cognates.json"); return
    data = json.loads(path.read_text(encoding="utf-8"))
    roots = data.get("roots", data)
    rows = []
    for root, e in roots.items():
        if not isinstance(e, dict):
            continue
        rows.append((root, e.get("root_syriac", ""), e.get("gloss_en", ""),
                     json.dumps(e.get("hebrew", []), ensure_ascii=False)))
    conn.execute("DELETE FROM aramaic_cognates")
    conn.executemany("INSERT OR REPLACE INTO aramaic_cognates(root,syriac,gloss,hebrew) VALUES(?,?,?,?)", rows)
    conn.commit()
    print(f"  {len(rows)} roots")


def ingest_audit(conn):
    print("→ language audit", flush=True)
    conn.execute(
        "UPDATE verses SET lang='grc', lang_note='No TAGNT Greek token row; translation-only verse (textual/versification gap)' "
        "WHERE (lang IS NULL OR lang='') AND testament='NT'")
    conn.execute(
        "UPDATE verses SET lang='heb', lang_note='No TAHOT Hebrew token row; translation-only verse (textual/versification gap)' "
        "WHERE (lang IS NULL OR lang='') AND testament='OT'")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM verses WHERE id NOT IN (SELECT DISTINCT verse_id FROM words)").fetchone()[0]
    print(f"  {n} verses remain translation-only")


def ingest_variants(conn):
    print("→ textual / spelling variants", flush=True)
    conn.execute("DELETE FROM variants")
    rows = []
    for r in conn.execute(
        "SELECT verse_id,pos,surface,variant,morph FROM words "
        "WHERE variant IS NOT NULL AND variant<>'' ORDER BY verse_id,pos"):
        variant = r[3]
        if "type=Q" in variant or "type=K" in variant or "K=" in variant or "Q=" in variant:
            kind = "ketiv/qere"
        elif "type=" in variant:
            kind = "manuscript spelling/reading"
        else:
            kind = "STEPBible annotation"
        rows.append((r[0], r[1], variant, "", kind, r[2] or ""))
    conn.executemany("INSERT INTO variants(verse_id,pos,reading,witness,kind,note) VALUES(?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  {len(rows)} variant records")


def ingest_fts(conn):
    print("→ full-text index", flush=True)
    conn.execute("DELETE FROM verses_fts")
    conn.execute(
        "INSERT INTO verses_fts(id,book,content) "
        "SELECT id,book, trim(coalesce(kjv_text,'')||' '||coalesce(hebrew,'')||' '||coalesce(greek,'')||' '||coalesce(text,'')) FROM verses")
    conn.execute("DELETE FROM commentary_fts")
    conn.execute(
        "INSERT INTO commentary_fts(verse_id,author,work,text) "
        "SELECT verse_id,author,work,text FROM commentary")
    conn.commit()
    print("  done")


def ingest_sefirot(conn):
    print("→ Sefirot notebook / personal cross-references", flush=True)
    from . import sefirot
    result = sefirot.seed_defaults(conn)
    print(f"  {result['nodes']} notes, {result['links']} personal links")
    scanned = sefirot.scan(archive_missing=True, conn=conn, include_users=True)
    if scanned.get("files"):
        print(f"  {scanned['threads']} thread(s), {scanned['sections']} section(s), "
              f"{scanned['refs']} indexed reference row(s)")
        if scanned.get("user_threads"):
            print(f"  {scanned['user_threads']} user notebook(s) indexed")
    if scanned.get("errors"):
        for err in scanned["errors"]:
            print(f"  study scan warning: {err['path']}: {err['error']}", flush=True)


def ingest_registry(conn):
    counts = db.stats(conn)
    rows = []
    for key, s in SOURCES.items():
        status = "ingested" if key in ("kjv", "asv", "nheb", "ylt", "darby", "bbe", "webster",
                                       "geneva", "vulgate", "stepbible", "lxx", "openbible_xref",
                                       "nave", "torrey", "calvin", "fbmeyer",
                                       "openscriptures_strongs", "sdbh", "sahd",
                                       "aramaic_root_atlas", "local") else "on-demand"
        note = ""
        if key == "webster":
            note = "partial coverage in source DB"
        rows.append((key, s["kind"], s["license"], s["path"], status, 0, note))
    conn.executemany("INSERT OR REPLACE INTO source_registry(name,kind,license,path,status,rows,note) VALUES(?,?,?,?,?,?,?)", rows)
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('stats',?)", (json.dumps(counts),))
    conn.commit()


STEPS = [
    ("translations", ingest_translations),
    ("stepbible", ingest_stepbible),
    ("lexicons", ingest_lexicons),
    ("enrich_words", ingest_enrich_words),
    ("crossrefs", ingest_crossrefs),
    ("lxx", ingest_lxx),
    ("topics", ingest_topics),
    ("commentary", ingest_commentary),
    ("language", ingest_language),
    ("purpose", ingest_purpose),
    ("book_context", ingest_book_context),
    ("aramaic", ingest_aramaic_bridge),
    ("chunks", ingest_chunks),
    ("places", ingest_places),
    ("characters", ingest_characters),
    ("overlap", ingest_overlap),
    ("ancient_versions", ingest_ancient_versions),
    ("cognates", ingest_cognates),
    ("audit", ingest_audit),
    ("variants", ingest_variants),
    ("sefirot", ingest_sefirot),
    ("fts", ingest_fts),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Levi Monster database")
    ap.add_argument("--reset", action="store_true", help="delete and rebuild the DB")
    ap.add_argument("--only", default="", help="comma-separated steps")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args(argv)
    t0 = time.time()
    conn = db.reset(args.db) if args.reset else db.init(args.db)
    print(f"Database: {args.db}")
    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    for name, fn in STEPS:
        if wanted and name not in wanted:
            continue
        t = time.time()
        fn(conn)
        print(f"  [{time.time()-t:.1f}s]", flush=True)
    ingest_registry(conn)
    s = db.stats(conn)
    print("\n=== Levi Monster built ===")
    for k, v in s.items():
        print(f"  {k:16} {v:>10,}")
    print(f"  elapsed          {time.time()-t0:>10.1f}s")
    conn.close()


if __name__ == "__main__":
    main()
