# 01 - Tune: thread-count sweep

Model `gemma-4-E2B-it-UD-Q4_K_XL.gguf` · host `Windows-AMD64` · llama.cpp `b10488`
CPU: **4 physical · 8 logical** cores · `ngl=99` · metric `tg128`

| threads (-t) | tg128 (tok/s) | vs best |
|:--|--:|--:|
| 1 | 11.7 | 92% |
| 2 | 12.2 | 96% |
| 4 | 12.2 | 97% |
| 8 | 11.7 | 92% |
| 16 | 12.7 | 100% |

**Best**: `-t 16` at 12.7 tok/s
**Slowest tested**: `-t 1` at 11.7 tok/s (1.09x spread)
**Against the physical-core default** (`-t 4`, 12.2 tok/s): 1.04x

Use this in your run:

```bash
LAB_N_THREADS=16 make bench
```

## Your explanation

**Đường cong phẳng, không có knee, vì sweep này chạy với `-ngl 99`: decode nằm trên iGPU, CPU thread gần như không phải bên tính toán.** 1 thread đạt 11.7 tok/s (92% best), 4 thread 12.2, 16 thread 12.7; toàn dải chỉ chênh 1.09x và nằm trong nhiễu đo (các lần chạy lặp cùng cấu hình dao động tới ~25%). So với mặc định `-t 4`, thread "tốt nhất" (16) chỉ hơn 1.04x - không phải cải thiện thật.

Đây là hiệu chỉnh so với nhận định ban đầu của tôi ("băng thông bão hoà từ 1 thread"), vốn sai: tôi chỉ nhìn đường cong ở `-ngl 99`. Kiểm chứng bằng cách chạy lại sweep ở CPU-only (`llama-bench -ngl 0`, Q4, `tg48`, 2 lần mỗi điểm):

| threads | 1 | 2 | 4 | 8 |
|:--|--:|--:|--:|--:|
| tok/s (-ngl 0) | 3.9 | 7.1 | 8.7 | 8.6 |

Ở CPU-only đường cong có hình mong đợi: gần tuyến tính tới 2 thread, còn tăng nhẹ tới **4 = số core vật lý (knee)** rồi đi ngang ở 8 thread (logical). Thread thứ hai trên cùng một core chia sẻ ALU, cache L1/L2 và cổng bộ nhớ với thread thứ nhất nên không thêm công việc hữu ích; decode đọc lại toàn bộ weights mỗi token, nên khi vài core đã lấp đầy băng thông RAM thì thêm thread chỉ tăng tranh chấp. Tóm lại: trên máy này `-t` chỉ có ý nghĩa khi decode chạy trên CPU; ở cấu hình mặc định của lab (`-ngl 99`) nó không phải knob đáng tune, và knob thật là có offload lên iGPU hay không (xem `bonus-gpu-offload-sweep.md`).
