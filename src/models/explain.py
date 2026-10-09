"""
src/models/explain.py
SHAP TreeExplainer mapped back to biological coordinates (marker_id, chrom, pos).
Per Section 6.7 of spec.md.
"""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import shap


def explain_model_predictions(
    model,
    X_sample: np.ndarray,
    env_name: str,
    feature_metadata: dict,
    top_k: int = 10,
) -> list[dict]:
    """
    Compute SHAP attribution for a single sample and map back to biological coordinates:
    [marker_id, chrom, pos, shap_value].
    """
    marker_ids = feature_metadata["marker_ids"]
    environments = feature_metadata["environments"]

    # Construct joint feature row: [X_geno | One-Hot Environments]
    env_one_hot = np.zeros(len(environments), dtype=float)
    if env_name in environments:
        env_one_hot[environments.index(env_name)] = 1.0
    elif env_name == "across_environments":
        env_one_hot[:] = 1.0 / len(environments)

    x_joint = np.hstack([X_sample.ravel(), env_one_hot]).reshape(1, -1)

    # Use TreeExplainer on underlying XGBoost model if GxEXGBoostModel
    underlying_model = getattr(model, "model_", model)
    explainer = shap.TreeExplainer(underlying_model)
    shap_values = explainer.shap_values(x_joint)[0]

    # Only map genomic marker SHAP values (exclude one-hot environment features)
    marker_shap = shap_values[: len(marker_ids)]

    # Get top_k markers by absolute SHAP magnitude
    top_indices = np.argsort(np.abs(marker_shap))[::-1][:top_k]

    attributions = []
    for idx in top_indices:
        m_id = marker_ids[idx]
        # Parse chromosome and position if synthesized or from ID (e.g. S1_11984 -> chrom 1, pos 11984)
        chrom = "unknown"
        pos = 0
        if "_" in m_id:
            parts = m_id.split("_")
            chrom = parts[0].replace("S", "")
            try:
                pos = int(parts[1])
            except ValueError:
                pass

        attributions.append({
            "marker_id": m_id,
            "chrom": chrom,
            "pos": pos,
            "shap_value": float(marker_shap[idx]),
            "dosage": float(X_sample.ravel()[idx]),
        })

    return attributions
