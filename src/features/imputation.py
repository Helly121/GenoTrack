"""
src/features/imputation.py
Swappable missing dosage imputation strategies per Section 6.3 of spec.md.
"""
import numpy as np
import pandas as pd


def impute_dosage(
    dosage_matrix: pd.DataFrame,
    strategy: str = "per_marker_mean",
) -> pd.DataFrame:
    """
    Impute missing dosage values in a sample-by-marker DataFrame.
    Parameters:
        dosage_matrix: (N samples x M markers) DataFrame containing dosages or NaN
        strategy: 'per_marker_mean' | 'median' | 'mode' | 'zero'
    Returns:
        DataFrame with no NaNs
    """
    df = dosage_matrix.copy()

    if strategy == "per_marker_mean":
        means = df.mean(axis=0)
        # Fallback for any entirely NaN marker
        means = means.fillna(0.0)
        return df.fillna(means)

    elif strategy == "median":
        medians = df.median(axis=0)
        medians = medians.fillna(0.0)
        return df.fillna(medians)

    elif strategy == "mode":
        # Mode per column
        modes = df.mode(axis=0).iloc[0]
        modes = modes.fillna(0.0)
        return df.fillna(modes)

    elif strategy == "zero":
        return df.fillna(0.0)

    else:
        raise ValueError(
            f"Unknown imputation strategy: '{strategy}'. "
            "Supported strategies: 'per_marker_mean', 'median', 'mode', 'zero'"
        )
