"""SQLite schema for the Levi Monster."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, DB_DIR

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS verses (
    id TEXT PRIMARY KEY,
    osis TEXT,
    book TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    testament TEXT NOT NULL,
    lang TEXT,
    lang_note TEXT,
    kjv_text TEXT,
    hebrew TEXT,
    greek TEXT,
    text TEXT,
    word_count INTEGER DEFAULT 0,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_verses_book_chapter ON verses(book, chapter, verse);
CREATE INDEX IF NOT EXISTS idx_verses_testament ON verses(testament);
CREATE INDEX IF NOT EXISTS idx_verses_osis ON verses(osis);

CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    id UNINDEXED, book UNINDEXED, content,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS translations (
    verse_id TEXT NOT NULL,
    translation TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (verse_id, translation)
);
CREATE INDEX IF NOT EXISTS idx_translations_tr ON translations(translation);

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY,
    verse_id TEXT NOT NULL,
    pos INTEGER NOT NULL,
    lang TEXT,
    surface TEXT,
    translit TEXT,
    lemma TEXT,
    strongs TEXT,
    strongs_base TEXT,
    morph TEXT,
    gloss TEXT,
    root TEXT,
    domains TEXT,
    variant TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_words_verse ON words(verse_id, pos);
CREATE INDEX IF NOT EXISTS idx_words_strong ON words(strongs_base);
CREATE INDEX IF NOT EXISTS idx_words_lemma ON words(lemma);
CREATE INDEX IF NOT EXISTS idx_words_surface ON words(surface);

CREATE TABLE IF NOT EXISTS lexicon (
    strongs TEXT NOT NULL,
    base TEXT,
    lang TEXT,
    lemma TEXT,
    translit TEXT,
    morph TEXT,
    gloss TEXT,
    definition TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (strongs, source)
);
CREATE INDEX IF NOT EXISTS idx_lexicon_base ON lexicon(base);
CREATE INDEX IF NOT EXISTS idx_lexicon_lemma ON lexicon(lemma);

CREATE TABLE IF NOT EXISTS domains (
    strongs TEXT NOT NULL,
    code TEXT,
    label TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_domains_strong ON domains(strongs);
CREATE INDEX IF NOT EXISTS idx_domains_label ON domains(label);

CREATE TABLE IF NOT EXISTS cross_refs (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    votes INTEGER DEFAULT 0,
    source TEXT,
    PRIMARY KEY (from_id, to_id, source)
);
CREATE INDEX IF NOT EXISTS idx_xref_from ON cross_refs(from_id);
CREATE INDEX IF NOT EXISTS idx_xref_to ON cross_refs(to_id);

CREATE TABLE IF NOT EXISTS lang_tags (
    verse_id TEXT NOT NULL,
    lang TEXT NOT NULL,
    scope TEXT,
    word_start INTEGER,
    word_end INTEGER,
    note TEXT,
    PRIMARY KEY (verse_id, lang, scope, word_start, word_end)
);

CREATE TABLE IF NOT EXISTS variants (
    verse_id TEXT NOT NULL,
    pos INTEGER,
    reading TEXT,
    witness TEXT,
    kind TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_variants_verse ON variants(verse_id);

CREATE TABLE IF NOT EXISTS book_context (
    book TEXT PRIMARY KEY,
    author TEXT, date TEXT, genre TEXT, audience TEXT,
    purpose TEXT, register TEXT, summary TEXT,
    lang_primary TEXT, lang_secondary TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    topic TEXT NOT NULL,
    verse_id TEXT NOT NULL,
    source TEXT,
    entry TEXT,
    PRIMARY KEY (topic, verse_id, source)
);
CREATE INDEX IF NOT EXISTS idx_topics_topic ON topics(topic);
CREATE INDEX IF NOT EXISTS idx_topics_verse ON topics(verse_id);

CREATE TABLE IF NOT EXISTS commentary (
    id INTEGER PRIMARY KEY,
    verse_id TEXT NOT NULL,
    author TEXT,
    work TEXT,
    text TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_commentary_verse ON commentary(verse_id);
CREATE INDEX IF NOT EXISTS idx_commentary_author ON commentary(author);

CREATE VIRTUAL TABLE IF NOT EXISTS commentary_fts USING fts5(
    verse_id UNINDEXED, author UNINDEXED, work UNINDEXED, text,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS lxx_books (
    number INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT
);
CREATE TABLE IF NOT EXISTS lxx_verses (
    book_no INTEGER NOT NULL,
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    text TEXT,
    PRIMARY KEY (book_no, chapter, verse)
);

CREATE TABLE IF NOT EXISTS aramaic_bridge (
    greek_strong TEXT,
    greek_lemma TEXT,
    aramaic TEXT,
    translit TEXT,
    gloss TEXT,
    confidence TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_aramaic_strong ON aramaic_bridge(greek_strong);

CREATE TABLE IF NOT EXISTS places (
    name TEXT,
    strongs TEXT,
    kind TEXT,
    description TEXT,
    refs TEXT
);
CREATE INDEX IF NOT EXISTS idx_places_name ON places(name);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT,
    tag TEXT,
    body TEXT,
    created TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_registry (
    name TEXT PRIMARY KEY,
    kind TEXT,
    license TEXT,
    path TEXT,
    status TEXT,
    rows INTEGER DEFAULT 0,
    note TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    book TEXT, chapter INTEGER,
    verse_start INTEGER, verse_end INTEGER,
    kind TEXT,
    label TEXT,
    text TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book, chapter);

CREATE TABLE IF NOT EXISTS language_purpose (
    verse_id TEXT PRIMARY KEY,
    language TEXT,
    purpose TEXT,
    period TEXT,
    confidence TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_purpose_purpose ON language_purpose(purpose);

CREATE TABLE IF NOT EXISTS book_overlap (
    book TEXT NOT NULL,
    related_book TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    basis TEXT,
    PRIMARY KEY (book, related_book, basis)
);
CREATE INDEX IF NOT EXISTS idx_overlap_book ON book_overlap(book, score DESC);

CREATE TABLE IF NOT EXISTS characters (
    name TEXT,
    strongs TEXT,
    description TEXT,
    refs TEXT
);
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);

CREATE TABLE IF NOT EXISTS ancient_versions (
    verse_id TEXT NOT NULL,
    version TEXT NOT NULL,
    text TEXT,
    source TEXT,
    PRIMARY KEY (verse_id, version)
);
CREATE INDEX IF NOT EXISTS idx_ancient_version ON ancient_versions(version);

CREATE TABLE IF NOT EXISTS aramaic_cognates (
    root TEXT PRIMARY KEY,
    syriac TEXT,
    gloss TEXT,
    hebrew TEXT
);

-- ── Sefirot: Levi's study notebook + personal cross-reference graph ──
-- Layer 1: notebook entries ("engrams") that anchor study to scripture.
-- Layer 2: personal links owned by a Layer 1 entry.  A link targets either
-- a scripture reference (to_ref) or another Layer 1 entry (to_node), so a
-- notebook entry can reference Layer 2 and also reference Layer 1.
CREATE TABLE IF NOT EXISTS sefirot_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    kind TEXT DEFAULT 'insight',
    refs TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    parent_id INTEGER,
    confidence TEXT DEFAULT 'exploratory',
    source TEXT DEFAULT 'levi',
    archived INTEGER DEFAULT 0,
    created TEXT DEFAULT CURRENT_TIMESTAMP,
    updated TEXT DEFAULT CURRENT_TIMESTAMP,
    meta TEXT DEFAULT '{}',
    source_path TEXT,
    source_hash TEXT,
    user_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_sefirot_kind ON sefirot_nodes(kind, archived);
CREATE INDEX IF NOT EXISTS idx_sefirot_parent ON sefirot_nodes(parent_id);

CREATE TABLE IF NOT EXISTS sefirot_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node INTEGER NOT NULL,
    to_node INTEGER,
    to_ref TEXT,
    relation TEXT NOT NULL DEFAULT 'see-also',
    note TEXT DEFAULT '',
    weight REAL DEFAULT 1.0,
    source TEXT DEFAULT 'levi',
    created TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK ((to_node IS NOT NULL) <> (to_ref IS NOT NULL)),
    UNIQUE (from_node, to_node, to_ref, relation)
);
CREATE INDEX IF NOT EXISTS idx_sefirot_from ON sefirot_links(from_node);
CREATE INDEX IF NOT EXISTS idx_sefirot_to_node ON sefirot_links(to_node);
CREATE INDEX IF NOT EXISTS idx_sefirot_to_ref ON sefirot_links(to_ref);
-- SQLite UNIQUE treats NULLs as distinct, so enforce the two link shapes
-- separately.  This also makes retries idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sefirot_link_node
    ON sefirot_links(from_node,to_node,relation) WHERE to_node IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sefirot_link_ref
    ON sefirot_links(from_node,to_ref,relation) WHERE to_ref IS NOT NULL;

-- Where notebook memories are anchored.  Every explicit scripture occurrence
-- inside a Markdown study section gets one row.  This is the local side of the
-- verse mesh: a verse points to every memory written about it, and the section
-- and thread ids are only storage labels.
CREATE TABLE IF NOT EXISTS sefirot_ref_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT NOT NULL,
    thread_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    raw TEXT DEFAULT '',
    position INTEGER DEFAULT 0,
    UNIQUE (section_id, ref)
);
CREATE INDEX IF NOT EXISTS idx_sefirot_ref_ref ON sefirot_ref_index(ref);
CREATE INDEX IF NOT EXISTS idx_sefirot_ref_thread ON sefirot_ref_index(thread_id);
CREATE INDEX IF NOT EXISTS idx_sefirot_ref_section ON sefirot_ref_index(section_id);

CREATE VIRTUAL TABLE IF NOT EXISTS sefirot_fts USING fts5(
    node_id UNINDEXED,
    title,
    body,
    refs,
    tags,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-100000")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create missing tables and add columns needed by an older database.

    SQLite ``CREATE TABLE IF NOT EXISTS`` does not add new columns, so the
    study-thread columns are migrated explicitly.  Everything here is additive
    and safe to run on every start.
    """
    conn.executescript(SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sefirot_nodes)")}
    for name, ddl in (
        ("source_path", "TEXT"),
        ("source_hash", "TEXT"),
        ("user_id", "TEXT"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE sefirot_nodes ADD COLUMN {name} {ddl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sefirot_source_path "
                 "ON sefirot_nodes(source_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sefirot_user "
                 "ON sefirot_nodes(user_id, archived)")
    conn.commit()


def init(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = connect(path)
    ensure_schema(conn)
    return conn


def reset(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    if path.exists():
        path.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    return init(path)


def set_meta(conn, key: str, value):
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                 (key, value if isinstance(value, str) else json.dumps(value)))


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]


def stats(conn) -> dict:
    def one(sql, *args):
        try:
            return conn.execute(sql, args).fetchone()[0]
        except Exception:
            return 0
    return {
        "verses": one("SELECT COUNT(*) FROM verses"),
        "translations": one("SELECT COUNT(*) FROM translations"),
        "words": one("SELECT COUNT(*) FROM words"),
        "lexicon": one("SELECT COUNT(*) FROM lexicon"),
        "domains": one("SELECT COUNT(*) FROM domains"),
        "cross_refs": one("SELECT COUNT(*) FROM cross_refs"),
        "lang_tags": one("SELECT COUNT(*) FROM lang_tags"),
        "variants": one("SELECT COUNT(*) FROM variants"),
        "topics": one("SELECT COUNT(*) FROM topics"),
        "commentary": one("SELECT COUNT(*) FROM commentary"),
        "lxx_verses": one("SELECT COUNT(*) FROM lxx_verses"),
        "aramaic_bridge": one("SELECT COUNT(*) FROM aramaic_bridge"),
        "places": one("SELECT COUNT(*) FROM places"),
        "chunks": one("SELECT COUNT(*) FROM chunks"),
        "language_purpose": one("SELECT COUNT(*) FROM language_purpose"),
        "book_overlap": one("SELECT COUNT(*) FROM book_overlap"),
        "characters": one("SELECT COUNT(*) FROM characters"),
        "ancient_versions": one("SELECT COUNT(*) FROM ancient_versions"),
        "aramaic_cognates": one("SELECT COUNT(*) FROM aramaic_cognates"),
        "sefirot_nodes": one("SELECT COUNT(*) FROM sefirot_nodes WHERE archived=0"),
        "sefirot_links": one("SELECT COUNT(*) FROM sefirot_links"),
        "sefirot_fts": one("SELECT COUNT(*) FROM sefirot_fts"),
        "sefirot_threads": one("SELECT COUNT(*) FROM sefirot_nodes WHERE archived=0 AND kind='study'"),
        "sefirot_sections": one("SELECT COUNT(*) FROM sefirot_nodes WHERE archived=0 AND kind='section'"),
        "sefirot_refs": one("SELECT COUNT(*) FROM sefirot_ref_index"),
        "sefirot_user_notebooks": one(
            "SELECT COUNT(*) FROM sefirot_nodes WHERE archived=0 AND kind='study' AND source='user'"
        ),
        "sefirot_user_notes": one(
            "SELECT COUNT(*) FROM sefirot_nodes WHERE archived=0 AND user_id IS NOT NULL"
        ),
        "users": one(
            "SELECT COUNT(DISTINCT user_id) FROM sefirot_nodes WHERE user_id IS NOT NULL"
        ),
    }


def backup(db_path: Path | str | None = None, dest_dir: Path | str | None = None,
           keep: int = 10) -> dict:
    """Make a safe online backup of the SQLite database.

    The SQLite backup API copies a consistent snapshot even while the main
    database is open in WAL mode.  The copy is checked with ``quick_check``
    before it is reported as usable.
    """
    source_path = Path(db_path or DB_PATH)
    if not source_path.exists():
        raise FileNotFoundError(f"database not found: {source_path}")
    out_dir = Path(dest_dir) if dest_dir else Path(DB_DIR).parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = out_dir / f"levi-{stamp}.db"
    counter = 2
    while destination.exists():
        destination = out_dir / f"levi-{stamp}-{counter}.db"
        counter += 1

    source = sqlite3.connect(str(source_path))
    destination_conn = sqlite3.connect(str(destination))
    try:
        source.backup(destination_conn)
        check = destination_conn.execute("PRAGMA quick_check").fetchone()[0]
        destination_conn.close()
    except Exception:
        destination_conn.close()
        if destination.exists():
            destination.unlink()
        raise
    finally:
        source.close()

    kept = []
    removed = []
    if keep is not None and int(keep) > 0:
        snapshots = sorted(out_dir.glob("levi-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        kept = [str(p) for p in snapshots[:int(keep)]]
        for old in snapshots[int(keep):]:
            try:
                old.unlink()
                removed.append(str(old))
            except OSError:
                pass
    return {
        "ok": check == "ok",
        "path": str(destination),
        "size_mb": round(destination.stat().st_size / 1e6, 2) if destination.exists() else 0,
        "quick_check": check,
        "kept": kept,
        "removed": removed,
    }


def restore(backup_path: Path | str, db_path: Path | str | None = None,
            safety_dir: Path | str | None = None, keep: int = 10) -> dict:
    """Restore a checked backup over the live database.

    This is deliberately offline and explicit.  Stop other Levi processes
    first.  A safety snapshot of the current database is made before anything
    is replaced, and the restored copy is checked again.
    """
    source_path = Path(backup_path)
    target = Path(db_path or DB_PATH)
    if not source_path.exists():
        raise FileNotFoundError(f"backup not found: {source_path}")
    if source_path.resolve() == target.resolve():
        raise ValueError("backup and live database are the same file")
    source = sqlite3.connect(str(source_path))
    try:
        source_check = source.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        source.close()
    if source_check != "ok":
        raise ValueError(f"backup failed quick_check: {source_check}")

    safety = None
    if target.exists():
        safety = backup(target, dest_dir=safety_dir or (Path(DB_DIR).parent / "backups"), keep=keep)
        for suffix in ("-wal", "-shm", "-journal"):
            leftover = Path(str(target) + suffix)
            if leftover.exists():
                leftover.unlink()

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(target) + ".restore-tmp")
    try:
        shutil.copy2(source_path, temporary)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()

    restored = sqlite3.connect(str(target))
    try:
        restored_check = restored.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        restored.close()
    return {
        "ok": restored_check == "ok",
        "path": str(target),
        "source": str(source_path),
        "quick_check": restored_check,
        "safety_backup": safety,
    }
