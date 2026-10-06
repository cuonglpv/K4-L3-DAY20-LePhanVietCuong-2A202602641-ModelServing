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

**Không có knee rõ ràng: đường cong gần như phẳng ngay từ 1 thread.** 1 thread đạt 11.7 tok/s (92% của best), 2 và 4 thread 12.2, 8 thread 11.7, 16 thread (oversubscribe 2x logical) 12.7. Chênh lệch toàn bộ chỉ 1.09x và nằm trong nhiễu đo (mỗi điểm chỉ chạy 2 lần). So với mặc định physical-core (`-t 4`), thread "tốt nhất" (16) chỉ hơn 1.04x - tôi không coi đây là cải thiện thật.

Lý do: decode đọc lại toàn bộ weights đang hoạt động cho mỗi token, nên tốc độ bị chặn bởi băng thông bộ nhớ chứ không phải số core. Máy này có RAM dùng chung giữa CPU và iGPU (UMA); một thread đã kéo gần hết băng thông khả dụng, thêm thread chỉ thêm tranh chấp, không thêm byte/giây. Một đối chứng cho thấy điều này: `llama-bench` với `-ngl 0` (14.1 tok/s) và `-ngl 99` (13.7 tok/s) gần như bằng nhau, tức đổi bên tính toán không đổi tốc độ - điểm nghẽn là bộ nhớ dùng chung. Hệ quả: trên máy này `-t` không phải knob đáng tune; thay đổi có tác dụng thật nằm ở chỗ khác (xem REFLECTION §5).
