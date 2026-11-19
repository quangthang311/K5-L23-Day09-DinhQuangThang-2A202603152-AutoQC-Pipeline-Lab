"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


#def run(ds, cfg):
    # TODO: duyệt từng file nhãn, từng dòng
    #raise NotImplementedError("check label_format chưa làm")

"""
(Giữ nguyên docstring gốc của stub nếu bạn muốn; phần dưới là code thực thi.)
"""
import math

from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


# ---------------------------------------------------------------------------
# HÀM PHỤ 1: tạo một Issue.
# Gom việc tạo Issue vào MỘT chỗ để nếu chữ ký của Issue trong common.py khác
# với mình đoán, bạn chỉ phải sửa đúng hàm này.
# ---------------------------------------------------------------------------
def _issue(image, line, code, severity, message, extra=None):
    return Issue(
        check="label_format",  # tên check, trường bắt buộc mà lần trước mình thiếu
        image=image,           # tên ảnh (stem), ví dụ "a"
        line=line,             # số dòng trong file nhãn, đếm từ 1
        code=code,             # mã lỗi, ví dụ "BAD_FORMAT"
        severity=severity,     # ERROR hoặc WARN
        message=message,       # lý do bằng lời cho người đọc
        extra=extra or {},     # dữ liệu thêm, ví dụ {"overflow": 0.05}
    )

# ---------------------------------------------------------------------------
# HÀM PHỤ 2: liệt kê các file nhãn (.txt) trong thư mục nhãn.
# Dùng suffix.lower() để nhận cả ".TXT" viết hoa. Chỉ ĐỌC, không sửa gì.
# ---------------------------------------------------------------------------
def _label_files(ds):
    files = []
    for path in sorted(ds.labels_dir.iterdir()):
        if path.is_file() and path.suffix.lower() == ".txt" and path.stem.lower() != "classes":
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# HÀM PHỤ 3: lấy kích thước ảnh (rộng, cao) bằng pixel.
# Trả None nếu không lấy được, khi đó ta bỏ qua kiểm BOX_TINY (cần pixel).
# Chỉ bắt đúng các lỗi "không có dữ liệu ảnh", không nuốt lỗi lạ.
# ---------------------------------------------------------------------------
def _image_size(ds, stem):
    try:
        return ds.image_size(stem)          # kỳ vọng (width_px, height_px)
    except (KeyError, FileNotFoundError, OSError):
        return None

# ds (dataset) , stem là tên file không có đuôi
# ---------------------------------------------------------------------------
# HÀM CHÍNH
# ---------------------------------------------------------------------------
# cfg (config) : cfg là cấu hình của pipeline

def run(ds, cfg):
    # --- BƯỚC 0: đọc ngưỡng từ config (KHÔNG viết cứng số vào code) ---------
    lf_cfg = cfg["label_format"]
    overflow_tol = lf_cfg["overflow_tol"]    # sai số tràn cho phép (vd 0.001)
    dup_iou = lf_cfg["dup_box_iou"]          # IoU trên mức này = box lặp
    min_box_px = lf_cfg["min_box_px"]        # cạnh ngắn (px) dưới mức này = box quá nhỏ
    max_box_frac = lf_cfg["max_box_frac"]    # w*h trên mức này = box quá to

    num_classes = len(ds.classes)            # id hợp lệ: 0 .. num_classes-1
    issues = []                              # danh sách kết quả trả về

    # --- BƯỚC 1: duyệt từng file nhãn --------------------------------------
    for label_path in _label_files(ds):
        stem = label_path.stem               # tên ảnh tương ứng, vd "a"
        size = _image_size(ds, stem)         # (W, H) px hoặc None

        # Các box HỢP LỆ đã gặp trong file này, dùng để dò box lặp.
        # Mỗi phần tử: (class_id, (cx, cy, w, h))
        seen_boxes = []

        text = label_path.read_text(encoding="utf-8", errors="replace")

        # --- BƯỚC 2: duyệt từng dòng, đếm từ 1, KỂ CẢ dòng trống ------------
        for line_no, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue                     # dòng trống: bỏ qua, số dòng vẫn tăng

            # --- BƯỚC 3: kiểm định dạng (5 cột số) --------------------------
            try:
                parsed = parse_yolo_line(raw)
                cls_id = int(parsed[0])
                cx, cy, w, h = (float(v) for v in parsed[1:5])
                if not all(math.isfinite(v) for v in (cx, cy, w, h)):
                    raise ValueError("giá trị nan/inf")
            except (ValueError, IndexError, TypeError) as exc:
                issues.append(_issue(stem, line_no, "BAD_FORMAT", ERROR,
                                     f"dòng không đúng 5 cột số: {raw!r} ({exc})"))
                continue                     # dòng hỏng: không kiểm tiếp

            # --- BƯỚC 4: kiểm id lớp và box rỗng (có thể dính cả hai) -------
            line_is_broken = False

            if cls_id < 0 or cls_id >= num_classes:
                issues.append(_issue(stem, line_no, "BAD_CLASS_ID", ERROR,
                                     f"id lớp {cls_id} ngoài 0..{num_classes - 1}"))
                line_is_broken = True

            if w <= 0 or h <= 0:
                issues.append(_issue(stem, line_no, "BOX_ZERO", ERROR,
                                     f"box rỗng: w={w}, h={h}"))
                line_is_broken = True

            if line_is_broken:
                continue                     # không kiểm hình học dòng này

            box = (cx, cy, w, h)

            # --- BƯỚC 5: box tràn ảnh --------------------------------------
            # Với mỗi mép, đo "mức tràn" (dương = ra ngoài ảnh):
            left = cx - w / 2                # mép trái, tràn nếu < 0
            right = cx + w / 2               # mép phải, tràn nếu > 1
            top = cy - h / 2                 # mép trên, tràn nếu < 0
            bottom = cy + h / 2              # mép dưới, tràn nếu > 1
            overflow = max(-left, right - 1.0, -top, bottom - 1.0)

            if overflow > overflow_tol:
                issues.append(_issue(stem, line_no, "BOX_OUT_OF_IMAGE", ERROR,
                                     f"box tràn ảnh {overflow:.4f} (tolerance {overflow_tol})",
                                     extra={"overflow": overflow}))

            # --- BƯỚC 6: box lặp (cùng lớp, IoU cao với dòng TRƯỚC) --------
            for prev_cls, prev_box in seen_boxes:
                if prev_cls == cls_id and iou_xywh(prev_box, box) > dup_iou:
                    issues.append(_issue(stem, line_no, "DUP_BOX", ERROR,
                                         f"trùng box ở dòng trước (cùng lớp {cls_id}, IoU > {dup_iou})"))
                    break                    # báo một lần cho dòng này là đủ
            seen_boxes.append((cls_id, box))

            # --- BƯỚC 7: box quá nhỏ (WARN), cần kích thước ảnh -------------
            if size is not None:
                img_w, img_h = size
                short_side_px = min(w * img_w, h * img_h)   # cạnh ngắn, px
                if short_side_px < min_box_px:
                    issues.append(_issue(stem, line_no, "BOX_TINY", WARN,
                                         f"cạnh ngắn {short_side_px:.1f}px < {min_box_px}px"))

            # --- BƯỚC 8: box quá to (WARN) ----------------------------------
            if w * h > max_box_frac:
                issues.append(_issue(stem, line_no, "BOX_HUGE", WARN,
                                     f"box chiếm {w * h:.2f} diện tích ảnh > {max_box_frac}"))

    return issues
