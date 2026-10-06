# 03 - Integrate: RAG pipeline run

Host `Windows-AMD64` · llama.cpp `b10488` ·
retrieval backend: **lakehouse vector index (265 chunks) + llama-server /v1/embeddings** · 3 queries

| Query | Contexts retrieved | embed (ms) | retrieve (ms) | llm (ms) | total (ms) |
|:--|--:|--:|--:|--:|--:|
| Why is goodput more useful than raw throughp... | docs/labs/02-serve.md#4, data/corpus/serving-notes.md#3, data/corpus/serving-notes.md#2 | 718.9 | 0.2 | 3467.6 | 4274.6 |
| What problem does PagedAttention actually so... | data/corpus/serving-notes.md#0, data/corpus/serving-notes.md#2, docs/labs/02-serve.md#5 | 204.2 | 0.1 | 3283.2 | 3487.6 |
| When does splitting prefill and decode help?... | data/corpus/serving-notes.md#2, data/corpus/serving-notes.md#1, docs/labs/03-integrate.md#5 | 248.7 | 0.1 | 3939.2 | 4188.0 |

Mean per stage (ms): embed **390.6** · retrieve **0.1** ·
llm **3563.3** · total **3983.4**
Dominant stage: **llm** (89% of total)

## Answers returned

**Why is goodput more useful than raw throughput?**

> Goodput@SLO counts only the requests per second that met the TTFT and TPOT targets.

**What problem does PagedAttention actually solve?**

> PagedAttention stores the KV cache in non-contiguous pages, removing the internal fragmentation that wasted most GPU memory.

**When does splitting prefill and decode help?**

> Splitting prefill and decode helps when long prompts would otherwise stall the decode of other requests.


## Which N16-N19 pieces are real

Chạy bằng: `python labs/03-integrate/pipeline.py --lakehouse data/lakehouse.db --embed-url http://127.0.0.1:8081` (retrieval thật, server LLM khởi động lại trước đó nên prompt cache lạnh).

| Day | Piece | Trạng thái |
|:--|:--|:--|
| N16 Cloud/IaC | `infra/Dockerfile` + `infra/docker-compose.yml` mô tả đúng topology của lab (chat server `--parallel 4 --cont-batching --metrics`, embedding server, loopback-only, giới hạn RAM, healthcheck). Chỉ validate bằng `docker compose config`; **chưa build, chưa chạy, chưa deploy lên cloud** (Docker daemon tắt, không có tài khoản cloud). | **một phần** (IaC viết, chưa áp dụng) |
| N17 Data pipeline | `labs/03-integrate/stack.py`: đọc 17 file (README, `docs/**`, `data/corpus/serving-notes.md`), làm sạch markdown, chia 265 chunk (70 từ, gối 15), băm sha256 để nạp tăng dần. Chạy lại lần hai: 17 unchanged, 0 chunk mới, 0 embedding mới. | **real** (local) |
| N18 Lakehouse | SQLite với ba lớp medallion: `bronze_docs` (raw + sha256) -> `silver_chunks` -> `gold_embeddings` (vector + tên model). Xóa vector cũ khi file nguồn đổi để không bao giờ stale. **Không** phải Iceberg/Delta và không có object store. | **một phần** (SQLite thay lakehouse) |
| N19 Vector index | Embedding thật từ `llama-server --embedding` với `nomic-embed-text-v1.5.Q4_K_M` (84 MB, 768 chiều, Hugging Face, Apache-2.0); tìm kiếm cosine chính xác trên ma trận 265x768. Không phải ANN (HNSW/IVF): với 265 vector chưa cần. | **real** (exact search) |
| N20 Serving | `llama-server` Gemma 4 E2B Q4_K_XL | **real** |

Một điều cần khai báo: `data/corpus/serving-notes.md` do tôi viết, lặp lại các sự kiện của `TOY_DOCS` (PagedAttention, RadixAttention, ...) để chúng đi qua pipeline ingest thật. Docs của lab chỉ nhắc các khái niệm này chứ không giải thích; lần chạy đầu chỉ với docs cho kết quả "context does not contain the answer".

**Stage chiếm nhiều nhất là llm: 89% (3563 ms trên 3983 ms).** embed trung bình 391 ms (lần đầu 719 ms khởi động, sau đó 204-249 ms), retrieve 0.1 ms. Đúng kỳ vọng: chỉ 265 vector nên tìm kiếm gần như miễn phí; embedder 84 MB đủ nhẹ. Trong stage llm, server báo prefill ~335-378 token mất 1.7-2.2 s và decode ~22 token mất 1.2-1.5 s, tức prefill chiếm hơn một nửa vì context retrieve làm prompt dài ra.

Hai phát hiện khi đo:
1. **`localhost` thêm ~2.1 s cho mỗi kết nối httpx mới trên Windows** (server chỉ bind IPv4 `127.0.0.1`, còn `localhost` thử `::1` trước). Lần chạy pipeline đầu cho llm 5.1 s trong khi server chỉ báo ~3 s; chênh ~2 s đó chính là nguyên nhân này. Tôi đổi mặc định sang `127.0.0.1` (`labkit.base_url`, `pipeline.py`, `stack.py`). Bench đã dùng `127.0.0.1` nên không ảnh hưởng; locust dùng keep-alive nên chỉ chịu ~2 s một lần cho request đầu của mỗi user (không đáng kể so với P50 22-53 s).
2. **Prompt cache**: chạy lại ngay cùng 3 prompt cho prefill 5 token (cache hit), llm 1790 ms, tổng 2067 ms so với 3983 ms lúc cache lạnh. Tôi báo số cache lạnh ở trên; số 2067 ms chỉ đúng khi prompt lặp lại y nguyên.

Nếu phải giảm latency 2x tôi tấn công **prefill trong stage llm**: giảm k hoặc chunk để prompt ngắn hơn, và giữ system prompt giống nhau từng byte để server dùng lại prefix. Lần chạy cache nóng ở trên (1.9x) là bằng chứng cho hướng này; decode (~22 token, ~60 ms/token) khó giảm hơn vì bị chặn bởi băng thông bộ nhớ.
