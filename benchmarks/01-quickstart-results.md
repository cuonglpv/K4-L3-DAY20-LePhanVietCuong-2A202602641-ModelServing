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

**2-bit không đáng dùng trên cấu hình mặc định của máy này.** `UD-Q2_K_XL` nhỏ hơn 0.73 GB (2.24 vs 2.97 GB, ~25%) và load nhanh hơn (10.9 s vs 17.5 s), nhưng decode **chậm hơn 1.9x**: TPOT P50 127.5 ms vs 67.0 ms (7.8 vs 14.9 tok/s). Tôi chạy lại `llama-bench` xen kẽ hai bản để loại trừ việc laptop giảm xung: kết quả lặp lại.

Nguyên nhân tôi tìm ra sau đó: `make bench` chạy với `-ngl 99` nên decode nằm trên iGPU qua Vulkan, và kernel Vulkan của Q2_K chậm hơn Q4_K trên Iris Xe (Q2: 6.7-7.3 tok/s, Q4: 10.5-12.0). Chạy CPU-only (`-ngl 0`) thì chiều hướng đảo ngược: Q2 14.0 và 8.6 tok/s, Q4 6.3 và 9.3 (nhiễu lớn, nhưng trung bình Q2 nhanh hơn ~1.4x) - đúng như kỳ vọng "ít byte hơn thì decode nhanh hơn" khi decode bị giới hạn bởi băng thông. Vì vậy câu "Q2 chậm hơn" mô tả đường Vulkan/iGPU của máy tôi, không phải một sự thật chung về Q2_K; tôi chưa kiểm chứng được nguyên nhân bên trong kernel, chỉ kiểm chứng được sự đảo chiều giữa hai backend. TTFT P95 (3362 / 8568 ms) bị kéo bởi request đầu tiên khi weights chưa nằm trong page cache; P50 (752 / 1226 ms) mới là giá trị điển hình.

Về chất lượng, tôi hỏi cùng 3 câu (giải thích decode/prefill, 17x24, one-liner Python) trên cả hai server (Q4 port 8080, Q2 port 8090, temperature 0). Cả hai trả lời đúng ý chính; Q2 diễn đạt kém gọn hơn và trình bày phép nhân cột khó theo dõi hơn. Cộng với việc chậm hơn trên đường Vulkan, tôi chọn Q4.
