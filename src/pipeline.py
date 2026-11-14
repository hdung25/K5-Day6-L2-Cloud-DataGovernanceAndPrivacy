from __future__ import annotations

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track

FEATURE_PARAMS = {
    "blur_lap_hi": 50.0,
    "blur_lap_lo": 3.0,
    "comp_blk_lo": 1.45,
    "comp_blk_span": 0.6,
    "dark_ratio_hi": 0.6,
    "dark_ratio_span": 0.4,
    "glare_blk_lo": 0.07,
    "glare_blk_span": 0.2,
    "glare_ratio_lo": 1.4,
    "glare_ratio_span": 0.6,
}

DEFECTS = ["blur", "compression", "dark", "glare"]


def blockiness(g: np.ndarray, b: int = 8) -> float:
    dx, dy = np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))
    cx, cy = np.arange(dx.shape[1]), np.arange(dy.shape[0])
    edge = dx[:, cx % b == b - 1].mean() + dy[cy % b == b - 1].mean()
    inner = dx[:, cx % b != b - 1].mean() + dy[cy % b != b - 1].mean()
    return float(edge / (inner + 1e-6))


def local_saturation(g: np.ndarray, cell: int = 20) -> float:
    H, W = (g.shape[0] // cell) * cell, (g.shape[1] // cell) * cell
    if H == 0 or W == 0:
        return float((g > 245).mean())
    sat = (g[:H, :W] > 245).astype(np.float32)
    return float(sat.reshape(H // cell, cell, W // cell, cell).mean(axis=(1, 3)).max())


def image_features(path) -> dict:
    img = load_rgb(path)
    g = to_gray(img)
    return {
        "lap_var": laplacian_variance(img),
        "mean": float(g.mean()),
        "blockiness": blockiness(g),
        "sat_local": local_saturation(g)
    }


def _clip(x):
    return np.clip(x, 0.0, 1.0)


def defect_scores(feat: pd.DataFrame, p: dict = FEATURE_PARAMS) -> pd.DataFrame:
    f = feat.copy()
    light_median = f.groupby("light")["mean"].transform("median")
    f["bright_ratio"] = f["mean"] / light_median

    f["s_blur"] = _clip(
        (np.log(p["blur_lap_hi"]) - np.log(f.lap_var + 1e-6))
        / np.log(p["blur_lap_hi"] / p["blur_lap_lo"])
    )

    f["s_compression"] = _clip(
        (f.blockiness - p["comp_blk_lo"]) / p["comp_blk_span"]
    )

    f["s_dark"] = _clip(
        (p["dark_ratio_hi"] - f.bright_ratio) / p["dark_ratio_span"]
    )

    f["s_glare"] = np.maximum(
        _clip((f.sat_local - p["glare_blk_lo"]) / p["glare_blk_span"]),
        _clip((f.bright_ratio - p["glare_ratio_lo"]) / p["glare_ratio_span"])
    )

    s = f[[f"s_{d}" for d in DEFECTS]]

    f["score"] = s.max(axis=1).round(4)
    f["pred_defect_type"] = np.where(
        f.score >= 0.5,
        s.idxmax(axis=1).str[2:],
        "none"
    )
    f["pred_action"] = np.where(
        f.score >= 0.5,
        "RECAPTURE",
        "KEEP"
    )

    f["reason"] = [
        f"{t} ({sc:.2f}) lap={lv:.0f} blk={b:.2f} ratio={r:.2f} sat={st:.2f}"
        for t, sc, lv, b, r, st in zip(
            s.idxmax(axis=1).str[2:],
            f.score,
            f.lap_var,
            f.blockiness,
            f.bright_ratio,
            f.sat_local
        )
    ]

    return f


def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]

    if problems:
        ctx.audit.log(
            actor="pipeline",
            action="provenance_problems",
            item_id=str(manifest),
            after=problems[:20]
        )

        if ctx.config.get("strict_provenance", True):
            raise ValueError(
                f"provenance check failed ({len(problems)} problems), first: {problems[:3]}"
            )

    images = pd.read_csv(ctx.input_dir / "images.csv")
    missing = [p for p in images.path if not (ctx.input_dir / p).exists()]

    if missing:
        raise FileNotFoundError(
            f"{len(missing)} images missing, e.g. {missing[:3]}"
        )

    return {
        "manifest": pd.read_csv(manifest),
        "images": images
    }


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    images = data["images"]
    feats = pd.DataFrame([
        image_features(ctx.input_dir / p)
        for p in images.path
    ])

    scored = defect_scores(
        pd.concat([images.reset_index(drop=True), feats], axis=1)
    )

    scored.to_csv(ctx.out("features.csv"), index=False)

    cols = [
        "image_id",
        "score",
        "pred_defect_type",
        "pred_action",
        "reason",
        "path",
        "camera_id",
        "light",
        "split"
    ]

    return scored[cols].sort_values(
        "score",
        ascending=False,
        kind="mergesort"
    ).reset_index(drop=True)


def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))

    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="pred_action",
        slice_col="light",
        evidence_col="path"
    )

    write_review_queue(q, ctx.out("review_queue.csv"))

    render_contact_sheet(
        q,
        ctx.out("contact_sheet.html"),
        image_root=ctx.input_dir,
        title=f"T02 Raw QC — top-{budget} ảnh nghi lỗi"
    )

    return q


def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"

    if not reviewed_path.exists():
        return scored

    reviewed = load_review_decisions(reviewed_path)
    ctx.stats["n_reviewed"] = len(reviewed)

    final = scored.set_index("image_id")

    for r in reviewed.itertuples():
        if r.item_id not in final.index:
            continue

        before = final.loc[r.item_id, "pred_action"]

        if r.reviewer_decision == "reject":
            final.loc[r.item_id, ["pred_action", "pred_defect_type", "score"]] = [
                "KEEP",
                "none",
                0.0
            ]

        elif r.reviewer_decision == "edit" and str(r.override_value).strip():
            final.loc[r.item_id, "pred_action"] = str(r.override_value).strip()

        ctx.audit.log(
            actor=r.reviewer,
            action=f"review_{r.reviewer_decision}",
            item_id=r.item_id,
            before=before,
            after=final.loc[r.item_id, "pred_action"]
        )

    return final.reset_index().sort_values(
        "score",
        ascending=False,
        kind="mergesort"
    )


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    rate = float((final.pred_action == "RECAPTURE").mean())

    by_type = final.loc[
        final.pred_action == "RECAPTURE",
        "pred_defect_type"
    ].value_counts().to_dict()

    owner = ctx.config.get("owner", "QC lead")

    evidence = [
        str(ctx.out("ranked_review.csv")),
        str(ctx.out("contact_sheet.html"))
    ]

    if rate > 0.6:
        return Decision(
            status="REWORK",
            reason_code="DEFECT_RATE_HIGH",
            reason=f"{rate:.0%} ảnh cần chụp lại {by_type} — batch không dùng được",
            owner=owner,
            scope=ctx.track,
            evidence=evidence
        )

    if rate > 0.1:
        return Decision(
            status="HOLD",
            reason_code="RECAPTURE_NEEDED",
            reason=f"{rate:.0%} ảnh nghi lỗi {by_type}: chụp lại các ảnh RECAPTURE trước khi release",
            owner=owner,
            scope=ctx.track,
            evidence=evidence
        )

    return Decision(
        status="GO",
        reason_code="QC_PASS",
        reason=f"Chỉ {rate:.0%} ảnh nghi lỗi",
        owner=owner,
        scope=ctx.track,
        evidence=evidence
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)

    ctx.stats["n_items"] = len(scored)

    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)

    final[
        spec.pred_columns + [
            c for c in final.columns
            if c not in spec.pred_columns
        ]
    ].to_csv(ctx.out(spec.pred_file), index=False)

    write_decision(
        decide(ctx, final),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv")
    )