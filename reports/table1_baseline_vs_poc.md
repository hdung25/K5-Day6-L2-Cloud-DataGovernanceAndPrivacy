Baseline: `baseline` (git 9538aa6, seed 42) · PoC: `poc` (git 9538aa6, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (GT defects in top-B / GT defects) | all | 0.8500 | 1.0000 | 0.1500 | +17.6% | higher | 40 |
| Precision@B (GT defects in top-B / B) | all | 0.8500 | 1.0000 | 0.1500 | +17.6% | higher | 40 |
| Defect-type accuracy (GT defects) (fraction) | all | n/a | 0.9500 | n/a | n/a | higher | 20 |
| False alarm in top-B (clean images in top-B / clean images) | light=day | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 20 |
| False alarm in top-B (clean images in top-B / clean images) | light=dusk | 0.5000 | 0.0000 | -0.5000 | -100.0% | lower | 4 |
| False alarm in top-B (clean images in top-B / clean images) | light=night | 0.2500 | 0.0000 | -0.2500 | -100.0% | lower | 16 |
| Runtime / 100 items (s) | all | 0.2435 | 0.5050 | | | lower | |
