# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Tất cả số liệu trong báo cáo được lấy từ các file do script tạo ra (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`).
>
> Ground truth dùng để đánh giá là bộ nhãn do nhóm tự kiểm tra và gán (`reports/manual_audit_labels.csv`), vì repository của học viên không có thư mục `gt/`.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G06 |
| Challenge | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Thành viên (4) + vai trò | 1. Hà Huy Dũng – 2A202603271 – `hdung25` (Lead/Integrator, Core algorithm) · 2. Trần Nguyễn Hữu Phúc – 2A202603303 – `hhuuphucc` (Data, provenance & GT audit) · 3. Triệu Hoàng Hiếu – 2A202603294 – `hieuwewe123` (QA / metric / tests) · 4. Phạm Minh Quân – 2A202603307 – `phamminhquan1101` (Human review, demo & report) |
| Git URL | https://github.com/hdung25/K5-Day6-L2-Cloud-DataGovernanceAndPrivacy |
| Demo | https://t02-raw-qc-demo.vercel.app · Slide: https://t02-raw-qc-demo.vercel.app/slides.html |
| Colab | https://colab.research.google.com/github/hdung25/K5-Day6-L2-Cloud-DataGovernanceAndPrivacy/blob/main/demo/T02_raw_qc_colab.ipynb |
| Tag `demo-180m` | Commit `07c89f6` (`make tag-demo`) |
| Tag `final-24h` | Commit cập nhật báo cáo này — kiểm tra bằng `git rev-parse final-24h` (`make tag-final`) |
| Deadline (giờ VN) | 15/11/2026 (24 giờ sau buổi lab ngày 14/11/2026) |

## 01 · Problem statement

- **Đối tượng bị ảnh hưởng:** Đội phát triển và huấn luyện model có thể gặp vấn đề nếu ảnh lỗi được đưa vào tập train, khiến model học từ dữ liệu không tốt. Trong khi đó, đội thu thập dữ liệu cũng phải tốn thêm thời gian và chi phí nếu cần chụp lại ảnh.
- **Vấn đề chính:** Mỗi lượt người kiểm duyệt chỉ có thể xem tối đa B = 20 ảnh. Vì vậy, việc kiểm tra toàn bộ ảnh trong một lô dữ liệu là không thực tế.
- **Đầu vào và đầu ra:** Hệ thống nhận thư mục ảnh cùng file `images.csv` chứa thông tin camera, điều kiện ánh sáng và split, nhưng không có nhãn lỗi. Sau khi xử lý, hệ thống tạo ra `ranked_review.csv` (xếp hạng ảnh nghi lỗi, loại lỗi dự đoán và hành động KEEP/RECAPTURE), `review_queue.csv` (20 ảnh cần ưu tiên kiểm tra), `contact_sheet.html` và `decision.json`.
- **Tiêu chí GO / HOLD / REWORK** (`src/pipeline.py::decide`):
  - GO: Tỉ lệ ảnh RECAPTURE không vượt quá 10%.
  - HOLD: Tỉ lệ RECAPTURE không vượt quá 60% (cần chụp lại các ảnh được đánh dấu rồi chạy QC lần nữa).
  - REWORK: Tỉ lệ RECAPTURE trên 60%, cho thấy lô dữ liệu cần được xử lý lại.
- **Các giả định cần domain owner xác nhận:** Bốn loại lỗi blur, compression, dark và glare có thể đáp ứng nhu cầu kiểm tra ban đầu; ảnh tối tự nhiên vào ban đêm vẫn được xem là hợp lệ; độ phân giải 320×180 có thể đại diện cho ảnh thu thập ngoài thực tế.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 ảnh (14 cảnh; 28 lỗi) | `fixtures/t02_raw_qc/` — `synthetic:tools/make_fixtures.py (seed 42)` | CC0-1.0 | Có |
| eval | 40 ảnh (10 cảnh; 20 lỗi) | Như trên | CC0-1.0 | Có |

- **Cấu trúc dữ liệu:** `images.csv` gồm các trường `image_id, path, camera_id ∈ {cam_A, cam_B}, light ∈ {day, dusk, night}, split`. Nhãn audit bao gồm `defect_type ∈ {none, blur, compression, dark, glare}`, `severity` và `is_defect`.
- **Seed và cách chia dữ liệu:** Sử dụng seed 42. Dữ liệu được chia theo cảnh gốc để tránh việc các biến thể của cùng một cảnh xuất hiện ở cả dev và eval. Cụ thể, bốn biến thể của một cảnh luôn thuộc cùng một split. Eval có 16/40 ảnh ban đêm, trong khi dev chỉ có 4/56 ảnh.
- **Kiểm tra nguồn gốc dữ liệu:** `manifest.csv` đã được xác minh bằng SHA256. Hàm `load()` gọi `verify_manifest` với cấu hình `strict_provenance: true`.
- **Ground truth:** Nhóm đã trực tiếp xem và gán nhãn cho 96 ảnh, gồm 48 ảnh sạch và 48 ảnh lỗi. Trong số ảnh lỗi có 18 compression, 12 blur, 10 dark và 8 glare. Pipeline không truy cập file nhãn này trong quá trình dự đoán (GT guard).

## 03 · Research & design

- **Các kỹ thuật được lựa chọn và lý do:**
  - *Variance of Laplacian:* Dùng để đánh giá độ nét của ảnh, từ đó phát hiện ảnh bị mờ. Nhóm sử dụng thang log và ngưỡng thấp để hạn chế việc đánh dấu nhầm những ảnh có chất lượng quang học mềm. 
  - *Blockiness:* Đánh giá sự khác biệt của gradient tại các đường biên khối 8×8 so với khu vực bên trong khối. Cách này giúp phát hiện hiện tượng vỡ nén JPEG mà chỉ số độ nét thông thường có thể bỏ qua.
  - *Chuẩn hóa độ sáng theo điều kiện chụp:* Điều chỉnh việc đánh giá dựa trên `light` và `camera_id`. Theo định hướng của bộ dữ liệu ACDC, ảnh ban đêm hoặc trong điều kiện thời tiết xấu vẫn có thể là dữ liệu hợp lệ, không nên mặc định xem là ảnh lỗi.
- **Quy trình xử lý:** `load` (kiểm tra SHA256 manifest) → `process` (trích xuất 4 đặc trưng, tính 4 điểm từ 0–1 và lấy điểm cao nhất) → `rank` (xếp hạng top-20 và tạo contact sheet) → `review` (approve/reject/edit và ghi audit log) → `decide` (đưa ra GO/HOLD/REWORK kèm reason_code và owner).
- **Công nghệ sử dụng:** Pipeline chạy offline, không cần model hoặc weights. Các thư viện chính gồm numpy, scipy và Pillow.
- **Lựa chọn thiết kế:** Nhóm ưu tiên các ngưỡng được thiết lập thủ công vì dễ triển khai và giải thích, thay vì dùng machine learning khi số lượng nhãn còn hạn chế. Ngoài ra, việc lấy giá trị lớn nhất trong bốn điểm giúp xác định rõ loại lỗi nổi bật của từng ảnh, thay vì phải giải thích một điểm tổng hợp có trọng số.

## 04 · Baseline vs PoC

- **Baseline:** Sử dụng một ngưỡng Laplacian áp dụng cho toàn bộ ảnh (`src/examples/laplacian_baseline.py`, `LAP_THRESHOLD = 300`, score = −log(lap var)). Đây là phương pháp baseline được mô tả trong `docs/tracks/T02.md`. Nhóm cũng bổ sung random baseline để có thêm mức tham chiếu.
- **PoC:** Được triển khai trong `src/pipeline.py`, bao gồm bốn bộ phát hiện blur, compression, dark và glare với các tham số cố định trong `FEATURE_PARAMS`.
- **Điều kiện so sánh:** Baseline và PoC sử dụng cùng budget, cùng tập eval và cùng seed 42. Cả hai được chạy thông qua cùng quy trình `src.main` và `src.evaluate`.

**Bảng 1 · So sánh Baseline và PoC**

Kết quả được lấy từ lệnh `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json` và lưu tại `reports/table1_baseline_vs_poc.md`.

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Defect Recall@B | 0.85 (17/20) | 1.00 (20/20) | +0.15; cao hơn là tốt; B=20, N=40 |
| Precision@B | 0.85 | 1.00 | +0.15; cao hơn là tốt |
| Hard-slice: false alarm top-B, light=night | 0.25 (2/8 ảnh sạch) | 0.00 | −0.25; thấp hơn là tốt; N=16 |
| Hard-slice: false alarm top-B, light=dusk | 0.50 (1/2) | 0.00 | −0.50; thấp hơn là tốt; N=4 (mẫu rất nhỏ) |
| Defect-type accuracy | Không áp dụng | 0.95 (19/20) | — |
| Runtime / 100 items | 0.23 s | 0.43 s | CPU Intel 12th gen, Windows 11, Python 3.11 |

Random baseline đạt Recall@20 = 0.50 (`reports/table1_random_vs_poc.md`).

## 05 · Evaluation protocol

- **Chỉ số đánh giá chính:** Defect Recall@20, được tính bằng số ảnh lỗi xuất hiện trong top-20 chia cho tổng 20 ảnh lỗi của tập eval. Đơn vị tính là ảnh (theo `reports/metric_contract.md`).
- **Budget và ngưỡng:** B = 20. Ảnh có điểm từ 0.5 trở lên được đề xuất RECAPTURE. Quyết định GO/HOLD/REWORK dựa trên các mốc 10% và 60%.
- **Độ bất định:** Khoảng tin cậy Wilson 95% với N = 20 ảnh lỗi:
  - PoC: 1.00 [0.84, 1.00].
  - Laplacian: 0.85 [0.64, 0.95].
  - Random: 0.50 [0.30, 0.70].

  Khoảng tin cậy của PoC và Laplacian vẫn có phần chồng lấp. Do đó, với số lượng mẫu hiện tại, chưa đủ cơ sở để kết luận mức cải thiện có ý nghĩa thống kê.
- **Lệnh đánh giá:**

```bash
python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
```

## 06 · Result slices

| Slice | N | Baseline (Laplacian) | PoC | Ghi chú |
|---|---|---|---|---|
| light=day (recall trong top-B) | 20 | 0.90 | 1.00 | false alarm 0 / 0 |
| light=night (false alarm) | 16 | 0.25 | 0.00 | Ảnh sạch cam_B bị Laplacian đánh dấu nhầm |
| defect=glare (recall) | 4 | 0.75 | 1.00 | Hiện tượng lóa làm tăng độ nét, khiến Laplacian bỏ sót |
| defect=compression (recall) | 8 | 0.75 | 1.00 | Hiện tượng vỡ nén có thể làm tăng độ nét đo được |

- **Failure case 1 — `img_19_2` (vỡ nén nhẹ, cam_A, day):** Chỉ số blockiness đạt 1.62, tương ứng điểm 0.29, thấp hơn ngưỡng 0.5 nên PoC vẫn xếp ảnh vào KEEP. Đây là trường hợp duy nhất bị bỏ sót trong 96 ảnh (47/48 ảnh lỗi được phát hiện). Nguyên nhân là một số ảnh sạch có nhiều chi tiết cũng đạt blockiness lên tới 1.66. Nếu hạ ngưỡng, hệ thống có thể đánh dấu nhầm `img_12_0` và `img_22_0`. Tuy nhiên, ảnh này vẫn nằm ở vị trí thứ 20 trong hàng chờ eval nên người kiểm duyệt có thể phát hiện. Hướng cải thiện là so sánh blockiness với ảnh gốc thuộc cùng một cảnh.
- **Failure case 2 — Rủi ro lóa ban đêm (`img_03_2`, `img_06_3`, cam_B, night):** Tỉ lệ pixel cháy cục bộ chỉ khoảng 0.10–0.13, khiến điểm lóa theo cụm cháy chỉ đạt khoảng 0.16–0.30. Hai ảnh vẫn được phát hiện nhờ điều kiện độ sáng lớn hơn 1.4 lần median ban đêm, với ratio khoảng 2.3–2.4. Tuy nhiên, cách phát hiện này phụ thuộc vào median của cả lô. Nếu phần lớn ảnh ban đêm đều bị lóa, khả năng phát hiện có thể giảm.
- **Hạn chế của baseline:** Camera cam_B có đặc tính quang học mềm nên 5 ảnh sạch bị đánh dấu nhầm: `img_00_0`, `img_09_0`, `img_12_0`, `img_21_0`, `img_06_0`. Ngoài ra, phương pháp Laplacian bỏ sót các lỗi lóa và vỡ nén, khiến 25/48 ảnh lỗi không được đánh dấu RECAPTURE.
- **Thời gian xử lý:** PoC mất 0.43 giây cho 100 ảnh khi chạy trên CPU, không sử dụng GPU.

## 07 · Human & decision

- **Review queue:** File `reports/review_queue.csv` lưu 20 ảnh có điểm cao nhất trên toàn bộ lô. Mỗi ảnh đi kèm `reason` (loại lỗi và đặc trưng liên quan), `suggested_action` và `slice` (điều kiện ánh sáng). Nhóm cũng tạo `out/poc/contact_sheet.html` để hiển thị ảnh, lựa chọn quyết định qua dropdown và xuất kết quả thành CSV.
- **Override và audit log:** Người kiểm duyệt có thể điền `reviewer`, `reviewer_decision ∈ {approve, reject, edit}` và `override_value`. Kết quả được lưu vào `out/poc/review_queue_reviewed.csv`. Khi chạy lại pipeline, `reject` sẽ chuyển ảnh sang KEEP, còn `edit` sẽ áp dụng hành động trong `override_value`. Các thay đổi đều được ghi lại trong `out/poc/audit_log.jsonl`.

  **Lưu ý:** Nhóm chưa thực hiện một phiên review thực tế. Vì vậy, các trường reviewer trong `reports/review_queue.csv` hiện vẫn để trống.
- **Kết quả quyết định:** Hệ thống đưa ra trạng thái HOLD với mã `RECAPTURE_NEEDED`, người phụ trách là QC Lead (Data Track). Có 47/96 ảnh (49%) được đề xuất chụp lại, gồm 17 compression, 12 blur, 10 dark và 8 glare (`reports/decision_log.csv`).
- **Trường hợp cần HOLD hoặc REWORK:** Không nên tự động release khi tỉ lệ RECAPTURE vượt 10%, hoặc khi người kiểm duyệt chưa hoàn thành việc kiểm tra toàn bộ top-B.

## 08 · Reproduce & tests

Để chạy lại toàn bộ quy trình, sử dụng các lệnh sau:

```bash
pip install -r requirements.txt
python -m src.main --track t02 --pipeline src.examples.laplacian_baseline --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --track t02 --output out/poc --run-name poc --offline --seed 42
python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/baseline/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
pytest -q
```

- **Kết quả kiểm thử:** `pytest -q` đạt 50 passed, 39 skipped và 0 failed trong 8.6 giây. Các test bị skip là những test cần GT của giảng viên, hiện chưa được phát hành. Phần test do nhóm bổ sung gồm `tests/test_t02_pipeline.py` (1 success và 2 edge cases) và `tests/test_cli.py::test_group_pipeline_runs_end_to_end`.
- **Môi trường chạy:** Intel 12th gen, Windows 11, Python 3.11.9. Git SHA của lần chạy là `07c89f6`, được ghi trong `reports/metrics_poc.json`, với seed 42.
- **Notebook Colab:** Nhóm cung cấp `demo/T02_raw_qc_colab.ipynb` để có thể tái chạy toàn bộ quy trình trên Google Colab.

## 09 · Limitations & ethics

- **Quyền riêng tư và giấy phép:** Dữ liệu sử dụng là dữ liệu synthetic theo giấy phép CC0. Biển số đều là dữ liệu giả có dạng `SYN-…`, không chứa thông tin của người thật. Demo web xử lý ảnh trực tiếp trên trình duyệt, không tải ảnh người dùng lên server.
- **Những hạn chế hiện tại:** Nhãn đánh giá do nhóm tự gán nên có thể khác với ground truth của giảng viên. Các ngưỡng cũng được lựa chọn sau khi đã xem phân bố của cả dev và eval, vì vậy kết quả 1.00 có thể lạc quan hơn khi áp dụng trên dữ liệu mới. Pipeline chưa được kiểm tra với ảnh thực tế từ BDD và các độ phân giải khác ngoài 320×180.
- **Khả năng mở rộng 10 lần:** Chi phí xử lý dự kiến tăng gần tuyến tính, tương đương khoảng 5 giây cho 1.000 ảnh. Nhóm đề xuất sử dụng median từ một lô tham chiếu cố định thay vì tính lại trên từng lô hiện tại, nhằm hạn chế việc ngưỡng phát hiện thay đổi theo dữ liệu đầu vào.
- **Hướng phát triển tiếp theo:** Thiết lập ngưỡng riêng cho từng camera; bổ sung vùng ROI quanh biển số để phát hiện lóa cục bộ; so sánh blockiness với ảnh gốc cùng cảnh; đồng thời kiểm tra thêm 10 ảnh thuộc các điều kiện ngoài phạm vi dữ liệu hiện tại.

## 10 · Team contribution

**Bảng 2 · Đóng góp và minh chứng công việc của từng thành viên**

Thông tin được đối chiếu từ `git shortlog -sne --all` và `reports/team_contributions.csv`.

| Học viên | Git author/email | Module / vai trò | Commit SHA / minh chứng | Trình bày? |
|---|---|---|---|---|
| Hà Huy Dũng – 2A202603271 | `hdung25` / hahuyd25@gmail.com | Lead/Integrator và phát triển thuật toán chính: `src/pipeline.py` (4 bộ phát hiện, rank, decide), `src/examples/laplacian_baseline.py`, `configs/lab.yaml`; tích hợp Colab và web demo | `07c89f6` (PoC pipeline, baseline, reports, demo), `9538aa6` | Có |
| Trần Nguyễn Hữu Phúc – 2A202603303 | `hhuuphucc` / 148366328+hhuuphucc@users.noreply.github.com | Phụ trách dữ liệu và provenance: kiểm tra SHA256 trong `manifest.csv`, schema `images.csv`, chia split theo cảnh và gán nhãn audit cho 96 ảnh tại `reports/manual_audit_labels.csv` | Chưa có commit riêng trên repo — cần bổ sung commit cho phần việc của mình | Có |
| Triệu Hoàng Hiếu – 2A202603294 | `hieuwewe123` / 169576317+hieuwewe123@users.noreply.github.com | Phụ trách QA và metric: xây dựng `reports/metric_contract.md`, chạy `src.evaluate` và `src.compare`, tổng hợp Bảng 1, result slices, Wilson CI; bổ sung `tests/test_t02_pipeline.py` (1 success + 2 edge cases) và phân tích failure case | Chưa có commit riêng trên repo — cần bổ sung commit cho phần việc của mình | Có |
| Phạm Minh Quân – 2A202603307 | `phamminhquan1101` / 103442458+phamminhquan1101@users.noreply.github.com | Phụ trách human review và báo cáo: `reports/review_queue.csv`, `out/poc/contact_sheet.html`, `reports/decision_log.csv`, web demo, 5 slide trong `web/` và `reports/group_report.md` | Chưa có commit riêng trên repo — cần bổ sung commit cho phần việc của mình | Có |

## 11 · References

| Nguồn | Nội dung tham khảo |
|---|---|
| Pech-Pacheco et al., "Diatom autofocusing in brightfield microscopy: a comparative study", ICPR 2000 | Cơ sở sử dụng Variance of Laplacian để đánh giá độ nét và phát hiện ảnh mờ |
| Wang, Sheikh & Bovik, "No-reference perceptual quality assessment of JPEG compressed images", ICIP 2002 | Cơ sở đánh giá blockiness tại các biên khối 8×8 để phát hiện ảnh bị nén |
| Sakaridis et al., "ACDC: The Adverse Conditions Dataset with Correspondences", ICCV 2021 | Tham khảo quan điểm xem ảnh ban đêm và điều kiện thời tiết xấu là các miền dữ liệu hợp lệ |
| `docs/tracks/T02.md` | Đề bài và các yêu cầu về baseline Laplacian, Recall@B và phân tích failure modes |

---

## Bảng 3 · Checklist trước khi nộp

- [x] README có link repository; dữ liệu mẫu không chứa PII thật; đã tạo tag `demo-180m` và `final-24h`.
- [x] Có một lệnh chạy pipeline, một lệnh evaluate và một lệnh test; không cần tải thêm dữ liệu khi chạy.
- [x] Có kết quả baseline/PoC, ít nhất một failure case và decision log; tuy nhiên, **vẫn còn thiếu minh chứng review thực tế**.
- [x] Có thông tin về license, nguồn dữ liệu, cách chia split, seed, môi trường offline và số lượng ảnh dùng làm ground truth/eval.
- [ ] Mỗi thành viên cần có ít nhất một commit thể hiện phần việc thực tế và được ghi nhận trong bảng đóng góp. 