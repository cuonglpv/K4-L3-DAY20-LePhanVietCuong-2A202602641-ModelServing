#!/usr/bin/env python3
"""03 - Integrate: RAG pipeline against your local llama-server.

Runs as-is on toy data, so you can prove the serving endpoint works before wiring
in your real N16-N19 stack. Replace the two STUB functions with your own code and
the timing breakdown starts telling you something real.

The point of the timing split is to find out where your latency actually lives.
Most students guess "the LLM" and are right; the interesting cases are the ones
where retrieval or embedding turns out to cost more than decode.

    make serve         # terminal 1
    make pipeline      # terminal 2
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
from dataclasses import dataclass, field

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import labkit  # noqa: E402

SYSTEM_PROMPT = (
    "You are a model-serving tutor. Answer using only the provided context. "
    "If the context does not contain the answer, say so plainly."
)

# ── STUB 1 ─────────────────────────────────────────────────────────────
# Replace TOY_DOCS + retrieve() with your N19 vector index.
# Keeping SQLite or a dict as your "lakehouse" is fine -- say so in REFLECTION.
TOY_DOCS = [
    {"id": "paged", "text": "PagedAttention stores the KV cache in non-contiguous pages, "
                            "removing the internal fragmentation that wasted most GPU memory."},
    {"id": "radix", "text": "RadixAttention keys cached KV by token prefix in a trie, so a "
                            "shared prefix lets the engine skip prefill entirely."},
    {"id": "disagg", "text": "Disaggregated serving splits prefill and decode onto separate "
                             "pools because prefill is compute-bound and decode is "
                             "memory-bandwidth-bound."},
    {"id": "goodput", "text": "Goodput@SLO counts only the requests per second that met the "
                              "TTFT and TPOT targets. Throughput at saturation ignores SLOs."},
    {"id": "quant", "text": "GGUF 4-bit quantization is the practical default for laptop and "
                            "edge serving; 2-bit trades noticeable quality for size."},
    {"id": "batching", "text": "Continuous batching lets requests join and leave the running "
                               "batch each decode step instead of waiting for a full batch."},
]


@dataclass
class Doc:
    id: str
    text: str
    score: float
    timings: dict = field(default_factory=dict)


def embed(texts: list[str], embed_url: str | None) -> list[list[float]] | None:
    """Optional real embeddings from a llama-server started with --embedding.

    Returns None when no embedding server is running, which is the normal case
    for the core lab -- retrieve() then falls back to keyword overlap.
    Start one with `make serve-embed` (bonus C9) to make this path real.
    """
    if not embed_url:
        return None
    try:
        r = httpx.post(f"{embed_url}/v1/embeddings",
                       json={"model": "local", "input": texts}, timeout=120.0)
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]
    except (httpx.HTTPError, KeyError):
        return None


LAKEHOUSE_DB: str | None = None   # set by --lakehouse; see stack.py (N17-N19)
_INDEX = None


def retrieve_lakehouse(query: str, k: int, embed_url: str) -> tuple[list[Doc], dict, str]:
    """Real N19 path: embed the query, exact cosine search over the gold table."""
    global _INDEX
    import numpy as np
    import stack  # labs/03-integrate/stack.py
    if _INDEX is None:
        _INDEX = stack.VectorIndex(pathlib.Path(LAKEHOUSE_DB))
    t0 = time.perf_counter()
    qv = stack.embed([_INDEX.query_prefix + query], embed_url)[0]
    embed_ms = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    hits = _INDEX.search(np.asarray(qv, dtype=np.float32), k)
    retrieve_ms = (time.perf_counter() - t0) * 1000.0
    docs = [Doc(cid, text, score) for cid, text, score in hits]
    return docs, {"embed": round(embed_ms, 1), "retrieve": round(retrieve_ms, 1)}, (
        f"lakehouse vector index ({len(_INDEX.ids)} chunks) + llama-server /v1/embeddings")


def retrieve(query: str, k: int = 3,
             embed_url: str | None = None) -> tuple[list[Doc], dict, str]:
    """STUB 2: replace with your N19 vector search. Returns (docs, timings_ms)."""
    if LAKEHOUSE_DB and embed_url:
        return retrieve_lakehouse(query, k, embed_url)
    t0 = time.perf_counter()
    vectors = embed([query] + [d["text"] for d in TOY_DOCS], embed_url)
    embed_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    if vectors:
        import math

        qv, dvs = vectors[0], vectors[1:]

        def cos(a: list[float], b: list[float]) -> float:
            num = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
            return num / (na * nb) if na and nb else 0.0

        scored = [Doc(d["id"], d["text"], cos(qv, dv)) for d, dv in zip(TOY_DOCS, dvs)]
    else:
        terms = {w.lower().strip(".,?") for w in query.split() if len(w) > 3}
        scored = [
            Doc(d["id"], d["text"],
                float(len(terms & {w.lower().strip(".,?") for w in d["text"].split()})))
            for d in TOY_DOCS
        ]
    retrieve_ms = (time.perf_counter() - t0) * 1000.0

    top = sorted(scored, key=lambda d: d.score, reverse=True)[:k]
    return top, {"embed": round(embed_ms, 1), "retrieve": round(retrieve_ms, 1)}, (
        "llama-server /v1/embeddings" if vectors else "keyword overlap")


def build_prompt(query: str, contexts: list[Doc]) -> list[dict]:
    ctx = "\n".join(f"[{c.id}] {c.text}" for c in contexts)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {query}"},
    ]


def call_llm(messages: list[dict], base: str) -> tuple[str, float, dict]:
    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{base}/v1/chat/completions",
                       json={"model": "local", "messages": messages,
                             "max_tokens": 200, "temperature": 0.3},
                       timeout=300.0)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        labkit.die(f"{exc}", "Is llama-server running?  Start it with: make serve")
    body = r.json()
    return (body["choices"][0]["message"]["content"],
            (time.perf_counter() - t0) * 1000.0,
            body.get("timings") or {})


def answer(query: str, base: str, embed_url: str | None, k: int = 3) -> dict:
    t_all = time.perf_counter()
    docs, t_retr, backend = retrieve(query, k=k, embed_url=embed_url)
    text, llm_ms, server_timings = call_llm(build_prompt(query, docs), base)
    return {
        "query": query,
        "answer": text.strip(),
        "contexts": [{"id": d.id, "score": round(d.score, 4)} for d in docs],
        "embed_backend": backend,
        "timings_ms": {
            **t_retr,
            "llm": round(llm_ms, 1),
            "total": round((time.perf_counter() - t_all) * 1000.0, 1),
        },
        "server_timings": {k2: server_timings.get(k2) for k2 in
                           ("prompt_n", "prompt_ms", "predicted_n", "predicted_ms")},
    }


QUERIES = [
    "Why is goodput more useful than raw throughput?",
    "What problem does PagedAttention actually solve?",
    "When does splitting prefill and decode help?",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG pipeline against local llama-server.")
    port = labkit.server_port()
    ap.add_argument("--base-url", default=f"http://127.0.0.1:{port}")  # not localhost: see labkit.base_url
    ap.add_argument("--embed-url", default=None,
                    help=f"Embedding server, e.g. http://localhost:{labkit.embed_port()} "
                         "(bonus C9). Omit to use keyword retrieval.")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--lakehouse", default=None,
                    help="SQLite lakehouse built by stack.py (needs --embed-url). "
                         "Replaces the toy keyword retrieval with the real N17-N19 stack.")
    args = ap.parse_args()
    global LAKEHOUSE_DB
    if args.lakehouse:
        if not args.embed_url:
            labkit.die("--lakehouse needs --embed-url.", "Start one with: make serve-embed")
        LAKEHOUSE_DB = args.lakehouse

    labkit.banner("03 - RAG pipeline")
    print(f"  llama-server : {args.base_url}")
    print(f"  embeddings   : {args.embed_url or 'none (keyword overlap fallback)'}")

    results = []
    for q in QUERIES:
        print(f"\n=== {q}")
        res = answer(q, args.base_url, args.embed_url, k=args.k)
        results.append(res)
        print(f"  contexts : {[(c['id'], c['score']) for c in res['contexts']]}")
        print(f"  timings  : {res['timings_ms']}")
        st = res["server_timings"]
        if st.get("predicted_n"):
            print(f"  server   : prefill {st['prompt_n']} tok / {st['prompt_ms']:.0f} ms, "
                  f"decode {st['predicted_n']} tok / {st['predicted_ms']:.0f} ms")
        print(f"  answer   : {res['answer'][:280]}")

    avg = {k: round(sum(r["timings_ms"][k] for r in results) / len(results), 1)
           for k in ("embed", "retrieve", "llm", "total")}
    print(f"\n  Mean over {len(results)} queries (ms): {avg}")
    dominant = max(("embed", "retrieve", "llm"), key=lambda k: avg[k])
    share = 100 * avg[dominant] / avg["total"] if avg["total"] else 0.0
    print(f"  Dominant stage: {dominant} ({share:.0f}% of total)")

    backend = results[0]["embed_backend"]
    per_query = labkit.md_table(
        ["Query", "Contexts retrieved", "embed (ms)", "retrieve (ms)", "llm (ms)", "total (ms)"],
        [[f"{r['query'][:44]}...", ", ".join(c["id"] for c in r["contexts"]),
          r["timings_ms"]["embed"], r["timings_ms"]["retrieve"],
          r["timings_ms"]["llm"], r["timings_ms"]["total"]] for r in results],
    )
    md = f"""# 03 - Integrate: RAG pipeline run

Host `{labkit.host_tag()}` · llama.cpp `{labkit.LLAMA_CPP_BUILD}` ·
retrieval backend: **{backend}** · {len(results)} queries

{per_query}

Mean per stage (ms): embed **{avg['embed']}** · retrieve **{avg['retrieve']}** ·
llm **{avg['llm']}** · total **{avg['total']}**
Dominant stage: **{dominant}** ({share:.0f}% of total)

## Answers returned

{chr(10).join(f"**{r['query']}**{chr(10)}{chr(10)}> {r['answer'][:400]}{chr(10)}" for r in results)}

## Which N16-N19 pieces are real (required -- replace this line)

_List each of N16, N17, N18, N19 as real or stubbed. Stubbing costs no points;
misrepresenting it does. Then answer: is the dominant stage above what you expected?
If you had to halve this pipeline's latency, which stage would you attack and why?_
"""
    out = labkit.write_report("03-integration-results.md", md,
                              {"backend": backend, "mean_ms": avg, "results": results})
    print(f"\n==> Wrote {out.relative_to(labkit.repo_root())}")
    print("  Put these numbers in REFLECTION.md section 4 as well.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
