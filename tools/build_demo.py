"""Build the static demo site (web/) and the Colab notebook (demo/T02_raw_qc_colab.ipynb).

Run after the 3 pipelines + evaluations (see README of demo):
    python tools/build_demo.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
RUNS = ["baseline_random", "baseline_lap", "poc"]
FILES = {"baseline_random": "baseline_random", "baseline_lap": "baseline", "poc": "poc"}


def metric(run: str, name: str, slice_: str = "all"):
    m = json.loads((ROOT / f"reports/metrics_{FILES[run]}.json").read_text(encoding="utf-8"))
    for x in m["metrics"]:
        if x["name"] == name and x.get("slice", "all") == slice_:
            return x["value"]
    return None


def build_web() -> None:
    (WEB / "img").mkdir(parents=True, exist_ok=True)
    lab = pd.read_csv(ROOT / "reports/manual_audit_labels.csv")
    feat = pd.read_csv(ROOT / "out/poc/features.csv")
    lap = pd.read_csv(ROOT / "out/baseline/ranked_review.csv")[["image_id", "pred_action"]] \
        .rename(columns={"pred_action": "lap_action"})
    df = lab.merge(feat[["image_id", "lap_var", "mean", "blockiness", "sat_local", "bright_ratio",
                         "s_blur", "s_compression", "s_dark", "s_glare", "score", "pred_defect_type",
                         "pred_action"]], on="image_id").merge(lap, on="image_id")
    for p in (ROOT / "fixtures/t02_raw_qc/images").glob("*.jpg"):
        shutil.copy2(p, WEB / "img" / p.name)
    light_median = feat.groupby("light")["mean"].median().round(3).to_dict()
    metrics = {r: {"recall": metric(r, "Defect Recall@B"), "precision": metric(r, "Precision@B"),
                   "fa_day": metric(r, "False alarm in top-B", "light=day"),
                   "fa_dusk": metric(r, "False alarm in top-B", "light=dusk"),
                   "fa_night": metric(r, "False alarm in top-B", "light=night")} for r in RUNS}
    metrics["poc"]["type_acc"] = metric("poc", "Defect-type accuracy (GT defects)")
    decision = json.loads((ROOT / "out/poc/decision.json").read_text(encoding="utf-8"))
    data = {"images": json.loads(df.round(4).to_json(orient="records")), "light_median": light_median,
            "metrics": metrics, "decision": {k: decision[k] for k in ("status", "reason_code", "reason", "owner")}}
    (WEB / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print("web/data.json:", len(df), "images; light medians", light_median)


def code_cell(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": src.strip("\n")}


def md_cell(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.strip("\n")}


def build_notebook() -> None:
    pipeline_src = (ROOT / "src/pipeline.py").read_text(encoding="utf-8")
    baseline_src = (ROOT / "src/examples/laplacian_baseline.py").read_text(encoding="utf-8")
    labels_src = (ROOT / "reports/manual_audit_labels.csv").read_text(encoding="utf-8")
    cells = [
        md_cell("""
# T02 · Raw QC Triage — demo chấm điểm trên Google Colab

**Bài toán:** 96 ảnh camera (day / dusk / night, cam_A / cam_B). Người review chỉ xem được **B = 20 ảnh**.
Pipeline phải xếp hạng sao cho 20 ảnh đầu chứa nhiều ảnh lỗi nhất (blur · compression · dark · glare).

Notebook này: clone repo → cài pipeline của nhóm → chạy **3 phương pháp** (Random, Laplacian, PoC) → chấm
**Defect Recall@20 / Precision@20** trên split `eval` → xem ảnh minh chứng.

> Nhãn dùng để chấm (`manual_audit_labels.csv`) do nhóm tự gán bằng mắt cho 96 ảnh (repo học viên không có `gt/` của giảng viên).
> Chạy: **Runtime → Run all** (~1 phút, chỉ CPU).
"""),
        code_cell("""
!git clone -q https://github.com/hdung25/K5-Day6-L2-Cloud-DataGovernanceAndPrivacy day06 2>/dev/null || echo "đã clone"
%cd day06
!pip -q install -r requirements.txt 2>/dev/null | tail -1
!sed -i 's/^owner: .*/owner: "QC Lead (Data Track)"/' configs/lab.yaml
"""),
        md_cell("## 1 · Cài pipeline của nhóm (PoC) + baseline Laplacian + nhãn audit"),
        code_cell("%%writefile src/pipeline.py\n" + pipeline_src),
        code_cell("%%writefile src/examples/laplacian_baseline.py\n" + baseline_src),
        code_cell("%%writefile reports/manual_audit_labels.csv\n" + labels_src),
        md_cell("## 2 · Chạy 3 phương pháp (cùng ảnh, cùng budget B=20, seed 42, offline)"),
        code_cell("""
!python -m src.main --track t02 --pipeline src.examples.random_baseline    --output out/baseline_random --run-name baseline_random --offline --seed 42
!python -m src.main --track t02 --pipeline src.examples.laplacian_baseline --output out/baseline_lap    --run-name baseline_lap    --offline --seed 42
!python -m src.main --track t02                                            --output out/poc             --run-name poc             --offline --seed 42
"""),
        md_cell("## 3 · Chấm điểm (script chuẩn `src.evaluate`, split eval)"),
        code_cell("""
for run in ["baseline_random", "baseline_lap", "poc"]:
    !python -m src.evaluate --track t02 --gt reports/manual_audit_labels.csv --pred out/{run}/ranked_review.csv --run-name {run} --out reports/metrics_{run}.json > /dev/null
!python -m src.compare reports/metrics_baseline_lap.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md > /dev/null
from IPython.display import Markdown, display
display(Markdown(open("reports/table1_baseline_vs_poc.md", encoding="utf-8").read()))
"""),
        code_cell("""
import json, matplotlib.pyplot as plt
names = {"baseline_random": "Random", "baseline_lap": "Laplacian (1 ngưỡng)", "poc": "PoC nhóm (4 detector)"}
def get(run, name):
    return next(x["value"] for x in json.load(open(f"reports/metrics_{run}.json"))["metrics"] if x["name"] == name)
rec = [get(r, "Defect Recall@B") for r in names]
fig, ax = plt.subplots(figsize=(7, 3.2))
bars = ax.barh(list(names.values()), rec, color=["#b0b7c3", "#7c8db5", "#1f6feb"])
ax.bar_label(bars, labels=[f"{v:.2f}" for v in rec], padding=4)
ax.set_xlim(0, 1.1); ax.set_xlabel("Defect Recall@20 (split eval, 20 ảnh lỗi / 40 ảnh)")
ax.invert_yaxis(); ax.spines[["top", "right"]].set_visible(False); plt.tight_layout(); plt.show()
"""),
        md_cell("## 4 · Ảnh minh chứng: top-8 ảnh PoC đưa cho reviewer + quyết định"),
        code_cell("""
import pandas as pd
from PIL import Image
r = pd.read_csv("out/poc/ranked_review.csv").merge(pd.read_csv("reports/manual_audit_labels.csv")[["image_id","defect_type"]], on="image_id")
fig, axes = plt.subplots(2, 4, figsize=(16, 6))
for ax, row in zip(axes.flat, r.head(8).itertuples()):
    ax.imshow(Image.open(f"fixtures/t02_raw_qc/{row.path}")); ax.axis("off")
    ax.set_title(f"{row.image_id} · {row.light}\\nPoC: {row.pred_defect_type} ({row.score:.2f}) · nhãn: {row.defect_type}", fontsize=9)
plt.tight_layout(); plt.show()
print(open("out/poc/decision.json", encoding="utf-8").read())
"""),
        md_cell("## 5 · Failure case của baseline Laplacian: cam_B (quang học mềm) bị báo nhầm, lóa/vỡ nén bị bỏ sót"),
        code_cell("""
lap = pd.read_csv("out/baseline_lap/ranked_review.csv")
f = pd.read_csv("out/poc/features.csv").set_index("image_id")
cases = [("img_09_0", "sạch · cam_B"), ("img_21_0", "sạch · cam_B"), ("img_17_2", "glare"), ("img_05_2", "compression")]
fig, axes = plt.subplots(1, 4, figsize=(16, 2.9))
for ax, (img, note) in zip(axes, cases):
    a = lap.set_index("image_id").loc[img, "pred_action"]; p = f.loc[img]
    ax.imshow(Image.open(f"fixtures/t02_raw_qc/images/{img}.jpg")); ax.axis("off")
    ax.set_title(f"{img} ({note})\\nLaplacian: {a} · PoC: {p.pred_action}", fontsize=9)
plt.tight_layout(); plt.show()
"""),
        md_cell("""
## Kết luận
- PoC đạt **Recall@20 = 1.00, Precision@20 = 1.00** trên split eval (Laplacian 0.85, Random 0.50).
- Toàn bộ 96 ảnh: PoC bắt 47/48 ảnh lỗi, **0** ảnh sạch bị báo nhầm (sót `img_19_2` — vỡ nén nhẹ).
- Hạn chế: nhãn do nhóm tự gán, tập nhỏ (synthetic); cần kiểm thêm ảnh thật out-of-domain.
"""),
    ]
    nb = {"cells": cells, "metadata": {"colab": {"provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 0}
    out = ROOT / "demo/T02_raw_qc_colab.ipynb"
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy2(out, WEB / out.name)
    print("notebook:", out)


if __name__ == "__main__":
    build_web()
    build_notebook()
