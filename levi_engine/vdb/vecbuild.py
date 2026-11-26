#!/usr/bin/env python3
"""vecbuild.py — build dense embeddings for runtime semantic search.

Two artifacts:
  1) Verse vectors (--verses-only) -> a compact stand-alone DB
     (verse_id -> fp16 unit vector) that ships with the deployed Levi API.
  2) Word + lemma vectors -> vdb_vectors table inside the source VDB
     (levi_vdb.db), per build-plan D3 (BAAI/bge-m3, originals only).

Resumable: rows already present are skipped. Runs on CPU.

    python3 levi_engine/vdb/vecbuild.py --verses-only \
        --main-db /root/levi-deploy/levi.db \
        --out /root/levi-deploy/verse_vectors.db
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
MODEL_NAME = "BAAI/bge-m3"


def norm(text, lang):
    """Same originals normalization as build.py (cantal spill-free NFC)."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFC", text or "")
    if lang == "grc":
        s = re.sub(r"[⸀⸁⸂⸃⸄⸅\[\].,·;—']+", "", s).replace("ς", "σ")
        return s.strip().lower()
    out = []
    for ch in s:
        cp = ord(ch)
        if 0x0591 <= cp <= 0x05AF or cp in (0x05BE, 0x05C0, 0x05C3):
            continue
        out.append(ch)
    return "".join(out).strip()


def build_verses(main_db_path: str, out_path: str) -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    main = sqlite3.connect(f"file:{main_db_path}?mode=ro", uri=True)
    out = sqlite3.connect(out_path)
    out.execute("CREATE TABLE IF NOT EXISTS verse_vectors (verse_id TEXT PRIMARY KEY, dim INTEGER, vec BLOB)")
    out.commit()

    done_ids = {r[0] for r in out.execute("SELECT verse_id FROM verse_vectors")}
    rows = main.execute("SELECT id, lang, hebrew, greek, kjv_text FROM verses").fetchall()
    pending = [(r, norm(r[2] if r[1] != "grc" else r[3] or "", r[1]) or r[4] or "") for r in rows if r[0] not in done_ids]
    print(f"[vecbuild] {len(pending)} verses to embed ({len(rows)} total, {len(done_ids)} done)", flush=True)

    for start in range(0, len(pending), 256):
        chunk = pending[start:start + 256]
        texts = [t for _, t in chunk]
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=128,
                            convert_to_numpy=True, show_progress_bar=False)
        vecs = vecs.astype("float16")
        with out:
            for (row, _), vec in zip(chunk, vecs):
                out.execute(
                    "INSERT OR REPLACE INTO verse_vectors (verse_id, dim, vec) VALUES (?,?,?)",
                    (row[0], vecs.shape[1], vec.tobytes()),
                )
        print(f"[vecbuild] verses {min(start + 256, len(pending))}/{len(pending)}", flush=True)

    n = out.execute("SELECT COUNT(*) FROM verse_vectors").fetchone()[0]
    print(f"[vecbuild] verse vectors done: {n:,} in {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verses-only", action="store_true", help="only verse vectors (runtime artifact)")
    ap.add_argument("--main-db", default=os.environ.get("LEVI_DB_PATH") or "/home/damian/Documents/ENGRAM1/Dirac-Sea/Levi-s-Soul/data/db/levi.db")
    ap.add_argument("--out", default=os.environ.get("LEVI_VEC_PATH") or str(REPO / "data" / "vdb" / "verse_vectors.db"))
    args = ap.parse_args()

    t0 = time.time()
    build_verses(args.main_db, args.out)
    print(f"[vecbuild] total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())