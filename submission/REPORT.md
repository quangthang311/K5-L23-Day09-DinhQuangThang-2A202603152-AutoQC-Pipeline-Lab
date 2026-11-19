# Báo cáo Day 09 — Đinh Quang Thắng, 2A202603152

## 1. Kết luận trước
Pipeline kết luận **Release**: quét 224 ảnh từ `01_intake.txt`, loại 31 dòng/ảnh lỗi ở Bước 1 và xuất 193 ảnh vào `clean_v1` theo `08_summary.json`. Sau vòng duyệt 80 ảnh, còn 0 lỗi bắt buộc; 11/193 ảnh (5.70%) còn cảnh báo, thấp hơn ngưỡng Hold 10%. Lý do chính: không còn `MISSING_LABEL_FILE`; các cảnh báo còn lại chỉ là cảnh báo và đã được rà qua ngân sách 80 ảnh.

## 2. Lỗi và phân việc
| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE`, `BAD_SIZE` | 2 + 3 dòng | Máy | Bước nhận loại ảnh không mở được hoặc cạnh ngắn dưới 250 px. |
| `DUP_IMAGE_EXACT`, `DUP_IMAGE_NEAR`, `LEAK_TEST` | 8 + 7 + 11 dòng | Máy | Loại trùng từng byte, trùng gần hoặc trùng với tập test/val để tránh rò rỉ và trùng dữ liệu. |
| `MISSING_LABEL_FILE` | 6 dòng | Người | Không có file nhãn để máy bịa nhãn; autofix ghi `NEEDS_LABEL`, người gán nhãn. |
| `BAD_FORMAT`, `BAD_CLASS_ID`, `BOX_ZERO`, `BOX_OUT_OF_IMAGE`, `DUP_BOX` | 3 + 6 + 4 + 8 + 7 dòng | Máy | Tự bỏ dòng/chuyển box/clip box bằng `03_fixes.csv`; đây là lỗi định dạng có quy tắc xác định. |
| `BAD_CLASS_NAME` | 2 dòng | Máy | Đổi tên `Person→person`, `Bus→bus` trong `data.yaml`. |
| `EMPTY_LABEL`, `BOX_TINY`, `BOX_HUGE`, `CLASS_RARE` | 11 + 6 + 3 + 4 dòng | Người | Có thể là ảnh nền, box nhỏ/lớn, hoặc lệch phân bố lớp; cần mắt người xác nhận/ngữ nghĩa. |
| `POSSIBLE_MISSING`, `POSSIBLE_WRONG_CLASS`, `POSSIBLE_LOOSE_BOX`, `POSSIBLE_FALSE_POS` | 32 + 13 + 11 + 24 dòng | Người | Cả hai tầng model–nhãn đều có thể sai; đưa vào hàng đợi để mắt người quyết định. |

Hàng đợi `05_review_queue.csv` được xếp theo điểm ưu tiên cộng dồn: `NEEDS_LABEL` = 10, nhầm lớp = 3, thiếu nhãn = 2, thừa box = 2, box lỏng = 1.5, lỗi định dạng đã sửa = 2/1, rồi mới các cảnh báo nhẹ như `BOX_TINY` 0.3 và `BOX_HUGE` 0.5. Với 80 ảnh, hàng đầu gồm 80 ảnh/80 dòng; trong 80 dòng đó có 69 ảnh chứa ít nhất một lỗi ngữ nghĩa `POSSIBLE_*`: 32 thiếu nhãn, 13 nhầm lớp, 11 box lỏng và 22 thừa box ở vòng trước người duyệt. Các con số về loại cảnh báo chồng lấn nên số ảnh 69 không bằng tổng số mã.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 16 | DUP_IMAGE_NEAR: 1.00 / 0.50 → 1.00 / 0.83 | Ngưỡng 16 tăng recall từ 3/6 lên 5/6 nhãn trùng gần, còn precision giữ 1.00; tránh hạ recall như ngưỡng 20 (exact recall còn 0.33). |
| `second_opinion.conf` | 0.25 | 0.80 | WRONG_CLASS: 0.56 / 0.83 → 1.00 / 0.83; MISSING: 0.50 / 1.00 → 0.67 / 0.75; LOOSE_BOX: 0.29 / 0.40 → 0.50 / 0.20; FALSE_POS: 0.36 / 1.00 → 0.36 / 1.00 | Ngưỡng 0.80 nằm trong cấu hình xuất `clean_v1`; nó loại được nhiều cảnh báo giả cho WRONG_CLASS (precision tăng 0.56→1.00) và giữ recall nhầm lớp 0.83, nhưng recall MISSING giảm 1.00→0.75 và recall LOOSE_BOX giảm 0.40→0.20. Đây là đánh đổi thiên về ít cảnh báo nhiễu, giữ ngưỡng thấp cho FALSE_POS và để người duyệt xử lý phần rủi ro còn lại. |

Calibration có thể đánh lừa ở **ngưỡng pHash**: sweep ghi DUP_IMAGE_NEAR precision 1.00 và recall 0.83 tại ngưỡng 16, nhưng mẫu kiểm tra có thể làm precision lệch thực tế. Cụ thể, `img_0011` được ghép với `img_0008` ở khoảng cách pHash 16; khi mở hai ảnh, `img_0008` là trượt tuyết còn `img_0011` là quần vợt, nên đây là cặp không trùng dù chỉ số pHash hợp. Do đó recall cải thiện không nhất thiết đồng nghĩa mọi cặp ở ngưỡng 16 đều hợp lệ. Bước 1 quét 224 ảnh và ghi 26 dòng lỗi trùng lặp + 5 ảnh lỗi hình ảnh (BAD_SIZE/CORRUPT), còn 193 ảnh trong quyết định; số loại khoảng 31 dòng là phù hợp để kiểm tra, nhưng cần xem thị giác vì pHash không hoàn hảo.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) Với `--budget 0`, không có người duyệt xử lý 6 ảnh `MISSING_LABEL_FILE`; nhánh gate phải kết luận **Rework**, mã thoát **20** và **không xuất** dataset. Đây được `04_error_list_v2.txt` minh họa bằng 6 lỗi MISSING_LABEL_FILE còn nguyên ở vòng 2; `07_error_list_v3.txt` và `08_summary.json` minh họa nhánh ngược lại sau khi duyệt 80 ảnh thì mới Release và xuất 193 ảnh.

(b) Ba điểm mù tự quan sát trên `work/viz/`:

1. `img_0001.png`: box lớn bao trọn người mặc suit ở bên trái nhưng kéo dài quá sang phải và bao cả nền/cửa; đây là box lỏng, chưa bám sát vật thể.
2. `img_0001.png`: hai biển báo “Emergency Operation” ở tường bị giữ lại như vùng có vật thể/box; nếu đây là box của lớp Person thì là phát hiện nhầm lớp/vật thể không phải người.
3. `img_0030.png`: có nhiều box chồng lấn ở cụm người phía giữa sân, khiến một người có thể được gán nhiều box trùng nhau; ngoài ra box tràn nhẹ ra mép phải sát người chơi áo xanh là vị trí không khớp chính xác.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
| biến thể | #ảnh train | model | epoch | seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) | precision | recall |
|---|---:|---|---:|---|---|---|---|---|
| raw | 224 | `yolo26n.pt` | 20 | 0, 1 | 0.726 ± 0.000 (làm tròn 0.0002) | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 193 | `yolo26n.pt` | 20 | 0, 1 | 0.733 ± 0.002 | 0.514 ± 0.007 | 0.758 ± 0.011 | 0.653 ± 0.006 |

Chênh mAP50 clean − raw là **+0.007**. Mức chênh này lớn hơn độ lệch giữa seed của raw (0.0002) và clean (0.0023), nên hai seed cho thấy clean cao hơn nhưng đây vẫn chưa đủ để kết luận cải thiện bền vững; với chỉ 2 seed, độ trượt seed và kích thước tập test nhỏ cần được xem là nguồn nhiễu.

- Giả thuyết 1: tập raw có ảnh trùng/rò rỉ test (11 `LEAK_TEST` và 15 trùng exact/near) có thể làm metric không độc lập hoặc bơm hiệu quả train. Cách kiểm: loại chặt duplicate và leak, kiểm tra test độc lập bằng ID ảnh rồi chạy ≥5 seed.
- Giả thuyết 2: clean vẫn còn nhãn máy/cảnh báo chưa được xác nhận và 31 ảnh bị loại làm mẫu train giảm mạnh 224→193. Cách kiểm: chỉ giữ `clean` đã con người gán lại và duyệt 11 ảnh cảnh báo còn lại; chạy ablation thêm/dừng từng lớp lỗi.
- Giả thuyết 3: test chỉ có 100 ảnh (`data/test/images`) nên chênh 0.007 dễ nằm trong nhiễu lấy mẫu. Cách kiểm: báo bootstrap 95% CI cho mAP50, repeated split và bổ sung ảnh gold/test độc lập.

Kết luận: raw và clean chênh mAP50 +0.007 theo trung bình 2 seed, nhưng không kết luận đây là cải thiện có ý nghĩa thực chất trước khi có CI, ≥5 seed và test phân phối độc lập.

## 6. Quyết định và ghi chú AI
(a) Quyết định cuối: **Release**. Không còn lỗi bắt buộc trong v3; 11/193 ảnh còn cảnh báo (5.70%) dưới ngưỡng Hold 10%; 80 ảnh đã được người duyệt mô phỏng. Tiếp tục xuất hiện 193 ảnh trong `submission/export/clean_v1`.

(b) Đã dùng AI để viết code cho 4 module (đã được GV/LabCoach cho phép). Có dùng AI để giúp lấy dữ liệu từ Terminal và các file để so sánh với dữ liệu trong báo cáo để đảm bảo cách chính xác.
