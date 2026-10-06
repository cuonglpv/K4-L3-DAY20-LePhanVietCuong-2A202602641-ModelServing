# 02 - Serve: load test + saturation reading

Host `Windows-AMD64` · llama.cpp `b10488` ·
`--parallel 4` · `ctx=2048` · `threads=4` ·
`ngl=99`

| Users | Reqs | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 10 | 69 | 0.39 | 22000 | 30000 | 35000 | 8.7 | 0.0% |
| 50 | 35 | 0.37 | 53000 | 92000 | 94000 | 19.3 | 0.0% |

*Effective concurrency = RPS x average latency (Little's Law) -- how many requests were
really in flight, regardless of how many users locust simulated. It counts queued requests
too, so the occupancy/slot ratio can legitimately exceed 1.0; it is occupancy, not
utilisation. For true slot utilisation use the server's own gauges (`make metrics`).*

## What these two runs say

> Run conditions: 10 users ran 3 min (69 requests); 50 users ran 100 s (35 requests) because a 3 min run at 50 users hit locust's 120 s read timeout while requests waited in the queue. Samples are small, so percentiles are indicative. The two runs use different durations; RPS and percentiles are still comparable because they are rates and quantiles, not totals.

| Going from 10 to 50 users | |
|:--|--:|
| Offered load | 5x |
| Throughput actually delivered | **0.94x** (19% of linear) |
| P95 latency | **3.07x** |
| Effective concurrency at 50 users | 19.3 vs `--parallel 4` slots (occupancy/slot ratio 4.82) |

**Saturated.** Throughput delivered only 0.94x for 5x the offered load, and effective concurrency (19.3) is at or above all 4 decode slots. Saturation sets in somewhere at or below 50 users; the load you added beyond that point became queue time rather than throughput.

Throughput moved 0.94x while P95 moved 3.07x. That gap is the goodput argument: past saturation you buy throughput by spending latency, and if your SLO is a P95 target then the requests you added are no longer being served within it. (This lab does not fix an SLO number for you -- pick one in your write-up and state how much goodput you keep at it.)

## Your reading

**Server đã bão hoà ở mức 10 user hoặc sớm hơn** (tôi chỉ đo 10 và 50 user nên không xác định được điểm chính xác bên dưới 10). Bằng chứng thuyết phục nhất: tải tăng 5x nhưng throughput **đi ngang** (0.39 -> 0.37 RPS, 0.94x) trong khi P95 tăng **3.07x** (30 s -> 92 s). Ngay ở 10 user, effective concurrency đã là 8.7, gấp đôi 4 slot; ở 50 user là 19.3 (4.82x slot). Server báo cùng điều đó: `processing=4`, `deferred=46` và busy slots 4.00/4. Phần tải thêm không tạo ra throughput, nó thành queue time (P95 tăng nhanh hơn RPS vì thế).

Goodput@SLO: chọn SLO là P95 <= 30 s cho mỗi request. Ở 10 user P95 = 30 s nên vừa đạt, goodput gần bằng throughput (~0.37-0.39 req/s). Ở 50 user P95 = 92 s và P50 = 53 s, tức hơn một nửa request đã vượt SLO, nên goodput chỉ tối đa khoảng một nửa 0.37 (~0.19 req/s) dù throughput thô vẫn ~0.37.

Cảnh báo về độ tin cậy: mẫu nhỏ (69 và 35 request), hai lần chạy khác thời lượng (3 min và 100 s), và locust chỉ đếm request đã hoàn tất nên các request còn xếp hàng lúc dừng không nằm trong percentile; P95 ở 50 user vì vậy là ước lượng thấp. Tôi tin hàng throughput và gauge của server hơn hàng P95. Tôi từng chạy 50 user trong 3 min: request chờ quá 120 s và bị ReadTimeout (26 request lỗi), đó cũng là bằng chứng độc lập cho hàng đợi dài hơn timeout.

Knob đổi đầu tiên: **không phải `--parallel`** (đã kín 4/4; thêm slot chỉ chia nhỏ cùng ngân sách tính toán và băng thông). Tôi sẽ giảm công việc mỗi request: giới hạn `max_tokens`, rút ngắn context RAG (prefill của prompt dài cũng chiếm thời gian server), hoặc dùng model nhỏ hơn (Qwen3.5 0.8B).
