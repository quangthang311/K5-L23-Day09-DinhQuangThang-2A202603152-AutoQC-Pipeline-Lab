"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


#def run(ds, cfg, preds=None):
    # TODO
    #raise NotImplementedError("check second_opinion chưa làm")

"""CHECK — Ý kiến thứ hai từ yolo26l (dự đoán lưu sẵn). Chỉ CẢNH BÁO, không sửa gì.

Test:  pytest tests/test_second_opinion.py -q
(Giữ nguyên docstring gốc của stub nếu bạn muốn; phần dưới là code thực thi.)
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

CHECK_NAME = "second_opinion"


def _issue(image, code, message, line=None, extra=None):
    """Tạo Issue WARN. Chữ ký: Issue(check, severity, code, image, message, line, extra)."""
    return Issue(CHECK_NAME, WARN, code, image, message, line, extra or {})


def _labels_with_lines(ds, stem, num_classes):
    """Trả list (số_dòng_gốc, lớp, (cx, cy, w, h)) của các dòng nhãn HỢP LỆ.
    read_label_lines trả tuple, nên tách ra: phần là int = số dòng, phần là str = nội dung."""
    result = []
    for pos, item in enumerate(ds.read_label_lines(stem), start=1):
        line_no, text = pos, item
        if isinstance(item, (tuple, list)):
            ints = [x for x in item if isinstance(x, int) and not isinstance(x, bool)]
            strs = [x for x in item if isinstance(x, str)]
            if strs:
                text = strs[0]
                if ints:
                    line_no = ints[0]
        if not text.strip():
            continue                                    # dòng trống: bỏ qua, số dòng vẫn đúng
        try:
            cls_id, cx, cy, w, h = parse_yolo_line(text)
        except ValueError:
            continue                                    # dòng hỏng là việc của label_format
        if 0 <= cls_id < num_classes and w > 0 and h > 0:
            result.append((line_no, int(cls_id), (cx, cy, w, h)))
    return result


def run(ds, cfg, preds=None):
    # Không truyền preds (pipeline gọi run(ds, cfg)) thì lấy dự đoán yolo26l đã cache sẵn
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    # --- BƯỚC 0: ngưỡng từ config, không viết cứng ----------------------------
    so = cfg["second_opinion"]
    conf_min, min_area_px, fp_conf = so["conf"], so["min_area_px"], so["fp_conf"]
    iou_missing, iou_match, iou_loose = so["iou_missing"], so["iou_match"], so["iou_loose"]

    num_classes = len(ds.classes)
    issues = []

    # --- BƯỚC 1: duyệt ảnh theo ds.image_files() ------------------------------
    for img_path in ds.image_files():
        stem = img_path.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue                                    # không có dự đoán hoặc chưa có file nhãn

        labels = _labels_with_lines(ds, stem, num_classes)
        img_w, img_h = ds.image_size(stem)
        # mỗi dự đoán: [id_lớp, conf, cx, cy, w, h]
        all_preds = [(int(p[0]), float(p[1]), tuple(p[2:6])) for p in preds[stem]]

        # --- BƯỚC 2: với mỗi dự đoán đủ conf và đủ diện tích --------------------
        for pred_cls, conf, pbox in all_preds:
            if conf < conf_min:
                continue
            if (pbox[2] * img_w) * (pbox[3] * img_h) < min_area_px:
                continue

            # cands: nhãn MỌI lớp có IoU >= iou_missing -> (iou, lớp)
            cands = []
            for _line, lab_cls, lbox in labels:
                iou = iou_xywh(pbox, lbox)
                if iou >= iou_missing:
                    cands.append((iou, lab_cls))

            if not cands:                               # (1) model thấy, nhãn không có
                issues.append(_issue(stem, "POSSIBLE_MISSING",
                                     f"model thấy lớp {pred_cls} (conf {conf:.2f}) nhưng không có nhãn",
                                     extra={"conf": conf}))
                continue

            same = [c for c in cands if c[1] == pred_cls]
            if same:                                    # (2) có nhãn cùng lớp
                best_iou = max(c[0] for c in same)
                if best_iou < iou_loose:
                    issues.append(_issue(stem, "POSSIBLE_LOOSE_BOX",
                                         f"box lỏng: IoU {best_iou:.2f} < {iou_loose}",
                                         extra={"conf": conf, "iou": best_iou}))
                continue                                # IoU đủ tốt: không cờ

            best_iou, best_cls = max(cands)             # (3) chỉ có nhãn khác lớp
            if best_iou >= iou_match:
                issues.append(_issue(stem, "POSSIBLE_WRONG_CLASS",
                                     f"nhãn lớp {best_cls} nhưng model thấy lớp {pred_cls} "
                                     f"(IoU {best_iou:.2f})",
                                     extra={"conf": conf, "iou": best_iou}))
            # còn lại: mơ hồ, không cờ

        # --- BƯỚC 3: FALSE_POS, dùng conf >= fp_conf, KHÔNG lọc diện tích -------
        support = [box for _c, conf, box in all_preds if conf >= fp_conf]
        for line_no, lab_cls, lbox in labels:
            if all(iou_xywh(lbox, pbox) < iou_missing for pbox in support):
                issues.append(_issue(stem, "POSSIBLE_FALSE_POS",
                                     f"nhãn lớp {lab_cls} không khớp dự đoán nào (conf >= {fp_conf})",
                                     line=line_no, extra={"conf": fp_conf}))

    return issues