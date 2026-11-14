"""T02 baseline đúng đề: MỘT ngưỡng Laplacian toàn ảnh (score = ảnh càng ít nét càng nghi lỗi).

    python -m src.main --track t02 --pipeline src.examples.laplacian_baseline --output out/baseline_lap --run-name baseline_lap --offline
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..common.context import RunContext
from ..common.decision import Decision, write_decision
from ..common.image_ops import laplacian_variance, load_rgb
from ..common.review import make_review_queue, write_review_queue

LAP_THRESHOLD = 300.0  # chốt trên dev: dưới ngưỡng = RECAPTURE


def run(ctx: RunContext) -> None:
    items = pd.read_csv(ctx.input_dir / "images.csv")
    lap = np.array([laplacian_variance(load_rgb(ctx.input_dir / p)) for p in items.path])
    items = items.assign(score=(-np.log(lap + 1e-6)).round(4),
                         pred_action=np.where(lap < LAP_THRESHOLD, "RECAPTURE", "KEEP"),
                         reason=[f"lap={v:.0f}" for v in lap])
    ctx.stats["n_items"] = len(items)
    q = make_review_queue(items, "image_id", "score", int(ctx.param("budget", 20)), reason_col="reason")
    write_review_queue(q, ctx.out("review_queue.csv"))
    items.sort_values("score", ascending=False)[["image_id", "score", "pred_action", "light", "camera_id"]] \
        .to_csv(ctx.out("ranked_review.csv"), index=False)
    write_decision(Decision(status="HOLD", reason_code="BASELINE_ONLY", reason="Laplacian-only baseline",
                            owner=ctx.config.get("owner", "baseline"), scope=ctx.track),
                   ctx.out("decision.json"), ctx.out("decision_log.csv"))
