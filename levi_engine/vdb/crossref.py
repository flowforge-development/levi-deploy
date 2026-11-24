#!/usr/bin/env python3
"""Levi VDB — condensed cross-reference overlay (build-plan §4 stage 6).

Merges the brain's existing verse-pair cross-references into ONE condensed
directed edge per (source, target), then attaches them as relata onto the
verse's chunk_phrase occurrence nodes. Uses the OpenBible vote signal now;
TSK/BSB/NuBerea tiers join later.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = Path("/home/damian/Documents/ENGRAM1/Dirac-Sea/Levi-s-Soul/data/db/levi.db")
VDB = REPO / "data" / "vdb" / "levi_vdb.db"

BOOK_USFM = {
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM", "Deuteronomy": "DEU",
    "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT", "1 Samuel": "1SA", "2 Samuel": "2SA",
    "1 Kings": "1KI", "2 Kings": "2KI", "1 Chronicles": "1CH", "2 Chronicles": "2CH",
    "Ezra": "EZR", "Nehemiah": "NEH", "Esther": "EST", "Job": "JOB", "Psalms": "PSA",
    "Proverbs": "PRO", "Ecclesiastes": "ECC", "Song of Solomon": "SNG", "Isaiah": "ISA",
    "Jeremiah": "JER", "Lamentations": "LAM", "Ezekiel": "EZK", "Daniel": "DAN", "Hosea": "HOS",
    "Joel": "JOL", "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON", "Micah": "MIC",
    "Nahum": "NAM", "Habakkuk": "HAB", "Zephaniah": "ZEP", "Haggai": "HAG", "Zechariah": "ZEC",
    "Malachi": "MAL", "Matthew": "MAT", "Mark": "MRK", "Luke": "LUK", "John": "JHN",
    "Acts": "ACT", "Romans": "ROM", "1 Corinthians": "1CO", "2 Corinthians": "2CO",
    "Galatians": "GAL", "Ephesians": "EPH", "Philippians": "PHP", "Colossians": "COL",
    "1 Thessalonians": "1TH", "2 Thessalonians": "2TH", "1 Timothy": "1TI", "2 Timothy": "2TI",
    "Titus": "TIT", "Philemon": "PHM", "Hebrews": "HEB", "James": "JAS", "1 Peter": "1PE",
    "2 Peter": "2PE", "1 John": "1JN", "2 John": "2JN", "3 John": "3JN", "Jude": "JUD",
    "Revelation": "REV",
}


def main() -> None:
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    vdb = sqlite3.connect(VDB)
    vdb.executescript("""
    CREATE TABLE IF NOT EXISTS crossref_condensed (
      from_id TEXT, to_id TEXT, votes INTEGER, sources TEXT, weight REAL,
      PRIMARY KEY (from_id, to_id)
    );
    CREATE TABLE IF NOT EXISTS verse_first_phrase (
      book TEXT, chapter INTEGER, verse INTEGER, phrase_id TEXT,
      PRIMARY KEY (book, chapter, verse)
    );
    """)

    # verse -> first chunk_phrase occurrence (the anchor)
    rows = vdb.execute("SELECT book, chapter, verse, MIN(id) FROM chunk_phrases GROUP BY book, chapter, verse").fetchall()
    vdb.executemany("INSERT OR REPLACE INTO verse_first_phrase VALUES (?,?,?,?)",
                    [(b, c, v, pid) for b, c, v, pid in rows if pid])

    cond = defaultdict(lambda: {"votes": 0, "sources": set()})
    for from_id, to_id, votes, source in src.execute("SELECT from_id, to_id, votes, source FROM cross_refs"):
        e = cond[(from_id, to_id)]
        e["votes"] = max(e["votes"], votes or 0)
        if source:
            e["sources"].add(source)

    rows = [(f, t, e["votes"], ",".join(sorted(e["sources"])), e["votes"] / 100.0)
            for (f, t), e in cond.items()]
    vdb.executemany("INSERT OR REPLACE INTO crossref_condensed VALUES (?,?,?,?,?)", rows)

    # relata: verse anchor -> verse anchor (resolve full-name verse ids -> USFM book)
    def resolve(verse_id: str):
        # "Genesis.1.1" -> ("GEN", 1, 1); "1 Samuel.2.4" -> ("1SA", 2, 4)
        parts = verse_id.split(".")
        if len(parts) < 3:
            return None
        books = BOOK_USFM.get(parts[0]) or None
        # handle "1 Samuel" style (dotless single-piece names already covered)
        if books:
            return (books, int(parts[1]), int(parts[2]))
        if len(parts) >= 4 and f"{parts[0]} {parts[1]}" in BOOK_USFM:
            return (BOOK_USFM[f"{parts[0]} {parts[1]}"], int(parts[2]), int(parts[3]))
        return None

    anchor = {(b, c, v): pid for b, c, v, pid in vdb.execute("SELECT book,chapter,verse,phrase_id FROM verse_first_phrase")}
    edges = 0
    for f, t, votes, sources, weight in rows:
        rf, rt = resolve(f), resolve(t)
        if not rf or not rt:
            continue
        a, b = anchor.get(rf), anchor.get(rt)
        if a and b:
            vdb.execute("INSERT OR REPLACE INTO relata (source_type,source_id,relation,target_type,target_id,description,text) VALUES (?,?,?,?,?,?,?)",
                        ("chunk_phrase", a, "cross_ref", "chunk_phrase", b, str(weight), sources))
            edges += 1
    vdb.commit()
    print(f"Cross-ref overlay: {len(rows):,} condensed edges from 256,649 raw pairs "
          f"({len(anchor):,} verse anchors) — {edges:,} relata attached")


if __name__ == "__main__":
    main()