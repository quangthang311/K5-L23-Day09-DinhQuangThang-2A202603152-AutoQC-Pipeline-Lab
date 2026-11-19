"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


#def decide(issues, image_stems, cfg, reviewed=frozenset()):
    # TODO
    #raise NotImplementedError("gate chưa làm")

"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.
(Giữ nguyên docstring gốc của stub nếu bạn muốn; phần dưới là code thực thi.)

Test:  pytest tests/test_gate.py -q
"""
from ..common import ERROR, WARN  # noqa: F401

# Sai số cho phép khi so sánh số thực (để 2/20 so với 0.10 không bị lệch do làm tròn nhị phân).
# Đây là hằng kỹ thuật, KHÔNG phải ngưỡng nghiệp vụ; ngưỡng nghiệp vụ lấy từ cfg.
_FLOAT_EPS = 1e-9


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    # --- BƯỚC 0: đọc ngưỡng từ config (KHÔNG viết cứng 0.10) ---------------
    warn_ratio_hold = cfg["gate"]["warn_ratio_hold"]

    # --- BƯỚC 1: chuẩn bị dữ liệu -------------------------------------------
    stems = set(image_stems)       # tập ảnh thật của lô; set để tra nhanh và không đếm trùng
    reviewed = set(reviewed)       # tập ảnh người đã xem
    n_images = len(stems)          # MẪU SỐ: số ảnh (không phải số issue)

    # --- BƯỚC 2: đếm lỗi bắt buộc -------------------------------------------
    # Đếm TẤT CẢ issue ERROR, không lọc theo stems và không bỏ qua reviewed:
    # lỗi bắt buộc không bao giờ được che.
    n_errors = sum(1 for i in issues if i.severity == ERROR)

    # --- BƯỚC 3: tìm các ảnh còn cảnh báo ------------------------------------
    # Điều kiện để một issue được tính:
    #   (a) là WARN, (b) ảnh nằm trong stems (bỏ <dataset>, data.yaml, ảnh đã xóa),
    #   (c) ảnh chưa được người duyệt.
    # Dùng set để một ảnh nhiều cảnh báo vẫn chỉ tính 1 lần.
    warn_images = {
        i.image
        for i in issues
        if i.severity == WARN and i.image in stems and i.image not in reviewed
    }
    n_warn_images = len(warn_images)

    # --- BƯỚC 4: tính tỉ lệ cảnh báo, tránh chia cho 0 -----------------------
    ratio = (n_warn_images / n_images) if n_images > 0 else 0.0

    # --- BƯỚC 5: áp cây quyết định Day 07 ------------------------------------
    reasons = []
    if n_errors >= 1:
        decision = "Rework"
        reasons.append(
            f"Còn {n_errors} lỗi bắt buộc (ERROR) chưa sửa được: lỗi bắt buộc chặn pipeline, "
            f"người duyệt không thể bỏ qua."
        )
    elif ratio + _FLOAT_EPS >= warn_ratio_hold:
        decision = "Hold"
        reasons.append(
            f"Không còn lỗi bắt buộc, nhưng {n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({ratio:.2%}) >= ngưỡng Hold {warn_ratio_hold:.0%}."
        )
    else:
        decision = "Release"
        reasons.append(
            f"Không còn lỗi bắt buộc; {n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({ratio:.2%}) < ngưỡng Hold {warn_ratio_hold:.0%}."
        )

    if reviewed:
        reasons.append(f"Người đã duyệt {len(reviewed)} ảnh; cảnh báo của các ảnh này không tính vào tỉ lệ.")

    # --- BƯỚC 6: trả kết quả đúng cấu trúc docstring ---------------------------
    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": round(ratio, 4),
        "reasons": reasons,
    }
