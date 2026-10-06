# Bonus - GPU offload sweep

Host `Windows-AMD64` · backend(s) `vulkan` ·
llama.cpp `b10488` · `threads=4` · metric `tg128`

| -ngl | tg128 (tok/s) | vs -ngl 0 | vs best |
|:--|--:|--:|--:|
| 0 | 7.8 | 1.00x | 72% |
| 8 | 8.3 | 1.06x | 77% |
| 16 | 8.4 | 1.08x | 78% |
| 24 | 8.6 | 1.10x | 80% |
| 32 | 8.9 | 1.14x | 82% |
| 99 | 10.8 | 1.39x | 100% |

Best: `-ngl 99` at 10.8 tok/s
-- 1.39x faster than CPU-only.

Where the curve flattens tells you the model ran out of layers to move. Where it
*peaks below* full offload tells you something did not fit and the accelerator
started paying to fetch weights it could not hold.

## Your finding

**Full offload (`-ngl 99`) là tốt nhất, nhưng chỉ nhanh hơn CPU-only khoảng 1.2x, và đo rất nhiễu.** Lần sweep này cho 1.39x (7.8 -> 10.8 tok/s). Tôi lặp lại `llama-bench` xen kẽ: `-ngl 0` cho 6.3-10.6 tok/s (median 8.9 trên 10 lần), `-ngl 99` cho 10.4-12.4 (median 10.8 trên 6 lần), tức ~1.21x. Độ lệch giữa các lần chạy cùng cấu hình lên tới 25%, nên tôi chỉ tin hướng và bậc độ lớn, không tin con số thập phân.

Đường cong tăng đều theo số layer offload (8 -> 32: 8.3 -> 8.9, rồi nhảy lên 10.8 ở 99) chứ không có đỉnh ở giá trị riêng: không có gì "hết chỗ". iGPU Iris Xe dùng chung RAM hệ thống (UMA), nên offload không phải copy weights qua PCIe và cũng không có VRAM riêng để hết; cả hai bên cùng đọc một bus bộ nhớ, đó là lý do lợi ích chỉ vừa phải.

Hệ quả quan trọng cho phần base: `make tune` và `make bench` chạy với `-ngl 99`, tức decode nằm trên iGPU. Điều này giải thích hai kết quả tưởng "lạ" của tôi: đường cong thread phẳng (CPU gần như không phải bên tính toán), và Q2_K chậm hơn Q4_K (kernel Vulkan của Q2_K trên iGPU, xem `benchmarks/01-quickstart-results.md`). Kiểm chứng ở CPU-only (`-ngl 0`, Q4, `tg48`): 1 thread 3.9 tok/s, 2 thread 7.1, 4 thread 8.7, 8 thread 8.6 - đúng dạng knee tại 4 core vật lý rồi đi ngang; thread logic thứ hai không thêm gì vì chia sẻ ALU/cache và băng thông của cùng core.
