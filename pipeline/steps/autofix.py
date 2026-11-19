"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


#def fix(ds, issues, cfg):
    # TODO
    #raise NotImplementedError("autofix chưa làm")

"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.
(Giữ nguyên docstring gốc của stub nếu bạn muốn; phần dưới là code thực thi.)

Test:  pytest tests/test_autofix.py -q
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

# Nhóm mã lỗi theo cách sửa (khớp bảng trong docstring).
DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}   # xóa dòng
CLIP_CODE = "BOX_OUT_OF_IMAGE"                                            # cắt box
REMOVE_IMAGE_PREFIX = "DUP_IMAGE_"                                        # DUP_IMAGE_*
REMOVE_IMAGE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}           # xóa ảnh


def _is_remove_image(code):
    """True nếu mã lỗi này nghĩa là phải xóa cả ảnh (DUP_IMAGE_*, LEAK_TEST, ...)."""
    return code.startswith(REMOVE_IMAGE_PREFIX) or code in REMOVE_IMAGE_CODES


def _make_fix(image, line, action, before, after):
    """Một dòng log, đúng 5 khóa của 03_fixes.csv."""
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def _clip_line(raw):
    """Cắt box về trong [0,1].
    Trả (dòng_mới, None) nếu cắt được; (None, lý_do) nếu box hết diện tích hoặc dòng không đọc được."""
    try:
        cls_id, cx, cy, w, h = parse_yolo_line(raw)
    except ValueError as exc:
        return None, f"không đọc được dòng: {exc}"

    # Bốn mép của box, kẹp vào [0,1]
    left = max(0.0, cx - w / 2)
    right = min(1.0, cx + w / 2)
    top = max(0.0, cy - h / 2)
    bottom = min(1.0, cy + h / 2)

    new_w = right - left
    new_h = bottom - top
    if new_w <= 0 or new_h <= 0:
        return None, "box nằm hẳn ngoài ảnh sau khi cắt"

    # Tính lại tâm và kích thước từ các mép đã cắt, giữ nguyên lớp
    new_cx = (left + right) / 2
    new_cy = (top + bottom) / 2
    return f"{int(cls_id)} {new_cx:.6f} {new_cy:.6f} {new_w:.6f} {new_h:.6f}", None


def _remove_image(ds, stem):
    """Xóa ảnh và file nhãn của `stem` khỏi ds. Trả True nếu có xóa gì đó."""
    removed = False
    for img_path in ds.image_files():              # list Path, test dùng p.stem
        if img_path.stem == stem:
            img_path.unlink()
            removed = True
    label_path = ds.label_path(stem)
    if label_path.exists():
        label_path.unlink()
        removed = True
    return removed


def _rewrite_class_names(ds, cfg):
    """Ghi lại `names` trong data.yaml đúng cfg["classes"]. Trả (trước, sau) để ghi log."""
    # GIẢ ĐỊNH: đường dẫn data.yaml. Nếu Dataset có thuộc tính khác, sửa đúng dòng này.
    yaml_path = getattr(ds, "yaml_path", None) or (ds.root / "data.yaml")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    before = data.get("names")
    classes = list(cfg["classes"])
    # Giữ nguyên kiểu cũ: nếu names đang là dict {0: 'car'} thì ghi dict, không thì ghi list
    data["names"] = dict(enumerate(classes)) if isinstance(before, dict) else classes
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return before, data["names"]


def fix(ds, issues, cfg):
    fixes = []                                    # log trả về (= 03_fixes.csv)

    # --- BƯỚC 0: chỉ lấy lỗi ERROR (WARN là việc của người, không động tới) ---
    errors = [i for i in issues if i.severity == ERROR]

    # --- BƯỚC 1: xóa ảnh (làm TRƯỚC để biết ảnh nào đã mất) ----------------
    removed = set()                               # các ảnh đã bị xóa
    for issue in errors:
        if _is_remove_image(issue.code) and issue.image not in removed:
            if _remove_image(ds, issue.image):
                removed.add(issue.image)
                fixes.append(_make_fix(issue.image, None, "remove_image",
                                       f"{issue.code}: có ảnh + nhãn", "(đã xóa khỏi dataset)"))

    # --- BƯỚC 2: lỗi cấp dataset và ảnh thiếu nhãn --------------------------
    renamed = False
    missing_done = set()
    for issue in errors:
        if issue.code == "BAD_CLASS_NAME" and not renamed:
            before, after = _rewrite_class_names(ds, cfg)
            renamed = True
            fixes.append(_make_fix(issue.image, None, "rename_classes", str(before), str(after)))
        elif issue.code == "MISSING_LABEL_FILE" and issue.image not in removed \
                and issue.image not in missing_done:
            # KHÔNG tạo file nhãn (rỗng nghĩa là "ảnh nền", khác "chưa gán")
            missing_done.add(issue.image)
            fixes.append(_make_fix(issue.image, None, "needs_label",
                                   "(không có file)", "chuyển người gán"))

    # --- BƯỚC 3: gom lỗi theo dòng, theo từng ảnh ---------------------------
    # by_image[stem][line_gốc] = tập các mã lỗi của dòng đó
    by_image = defaultdict(lambda: defaultdict(set))
    for issue in errors:
        is_line_issue = issue.code in DROP_LINE_CODES or issue.code == CLIP_CODE
        if is_line_issue and issue.line is not None and issue.image not in removed:
            by_image[issue.image][issue.line].add(issue.code)

    # --- BƯỚC 4: mỗi file đọc một lần, quyết định từng dòng, ghi một lần ----
    for stem, line_codes in by_image.items():
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue                              # file không còn: bỏ qua êm

        text = label_path.read_text(encoding="utf-8")
        old_lines = text.splitlines()             # cùng cách đếm dòng với check
        new_lines = []
        changed = False

        for line_no, raw in enumerate(old_lines, start=1):   # số dòng GỐC, kể cả dòng trống
            codes = line_codes.get(line_no, set())

            if codes & DROP_LINE_CODES:           # có lỗi thuộc nhóm xóa: xóa, không clip
                fixes.append(_make_fix(stem, line_no, "drop_line", raw, "(đã xóa dòng)"))
                changed = True
            elif CLIP_CODE in codes:
                new_line, reason = _clip_line(raw)
                if new_line is None:              # hết diện tích: xóa thay vì ghi box rỗng
                    fixes.append(_make_fix(stem, line_no, "drop_line", raw, f"(đã xóa: {reason})"))
                else:
                    fixes.append(_make_fix(stem, line_no, "clip_box", raw, new_line))
                    new_lines.append(new_line)
                changed = True
            else:
                new_lines.append(raw)             # dòng không lỗi (kể cả dòng trống): giữ nguyên

        if changed:                               # chỉ ghi khi có thay đổi
            label_path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""),
                                  encoding="utf-8")

    return fixes