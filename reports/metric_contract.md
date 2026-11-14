# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage |
| Primary metric (tên đúng như evaluator in ra) | `Defect Recall@B` |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | số ảnh lỗi (`is_defect = 1`) nằm trong top-B của `ranked_review.csv` / tổng số ảnh lỗi trong split eval (20) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | ghép theo `image_id` |
| Candidate pool cố định | 40 ảnh split `eval` trong `fixtures/t02_raw_qc/images.csv` (24 cảnh, chia theo cảnh do đề cung cấp) |
| Review budget B / K | B = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Ngưỡng cố định trong `src/pipeline.py::FEATURE_PARAMS`, chọn tay từ phân bố đặc trưng. **Lưu ý:** khi phân tích, nhóm đã xem phân bố đặc trưng của cả dev và eval → số trên eval cần xác nhận lại trên heldout mới. |
| Eval split (không dùng để tune) | `eval` (40 ảnh, 20 lỗi) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | miss = ảnh lỗi nằm ngoài top-B; false alarm = ảnh sạch lọt top-B (báo theo slice `light`) |
| Slices sẽ báo cáo (≥2) | `light` ∈ {day, dusk, night}; `defect_type` ∈ {blur, compression, dark, glare} |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson 95% CI cho Recall@20 (N = 20 ảnh lỗi) |
| Ngày giờ chốt + người chốt | 2026-11-14 · QC Lead (Data Track) |

**Ground truth:** repo học viên không có `fixtures/t02_raw_qc/gt/`. Nhóm tự gán nhãn bằng mắt cho 96 ảnh
(`reports/manual_audit_labels.csv`, cùng schema với `gt/labels.csv`: `defect_type, severity, is_defect, light, split`)
và chấm bằng evaluator chuẩn: `python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv ...`.
Khi có overlay `gt/` của giảng viên, chạy lại `make eval-baseline eval-poc compare TRACK=t02` để có số chính thức.
