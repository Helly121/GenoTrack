"""
tests/test_features.py
Unit tests for ploidy-parameterized dosage encoding, Patterson scaling, and CV partitioning.
"""
import numpy as np
import pandas as pd
import pytest

from src.features.encoding import encode_dosage_vectorized
from src.features.imputation import impute_dosage
from src.features.split import patterson_scaling, compute_population_clusters, build_cv_splits
from tests.fixtures.synthetic_crop import generate_synthetic_genotype


def test_dosage_encoding_diploid():
    """Verify diploid (ploidy=2) dosage encoding produces values in {0, 1, 2} or NaN."""
    call_matrix, marker_meta = generate_synthetic_genotype(n_markers=20, n_samples=10, ploidy=2)
    dosage = encode_dosage_vectorized(call_matrix, marker_meta, ploidy=2)

    assert dosage.shape == (10, 20)
    vals = dosage.values[~np.isnan(dosage.values)]
    assert set(np.unique(vals)).issubset({0.0, 1.0, 2.0})


def test_dosage_encoding_hexaploid():
    """Verify hexaploid (ploidy=6) dosage encoding generalizes to 0..6 scale."""
    call_matrix, marker_meta = generate_synthetic_genotype(n_markers=20, n_samples=10, ploidy=6)
    dosage = encode_dosage_vectorized(call_matrix, marker_meta, ploidy=6)

    assert dosage.shape == (10, 20)
    vals = dosage.values[~np.isnan(dosage.values)]
    assert np.all(vals >= 0.0) and np.all(vals <= 6.0)


def test_imputation_strategies():
    """Verify all 4 swappable imputation strategies eliminate NaNs."""
    df = pd.DataFrame({
        "M1": [0.0, np.nan, 2.0],
        "M2": [1.0, 1.0, np.nan],
    })

    for strat in ["per_marker_mean", "median", "mode", "zero"]:
        imputed = impute_dosage(df, strategy=strat)
        assert not imputed.isna().any().any()
        assert imputed.shape == df.shape


def test_patterson_scaling():
    """Verify Patterson scaling standardizes matrix by allele frequency."""
    rng = np.random.RandomState(42)
    # 50 samples, 10 markers
    X = rng.binomial(n=2, p=0.3, size=(50, 10)).astype(float)
    Z = patterson_scaling(X, ploidy=2)

    assert Z.shape == X.shape
    # Means across samples should be approximately zero
    means = np.mean(Z, axis=0)
    assert np.all(np.abs(means) < 1e-6)


def test_population_clustering_guardrails():
    """Verify cluster size guardrail prevents degenerate clusters."""
    rng = np.random.RandomState(42)
    # 60 samples, 20 markers
    X = pd.DataFrame(
        rng.binomial(n=2, p=0.3, size=(60, 20)).astype(float),
        index=[f"S_{i}" for i in range(60)],
        columns=[f"M_{j}" for j in range(20)],
    )

    clusters = compute_population_clusters(
        X,
        n_clusters=3,
        n_pcs=5,
        ploidy=2,
        min_cluster_size=10,
    )
    assert len(clusters) == 60
    assert clusters.nunique() == 3

    # Check CV splits
    splits = build_cv_splits(sample_ids=X.index, clusters=clusters, n_folds=3)
    assert len(splits) == 3
    for train_idx, test_idx in splits:
        assert len(train_idx) > 0
        assert len(test_idx) > 0
        assert len(set(train_idx).intersection(set(test_idx))) == 0
