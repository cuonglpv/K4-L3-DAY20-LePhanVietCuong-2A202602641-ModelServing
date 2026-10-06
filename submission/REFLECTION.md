# Reflection — Day 20 Lab (Personal Report)

> **Đây là báo cáo cá nhân.** Số liệu của bạn **không** so sánh được với bạn cùng lớp
> — chỉ so **before vs after trên chính máy bạn**. Rubric chấm độ rõ ràng của setup,
> đo lường và **lập luận**, không chấm tốc độ tuyệt đối.
>
> `make verify` sẽ fail nếu còn placeholder chưa điền. Đó là cố ý.

**Họ Tên:** Lê Phan Việt Cường
**MSSV:** 2A202602641
**Cohort:** K4-L3
**Ngày submit:** 2026-10-06

---

## 1. Hardware & runtime  *(rubric 1, 2 — 10 điểm)*

> Từ `make probe`. Paste output hoặc điền tay.

- **OS:** Windows 11 (AMD64)
- **CPU:** 11th Gen Intel Core i5-1130G7 @ 1.10GHz
- **Cores:** 4 physical / 8 logical
- **CPU extensions:** AVX-512 (llama.cpp tự nạp `ggml-cpu-icelake.dll`)
- **RAM:** 15.7 GB
- **Accelerator:** Vulkan (Intel Iris Xe iGPU, RAM dùng chung với CPU)
- **llama.cpp asset đã tải:** llama-b10488-bin-win-vulkan-x64.zip
- **Model đã dùng:** Gemma 4 E2B (`LAB_MODEL=gemma4-e2b`)
- **Quantization:** UD-Q4_K_XL (primary) + UD-Q2_K_XL (compare) (từ `models/active.json`)

**Chạy ở đâu:** laptop của tôi
_(Nếu dùng cloud fallback: nói rõ vì sao — RAM < 8 GB, setup fail, v.v. Không mất điểm.)_

**Setup story** (≤ 80 chữ): điều gì cần thay đổi để lab chạy trên máy bạn? Có bước
nào fail rồi phải workaround không?

Hai chỗ phải xử lý. (1) `lab.ps1` lỗi parse trên Windows PowerShell 5.1 vì có em dash nhưng không có BOM UTF-8; tôi thêm BOM, đồng thời đặt `PYTHONUTF8=1` vì Python crash `UnicodeEncodeError` (cp1252) khi in ký tự `─` qua pipe. (2) Tải model bị kẹt ở ~10 KB/s; thử lại trên mạng nhanh hơn thì xong (setup resume được).

---

## 2. Đo lường  *(rubric 3, 4, 5 — 20 điểm)*

> Paste bảng từ `benchmarks/01-quickstart-results.md` (`make bench` tự sinh).

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|---|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 17526 | 752 / 3362 | 67.0 / 75.9 | 4944 / 8143 / 8143 | 14.9 |
| UD-Q2_K_XL | 2.24 | 10892 | 1226 / 8568 | 127.5 / 136.1 | 9216 / 16195 / 16195 | 7.8 |

**Quan sát** (≤ 60 chữ): 2-bit nhanh hơn bao nhiêu, và **có đáng không**? Bạn đã thử
hỏi cùng một câu trên cả hai (`make serve` vs `.venv/bin/python labs/02-serve/serve.py --compare`)
chưa? Chất lượng khác nhau thế nào?

2-bit nhỏ hơn 0.73 GB (~25%) nhưng decode **chậm hơn 1.9x** trên cấu hình mặc định (7.8 vs 14.9 tok/s; `llama-bench` chạy lại xen kẽ cho 1.7x nên không phải do giảm xung). Nguyên nhân tôi tìm ra: `make bench` chạy `-ngl 99` nên decode nằm trên iGPU (Vulkan), nơi kernel Q2_K chậm hơn Q4_K; ở CPU-only chiều hướng đảo ngược (Q2 nhanh hơn ~1.4x, nhiễu lớn). Tôi hỏi cùng 3 câu trên cả hai server: chất lượng gần nhau, Q2 kém gọn hơn chút, nên chọn Q4. TTFT P95 bị kéo bởi request đầu (cold cache).

---

## 3. Serving under load  *(rubric 8, 9, 10 — 20 điểm)*

> Từ `benchmarks/02-server-results.md` (`make load-report`).

| Users | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|--:|--:|--:|--:|--:|--:|--:|
| 10 | 0.39 | 22000 | 30000 | 35000 | 8.7 | 0.0% |
| 50 | 0.37 | 53000 | 92000 | 94000 | 19.3 | 0.0% |

- **Offered load tăng 5×, throughput thực tăng:** 0.94× (throughput đi ngang: 0.39 → 0.37 RPS)
- **P95 tăng:** 3.07× (30 s → 92 s; vẫn là ước lượng thấp vì locust chỉ tính request đã xong)
- **Effective concurrency ở 50 users:** 19.3 so với `--parallel` = 4 slots (10 user: 8.7)

**Peak `llamacpp:n_busy_slots_per_decode`** (từ `make metrics` khi `make load-50` đang
chạy): 4.00 / 4 slots (`processing=4`, `deferred=46`)

**Saturation reading** (≤ 80 chữ): server của bạn bão hoà ở đâu, và **bằng chứng nào**
thuyết phục bạn? Nếu P95 tăng nhanh hơn RPS thì phần latency thêm đó là queue time hay
compute time — bạn biết bằng cách nào? Nếu bạn phải nâng goodput@SLO, bạn sẽ đổi knob
nào **trước**, và vì sao knob đó?

Server đã bão hoà ở mức 10 user hoặc sớm hơn (tôi chỉ đo 10 và 50). Bằng chứng: tải 5× nhưng throughput đi ngang (0.94×) còn P95 tăng 3.07×; effective concurrency 8.7 ở 10 user và 19.3 ở 50 user, so với 4 slot; server báo `processing=4`, `deferred=46`. Phần tải thêm thành queue time, không phải compute: P95 tăng nhanh hơn RPS. Batching chỉ cho ~18 tok/s tổng so với ~13 tok/s một request (~1.4×). Với SLO P95 ≤ 30 s, 10 user vừa đạt, 50 user không đạt (goodput tối đa ~0.19 req/s). Knob đổi trước: giảm công việc mỗi request (`max_tokens`, context RAG ngắn hơn, model nhỏ hơn), không phải `--parallel`. Mẫu nhỏ (69 và 35 request; 10 user chạy 3 phút, 50 user chạy 100 giây vì 3 phút gây ReadTimeout).

---

## 4. Integration  *(rubric 12, 13 — 15 điểm)*

> Từ `make pipeline`. Nói thật cái nào real, cái nào stub — stub **không** mất điểm.

| Day | Piece | Real hay stub? |
|---|---|---|
| N16 Cloud/IaC | `infra/Dockerfile` + `docker-compose.yml`, chỉ validate (`docker compose config`), chưa build/deploy | một phần |
| N17 Data pipeline | `labs/03-integrate/stack.py`: ingest 17 file → 265 chunk, nạp tăng dần theo sha256 | real (local) |
| N18 Lakehouse | SQLite medallion bronze/silver/gold (không phải Iceberg/Delta) | một phần (SQLite thay thế) |
| N19 Vector + features | embedding thật (nomic-embed-text-v1.5, 768 chiều) + cosine chính xác trên 265 vector | real (không phải ANN) |
| N20 Serving | `llama-server` | real |

**Latency split** (mean của 3 query, retrieval thật, cache lạnh, từ `pipeline.py --lakehouse`):

- embed: 390.6 ms (lần đầu 719 ms, sau đó 204–249 ms)
- retrieve: 0.1 ms
- llm: 3563.3 ms
- **stage chiếm nhiều nhất:** llm (89% của total, 3983.4 ms)

**Reflection** (≤ 60 chữ): bottleneck ở đâu? Có khớp với kỳ vọng của bạn không? Nếu
phải giảm latency của pipeline này 2×, bạn sẽ tấn công vào đâu?

Bottleneck là llm (89%), đúng kỳ vọng; retrieval gần như miễn phí với 265 vector. Trong llm, prefill ~350 token (1.7–2.2 s) chiếm hơn nửa vì context retrieve làm prompt dài, decode ~22 token (1.2–1.5 s). Muốn giảm 2× tôi tấn công prefill: prompt ngắn hơn và giữ system prompt giống nhau từng byte để dùng lại prefix cache (chạy lại cùng prompt cho 3983 → 2067 ms, 1.9×, chỉ đúng khi prompt lặp lại). Phát hiện khi đo: `localhost` thêm ~2.1 s mỗi kết nối httpx mới trên Windows (server chỉ bind IPv4); tôi đổi mặc định sang `127.0.0.1`, và đó chính là khoảng chênh ~2 s mà lần đo đầu chưa giải thích được. Corpus `data/corpus/serving-notes.md` do tôi viết (lặp lại các sự kiện của TOY_DOCS) để câu hỏi có đáp án trong dữ liệu.

---

## 5. The single change that mattered most  *(rubric 11 — 10 điểm)*

> **Phần quan trọng nhất của report.** Không cần bonus track: `make tune` đã cho bạn
> một before/after thật (`benchmarks/01-tuning-tg128.md`). Đổi quantization,
> `LAB_N_CTX`, hay `--parallel` rồi đo lại cũng được.

**Change:** giữ quantization UD-Q4_K_XL thay vì UD-Q2_K_XL (số thread không đổi được gì: 1.04×)

```
before:  7.8 tok/s decode (UD-Q2_K_XL, `make bench`)
after:   14.9 tok/s decode (UD-Q4_K_XL, `make bench`)
speedup: 1.91× (llama-bench chạy lại: 7.7 → 13.3 tok/s = 1.73×)
```

**Tại sao nó work** (1–2 đoạn — đây là phần grader đọc kỹ nhất):

_Giải thích như đang nói với bạn ngồi cạnh. Bám vào **cơ chế**, không phải "vibes":
memory bandwidth? vector width? cache residency? scheduling? queueing? Nếu kết quả
**khác** với kỳ vọng từ deck — nói rõ, và giải thích vì sao. Grader thưởng điểm cho
lập luận đúng về một kết quả bất ngờ, hơn là một con số đẹp không được giải thích._

Thay đổi tôi kỳ vọng sẽ quan trọng nhất là số thread, nhưng `make tune` cho kết quả ngược kỳ vọng: đường cong phẳng ngay từ 1 thread (11.7 → 12.7 tok/s, 1.09× toàn dải, 1.04× so với `-t 4`). Ban đầu tôi giải thích bằng băng thông bộ nhớ, và giải thích đó **sai**: tôi chỉ nhìn đường cong ở `-ngl 99`, tức decode đang chạy trên iGPU nên CPU thread gần như không phải bên tính toán. Khi chạy lại ở CPU-only (`-ngl 0`) đường cong có đúng hình mong đợi: 1 thread 3.9, 2 thread 7.1, 4 thread 8.7 (knee ở 4 core vật lý), 8 thread 8.6 tok/s (thread logic không thêm gì vì chia sẻ ALU/cache/cổng bộ nhớ với thread cùng core).

Thay đổi có tác dụng thật trên cấu hình mặc định là chọn quantization, theo hướng bất ngờ: 2-bit nhỏ hơn 25% nhưng chậm hơn 1.9×. Nếu decode thuần bandwidth-bound thì ít byte hơn phải nhanh hơn, và thật vậy ở CPU-only Q2 nhanh hơn Q4. Cái làm Q2 chậm là backend: trên iGPU Iris Xe qua Vulkan, Q2 chỉ 6.7–7.3 tok/s so với Q4 10.5–12.0. Tôi kiểm chứng được sự đảo chiều giữa hai backend, nhưng chưa kiểm chứng được nguyên nhân bên trong kernel Vulkan. Bài học: "ít bit hơn" không tự động nhanh hơn; kết quả phụ thuộc vào bên nào đang tính (CPU hay iGPU), và đo lặp lại là bắt buộc vì các lần chạy cùng cấu hình dao động tới ~25%.

---

## 6. Bonus  *(optional — tối đa 10 điểm)*

> Bỏ trống nếu không làm. Xem `docs/bonus/README.md`. Đừng làm hết — **một** finding sâu
> ăn điểm hơn năm bảng nông.

**Đã làm:** B2 (`make sweep-gpu` → `benchmarks/bonus-gpu-offload-sweep.md`), B3 (before/after bên dưới) và B5 chọn C9 (embedding serving → `benchmarks/bonus-embed-demo.md`). Không làm B1: máy không có cmake/compiler C++.

**Numbers** (GPU offload, Q4_K_XL, 4 thread, `tg` decode; median của các lần `llama-bench` xen kẽ):

```
before:  8.9 tok/s   (-ngl 0, CPU-only, median 10 lần, khoảng 6.3-10.6)
after:   10.8 tok/s  (-ngl 99, full offload iGPU, median 6 lần, khoảng 10.4-12.4)
speedup: 1.21x       (lần sweep đơn: 7.8 -> 10.8 = 1.39x)
```

**Điều này nói lên gì mà deck chưa nói:** trên laptop UMA, offload lên iGPU chỉ cho lợi ích vừa phải (~1.2×) vì CPU và iGPU cùng đọc một bus RAM; không có VRAM riêng để "hết chỗ" nên đường cong tăng đều chứ không có đỉnh. Quan trọng hơn, nó đổi cách đọc các kết quả base: vì `-ngl 99` là mặc định nên `make tune` đo một iGPU gần như không phụ thuộc thread (phẳng), còn CPU-only mới cho knee ở 4 core vật lý (3.9 → 7.1 → 8.7 → 8.6 tok/s); và Q2_K chậm hơn Q4_K chỉ ở đường Vulkan, ngược lại ở CPU. Với C9: embedding là regime prefill-bound, throughput tăng 9× từ batch 1 lên 16 (4.9 → 43.9 texts/s) trong khi latency chỉ tăng 1.8×.

---

## 7. Điều làm bạn ngạc nhiên nhất  *(optional)*

Hai giải thích đầu tiên của tôi (thread phẳng do băng thông; Q2 chậm do giải nén) đều sai hoặc thiếu vì tôi không để ý `-ngl 99` mặc định đẩy decode sang iGPU, và `localhost` trên Windows thêm ~2 s mỗi kết nối. Cả hai chỉ lộ ra khi tôi chạy thêm một thí nghiệm đối chứng; tôi đã sửa lại các phần liên quan thay vì giữ lập luận ban đầu.

---

## 8. Self-check trước khi push

- [ ] `hardware.json` committed
- [ ] `models/active.json` committed
- [ ] `benchmarks/01-quickstart-results.md` committed (`make bench`)
- [ ] `benchmarks/01-tuning-tg128.md` committed (`make tune`)
- [ ] `benchmarks/02-server-results.md` committed (`make load-report`)
- [ ] `benchmarks/02-server-batching-u50.md` hoặc `-metrics-u50.csv` committed (`make metrics`)
- [ ] `benchmarks/locust-10_stats.csv` + `locust-50_stats.csv` committed (`make load-10` / `load-50`)
- [ ] `benchmarks/03-integration-results.md` committed (`make pipeline`)
- [ ] Mọi section **"required — replace this line"** trong các file `benchmarks/*.md`
      đã được thay bằng nhận xét của bạn
- [ ] 5 screenshots trong `submission/screenshots/`
- [ ] `make verify` → **exit 0**
- [ ] Repo tên đúng mẫu `K4-L3-DAY20-HoVaTen-MSSV-ModelServing` (xem `docs/SUBMISSION.md`)
- [ ] Repo GitHub ở chế độ **public**
- [ ] Đã push và paste public URL vào VinUni LMS **trước 23:59 (UTC+7) ngày làm lab**
- [ ] **Không** commit `models/*.gguf`, `runtime/` hay `.env` (đã có trong `.gitignore`)

**Quan trọng:** repo phải **public** đến khi điểm được công bố. Private → grader không
xem được → 0 điểm.

---

## 9. Khai báo sử dụng AI  *(xem `docs/RULES.md` §3)*

_Claude Code (Anthropic): chạy các lệnh lab, sửa lỗi `lab.ps1` (BOM + UTF-8), và soạn nháp phần nhận xét/REFLECTION dựa trên số đo thật trong `benchmarks/`, viết `labs/03-integrate/stack.py` (N17–N19), `infra/` (N16) và tự chụp các screenshot từ cửa sổ console thật. Tôi đã đọc và chịu trách nhiệm về nội dung._
