"""
src/models/gate.py
Automated validation gate per Section 6.5 of spec.md.
Evaluates challenger against baseline and production bar:
1. Challenger mean CV Pearson r >= baseline mean r (or configured relative margin).
2. No single fold regresses beyond configured margin below mean.
3. No regression against current Production model if one exists.
Outputs structured evaluation report.
"""
import json
from pathlib import Path
import yaml


def evaluate_validation_gate(
    training_results: dict | Path,
    crop_name: str = "rice",
    project_root: Path | None = None,
) -> dict:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    if isinstance(training_results, (str, Path)):
        with open(training_results, "r") as f:
            training_results = json.load(f)

    config_path = project_root / "crops" / crop_name / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    gate_cfg = config["modeling"].get("gate", {})
    min_rel_improv = float(gate_cfg.get("min_relative_improvement_over_baseline", 0.0))
    max_fold_regress = float(gate_cfg.get("max_single_fold_regression", 0.05))

    baseline_r = training_results["baseline"]["mean_r"]
    challenger_r = training_results["challenger"]["mean_r"]
    challenger_folds = [m["pearson_r"] for m in training_results["challenger"]["fold_metrics"]]

    # Check 1: Relative improvement over baseline
    rel_improv = challenger_r - baseline_r
    check_baseline_pass = rel_improv >= min_rel_improv

    # Check 2: Single fold regression limit
    fold_regressions = [challenger_r - fold_r for fold_r in challenger_folds]
    max_observed_regression = max(fold_regressions) if fold_regressions else 0.0
    check_fold_stability_pass = max_observed_regression <= max_fold_regress

    # Check 3: Current Production baseline comparison
    prod_registry_file = project_root / "data" / "models" / f"production_{crop_name}_{training_results['target_trait']}.json"
    prod_model_r = None
    check_prod_pass = True

    if prod_registry_file.exists():
        with open(prod_registry_file, "r") as f:
            prod_meta = json.load(f)
            prod_model_r = prod_meta.get("mean_r", 0.0)
            if challenger_r < prod_model_r:
                check_prod_pass = False

    overall_pass = bool(check_baseline_pass and check_fold_stability_pass and check_prod_pass)

    report = {
        "status": "PASSED" if overall_pass else "FAILED",
        "crop_name": crop_name,
        "target_trait": training_results["target_trait"],
        "run_id": training_results.get("run_id"),
        "checks": {
            "beats_baseline": {
                "passed": bool(check_baseline_pass),
                "challenger_mean_r": challenger_r,
                "baseline_mean_r": baseline_r,
                "relative_improvement": rel_improv,
                "required_threshold": min_rel_improv,
            },
            "fold_stability": {
                "passed": bool(check_fold_stability_pass),
                "max_observed_fold_regression": max_observed_regression,
                "allowed_margin": max_fold_regress,
                "fold_values": challenger_folds,
            },
            "beats_current_production": {
                "passed": bool(check_prod_pass),
                "current_production_r": prod_model_r,
                "challenger_r": challenger_r,
            },
        },
        "recommendation": (
            "Promote to Staging/Production" if overall_pass else "Reject run: Model failed validation gate."
        ),
    }

    # Save report
    processed_dir = project_root / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_file = processed_dir / f"validation_gate_report_{training_results['target_trait']}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    return report
