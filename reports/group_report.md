# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Mọi con số lấy từ file do script sinh ra (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`).
> Ground truth dùng để chấm là nhãn audit nhóm tự gán (`reports/manual_audit_labels.csv`) vì repo học viên không có `gt/`.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G06 |
| Challenge | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Thành viên (4) + vai trò | 1. Hà Huy Dũng – 2A202603271 – `hdung25` (Lead/Integrator, Core algorithm) · 2. Trần Nguyễn Hữu Phúc – 2A202603303 – `hhuuphucc` (Data, provenance & GT audit) · 3. Triệu Hoàng Hiếu – 2A202603294 – `hieuwewe123` (QA / metric / tests) · 4. Phạm Minh Quân – 2A202603307 – `phamminhquan1101` (Human review, demo & report) |
| Git URL | https://github.com/hdung25/K5-Day6-L2-Cloud-DataGovernanceAndPrivacy |
| Demo | https://t02-raw-qc-demo.vercel.app · slide: https://t02-raw-qc-demo.vercel.app/slides.html |
| Colab | https://colab.research.google.com/github/hdung25/K5-Day6-L2-Cloud-DataGovernanceAndPrivacy/blob/main/demo/T02_raw_qc_colab.ipynb |
| Tag `demo-180m` (commit) | `07c89f6` (`make tag-demo`) |
| Tag `final-24h` (commit) | commit cập nhật report này — xem `git rev-parse final-24h` (`make tag-final`) |
| Deadline (giờ VN) | 15/11/2026 (24h sau buổi lab 14/11/2026) |

## 01 · Problem statement

- **Ai bị ảnh hưởng:** đội huấn luyện model (ảnh lỗi lọt vào train làm model học sai) và đội thu dữ liệu thực địa (chụp lại tốn chi phí). Hệ thống sai → hoặc lãng phí lượt review, hoặc ảnh lỗi lọt vào release.
- **Điểm nghẽn:** người kiểm duyệt chỉ xem được B = 20 ảnh mỗi lượt; xem hết cả lô là không khả thi.
- **Đầu vào → đầu ra:** thư mục ảnh + `images.csv` (camera, điều kiện sáng, split; không có nhãn lỗi) → `ranked_review.csv` (điểm nghi lỗi, loại lỗi dự đoán, KEEP/RECAPTURE), `review_queue.csv` top-20, `contact_sheet.html`, `decision.json`.
- **Tiêu chí GO / HOLD / REWORK** (`src/pipeline.py::decide`): tỉ lệ ảnh RECAPTURE ≤ 10% → GO · ≤ 60% → HOLD (chụp lại các ảnh RECAPTURE rồi chạy QC lại) · > 60% → REWORK (lô không dùng được).
- **Giả định cần domain owner xác nhận:** 4 loại lỗi (blur / compression / dark / glare) là đủ; ảnh đêm tối tự nhiên là hợp lệ; độ phân giải 320×180 đại diện cho ảnh thực địa.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 ảnh (14 cảnh; 28 lỗi) | `fixtures/t02_raw_qc/` — `synthetic:tools/make_fixtures.py (seed 42)` | CC0-1.0 | có |
| eval | 40 ảnh (10 cảnh; 20 lỗi) | như trên | CC0-1.0 | có |

- **Schema:** `images.csv` = `image_id, path, camera_id ∈ {cam_A, cam_B}, light ∈ {day, dusk, night}, split`. Nhãn audit: `defect_type ∈ {none, blur, compression, dark, glare}, severity, is_defect`.
- **Seed:** 42 · **Chia split:** theo cảnh gốc (đề cung cấp; 4 biến thể của một cảnh luôn chung split) → tránh leakage. Eval có nhiều ảnh đêm (16/40) hơn dev (4/56).
- **`manifest.csv` verified (sha256):** có — `load()` gọi `verify_manifest` với `strict_provenance: true`.
- **Ground truth:** nhóm xem từng ảnh và gán nhãn bằng mắt (96 ảnh: 48 sạch, 48 lỗi = 18 compression, 12 blur, 10 dark, 8 glare). Pipeline **không** đọc file nhãn (GT guard).

## 03 · Research & design

- **Kỹ thuật & lý do:**
  - *Variance of Laplacian* làm độ đo độ nét (Pech-Pacheco et al., ICPR 2000) — nhưng dùng thang log và ngưỡng thấp để không phạt camera quang học mềm.
  - *Blockiness* đo chênh lệch gradient tại biên khối 8×8 so với bên trong khối (ý tưởng no-reference JPEG quality, Wang, Sheikh & Bovik, ICIP 2002) — bắt vỡ nén mà độ nét không thấy.
  - Chuẩn hoá độ sáng theo điều kiện chụp (gợi ý trong đề: "chuẩn hoá theo light/camera_id"; ACDC dataset — ảnh xấu thời tiết/ban đêm là domain hợp lệ, không phải lỗi).
- **Data flow:** `load` (sha256 manifest) → `process` (4 đặc trưng / ảnh → 4 điểm 0–1 → max) → `rank` (top-20 + contact sheet) → `review` (approve/reject/edit + audit log) → `decide` (GO/HOLD/REWORK + reason_code + owner).
- **Thành phần offline:** không dùng model/weights; chỉ numpy, scipy, Pillow.
- **Trade-offs:** ngưỡng chọn tay (đơn giản, giải thích được) thay vì học máy (cần nhiều nhãn hơn); lấy max của 4 điểm (dễ giải thích loại lỗi) thay vì tổng có trọng số.

## 04 · Baseline vs PoC

- **Baseline:** một ngưỡng Laplacian toàn ảnh (`src/examples/laplacian_baseline.py`, `LAP_THRESHOLD = 300`, score = −log(lap var)) — đúng mô tả baseline trong `docs/tracks/T02.md`. Thêm random baseline (`src/examples/random_baseline.py`) làm mức sàn.
- **PoC:** `src/pipeline.py` — 4 bộ phát hiện (blur, compression, dark, glare), `FEATURE_PARAMS` cố định.
- **Cùng budget / cùng split eval / cùng seed 42:** xác nhận (cùng lệnh `src.main` + `src.evaluate`).

**Bảng 1 · Baseline (Laplacian) vs PoC** — output của `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json` (xem `reports/table1_baseline_vs_poc.md`):

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Defect Recall@B | 0.85 (17/20) | 1.00 (20/20) | +0.15; higher; B=20, N=40 |
| Precision@B | 0.85 | 1.00 | +0.15; higher |
| Hard-slice: false alarm top-B, light=night | 0.25 (2/8 ảnh sạch) | 0.00 | −0.25; lower; N=16 |
| Hard-slice: false alarm top-B, light=dusk | 0.50 (1/2) | 0.00 | −0.50; lower; N=4 (rất nhỏ) |
| Defect-type accuracy | n/a | 0.95 (19/20) | — |
| Runtime / 100 items | 0.23 s | 0.43 s | CPU Intel 12th gen, Windows 11, Python 3.11 |

Random baseline: Recall@20 = 0.50 (`reports/table1_random_vs_poc.md`).

## 05 · Evaluation protocol

- **Primary:** Defect Recall@20 = ảnh lỗi trong top-20 / 20 ảnh lỗi của split eval; đơn vị = ảnh (xem `reports/metric_contract.md`).
- **Threshold / budget:** B = 20; ngưỡng RECAPTURE = điểm ≥ 0.5; quyết định GO/HOLD/REWORK theo 10% / 60%.
- **Độ bất định (Wilson 95% CI, N = 20 ảnh lỗi):** PoC 1.00 [0.84, 1.00] · Laplacian 0.85 [0.64, 0.95] · Random 0.50 [0.30, 0.70]. Khoảng tin cậy PoC và Laplacian chồng nhau → với N nhỏ, chưa thể khẳng định chênh lệch có ý nghĩa thống kê.
- **Lệnh evaluate:** `python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json`


## 06 · Result slices

| Slice | N | Baseline (Laplacian) | PoC | Ghi chú |
|---|---|---|---|---|
| light=day (recall trong top-B) | 20 | 0.90 | 1.00 | false alarm 0 / 0 |
| light=night (false alarm) | 16 | 0.25 | 0.00 | ảnh sạch cam_B bị Laplacian báo nhầm |
| defect=glare (recall) | 4 | 0.75 | 1.00 | lóa làm tăng độ nét → Laplacian bỏ sót |
| defect=compression (recall) | 8 | 0.75 | 1.00 | pixel hoá làm tăng độ nét |

- **Failure case 1 — `img_19_2` (vỡ nén nhẹ, cam_A, day):** blockiness 1.62 → điểm 0.29 < 0.5 → PoC tự gắn KEEP (bỏ sót duy nhất trên 96 ảnh: 47/48). Root cause: phân bố blockiness của ảnh sạch nhiều chi tiết lên tới 1.66 → hạ ngưỡng sẽ báo nhầm `img_12_0`, `img_22_0`. Ảnh vẫn nằm hạng 20 của hàng chờ eval nên được người review bắt. Cải tiến: so blockiness với ảnh gốc cùng cảnh.
- **Failure case 2 (rủi ro) — lóa ban đêm `img_03_2`, `img_06_3` (cam_B, night):** tỉ lệ pixel cháy cục bộ chỉ 0.10–0.13 (điểm lóa theo cụm cháy ~0.16–0.30); được bắt nhờ điều kiện "sáng > 1.4× median ban đêm" (ratio 2.3–2.4). Biên an toàn phụ thuộc vào median của lô → lô toàn ảnh đêm có lóa sẽ yếu đi.
- **Failure mode của baseline (đề yêu cầu phân tích):** cam_B quang học mềm → 5 ảnh sạch cam_B bị báo nhầm (`img_00_0, img_09_0, img_12_0, img_21_0, img_06_0`); lóa/vỡ nén bị bỏ sót (25/48 ảnh lỗi không bị gắn RECAPTURE).
- **Latency:** 0.43 s / 100 ảnh (CPU, không GPU).

## 07 · Human & decision

- **Review queue:** `reports/review_queue.csv` (top-20 trên cả lô theo `score`, kèm `reason` = loại lỗi + đặc trưng, `suggested_action`, `slice` = light) và `out/poc/contact_sheet.html` (ảnh, dropdown quyết định, nút Export CSV).
- **Override + audit log:** reviewer điền `reviewer`, `reviewer_decision ∈ {approve, reject, edit}`, `override_value` → lưu `out/poc/review_queue_reviewed.csv` → chạy lại pipeline: `reject` → KEEP, `edit` → action = `override_value`; mọi thay đổi ghi vào `out/poc/audit_log.jsonl`. **Chưa có phiên review thật nào** — các cột reviewer trong `reports/review_queue.csv` đang trống.
- **Decision:** `HOLD` · `RECAPTURE_NEEDED` · owner "QC Lead (Data Track)" — 47/96 ảnh (49%) cần chụp lại: 17 compression, 12 blur, 10 dark, 8 glare (`reports/decision_log.csv`).
- **Khi nào HOLD/REWORK thay vì tự release:** bất cứ khi nào tỉ lệ RECAPTURE > 10%, hoặc khi người review chưa duyệt hết top-B.

## 08 · Reproduce & tests


```bash
pip install -r requirements.txt
python -m src.main --track t02 --pipeline src.examples.laplacian_baseline --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --track t02 --output out/poc --run-name poc --offline --seed 42
python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/baseline/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
pytest -q
```


- **`pytest -q`:** 50 passed, 39 skipped, 0 failed (8.6 s; các test skip cần GT của giảng viên — instructor overlay không phát hành). Test của nhóm: `tests/test_t02_pipeline.py` (1 success + 2 edge case) và `tests/test_cli.py::test_group_pipeline_runs_end_to_end`.
- **Máy:** Intel 12th gen, Windows 11, Python 3.11.9 · git sha của lần chạy: `07c89f6` (ghi trong `reports/metrics_poc.json`, seed 42).
- **Notebook Colab** tái lập toàn bộ (`demo/T02_raw_qc_colab.ipynb`).

## 09 · Limitations & ethics

- **PII / license:** dữ liệu synthetic CC0, biển số giả `SYN-…`, không có người thật. Demo web xử lý ảnh hoàn toàn trên trình duyệt, ảnh người dùng không được tải lên server.
- **Điều chưa biết:** nhãn do nhóm tự gán (có thể lệch với GT giảng viên); ngưỡng chọn khi đã xem phân bố cả dev và eval → 1.00 là lạc quan, cần heldout mới; chưa thử ảnh thật (BDD) và độ phân giải khác 320×180.
- **Scale 10×:** chi phí tuyến tính (~5 s / 1 000 ảnh); median theo light nên tính trên lô tham chiếu cố định thay vì lô hiện tại để tránh trôi ngưỡng.
- **Kế hoạch cải tiến:** ngưỡng riêng theo camera; ROI biển số cho lóa cục bộ; so blockiness với ảnh gốc cùng cảnh; kiểm 10 ảnh out-of-domain.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Hà Huy Dũng – 2A202603271 | `hdung25` / hahuyd25@gmail.com | Lead/Integrator + core algorithm: `src/pipeline.py` (4 bộ phát hiện, rank, decide), `src/examples/laplacian_baseline.py`, `configs/lab.yaml`, tích hợp Colab + web demo | `07c89f6` (PoC pipeline, baseline, reports, demo), `9538aa6` | có |
| Trần Nguyễn Hữu Phúc – 2A202603303 | `hhuuphucc` / 148366328+hhuuphucc@users.noreply.github.com | Data & provenance: kiểm `manifest.csv` (sha256), schema `images.csv`, chia split theo cảnh; gán nhãn audit 96 ảnh `reports/manual_audit_labels.csv` (GT) | chưa có commit riêng trên repo — cần tự push phần việc | có |
| Triệu Hoàng Hiếu – 2A202603294 | `hieuwewe123` / 169576317+hieuwewe123@users.noreply.github.com | QA / metric: `reports/metric_contract.md`, chạy `src.evaluate` + `src.compare` (Bảng 1, slice, Wilson CI), `tests/test_t02_pipeline.py` (1 success + 2 edge case), phân tích failure case | chưa có commit riêng trên repo — cần tự push phần việc | có |
| Phạm Minh Quân – 2A202603307 | `phamminhquan1101` / 103442458+phamminhquan1101@users.noreply.github.com | Human review + report: `reports/review_queue.csv`, `out/poc/contact_sheet.html`, `reports/decision_log.csv`, web demo + 5 slide (`web/`), viết `reports/group_report.md` | chưa có commit riêng trên repo — cần tự push phần việc | có |


## 11 · References

| Nguồn | Ý nghĩa |
|---|---|
| Pech-Pacheco et al., "Diatom autofocusing in brightfield microscopy: a comparative study", ICPR 2000 | Variance of Laplacian làm độ đo độ nét → bộ phát hiện blur |
| Wang, Sheikh & Bovik, "No-reference perceptual quality assessment of JPEG compressed images", ICIP 2002 | Đo blockiness tại biên khối 8×8 → bộ phát hiện compression |
| Sakaridis et al., "ACDC: The Adverse Conditions Dataset with Correspondences", ICCV 2021 | Ảnh đêm/thời tiết xấu là domain hợp lệ → chuẩn hoá theo điều kiện sáng thay vì loại bỏ |
| `docs/tracks/T02.md` (đề bài) | Baseline Laplacian, metric Recall@B, failure modes bắt buộc |

---


**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo trong README; input mẫu không chứa PII thật; tag `demo-180m` + `final-24h` đã tạo.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, decision log — **còn thiếu reviewer evidence thật**.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên — **hiện mới có commit của `hdung25`**; 3 thành viên còn lại cần tự commit phần việc của mình.
