# 01 - Measure: latency baseline

Model `Gemma 4 E2B` · host `Windows-AMD64` · llama.cpp `b10488`
Settings: `threads=4` `ngl=99` `ctx=2048`
`max_tokens=64` · warm-up discarded
Completed requests: `UD-Q4_K_XL` 10/10 · `UD-Q2_K_XL` 10/10

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|:--|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 17526 | 752 / 3362 | 67.0 / 75.9 | 4944 / 8143 / 8143 | 14.9 |
| UD-Q2_K_XL | 2.24 | 10892 | 1226 / 8568 | 127.5 / 136.1 | 9216 / 16195 / 16195 | 7.8 |

- **TTFT** = prefill. Short prompts keep it small; long-context RAG is where it explodes.
- **TPOT** = per-output-token decode cost, bounded by memory bandwidth. `decode tok/s = 1000 / TPOT_p50`.
- `UD-Q2_K_XL` decodes **1.91x SLOWER** than `UD-Q4_K_XL` here, despite being 0.73 GB smaller. That is a real result, not a mistake: fewer bits only buys speed when decode is limited by memory bandwidth. On a machine that is compute-limited instead — few cores, no GPU offload — the extra dequantization work of a heavily-quantized format can cost more than the bytes it saves. Say which case yours is.

## Your observation

**2-bit không đáng dùng trên máy này.** `UD-Q2_K_XL` nhỏ hơn 0.73 GB (2.24 vs 2.97 GB, ~25%) và load nhanh hơn (10.9 s vs 17.5 s), nhưng decode **chậm hơn 1.9x**: TPOT P50 127.5 ms vs 67.0 ms (7.8 vs 14.9 tok/s). Tôi chạy lại `llama-bench tg64` xen kẽ Q2/Q4 hai vòng (7.5-8.0 vs 13.2-13.4 tok/s, ~1.7x) để loại trừ việc laptop giảm xung theo thời gian: kết quả lặp lại, nên đây là thật.

Máy của tôi (i5-1130G7, 4 core, iGPU Iris Xe dùng chung RAM) là trường hợp *compute-limited*, không phải bandwidth-limited thuần: Q2_K dùng các block với nhiều phép giải nén (scale/min lồng nhau) hơn Q4, nên chi phí dequantize lớn hơn phần byte tiết kiệm được. Số liệu TTFT P95 (3362 / 8568 ms) bị kéo bởi request đầu tiên khi weights chưa nằm trong page cache; P50 (752 / 1226 ms) mới là giá trị điển hình.

Về chất lượng, tôi hỏi cùng 3 câu (giải thích decode/prefill, 17x24, one-liner Python) trên cả hai server (Q4 port 8080, Q2 port 8090, temperature 0). Cả hai trả lời đúng ý chính; Q2 diễn đạt hơi kém gọn, và ở câu 17x24 trình bày phép nhân cột khó theo dõi hơn Q4. Nhưng Q2 mất thêm ~65% thời gian cho mỗi câu (13-20 s vs 8-12 s), nên không có lý do dùng nó ở đây.
