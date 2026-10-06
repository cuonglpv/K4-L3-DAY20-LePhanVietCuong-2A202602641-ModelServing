# Bonus C9 - embedding serving regime

Captured stdout of `python bonus/serving-regimes/embedding-serving.py --base-url http://127.0.0.1:8081/v1`
against `llama-server --embedding` serving `nomic-embed-text-v1.5.Q4_K_M` (768-dim) on the Iris Xe iGPU
(`-ngl 99`, 4 threads). The script itself prints to the terminal only; this file is that output.

Query: "Does embedding serving use a KV cache and a decode loop like chat serving?"

| Rank | Cosine | Document |
|--:|--:|:--|
| 1 | 0.811 | Embedding serving is prefill-bound: one forward pass, no KV cache, no decode loop. |
| 2 | 0.716 | PagedAttention stores the KV cache in non-contiguous virtual-memory pages. |
| 3 | 0.604 | Quantization to FP8 or INT4 shrinks model memory and raises throughput. |

| Batch | Latency (ms) | Texts/s |
|--:|--:|--:|
| 1 | 202.9 | 4.9 |
| 2 | 200.4 | 10.0 |
| 4 | 696.2 | 5.7 |
| 8 | 279.8 | 28.6 |
| 16 | 364.1 | 43.9 |

## Your finding

**Embedding serving là regime prefill-bound: throughput đến từ batch lớn, không phải từ continuous batching.** Từ batch 1 đến 16 throughput tăng 9x (4.9 -> 43.9 texts/s) trong khi latency mỗi lần gọi chỉ tăng 1.8x (203 -> 364 ms): chi phí cố định mỗi request (HTTP, nạp tensor, lên lịch GPU) được chia cho nhiều văn bản. Điểm batch 4 (696 ms) là outlier; tôi chỉ chạy mỗi điểm một lần nên không loại trừ được nhiễu hệ thống, vì vậy tôi chỉ tin xu hướng tổng thể.

Đối chiếu với chat serving của lab: embedding không có KV cache và không có vòng decode, mỗi văn bản là một lượt forward độc lập (~200 ms cho batch 1 ở đây, chủ yếu là chi phí cố định), nên stage embed của RAG pipeline chỉ ~0.2-0.4 s so với llm 3.6 s. Tôi không so sánh được nomic với Gemma làm embedder một cách công bằng: lần chạy Gemma trước đó dùng corpus khác (chưa có ghi chú serving), nên chênh lệch chất lượng retrieval bị lẫn với thay đổi dữ liệu.
