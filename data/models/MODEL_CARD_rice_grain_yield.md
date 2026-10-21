# GenoTrack Model Card: Rice — Grain Yield

## Model Summary
- **Crop:** rice
- **Target Trait:** grain_yield
- **Model Architecture:** GxE XGBoost Regressor (Additive Genetic + Environmental Interaction)
- **Deployment Stage:** `Staging`
- **Promotion Timestamp:** `2026-10-21T18:28:51.755236Z`

## Lineage & Governance
- **Data Hash (SHA256):** `3a99d12961a269ee498c85435ebfecdb007f0ff9abf2f01f95716de04c6866e9`
- **Config Hash (SHA256):** `22d3ec0c3f95c6d6d45fac63fa24bcca13c475a3728f92d8d9da37a2975013f5`
- **MLflow Run ID:** `0abeca497d1542ee849b7f754ea80233`
- **Validation Gate Decision:** `PASSED`

## Cross-Validation Performance
- **Challenger Mean Pearson $r$:** `0.8122`
- **Challenger Mean RMSE:** `768.76`
- **Baseline (Ridge) Mean Pearson $r$:** `0.7957`
- **Net Relative Improvement:** `+0.0165`

### Per-Fold Stability
| Fold | Challenger Pearson $r$ | Baseline Pearson $r$ |
|---|---|---|
| Fold 1 | 0.8130 | 0.7900 |
| Fold 2 | 0.8082 | 0.7900 |
| Fold 3 | 0.8283 | 0.8059 |
| Fold 4 | 0.8189 | 0.7957 |
| Fold 5 | 0.7927 | 0.7969 |

## Environmental Generalization
Evaluated across all observed trial seasons. Model is actively aware of environment-specific main effects and reaction norm interactions.

## Intended Use & Limitations
- **Intended Use:** Genomic selection ranking and expected yield predictions in targeted agricultural environments.
- **Limitations:** Predictions are conditioned on the genetic background of the diversity panel and the environmental bounds of the training seasons.
