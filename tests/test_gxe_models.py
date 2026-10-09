"""
tests/test_gxe_models.py
Unit tests for GxE models (Ridge baseline, XGBoost challenger) and Validation Gate pass/fail logic.
"""
import numpy as np
import pytest

from src.models.gxe import GxERidgeModel, GxEXGBoostModel
from src.models.gate import evaluate_validation_gate


def test_gxe_ridge_model():
    """Verify GxE Ridge model fits environmental effects and decomposes predictions."""
    rng = np.random.RandomState(42)
    N = 100
    M = 20
    X_geno = rng.binomial(n=2, p=0.4, size=(N, M)).astype(float)
    envs = rng.choice(["2009_DS", "2009_WS", "2010_DS"], size=N)

    # True model: genetic signal + environment shift
    env_shifts = {"2009_DS": 500.0, "2009_WS": -300.0, "2010_DS": 100.0}
    env_term = np.array([env_shifts[e] for e in envs])
    true_beta = rng.normal(0, 10, size=M)
    y = 5000.0 + env_term + (X_geno @ true_beta) + rng.normal(0, 20, size=N)

    model = GxERidgeModel()
    model.fit(X_geno, envs, y)

    # Predict specific environment
    preds_ds = model.predict(X_geno[:5], "2009_DS")
    assert len(preds_ds) == 5
    assert not np.isnan(preds_ds).any()

    # Predict across environments
    preds_across = model.predict(X_geno[:5], "across_environments")
    assert len(preds_across) == 5
    # 2009_DS shift was +500, so 2009_DS preds should be systematically higher than across_environments
    assert np.mean(preds_ds) > np.mean(preds_across)


def test_gxe_xgboost_model():
    """Verify GxE XGBoost challenger fits and predicts with environment conditioning."""
    rng = np.random.RandomState(42)
    N = 80
    M = 15
    X_geno = rng.binomial(n=2, p=0.4, size=(N, M)).astype(float)
    envs = rng.choice(["2011_DS", "2011_WS"], size=N)
    y = 4000.0 + (X_geno[:, 0] * 50) + rng.normal(0, 20, size=N)

    model = GxEXGBoostModel(n_estimators=20, max_depth=3)
    model.fit(X_geno, envs, y)

    preds = model.predict(X_geno[:5], "2011_DS")
    assert len(preds) == 5
    assert not np.isnan(preds).any()


def test_validation_gate_pass_and_fail():
    """Prove that the Validation Gate passes good models and rejects weakened models."""
    # Case 1: Challenger strictly beats baseline and folds are stable
    passing_results = {
        "crop_name": "rice",
        "target_trait": "grain_yield",
        "baseline": {
            "mean_r": 0.45,
            "mean_rmse": 500.0,
            "fold_metrics": [{"pearson_r": 0.44}, {"pearson_r": 0.46}],
        },
        "challenger": {
            "mean_r": 0.52,  # Higher r
            "mean_rmse": 470.0,
            "fold_metrics": [{"pearson_r": 0.50}, {"pearson_r": 0.54}],
        },
    }
    report_pass = evaluate_validation_gate(passing_results, crop_name="rice")
    assert report_pass["status"] == "PASSED"
    assert report_pass["checks"]["beats_baseline"]["passed"] is True

    # Case 2: Weakened challenger that regresses against baseline
    failing_results = {
        "crop_name": "rice",
        "target_trait": "grain_yield",
        "baseline": {
            "mean_r": 0.55,
            "mean_rmse": 450.0,
            "fold_metrics": [{"pearson_r": 0.54}, {"pearson_r": 0.56}],
        },
        "challenger": {
            "mean_r": 0.40,  # Weakened, worse than baseline
            "mean_rmse": 600.0,
            "fold_metrics": [{"pearson_r": 0.20}, {"pearson_r": 0.60}],  # Extreme fold regression
        },
    }
    report_fail = evaluate_validation_gate(failing_results, crop_name="rice")
    assert report_fail["status"] == "FAILED"
    assert report_fail["checks"]["beats_baseline"]["passed"] is False
