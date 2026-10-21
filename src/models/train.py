"""
src/models/train.py
Cross-validated model training orchestrator with MLflow tracking.
Fits GxE baseline (Ridge) and challenger (XGBoost) models.
Computes fold-level and per-environment Pearson r, RMSE, and MAE.
"""
import hashlib
import json
from pathlib import Path
import joblib
import mlflow
import numpy as np
import pandas as pd
from scipy import stats
import yaml

from .baseline import get_baseline_model
from .challenger import get_challenger_model
from ..features.split import build_cv_splits


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calculate Pearson r, RMSE, MAE."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    valid_mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    if valid_mask.sum() < 2:
        return {"pearson_r": 0.0, "rmse": float("inf"), "mae": float("inf")}

    yt = y_true[valid_mask]
    yp = y_pred[valid_mask]

    # Handle zero variance edge case
    if np.std(yt) < 1e-9 or np.std(yp) < 1e-9:
        r = 0.0
    else:
        r, _ = stats.pearsonr(yt, yp)
        r = float(r) if not np.isnan(r) else 0.0

    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    mae = float(np.mean(np.abs(yt - yp)))
    return {"pearson_r": r, "rmse": rmse, "mae": mae}


def train_and_track(
    crop_name: str = "rice",
    target_trait: str = "grain_yield",
    project_root: Path | None = None,
) -> dict:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    config_path = project_root / "crops" / crop_name / "config.yaml"
    processed_dir = project_root / "data" / "processed"
    models_dir = project_root / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    dataset_path = processed_dir / f"model_dataset_{target_trait}.parquet"
    if not dataset_path.exists():
        raise FileNotFoundError(f"Model dataset not found at {dataset_path}. Run features first.")

    meta_path = processed_dir / "feature_metadata.json"
    with open(meta_path, "r") as f:
        metadata = json.load(f)

    # Hash tracking for reproducibility (spec Section 3.4)
    data_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()

    print(f"[{crop_name}] Loading model dataset for '{target_trait}'...")
    df_data = pd.read_parquet(dataset_path)

    # Extract target y, environments E, and marker matrix X
    marker_cols = metadata["marker_ids"]
    X_geno = df_data[marker_cols].values.astype(np.float32)
    envs = df_data["environment"].values
    y = df_data["value"].values.astype(np.float32)
    sample_ids = df_data["sample_id"].values
    clusters = df_data["subpopulation_cluster"]
    n_obs = len(df_data)
    del df_data
    import gc
    gc.collect()

    n_folds = int(config["cv"].get("n_folds", 5))

    # Set up MLflow with SQLite backend
    db_path = project_root / "mlflow.db"
    mlflow.set_tracking_uri(f"sqlite:///{db_path.as_posix()}")
    experiment_name = f"genotrack_{crop_name}_{target_trait}"
    mlflow.set_experiment(experiment_name)

    # Build population-structure-aware CV splits
    print(f"[{crop_name}] Building {n_folds}-fold population-structure-aware CV splits...")
    splits = build_cv_splits(
        sample_ids=sample_ids,
        clusters=clusters,
        environments=envs,
        n_folds=n_folds,
        cv_type="within_environment",
    )

    with mlflow.start_run(run_name=f"run_{crop_name}_{target_trait}") as parent_run:
        mlflow.log_params({
            "crop": crop_name,
            "target_trait": target_trait,
            "n_samples": metadata["n_samples"],
            "n_markers": metadata["n_markers"],
            "n_observations": len(y),
            "n_environments": len(metadata["environments"]),
            "cv_strategy": "population_structure_stratified",
            "n_folds": n_folds,
            "data_hash": data_hash[:12],
            "config_hash": config_hash[:12],
        })

        # 1. Train & Evaluate Baseline (Ridge)
        print(f"[{crop_name}] Evaluating GxE Baseline (Ridge)...")
        baseline_fold_metrics = []
        baseline_oof_preds = np.zeros(len(y))

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            m_base = get_baseline_model()
            m_base.fit(X_geno[train_idx], envs[train_idx], y[train_idx])
            preds = m_base.predict(X_geno[test_idx], envs[test_idx])
            baseline_oof_preds[test_idx] = preds

            fold_met = compute_metrics(y[test_idx], preds)
            baseline_fold_metrics.append(fold_met)

        baseline_overall = compute_metrics(y, baseline_oof_preds)
        baseline_mean_r = float(np.mean([m["pearson_r"] for m in baseline_fold_metrics]))
        baseline_mean_rmse = float(np.mean([m["rmse"] for m in baseline_fold_metrics]))

        print(f"[{crop_name}] Baseline Mean CV r: {baseline_mean_r:.4f}, RMSE: {baseline_mean_rmse:.2f}")

        # 2. Train & Evaluate Challenger (XGBoost)
        print(f"[{crop_name}] Evaluating GxE Challenger (XGBoost)...")
        challenger_fold_metrics = []
        challenger_oof_preds = np.zeros(len(y))

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            m_chal = get_challenger_model(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.05,
                random_state=42 + fold_idx,
            )
            m_chal.fit(X_geno[train_idx], envs[train_idx], y[train_idx])
            preds = m_chal.predict(X_geno[test_idx], envs[test_idx])
            challenger_oof_preds[test_idx] = preds

            fold_met = compute_metrics(y[test_idx], preds)
            challenger_fold_metrics.append(fold_met)

        challenger_overall = compute_metrics(y, challenger_oof_preds)
        challenger_mean_r = float(np.mean([m["pearson_r"] for m in challenger_fold_metrics]))
        challenger_mean_rmse = float(np.mean([m["rmse"] for m in challenger_fold_metrics]))

        print(f"[{crop_name}] Challenger Mean CV r: {challenger_mean_r:.4f}, RMSE: {challenger_mean_rmse:.2f}")

        # Per-environment metric breakdown
        env_metrics = {}
        for env_name in np.unique(envs):
            mask = (envs == env_name)
            env_metrics[env_name] = {
                "baseline": compute_metrics(y[mask], baseline_oof_preds[mask]),
                "challenger": compute_metrics(y[mask], challenger_oof_preds[mask]),
            }

        # Log metrics to MLflow
        mlflow.log_metrics({
            "baseline_mean_r": baseline_mean_r,
            "baseline_mean_rmse": baseline_mean_rmse,
            "challenger_mean_r": challenger_mean_r,
            "challenger_mean_rmse": challenger_mean_rmse,
            "relative_r_improvement": challenger_mean_r - baseline_mean_r,
        })

        for i, (b_m, c_m) in enumerate(zip(baseline_fold_metrics, challenger_fold_metrics)):
            mlflow.log_metric(f"fold_{i}_baseline_r", b_m["pearson_r"])
            mlflow.log_metric(f"fold_{i}_challenger_r", c_m["pearson_r"])

        # Train full models on entire dataset for production serving
        print(f"[{crop_name}] Training full production models on entire dataset...")
        final_baseline = get_baseline_model()
        final_baseline.fit(X_geno, envs, y)

        final_challenger = get_challenger_model(n_estimators=120, max_depth=4, learning_rate=0.05)
        final_challenger.fit(X_geno, envs, y)

        # Save artifacts
        baseline_path = models_dir / f"baseline_{crop_name}_{target_trait}.joblib"
        challenger_path = models_dir / f"challenger_{crop_name}_{target_trait}.joblib"
        joblib.dump(final_baseline, baseline_path)
        joblib.dump(final_challenger, challenger_path)

        mlflow.log_artifact(str(baseline_path), "models")
        mlflow.log_artifact(str(challenger_path), "models")

        results = {
            "crop_name": crop_name,
            "target_trait": target_trait,
            "run_id": parent_run.info.run_id,
            "data_hash": data_hash,
            "config_hash": config_hash,
            "baseline": {
                "mean_r": baseline_mean_r,
                "mean_rmse": baseline_mean_rmse,
                "fold_metrics": baseline_fold_metrics,
                "model_path": str(baseline_path),
            },
            "challenger": {
                "mean_r": challenger_mean_r,
                "mean_rmse": challenger_mean_rmse,
                "fold_metrics": challenger_fold_metrics,
                "model_path": str(challenger_path),
            },
            "per_environment_metrics": env_metrics,
        }

        eval_path = processed_dir / f"training_results_{target_trait}.json"
        with open(eval_path, "w") as f:
            json.dump(results, f, indent=2)

        return results


if __name__ == "__main__":
    train_and_track("rice", "grain_yield")
