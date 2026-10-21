"""
pipelines/flow.py
Metaflow Pipeline Specification for GenoTrack with Visual Cards.
Orchestrates: setup_data -> ingest -> clean -> features -> train -> validation_gate -> register -> end
"""
import sys
from pathlib import Path

# Add project root to sys.path so modules resolve cleanly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure Windows/POSIX compatibility shim before importing Metaflow
import pipelines.compat

from metaflow import FlowSpec, Parameter, card, current, step
from metaflow.cards import Markdown, Table

from pipelines.setup_data import setup_rice_data
from src.ingest.pipeline import run_ingestion
from src.clean.qc import run_qc
from src.features.pipeline import run_features
from src.models.train import train_and_track
from src.models.gate import evaluate_validation_gate
from src.models.registry import promote_and_generate_model_card


class GenoTrackFlow(FlowSpec):
    """
    End-to-End MLOps Pipeline for Genomic Selection & GxE Yield Prediction.
    """

    crop_name = Parameter(
        "crop_name",
        help="Crop identifier (e.g. 'rice')",
        default="rice",
    )

    target_trait = Parameter(
        "target_trait",
        help="Target phenotypic trait (e.g. 'grain_yield')",
        default="grain_yield",
    )

    @step
    def start(self):
        """Pipeline entrypoint and environment validation."""
        self.project_root = Path(__file__).resolve().parents[1]
        print(f"Starting GenoTrackFlow for crop='{self.crop_name}', trait='{self.target_trait}'")
        print(f"Workspace root: {self.project_root}")
        self.next(self.setup_data)

    @card
    @step
    def setup_data(self):
        """Prepare raw data files in data/raw/<crop>/."""
        print(f"[{self.crop_name}] Setting up raw data layout...")
        setup_rice_data(project_root=self.project_root)
        current.card.append(Markdown("# Stage: Raw Data Setup"))
        current.card.append(Markdown(f"Raw data layout established under `data/raw/{self.crop_name}/`."))
        self.next(self.ingest)

    @card
    @step
    def ingest(self):
        """Parse raw files through the crop adapter into canonical Parquet tables."""
        print(f"[{self.crop_name}] Running ingestion adapter...")
        self.ingest_stats = run_ingestion(crop_name=self.crop_name, project_root=self.project_root)

        current.card.append(Markdown("# Stage: Data Ingestion"))
        current.card.append(
            Table(
                [
                    ["Genotype Canonical Rows", f"{self.ingest_stats.get('canonical_genotype_rows', 0):,}"],
                    ["Phenotype Canonical Rows", f"{self.ingest_stats.get('canonical_phenotype_rows', 0):,}"],
                    ["Quarantined Ingest Records", f"{self.ingest_stats.get('quarantined_records', 0):,}"],
                ],
                headers=["Metric", "Value"],
            )
        )
        self.next(self.clean)

    @card
    @step
    def clean(self):
        """Apply MAF filtering, missingness filtering, and Pandera QC."""
        print(f"[{self.crop_name}] Running Quality Control & Hygiene...")
        self.qc_stats = run_qc(crop_name=self.crop_name, project_root=self.project_root)

        current.card.append(Markdown("# Stage: Quality Control & Hygiene"))
        current.card.append(
            Table(
                [
                    ["Cleaned Markers", f"{self.qc_stats.get('retained_markers', 0):,}"],
                    ["Cleaned Accessions", f"{self.qc_stats.get('retained_samples', 0):,}"],
                    ["Excluded by MAF (< 0.05)", f"{self.qc_stats.get('excluded_by_maf', 0):,}"],
                    ["Excluded by Missingness (> 20%)", f"{self.qc_stats.get('excluded_by_missingness', 0):,}"],
                ],
                headers=["QC Filter", "Count"],
            )
        )
        self.next(self.features)

    @card
    @step
    def features(self):
        """Extract marker dosage matrix, VanRaden kinship, and Patterson PCA clusters."""
        print(f"[{self.crop_name}] Running Feature Engineering & Population Structure Split...")
        self.feature_stats = run_features(
            crop_name=self.crop_name,
            target_trait=self.target_trait,
            project_root=self.project_root,
        )

        current.card.append(Markdown("# Stage: Feature Engineering & Population Structure"))
        current.card.append(
            Table(
                [
                    ["Dosage Matrix Dimensions", f"{self.feature_stats.get('n_samples', 0)} samples × {self.feature_stats.get('n_markers', 0)} markers"],
                    ["Model Dataset Rows", f"{self.feature_stats.get('model_dataset_rows', 0):,}"],
                    ["CV Stratification Strategy", self.feature_stats.get("cv_strategy", "Kinship / PCA-stratified")],
                    ["PCA Dimensions Explaining Variance", str(self.feature_stats.get("n_pca_components", 10))],
                ],
                headers=["Feature Dimension", "Specification"],
            )
        )
        self.next(self.train)

    @card
    @step
    def train(self):
        """Train classical GBLUP baseline and GxE-XGBoost challenger with MLflow tracking."""
        print(f"[{self.crop_name}] Training GBLUP baseline and GxE-XGBoost challenger...")
        self.training_results = train_and_track(
            crop_name=self.crop_name,
            target_trait=self.target_trait,
            project_root=self.project_root,
        )

        b_r = self.training_results["baseline"]["mean_r"]
        b_rmse = self.training_results["baseline"]["mean_rmse"]
        c_r = self.training_results["challenger"]["mean_r"]
        c_rmse = self.training_results["challenger"]["mean_rmse"]

        current.card.append(Markdown("# Stage: Cross-Validated Model Training"))
        current.card.append(
            Table(
                [
                    ["GBLUP Baseline (Linear Additive)", f"r = {b_r:.4f}", f"RMSE = {b_rmse:.2f} kg/ha"],
                    ["GxE-XGBoost Challenger (Interaction)", f"r = {c_r:.4f}", f"RMSE = {c_rmse:.2f} kg/ha"],
                ],
                headers=["Candidate Architecture", "Mean Pearson r", "Mean RMSE"],
            )
        )
        self.next(self.validation_gate)

    @card
    @step
    def validation_gate(self):
        """Automated decision gate evaluating candidate performance and fold stability."""
        print(f"[{self.crop_name}] Evaluating Validation Gate criteria...")
        self.gate_report = evaluate_validation_gate(
            training_results=self.training_results,
            crop_name=self.crop_name,
            check_production=True,
            project_root=self.project_root,
        )

        status = self.gate_report["status"]
        current.card.append(Markdown(f"# Stage: Automated Validation Gate — Verdict: **{status}**"))
        checks = self.gate_report.get("checks", {})
        current.card.append(
            Table(
                [
                    ["Relative Improvement Over Baseline", "PASS" if checks.get("relative_improvement_over_baseline", {}).get("pass") else "FAIL"],
                    ["Single Fold Regression Limit", "PASS" if checks.get("fold_stability", {}).get("pass") else "FAIL"],
                    ["Comparison Against Production Baseline", "PASS" if checks.get("production_comparison", {}).get("pass") else "FAIL"],
                ],
                headers=["Gate Requirement", "Status"],
            )
        )
        self.next(self.register)

    @card
    @step
    def register(self):
        """Promote passing model to Staging in the registry and generate Model Card."""
        if self.gate_report["status"] == "PASSED":
            print(f"[{self.crop_name}] Gate PASSED! Promoting challenger model to Staging...")
            self.registry_result = promote_and_generate_model_card(
                training_results=self.training_results,
                gate_report=self.gate_report,
                stage="Staging",
                project_root=self.project_root,
            )
            card_md = f"Model successfully registered under stage **Staging** with run_id `{self.registry_result.get('run_id')}`."
        else:
            print(f"[{self.crop_name}] Gate FAILED ({self.gate_report['status']}). Promotion rejected.")
            card_md = f"Promotion blocked: Validation gate status is {self.gate_report['status']}."

        current.card.append(Markdown("# Stage: Model Registry & Governance"))
        current.card.append(Markdown(card_md))
        self.next(self.end)

    @step
    def end(self):
        """Pipeline completion and reporting."""
        print("\n" + "=" * 60)
        print(" GenoTrackFlow Run Completed Successfully!")
        print(f" Crop: {self.crop_name} | Trait: {self.target_trait}")
        print(f" Validation Gate: {self.gate_report['status']}")
        print("=" * 60)
        print("\nTo view interactive visual cards in your browser, run:")
        print("  python -m pipelines.flow card view validation_gate")
        print("  or start the card server with: python -m pipelines.flow card server\n")


if __name__ == "__main__":
    GenoTrackFlow()
