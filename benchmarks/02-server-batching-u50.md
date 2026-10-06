# 02 - Continuous batching under load (u50)

Host `Windows-AMD64` · `--parallel 4` · 45 samples over
100s at 2.0s intervals · raw CSV: `02-server-metrics-u50.csv`

| Gauge | Peak observed |
|:--|--:|
| `n_busy_slots_per_decode` (avg/decode) | 4.00 of 4 slots (100%) |
| `requests_processing` | 4 |
| `requests_deferred` | 46 |
| `kv_cache_usage_ratio` | n/a — not exported by llama.cpp `b10488` |
| `tokens_predicted_total` (final) | 2292 |

Highest sampled value was **4.00 of 4** slots. Note this gauge is llama.cpp's *average* busy slots per decode step, so the number below is the highest average we sampled, not an instantaneous maximum batch width. A peak near 1 means
requests were served one at a time -- either the load was too light to overlap, or
they arrived too far apart. A peak approaching `--parallel` means the scheduler was
genuinely packing concurrent requests into shared decode steps.
`requests_deferred` went above zero: more requests arrived than there were slots, so some waited. That wait is the queue time in your P95.

## Your observation

Peak `n_busy_slots_per_decode` là **4.00/4**, kèm `requests_processing=4` và `requests_deferred=46`: scheduler gộp đủ 4 request vào chung các bước decode và 46 request còn lại xếp hàng chờ slot. Đây là continuous batching đúng nghĩa. Server được khởi động mới trước lần chạy này nên gauge (là trung bình tích lũy của llama.cpp, không phải giá trị tức thời) không còn dư từ các lần chạy trước; mẫu đầu tiên đã là 4.0 vì 50 user vào gần như cùng lúc.

Khớp với `02-server-results.md`: effective concurrency 19.8 > 4 slot, cả hai cùng nói slot đã kín và phần dư là hàng đợi. Tôi tin gauge của server khi nói về slot và tin effective concurrency khi nói về số request đang nằm trong hệ thống (gồm hàng đợi). Lợi ích của batching có giới hạn: `tokens_predicted_total` tăng 0 -> 2292 trong 99.5 s (khoảng 23 tok/s), so với ~13 tok/s khi chạy một request đơn, tức ~1.8x chứ không phải 4x. Trần có thể là băng thông bộ nhớ dùng chung giữa CPU và iGPU (tôi chưa tách bạch được với giới hạn tính toán của iGPU), và prefill của các prompt RAG dài cũng lấy thời gian của slot. Lần chạy trước của cùng cấu hình cho ~18 tok/s, nên con số này dao động khoảng 20-25% giữa các lần.
