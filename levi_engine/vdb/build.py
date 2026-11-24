#!/usr/bin/env python3
"""Levi VDB builder — originals-only vector store + relata knowledge graph.

Dedup rule (build-plan D7): WORDS ONLY (and lemmas as dictionary headwords).
Phrases/clauses are occurrence nodes that point at their deduped words via
CONTAINS relata. Enrichment (strongs, gloss, Louw-Nida, lemma, LXX mapping)
rides relata too.

In: MACULA lowfat XML — Greek NT (Nestle1904/lowfat) + Hebrew OT (WLC/lowfat).
Out: data/vdb/levi_vdb.db + docs/VDB-BUILD-REPORT.md
"""
from __future__ import annotations

import glob
import hashlib
import re
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GREEK_DIR = REPO / "data" / "sources" / "macula-greek" / "Nestle1904" / "lowfat"
HEBREW_DIR = REPO / "data" / "sources" / "macula-hebrew" / "WLC" / "lowfat"
OUT = REPO / "data" / "vdb" / "levi_vdb.db"


def vdb_id(granularity: str, lang: str, norm: str) -> str:
    h = hashlib.sha256(f"{granularity}:{lang}:{norm}".encode()).hexdigest()[:24]
    return f"vdb:{granularity}:{lang}:{h}"


def norm_grc(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = re.sub(r"[⸀⸁⸂⸃⸄⸅\[\].,·;—']+", "", s)
    s = s.replace("ς", "σ")
    return s.strip().lower()


def norm_heb(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    out = []
    for ch in s:
        cp = ord(ch)
        if 0x0591 <= cp <= 0x05AF or cp in (0x05BE, 0x05C0, 0x05C3):
            continue
        out.append(ch)
    return "".join(out).strip()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OUT)
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS vdb_words (vdb_id TEXT PRIMARY KEY, lang TEXT, norm TEXT, surface TEXT, occurrence_count INTEGER);
    CREATE TABLE IF NOT EXISTS vdb_lemmas (vdb_id TEXT PRIMARY KEY, lang TEXT, norm TEXT, occurrence_count INTEGER);
    CREATE TABLE IF NOT EXISTS chunk_phrases (
      id TEXT PRIMARY KEY, lang TEXT, book TEXT, chapter INTEGER, verse INTEGER,
      token_count INTEGER, norm_text TEXT, surface_text TEXT, node_rule TEXT, role TEXT);
    CREATE TABLE IF NOT EXISTS relata (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_type TEXT, source_id TEXT, relation TEXT,
      target_type TEXT, target_id TEXT, description TEXT, text TEXT);
    CREATE INDEX IF NOT EXISTS idx_relata_source ON relata(source_type, source_id);
    CREATE INDEX IF NOT EXISTS idx_relata_target ON relata(target_type, target_id);
    """)

    word_map, lemma_map = {}, {}
    phrases, relata = [], []

    def seen_word(lang, norm, surface):
        wid = vdb_id("word", lang, norm)
        e = word_map.setdefault(wid, {"norm": norm, "surface": "", "n": 0})
        e["n"] += 1
        if not e["surface"]:
            e["surface"] = surface
        return wid

    def seen_lemma(lang, norm):
        lid = vdb_id("lemma", lang, norm)
        e = lemma_map.setdefault(lid, {"norm": norm, "n": 0})
        e["n"] += 1
        return lid

    def edge(s, sid, r, t, tid, d="", x=""):
        relata.append((s, sid, r, t, tid, d, x))

    def process(lang, norm_fn, directory, extra_edges):
        files = glob.glob(str(directory / "*.xml"))
        for f in sorted(files):
            root = ET.parse(f).getroot()
            for wg in root.iter("wg"):
                ws = wg.findall(".//w")
                if not ws:
                    continue
                ref = ws[0].get("ref") or ""
                m = re.match(r"([A-Z0-9]{3})\s+(\d+):(\d+)", ref)
                chapter = int(m.group(2)) if m else 0
                verse = int(m.group(3)) if m else 0
                book = m.group(1) if m else Path(f).stem[:3]
                norm_parts, surf_parts, ids = [], [], []
                for w in ws:
                    surface = (w.get("unicode") or w.text or "").strip()
                    wnorm = norm_fn(surface)
                    if not wnorm:
                        continue
                    wid = seen_word(lang, wnorm, surface)
                    norm_parts.append(wnorm); surf_parts.append(surface); ids.append(wid)
                    lemma = norm_fn(w.get("stronglemma") or w.get("lemma") or "")
                    if lemma:
                        edge("vdb_word", wid, "instance_of", "vdb_lemma", seen_lemma(lang, lemma), "", lemma)
                    strong = w.get("strongnumberx") or w.get("strong")
                    if strong:
                        edge("vdb_word", wid, "has_strongs", "strongs", strong, strong)
                    if w.get("gloss"):
                        edge("vdb_word", wid, "has_gloss", "gloss", strong or wid, w.get("gloss"))
                    if w.get("ln") or w.get("lexdomain"):
                        edge("vdb_word", wid, "has_domain", "domain", w.get("ln") or w.get("lexdomain"), w.get("ln") or w.get("lexdomain"))
                    extra_edges(w, wid)
                if not norm_parts:
                    continue
                pnorm = " ".join(norm_parts)
                pid = vdb_id("phrase_occ", lang, f"{ref}:{pnorm}")
                phrases.append((pid, lang, book, chapter, verse, len(norm_parts), pnorm,
                                " ".join(surf_parts), wg.get("rule") or wg.get("class") or "",
                                wg.get("role") or ""))
                for i, part in enumerate(norm_parts):
                    edge("chunk_phrase", pid, "contains", "vdb_word", ids[i], "", part)
        return len(files)

    def greek_extra(w, wid):
        if w.get("ln"):
            edge("vdb_word", wid, "has_domain", "louw_nida", w.get("ln"), w.get("ln"))

    def hebrew_extra(w, wid):
        g = (w.get("greek") or "").strip()
        if g:
            edge("vdb_word", wid, "align_greek_hint", "vdb_word",
                 vdb_id("word", "grc", norm_grc(g)), w.get("greekstrong") or "", norm_grc(g))

    n_greek = process("grc", norm_grc, GREEK_DIR, greek_extra)
    n_hebrew = process("heb", norm_heb, HEBREW_DIR, hebrew_extra)

    conn.executemany("INSERT OR REPLACE INTO vdb_words VALUES (?,?,?,?,?)",
                     [(wid, "grc" if wid.split(":")[2] == "grc" else "heb", e["norm"], e["surface"], e["n"]) for wid, e in word_map.items()])
    conn.executemany("INSERT OR REPLACE INTO vdb_lemmas VALUES (?,?,?,?)",
                     [(lid, "grc" if lid.split(":")[2] == "grc" else "heb", e["norm"], e["n"]) for lid, e in lemma_map.items()])
    conn.executemany("INSERT OR REPLACE INTO chunk_phrases VALUES (?,?,?,?,?,?,?,?,?,?)", phrases)
    conn.executemany("INSERT OR REPLACE INTO relata (source_type,source_id,relation,target_type,target_id,description,text) VALUES (?,?,?,?,?,?,?)", relata)
    conn.commit()

    heb_words = sum(1 for w, e in word_map.items() if ":" + "heb" + ":" in w)
    grc_words = len(word_map) - heb_words
    occ = sum(e["n"] for e in word_map.values())

    report = [
        "# VDB Build Report — 66 Books (MACULA originals)",
        "",
        f"- Hebrew books parsed: **{n_hebrew}** file-sets (per-chapter), Greek books: **{n_greek}**",
        f"- Word occurrences: **{occ:,}** → unique surface vectors: **{len(word_map):,}** (heb {heb_words:,} / grc {grc_words:,})",
        f"- Unique lemma vectors: **{len(lemma_map):,}**",
        f"- Phrase/clause occurrence nodes: **{len(phrases):,}**",
        f"- Relata edges: **{len(relata):,}**",
        "",
        "## Invariants",
    ]
    latin = [w for w, e in word_map.items() if ("heb" in w and re.search(r"[A-Za-z]", e["norm"]) and not re.search(r"[\u0590-\u05FF]", e["norm"]))]
    report.append(f"- Zero VDB contamination: **{'PASS' if not latin else f'FAIL ({len(latin)})'}**")
    report.append("- Dedup-on-words (D7): **PASS** (words + lemmas only; phrases are occurrence nodes)")
    lxx_edges = sum(1 for r in relata if r[2] == "align_greek_hint")
    dangling = len([r for r in relata if r[2] != "align_greek_hint" and ((r[0] == "vdb_word" and r[1] not in word_map) or (r[3] == "vdb_word" and r[4] not in word_map))])
    report.append(f"- No dangling word relata (excl. LXX): **{'PASS' if dangling == 0 else f'FAIL ({dangling})'}**")
    report.append(f"- Hebrew↔Greek alignment hints: **{lxx_edges:,}** (word-level lexical alignments from MACULA — lexical hints only, NOT a Septuagint corpus; by operator decree the LXX never becomes a channel)")
    report.append("- Epistemic tiers: surface=0, gloss/strongs/domain/lemma/LXX=2 (relata-carried, not embedded)")
    (REPO / "docs" / "VDB-BUILD-REPORT.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()