#!/usr/bin/env python3
"""Levi VDB — dense embeddings for the originals-only words + lemmas.

Model (build-plan D3): BAAI/bge-m3, 1024-d, no instruction prefix. Embeds
vdb_words + vdb_lemmas norm text only (zero English/commentary in vectors).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from sentence_transformers import SentenceTransformer

REPO = Path(__file__).resolve().parents[2]
VDB = REPO / "data" / "vdb" / "levi_vdb.db"
MODEL = "BAAI/bge-m3"


def main() -> None:
    t0 = time.time()
    model = SentenceTransformer(MODEL)
    conn = sqlite3.connect(VDB)
    conn.execute("CREATE TABLE IF NOT EXISTS vdb_vectors (vdb_id TEXT PRIMARY KEY, dim INTEGER, vec BLOB)")
    conn.commit()

    rows = conn.execute(
        "SELECT vdb_id, norm FROM vdb_words UNION ALL SELECT vdb_id, norm FROM vdb_lemmas"
    ).fetchall()
    texts = [r[1] for r in rows]
    print(f"[embed] {len(texts):,} vectors · {MODEL} · CPU batch pass")

    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True,
                        convert_to_numpy=True, batch_size=32)
    conn.executemany(
        "INSERT OR REPLACE INTO vdb_vectors VALUES (?,?,?)",
        [(rows[i][0], vecs.shape[1], vecs[i].astype("float32").tobytes()) for i in range(len(rows))],
    )
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM vdb_vectors").fetchone()[0]
    mins = (time.time() - t0) / 60
    print(f"[embed] done: {n:,} vectors stored · {mins:.1f} min")


if __name__ == "__main__":
    main()