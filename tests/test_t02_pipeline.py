"""Tests của nhóm cho T02 pipeline: 1 success case + 2 edge/failure case."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import blockiness, defect_scores, image_features, local_saturation

FIX = Path("fixtures/t02_raw_qc/images")


def test_known_defects_score_high_and_clean_low():
    """Success: ảnh nhòe / vỡ nén / tối / lóa đã biết bị chấm >= 0.5, ảnh sạch < 0.5."""
    cases = {"img_09_2": "blur", "img_00_2": "compression", "img_17_3": "dark", "img_02_2": "glare",
             "img_02_0": "none", "img_13_0": "none"}
    images = pd.read_csv("fixtures/t02_raw_qc/images.csv")
    feats = pd.DataFrame([image_features(FIX.parent / p) for p in images.path])
    scored = defect_scores(pd.concat([images, feats], axis=1)).set_index("image_id")
    for img, expected in cases.items():
        assert scored.loc[img, "pred_defect_type"] == expected, img


def test_night_image_is_not_flagged_dark():
    """Edge: ảnh đêm sạch (tối tự nhiên) không được báo 'dark' nhờ chuẩn hoá theo light."""
    images = pd.read_csv("fixtures/t02_raw_qc/images.csv")
    feats = pd.DataFrame([image_features(FIX.parent / p) for p in images.path])
    scored = defect_scores(pd.concat([images, feats], axis=1)).set_index("image_id")
    assert scored.loc["img_01_0", "s_dark"] == 0.0
    assert scored.loc["img_01_0", "pred_action"] == "KEEP"


def test_synthetic_edge_cases():
    """Edge: ảnh đồng màu không gây chia 0; ô cháy sáng cục bộ được phát hiện."""
    flat = np.full((180, 320), 128, dtype=np.float32)
    assert np.isfinite(blockiness(flat))
    glare = flat.copy()
    glare[40:60, 100:120] = 255
    assert local_saturation(glare) == pytest.approx(1.0)
    assert local_saturation(flat) == 0.0
