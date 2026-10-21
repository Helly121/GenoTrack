"""
src/models/registry.py
Model Registry promotion and automated Model Card generation.
Per Section 6.6 of spec.md:
- Promotes models passing validation gate to Staging and Production.
- Attaches full lineage tags (data hash, config hash, CV strategy, gate report).
- Auto-generates Markdown MODEL_CARD.md.
"""
from datetime import datetime
import json
from pathlib import Path
import shutil


def promote_and_generate_model_card(
    training_results: dict | Path,
    gate_report: dict | Path,
    stage: str = "Production",
    project_root: Path | None = None,
) -> dict:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    if isinstance(training_results, (str, Path)):
        with open(training_results, "r") as f:
            training_results = json.load(f)
    if isinstance(gate_report, (str, Path)):
        with open(gate_report, "r") as f:
            gate_report = json.load(f)

    if gate_report["status"] != "PASSED":
        raise ValueError(
            f"Cannot promote model: Validation gate status is {gate_report['status']}."
        )

    crop_name = training_results["crop_name"]
    trait = training_results["target_trait"]
    models_dir = project_root / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Production model file
    challenger_src = Path(training_results["challenger"]["model_path"])
    production_model_path = models_dir / f"production_{crop_name}_{trait}.joblib"
    shutil.copy2(challenger_src, production_model_path)

    # Lineage metadata
    metadata = {
        "crop": crop_name,
        "trait": trait,
        "stage": stage,
        "promoted_at": datetime.utcnow().isoformat() + "Z",
        "mean_r": training_results["challenger"]["mean_r"],
        "mean_rmse": training_results["challenger"]["mean_rmse"],
        "data_hash": training_results["data_hash"],
        "config_hash": training_results["config_hash"],
        "run_id": training_results.get("run_id"),
        "model_file": str(production_model_path.name),
        "gate_status": gate_report["status"],
    }

    metadata_path = models_dir / f"production_{crop_name}_{trait}.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    # MLflow Model Registry synchronization
    if metadata.get("run_id"):
        try:
            import mlflow
            from mlflow.tracking import MlflowClient
            db_path = project_root / "mlflow.db"
            mlflow.set_tracking_uri(f"sqlite:///{db_path.as_posix()}")
            client = MlflowClient()
            model_name = "GenoTrack-GxE-Yield"
            try:
                client.create_registered_model(model_name)
            except Exception:
                pass
            v = client.create_model_version(
                name=model_name,
                source=f"runs:/{metadata['run_id']}/models",
                run_id=metadata["run_id"],
                description=f"Auto-promoted {crop_name} {trait} model ({stage}).",
            )
            client.transition_model_version_stage(
                name=model_name,
                version=v.version,
                stage=stage,
            )
            print(f"[{crop_name}] Synchronized with MLflow Model Registry ({model_name} v{v.version} -> {stage})")
        except Exception as e:
            print(f"[{crop_name}] MLflow registry sync notice: {e}")

    # Generate Markdown Model Card
    model_card_content = f"""# GenoTrack Model Card: {crop_name.capitalize()} — {trait.replace('_', ' ').title()}

## Model Summary
- **Crop:** {crop_name}
- **Target Trait:** {trait}
- **Model Architecture:** GxE XGBoost Regressor (Additive Genetic + Environmental Interaction)
- **Deployment Stage:** `{stage}`
- **Promotion Timestamp:** `{metadata['promoted_at']}`

## Lineage & Governance
- **Data Hash (SHA256):** `{training_results['data_hash']}`
- **Config Hash (SHA256):** `{training_results['config_hash']}`
- **MLflow Run ID:** `{training_results.get('run_id')}`
- **Validation Gate Decision:** `{gate_report['status']}`

## Cross-Validation Performance
- **Challenger Mean Pearson $r$:** `{training_results['challenger']['mean_r']:.4f}`
- **Challenger Mean RMSE:** `{training_results['challenger']['mean_rmse']:.2f}`
- **Baseline (Ridge) Mean Pearson $r$:** `{training_results['baseline']['mean_r']:.4f}`
- **Net Relative Improvement:** `{training_results['challenger']['mean_r'] - training_results['baseline']['mean_r']:+.4f}`

### Per-Fold Stability
| Fold | Challenger Pearson $r$ | Baseline Pearson $r$ |
|---|---|---|
"""
    for i, (c_m, b_m) in enumerate(zip(training_results["challenger"]["fold_metrics"], training_results["baseline"]["fold_metrics"])):
        model_card_content += f"| Fold {i+1} | {c_m['pearson_r']:.4f} | {b_m['pearson_r']:.4f} |\n"

    model_card_content += f"""
## Environmental Generalization
Evaluated across all observed trial seasons. Model is actively aware of environment-specific main effects and reaction norm interactions.

## Intended Use & Limitations
- **Intended Use:** Genomic selection ranking and expected yield predictions in targeted agricultural environments.
- **Limitations:** Predictions are conditioned on the genetic background of the diversity panel and the environmental bounds of the training seasons.
"""

    model_card_path = models_dir / f"MODEL_CARD_{crop_name}_{trait}.md"
    with open(model_card_path, "w") as f:
        f.write(model_card_content)

    print(f"[{crop_name}] Generated Model Card: {model_card_path.name}")
    return metadata
