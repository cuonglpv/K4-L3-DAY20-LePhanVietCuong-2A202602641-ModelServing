#!/usr/bin/env python3
"""03 - N17 -> N18 -> N19 stack behind the RAG pipeline.

    N17 data pipeline : read the repo's own docs, clean, chunk, hash (incremental)
    N18 lakehouse     : SQLite tables in medallion layers
                          bronze_docs      raw text + sha256 per source file
                          silver_chunks    cleaned, chunked text
                          gold_embeddings  float32 vector per chunk (+ model name)
    N19 vector index  : embeddings from a llama-server started with --embedding,
                        exact cosine search over the gold matrix (numpy)

Honest scope: SQLite stands in for a lakehouse table format (no Iceberg/Delta, no
object store), and exact search over a few hundred vectors is not an ANN index.
What *is* real: the data flow, incremental loading by content hash, versioned
embedding model per vector, and the retrieval used by pipeline.py --lakehouse.

    make serve-embed                                  # terminal 1 (port 8081)
    python labs/03-integrate/stack.py build           # terminal 2
    python labs/03-integrate/pipeline.py --lakehouse data/lakehouse.db \
        --embed-url http://localhost:8081
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sqlite3
import sys
import time

import httpx
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lib"))
import labkit  # noqa: E402

ROOT = labkit.repo_root()
DEFAULT_DB = ROOT / "data" / "lakehouse.db"
CORPUS_GLOBS = ["README.md", "docs/*.md", "docs/labs/*.md", "docs/bonus/*.md",
                "data/corpus/*.md"]
# Embedding models trained with task prefixes need them on both sides.
PREFIXES = {"nomic": ("search_document: ", "search_query: ")}


def prefixes(model_name: str) -> tuple[str, str]:
    for key, pair in PREFIXES.items():
        if key in model_name.lower():
            return pair
    return "", ""
CHUNK_WORDS = 70   # 3 chunks + prompt must fit one slot: ctx 2048 / 4 slots = 512 tokens
CHUNK_OVERLAP = 15
EMBED_BATCH = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS bronze_docs (
    path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, raw TEXT NOT NULL, ingested_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS silver_chunks (
    chunk_id TEXT PRIMARY KEY, path TEXT NOT NULL, ord INTEGER NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gold_embeddings (
    chunk_id TEXT PRIMARY KEY, model TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL);
"""


# ── N17: data pipeline ────────────────────────────────────────────────────
def clean(raw: str) -> str:
    """Drop fenced code, HTML comments and markdown punctuation; collapse whitespace."""
    t = re.sub(r"```.*?```", " ", raw, flags=re.S)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)      # [text](url) -> text
    t = re.sub(r"[#*`>|_]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def chunk(text: str, size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, max(len(words) - overlap, 1), step)
            if words[i:i + size]]


def source_files() -> list[pathlib.Path]:
    seen: list[pathlib.Path] = []
    for pat in CORPUS_GLOBS:
        seen += sorted(ROOT.glob(pat))
    return [p for p in seen if p.is_file()]


def connect(db: pathlib.Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    return con


def ingest(con: sqlite3.Connection) -> dict:
    """Incremental load: only files whose sha256 changed are re-chunked; their stale
    silver chunks and gold vectors are dropped so embeddings can never go stale."""
    stats = {"files": 0, "new": 0, "changed": 0, "unchanged": 0, "chunks": 0}
    for p in source_files():
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        row = con.execute("SELECT sha256 FROM bronze_docs WHERE path=?", (rel,)).fetchone()
        stats["files"] += 1
        if row and row[0] == digest:
            stats["unchanged"] += 1
            continue
        stats["changed" if row else "new"] += 1
        con.execute("DELETE FROM gold_embeddings WHERE chunk_id IN "
                    "(SELECT chunk_id FROM silver_chunks WHERE path=?)", (rel,))
        con.execute("DELETE FROM silver_chunks WHERE path=?", (rel,))
        con.execute("INSERT OR REPLACE INTO bronze_docs VALUES (?,?,?,?)",
                    (rel, digest, raw, time.time()))
        pieces = chunk(clean(raw))
        con.executemany("INSERT INTO silver_chunks VALUES (?,?,?,?)",
                        [(f"{rel}#{i}", rel, i, t) for i, t in enumerate(pieces)])
        stats["chunks"] += len(pieces)
    con.commit()
    return stats


# ── N19: embeddings + vector index ────────────────────────────────────────
def embed(texts: list[str], embed_url: str) -> np.ndarray:
    r = httpx.post(f"{embed_url}/v1/embeddings",
                   json={"model": "local", "input": texts}, timeout=300.0)
    r.raise_for_status()
    v = np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
    return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)


def embed_missing(con: sqlite3.Connection, embed_url: str, model: str) -> int:
    doc_prefix = prefixes(model)[0]
    rows = con.execute("SELECT chunk_id, text FROM silver_chunks WHERE chunk_id NOT IN "
                       "(SELECT chunk_id FROM gold_embeddings)").fetchall()
    for i in range(0, len(rows), EMBED_BATCH):
        batch = rows[i:i + EMBED_BATCH]
        vecs = embed([doc_prefix + t for _, t in batch], embed_url)
        con.executemany("INSERT OR REPLACE INTO gold_embeddings VALUES (?,?,?,?)",
                        [(cid, model, vecs.shape[1], v.tobytes())
                         for (cid, _), v in zip(batch, vecs)])
        con.commit()
        print(f"  embedded {min(i + EMBED_BATCH, len(rows))}/{len(rows)}", end="\r", flush=True)
    return len(rows)


class VectorIndex:
    """Exact cosine search over the gold matrix, loaded once."""

    def __init__(self, db: pathlib.Path):
        con = sqlite3.connect(db)
        rows = con.execute("SELECT s.chunk_id, s.text, g.vec FROM silver_chunks s "
                           "JOIN gold_embeddings g USING (chunk_id) ORDER BY s.chunk_id").fetchall()
        models = {m for (m,) in con.execute("SELECT DISTINCT model FROM gold_embeddings")}
        con.close()
        if not rows:
            labkit.die("The lakehouse has no embeddings.",
                       "Run: python labs/03-integrate/stack.py build")
        if len(models) != 1:
            labkit.die(f"Mixed embedding models in the gold table: {sorted(models)}.",
                       "Delete data/lakehouse.db and rebuild.")
        self.model = models.pop()
        self.query_prefix = prefixes(self.model)[1]
        self.ids = [r[0] for r in rows]
        self.texts = [r[1] for r in rows]
        self.matrix = np.vstack([np.frombuffer(r[2], dtype=np.float32) for r in rows])

    def search(self, qvec: np.ndarray, k: int = 3) -> list[tuple[str, str, float]]:
        scores = self.matrix @ qvec
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], self.texts[i], float(scores[i])) for i in top]


# ── CLI ───────────────────────────────────────────────────────────────────
def build(args: argparse.Namespace) -> int:
    labkit.banner("N17-N19 - build the lakehouse")
    db = pathlib.Path(args.db)
    t0 = time.perf_counter()
    con = connect(db)
    s = ingest(con)
    print(f"  N17 ingest   : {s['files']} files ({s['new']} new, {s['changed']} changed, "
          f"{s['unchanged']} unchanged) -> {s['chunks']} new chunks")
    t1 = time.perf_counter()
    n = embed_missing(con, args.embed_url, args.model_name)
    print(f"\n  N19 embed    : {n} chunks embedded via {args.embed_url}")
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("bronze_docs", "silver_chunks", "gold_embeddings")}
    dim = con.execute("SELECT MAX(dim) FROM gold_embeddings").fetchone()[0]
    con.close()
    print(f"  N18 tables   : {counts}  (dim={dim})  -> {db}")
    report = {"db": db.relative_to(ROOT).as_posix() if db.is_relative_to(ROOT) else str(db),
              "ingest": s, "embedded_now": n, "tables": counts, "dim": dim,
              "embed_model": args.model_name,
              "ingest_s": round(t1 - t0, 2), "embed_s": round(time.perf_counter() - t1, 2)}
    out = ROOT / "benchmarks" / "03-lakehouse-build.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"==> Wrote {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--embed-url", default=f"http://127.0.0.1:{labkit.embed_port()}")
    ap.add_argument("--model-name", default="nomic-embed-text-v1.5.Q4_K_M (mean pooling)")
    return build(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
