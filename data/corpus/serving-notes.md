# LLM serving notes

These notes are a second source for the N17 ingest. They restate the standard serving
concepts that the lab's toy retrieval set used (the same facts as TOY_DOCS in pipeline.py),
so the RAG questions have answers in the corpus instead of only in the code.

## PagedAttention
PagedAttention stores the KV cache in non-contiguous pages, removing the internal
fragmentation that wasted most GPU memory. Requests of different lengths share one pool
of fixed-size blocks, so more requests fit in memory at the same time.

## RadixAttention
RadixAttention keys cached KV by token prefix in a trie, so a shared prefix lets the
engine skip prefill entirely. A byte-identical system prompt across requests is what
makes the prefix reusable.

## Disaggregated serving
Disaggregated serving splits prefill and decode onto separate pools because prefill is
compute-bound and decode is memory-bandwidth-bound. Splitting helps when long prompts
would otherwise stall the decode of other requests.

## Goodput at SLO
Goodput@SLO counts only the requests per second that met the TTFT and TPOT targets.
Throughput at saturation ignores SLOs, so past the saturation point it keeps growing
while goodput falls.

## Quantization
GGUF 4-bit quantization is the practical default for laptop and edge serving; 2-bit
trades noticeable quality for size and, on a compute-limited machine, can decode slower.

## Continuous batching
Continuous batching lets requests join and leave the running batch each decode step
instead of waiting for a full batch.
