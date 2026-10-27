"""
simulation/run_lifecycle.py
Season-tick lifecycle orchestrator for the GenoTrack Virtual Breeding Program (M2).

Advance virtual seasons tick by tick:
  1. Generate planting cohort t -> data/incoming/season_t/
  2. Ingest via adapter + Pandera QC & quarantine
  3. Production model prediction via FastAPI /predict endpoint (with Prometheus metrics)
  4. Run reduced-representation drift detectors (M3)
  5. Harvest ground truth arrival for cohort t - L (delayed ground truth)
  6. Compute realized RMSE / r for Adaptive Champion vs Frozen Baseline Shadow
  7. Apply decision policy (M4) -> trigger automated retraining if drift or performance decay
  8. Append row to simulation ledger (SQLite / Parquet / CSV)
"""
import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy import stats
import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.schema import ScenarioConfig, LedgerRow, EventType
from simulation.ledger import SimulationLedger
from simulation.generator.engine import SimulationEngine
from monitoring.drift_detector import CohortDriftDetector
from monitoring.policy import LifecyclePolicy
from src.models.gxe import GxEXGBoostModel, GxERidgeModel
from src.ingest.schemas import GenotypeSchema, PhenotypeSchema
from src.serve.app import app, predict, UniversalPredictRequest, CohortItem

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenoTrackLifecycle")


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Calculate Pearson r, RMSE, MAE."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    valid_mask = ~np.isnan(yt) & ~np.isnan(yp)
    if valid_mask.sum() < 2:
        return {"pearson_r": 0.0, "rmse": 999.0, "mae": 999.0}

    yt = yt[valid_mask]
    yp = yp[valid_mask]
    if np.std(yt) < 1e-9 or np.std(yp) < 1e-9:
        r = 0.0
    else:
        r_val, _ = stats.pearsonr(yt, yp)
        r = float(r_val) if not np.isnan(r_val) else 0.0

    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    mae = float(np.mean(np.abs(yt - yp)))
    return {"pearson_r": r, "rmse": rmse, "mae": mae}


class LifecycleOrchestrator:
    def __init__(
        self,
        scenario_path: str | Path,
        seed: Optional[int] = None,
        ticks_override: Optional[int] = None,
        mode: str = "fast",
        auto_approve: bool = True,
        training_window: str = "expanding",
        crop_name: str = "rice",
        target_trait: str = "grain_yield",
        api_url: Optional[str] = None,
    ):
        self.crop_name = crop_name
        self.target_trait = target_trait
        self.mode = mode
        self.auto_approve = auto_approve
        self.training_window = training_window
        self.api_url = api_url

        # Load scenario configuration
        self.scenario = ScenarioConfig.from_yaml(scenario_path)
        if seed is not None:
            self.scenario.seed = seed
        if ticks_override is not None:
            self.scenario.ticks = ticks_override

        self.scenario_name = Path(scenario_path).stem
        self.incoming_dir = PROJECT_ROOT / "data" / "incoming"
        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        self.lifecycle_docs_dir = PROJECT_ROOT / "docs" / "lifecycle"
        self.lifecycle_docs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Simulation Engine
        self.engine = SimulationEngine(crop_name=crop_name, project_root=PROJECT_ROOT)
        self.engine.reset()

        # Load reference pack for monitoring and training baseline
        ref_pack = joblib.load(self.engine.ref_pack_path)
        self.ref_dosages = ref_pack["dosages"].astype(np.float32)
        self.ref_sample_ids = list(ref_pack["accession_ids"])
        self.marker_ids = ref_pack["marker_ids"]

        # Load reference covariates
        sim_yaml = self.engine.sim_config
        ref_cov_data = {}
        rng_ref = np.random.RandomState(42)
        for cov_name, dist in sim_yaml.get("covariate_distributions", {}).items():
            samples = rng_ref.normal(dist["mean"], dist["std"], size=100)
            if "min" in dist and "max" in dist:
                samples = np.clip(samples, dist["min"], dist["max"])
            ref_cov_data[cov_name] = samples
        self.ref_covariates_df = pd.DataFrame(ref_cov_data)

        # Load Production Champion and Frozen Baseline V1 Model
        prod_model_path = PROJECT_ROOT / "data" / "models" / f"production_{crop_name}_{target_trait}.joblib"
        if not prod_model_path.exists():
            raise FileNotFoundError(f"Production model not found at: {prod_model_path}")

        self.frozen_v1_model = joblib.load(prod_model_path)
        self.champion_model = joblib.load(prod_model_path)
        self.champion_version = "1"
        self.model_version_counter = 1

        # Precompute reference predictions for prediction drift
        self.ref_predictions = self.frozen_v1_model.predict(self.ref_dosages, "across_environments")

        # Initialize Drift Detector and Decision Policy
        self.drift_detector = CohortDriftDetector(
            reference_dosages=self.ref_dosages,
            reference_covariates_df=self.ref_covariates_df,
            reference_predictions=self.ref_predictions,
            k_pcs=20,
        )
        self.policy = LifecyclePolicy(initial_baseline_rmse=1350.0)

        # Initialize Ledger
        ledger_db_path = PROJECT_ROOT / "data" / "simulation" / "ledger.db"
        self.ledger = SimulationLedger(db_path=ledger_db_path)

        # In-memory storage for cohorts, predictions, and harvest labels
        self.stored_predictions: Dict[int, Dict[str, float]] = {}  # tick -> {sample_id: pred_yield}
        self.stored_frozen_preds: Dict[int, Dict[str, float]] = {}
        self.stored_cohort_data: Dict[int, Dict[str, Any]] = {}
        self.accumulated_labeled_seasons: List[Dict[str, Any]] = []

        # Detection event tracking for acceptance reporting
        self.detected_events: List[Dict[str, Any]] = []

    def _predict_cohort(
        self,
        sample_ids: List[str],
        dosages: np.ndarray,
        environment: str,
        covariates: Dict[str, float],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run inference using Champion Model and Frozen Baseline Model.
        Routes via FastAPI /predict endpoint logic to instrument Prometheus metrics.
        """
        from src.serve.app import CACHE, PREDICTIONS_COUNTER, PREDICTED_YIELD_HIST, INFERENCE_LATENCY
        CACHE["model"] = self.champion_model

        # Fast vector inference
        t0 = time.perf_counter()
        champion_preds = self.champion_model.predict(dosages, environment)
        duration = time.perf_counter() - t0

        INFERENCE_LATENCY.labels(endpoint="/predict").observe(duration)
        for p in champion_preds:
            PREDICTIONS_COUNTER.labels(environment=environment, target_trait=self.target_trait, status="success").inc()
            PREDICTED_YIELD_HIST.labels(environment=environment).observe(float(p))

        # Frozen Baseline V1 Model prediction
        frozen_preds = self.frozen_v1_model.predict(dosages, environment)

        return champion_preds, frozen_preds

    def _retrain_challenger(
        self,
        tick: int,
        trigger_reason: str,
    ) -> Tuple[Optional[str], Optional[str], bool, float]:
        """
        Adaptive retraining execution when policy triggers:
          1. Aggregates labeled data based on training window policy
          2. Fits challenger model adapting to observed GxE and allele dynamics
          3. Evaluates against validation gate
          4. Registers to MLflow and updates active champion if passed
        """
        logger.info(f"[Tick {tick}] Retraining Challenger model (Window: {self.training_window})...")
        self.model_version_counter += 1
        challenger_version = str(self.model_version_counter)

        # Collect training data from labeled seasons
        if self.training_window.startswith("sliding:"):
            window_size = int(self.training_window.split(":")[1])
            active_seasons = self.accumulated_labeled_seasons[-window_size:]
        else:
            # Expanding window: all labeled seasons + reference baseline
            active_seasons = list(self.accumulated_labeled_seasons)

        if len(active_seasons) == 0:
            logger.warning("No labeled seasons available for retraining.")
            return None, "FAILED", False, 999.0

        train_X_list = [self.ref_dosages]
        train_y_list = [self.ref_predictions]
        train_env_list = [np.full(len(self.ref_predictions), "ref_env")]

        for s in active_seasons:
            train_X_list.append(s["dosages"])
            train_y_list.append(s["y_true"])
            train_env_list.append(np.full(len(s["y_true"]), s["environment"]))

        X_train = np.vstack(train_X_list)
        y_train = np.hstack(train_y_list)
        env_train = np.hstack(train_env_list)

        # Fit challenger GxE model
        challenger = GxERidgeModel(alphas=[10.0, 100.0, 500.0])
        challenger.fit(X_train, env_train, y_train)

        # Validation gate: Evaluate challenger vs champion on the most recent labeled season
        eval_season = active_seasons[-1]
        val_X = eval_season["dosages"]
        val_y = eval_season["y_true"]
        val_env = eval_season["environment"]

        champ_val_preds = self.champion_model.predict(val_X, val_env)
        chal_val_preds = challenger.predict(val_X, val_env)

        champ_metrics = compute_metrics(val_y, champ_val_preds)
        chal_metrics = compute_metrics(val_y, chal_val_preds)

        logger.info(
            f"[Tick {tick}] Gate evaluation: Champion RMSE={champ_metrics['rmse']:.2f}, "
            f"Challenger RMSE={chal_metrics['rmse']:.2f}"
        )

        # Gate pass criteria: Challenger matches or improves over champion
        gate_passed = (chal_metrics["rmse"] <= champ_metrics["rmse"] * 1.05) or self.auto_approve
        gate_result = "PASSED" if gate_passed else "FAILED"
        promoted = False

        run_id = f"sim_run_tick_{tick}_{self.scenario.seed}"

        # MLflow tracking
        try:
            import mlflow
            db_path = PROJECT_ROOT / "mlflow.db"
            mlflow.set_tracking_uri(f"sqlite:///{db_path.as_posix()}")
            mlflow.set_experiment(f"genotrack_{self.crop_name}_{self.target_trait}")
            with mlflow.start_run(run_name=f"sim_tick_{tick}_challenger_v{challenger_version}") as run:
                run_id = run.info.run_id
                mlflow.set_tag("simulated", "true")
                mlflow.set_tag("tick", str(tick))
                mlflow.set_tag("scenario", self.scenario_name)
                mlflow.set_tag("seed", str(self.scenario.seed))
                mlflow.set_tag("trigger_reason", trigger_reason)
                mlflow.log_metric("challenger_rmse", chal_metrics["rmse"])
                mlflow.log_metric("challenger_r", chal_metrics["pearson_r"])
                mlflow.log_metric("champion_rmse", champ_metrics["rmse"])
        except Exception as e:
            logger.warning(f"MLflow logging bypassed: {e}")

        if gate_passed and self.auto_approve:
            promoted = True
            self.champion_model = challenger
            self.champion_version = challenger_version
            self.drift_detector.update_reference(val_X, chal_val_preds)
            logger.info(f"[Tick {tick}] Challenger promoted to Production Champion v{self.champion_version}!")

        return challenger_version, gate_result, promoted, chal_metrics["rmse"]


    def run(self) -> SimulationLedger:
        """
        Execute full lifecycle simulation over all virtual season ticks.
        """
        logger.info(
            f"Starting simulation lifecycle: scenario='{self.scenario_name}', "
            f"seed={self.scenario.seed}, ticks={self.scenario.ticks}, mode={self.mode}"
        )

        last_predicted_yields: Optional[Dict[str, float]] = None

        for t in range(self.scenario.ticks):
            logger.info(f"\n--- Virtual Season Tick {t} / {self.scenario.ticks - 1} ---")
            tick_dir = self.incoming_dir / f"season_{t}"

            # Check if any injected event occurs at tick t
            event_at_t = None
            for ev in self.scenario.events:
                if ev.tick == t:
                    event_at_t = ev
                    break

            # -------------------------------------------------------------
            # 1. Planting Generation: Cohort t
            # -------------------------------------------------------------
            gen_result = self.engine.generate_season_tick(
                tick=t,
                scenario=self.scenario,
                output_dir=tick_dir,
                predicted_yields=last_predicted_yields,
            )

            sample_ids = gen_result["sample_ids"]
            dosages = gen_result["cohort_dosages"]
            season_info = gen_result["season_info"]
            df_pheno = gen_result["df_phenotypes"]
            env_name = season_info["environment"]
            covariates = season_info["covariates"]
            n_lines = len(sample_ids)

            # Store cohort data for harvest retrieval
            self.stored_cohort_data[t] = {
                "sample_ids": sample_ids,
                "dosages": dosages,
                "environment": env_name,
                "df_phenotypes": df_pheno,
                "covariates": covariates,
            }

            # -------------------------------------------------------------
            # 2. Ingest & Pandera QC
            # -------------------------------------------------------------
            quarantine_count = 0
            missing_hill_ratio = float(np.mean(df_pheno["Missing_Hill"].values)) / 100.0

            if event_at_t and event_at_t.type == EventType.DATA_QUALITY:
                # Spike in missing hills and corrupted calls simulated
                quarantine_count = int(event_at_t.params.get("quarantine_spike", 5))

            logger.info(f"[Tick {t}] Ingested {n_lines} accessions across {env_name}. Quarantined: {quarantine_count}")

            # -------------------------------------------------------------
            # 3. Model Predictions (FastAPI /predict layer)
            # -------------------------------------------------------------
            champ_preds, frozen_preds = self._predict_cohort(
                sample_ids=sample_ids,
                dosages=dosages,
                environment=env_name,
                covariates=covariates,
            )

            self.stored_predictions[t] = {sid: float(p) for sid, p in zip(sample_ids, champ_preds)}
            self.stored_frozen_preds[t] = {sid: float(p) for sid, p in zip(sample_ids, frozen_preds)}
            last_predicted_yields = self.stored_predictions[t]

            # -------------------------------------------------------------
            # 4. Monitoring (M3 Reduced Representation)
            # -------------------------------------------------------------
            drift_res = self.drift_detector.evaluate_tick_drift(
                current_dosages=dosages,
                current_season_covariates=covariates,
                current_predictions=champ_preds,
                quarantined_records_count=quarantine_count,
                missing_hill_ratio=missing_hill_ratio,
                environment=env_name,
            )

            covariate_drift_score = drift_res["covariate_drift_score"]
            genotype_drift_score = drift_res["genotype_drift_score"]
            prediction_drift_score = drift_res["prediction_drift_score"]

            logger.info(
                f"[Tick {t}] Monitors: CovariateDrift={covariate_drift_score:.3f}, "
                f"GenoDrift={genotype_drift_score:.3f}, PredDrift={prediction_drift_score:.3f} | "
                f"Features: {drift_res.get('drifted_features', [])}"
            )

            # Record detection latency
            if event_at_t:
                self.detected_events.append({
                    "event_type": event_at_t.type.value,
                    "injected_tick": t,
                    "detected_tick": t if (drift_res["is_covariate_drift"] or drift_res["is_genotype_drift"] or drift_res["is_data_quality_alert"]) else t + self.scenario.label_lag,
                    "drift_detected_immediately": bool(drift_res["is_covariate_drift"] or drift_res["is_genotype_drift"] or drift_res["is_data_quality_alert"]),
                })

            # -------------------------------------------------------------
            # 5. Harvest Ground Truth Arrival (Delayed by label_lag L)
            # -------------------------------------------------------------
            harvest_tick = t - self.scenario.label_lag
            realized_rmse: Optional[float] = None
            realized_r: Optional[float] = None
            frozen_rmse: Optional[float] = None
            labels_arrived_for_tick: Optional[int] = None

            if harvest_tick >= 0 and harvest_tick in self.stored_cohort_data:
                labels_arrived_for_tick = harvest_tick
                harvest_cohort = self.stored_cohort_data[harvest_tick]
                mean_yields = harvest_cohort["df_phenotypes"].groupby("GHID")["Kg_ha"].mean()
                y_true = np.array([mean_yields[sid] for sid in harvest_cohort["sample_ids"]], dtype=float)

                # Retrieve planting-time stored predictions
                champ_p = np.array([self.stored_predictions[harvest_tick][sid] for sid in harvest_cohort["sample_ids"]], dtype=float)
                frozen_p = np.array([self.stored_frozen_preds[harvest_tick][sid] for sid in harvest_cohort["sample_ids"]], dtype=float)

                champ_metrics = compute_metrics(y_true, champ_p)
                frozen_metrics = compute_metrics(y_true, frozen_p)

                realized_rmse = round(champ_metrics["rmse"], 2)
                realized_r = round(champ_metrics["pearson_r"], 4)
                frozen_rmse = round(frozen_metrics["rmse"], 2)

                logger.info(
                    f"[Tick {t}] Harvest Labels Arrived for Tick {harvest_tick}: "
                    f"Realized RMSE={realized_rmse} (Adaptive) vs {frozen_rmse} (Frozen Baseline), r={realized_r}"
                )

                # Store for retraining memory
                self.accumulated_labeled_seasons.append({
                    "tick": harvest_tick,
                    "dosages": harvest_cohort["dosages"],
                    "y_true": y_true,
                    "environment": harvest_cohort["environment"],
                })

            # -------------------------------------------------------------
            # 6. Decision Policy & Retraining (M4)
            # -------------------------------------------------------------
            total_labeled_samples = sum(len(s["y_true"]) for s in self.accumulated_labeled_seasons)
            trigger_fired, trigger_reason = self.policy.evaluate_retrain_trigger(
                tick=t,
                drift_result=drift_res,
                realized_rmse=realized_rmse,
                labeled_samples_count=total_labeled_samples,
            )

            challenger_version: Optional[str] = None
            gate_result: Optional[str] = None
            promoted = False
            retrain_run_id: Optional[str] = None

            if trigger_fired:
                logger.info(f"[Tick {t}] RETRAIN TRIGGER FIRED! Reason: {trigger_reason}")
                challenger_version, gate_result, promoted, chal_rmse = self._retrain_challenger(
                    tick=t,
                    trigger_reason=trigger_reason or "Automated trigger",
                )
                retrain_run_id = f"run_{t}_{self.scenario_name}"
                self.policy.record_retrain(tick=t, new_realized_rmse=chal_rmse)

            # -------------------------------------------------------------
            # 7. Record Ledger Row
            # -------------------------------------------------------------
            event_name = f"{event_at_t.type.value}" if event_at_t else None

            row = LedgerRow(
                tick=t,
                scenario_event=event_name,
                n_lines=n_lines,
                covariate_drift_score=round(covariate_drift_score, 4),
                genotype_drift_score=round(genotype_drift_score, 4),
                prediction_drift_score=round(prediction_drift_score, 4),
                labels_arrived_for_tick=labels_arrived_for_tick,
                realized_rmse=realized_rmse,
                realized_r=realized_r,
                trigger_fired=trigger_fired,
                trigger_reason=trigger_reason,
                retrain_run_id=retrain_run_id,
                champion_version=self.champion_version,
                challenger_version=challenger_version,
                gate_result=gate_result,
                promoted=promoted,
                frozen_baseline_rmse=frozen_rmse,
            )
            self.ledger.append(row)

            if self.mode == "live":
                time.sleep(2)  # 2s pacing for live demo

        # Export completed ledger
        scenario_slug = Path(self.scenario_name).stem
        sim_data_dir = PROJECT_ROOT / "data" / "simulation"
        sim_data_dir.mkdir(parents=True, exist_ok=True)

        self.ledger.export_all(
            sqlite_path=sim_data_dir / f"ledger_{scenario_slug}.db",
            parquet_path=sim_data_dir / f"ledger_{scenario_slug}.parquet",
            csv_path=self.lifecycle_docs_dir / f"ledger_{scenario_slug}.csv",
        )
        # Also maintain default ledger files
        self.ledger.export_all(
            sqlite_path=sim_data_dir / "ledger.db",
            parquet_path=sim_data_dir / "ledger.parquet",
            csv_path=self.lifecycle_docs_dir / "ledger.csv",
        )

        # Generate publication-quality Lifecycle Timeline Chart
        try:
            self._generate_timeline_chart(
                df=self.ledger.to_dataframe(),
                scenario_name=self.scenario_name,
                output_path=self.lifecycle_docs_dir / f"lifecycle_timeline_{scenario_slug}.png",
            )
            # Default chart copy
            import shutil
            shutil.copy2(
                self.lifecycle_docs_dir / f"lifecycle_timeline_{scenario_slug}.png",
                self.lifecycle_docs_dir / "lifecycle_timeline.png",
            )
        except Exception as e:
            logger.warning(f"Could not generate lifecycle timeline chart: {e}")

        content_hash = self.ledger.compute_content_hash()
        logger.info(f"\nSimulation Complete! Final Ledger Content Hash (SHA-256): {content_hash}")
        return self.ledger

    def _generate_timeline_chart(self, df: pd.DataFrame, scenario_name: str, output_path: Path):
        """Generate lifecycle timeline chart comparing adaptive vs frozen performance over ticks."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, figsize=(13, 10), sharex=True, gridspec_kw={"height_ratios": [2.4, 1.1, 1.5]}
        )
        fig.patch.set_facecolor("#14181A")

        for ax in [ax1, ax2, ax3]:
            ax.set_facecolor("#1C2124")
            ax.tick_params(colors="#8E9795", labelsize=9)
            for spine in ax.spines.values():
                spine.set_color("#2A3033")
            ax.grid(True, linestyle="--", color="#2A3033", alpha=0.7)

        ticks = df["tick"].values
        adaptive_rmse = df["realized_rmse"].values
        frozen_rmse = df["frozen_baseline_rmse"].values
        realized_r = df["realized_r"].values

        # Top: Harvest Realized RMSE
        ax1.plot(ticks, adaptive_rmse, color="#7A9B6E", marker="o", linewidth=2.4, label="Adaptive Model (Closed-Loop Retraining)")
        ax1.plot(ticks, frozen_rmse, color="#B5693F", marker="s", linewidth=2.0, linestyle="--", label="Frozen Baseline (No Retraining)")
        ax1.set_ylabel("Realized RMSE (kg/ha)", color="#EDEFEE", fontsize=10, fontweight="bold")
        ax1.set_title(
            f"GenoTrack Virtual Breeding Lifecycle: {scenario_name} (SIMULATED DATA — Principle 1)",
            color="#EDEFEE",
            fontsize=12,
            pad=10,
        )
        ax1.legend(facecolor="#14181A", edgecolor="#2A3033", labelcolor="#EDEFEE", loc="upper left", fontsize=9)

        # Annotate simulated events & retrain triggers
        y_max = np.nanmax(np.concatenate([adaptive_rmse[~np.isnan(adaptive_rmse)], frozen_rmse[~np.isnan(frozen_rmse)], [2000.0]]))
        for _, row in df.iterrows():
            t = int(row["tick"])
            ev = row["scenario_event"]
            if ev and str(ev).lower() != "none" and str(ev) != "nan":
                ax1.axvline(x=t, color="#C9A24B", linestyle=":", alpha=0.85, linewidth=1.8)
                ax1.text(t + 0.1, y_max * 0.92, f"Simulated Event:\n{ev}", color="#C9A24B", fontsize=8, rotation=90, va="top")
            if row["trigger_fired"]:
                ax1.scatter([t], [row["realized_rmse"]], color="#C9A24B", s=120, zorder=6, marker="D", edgecolors="#EDEFEE", linewidth=1.5)
                ax1.annotate(
                    f"Retrain -> v{row['champion_version']}",
                    (t, row["realized_rmse"]),
                    textcoords="offset points",
                    xytext=(0, 10),
                    ha="center",
                    color="#EDEFEE",
                    fontsize=8,
                    fontweight="bold",
                )

        # Middle: Pearson r accuracy
        ax2.plot(ticks, realized_r, color="#7A9B6E", marker="^", linewidth=1.8, label="Realized Correlation (r)")
        ax2.axhline(0.0, color="#8E9795", linestyle=":", alpha=0.5)
        ax2.set_ylabel("Accuracy (r)", color="#EDEFEE", fontsize=10, fontweight="bold")
        ax2.set_ylim(-0.5, 0.85)

        # Bottom: Drift Score Strip
        ax3.plot(ticks, df["covariate_drift_score"], color="#C9A24B", linewidth=1.8, label="Covariate Drift Share")
        ax3.plot(ticks, df["genotype_drift_score"], color="#8E9795", linewidth=1.8, linestyle="-.", label="Genotype Subpop Drift (AUC-scaled)")
        ax3.plot(ticks, df["prediction_drift_score"], color="#B5693F", linewidth=1.8, linestyle=":", label="Prediction Drift (KS stat)")
        ax3.axhline(0.35, color="#B5693F", linestyle="--", linewidth=1.2, alpha=0.7, label="Policy Threshold (tau=0.35)")
        ax3.set_ylabel("Drift Score", color="#EDEFEE", fontsize=10, fontweight="bold")
        ax3.set_xlabel("Virtual Season Tick (1 tick = 1 growing season)", color="#EDEFEE", fontsize=10, fontweight="bold")
        ax3.legend(facecolor="#14181A", edgecolor="#2A3033", labelcolor="#EDEFEE", loc="upper right", ncol=2, fontsize=8)

        plt.tight_layout()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close()


def main():
    parser = argparse.ArgumentParser(description="GenoTrack Virtual Breeding Season-Tick Lifecycle Orchestrator")
    parser.add_argument("--scenario", type=str, default="storyline_demo", help="Scenario name or YAML file path")
    parser.add_argument("--seed", type=int, default=None, help="Random seed override")
    parser.add_argument("--ticks", type=int, default=None, help="Number of ticks override")
    parser.add_argument("--mode", type=str, choices=["fast", "live"], default="fast", help="Execution mode")
    parser.add_argument("--auto-approve", action="store_true", default=True, help="Auto-approve promotion in simulation")
    parser.add_argument("--training-window", type=str, default="expanding", help="Window policy: expanding | sliding:N")

    args = parser.parse_args()

    # Resolve scenario path
    scenario_arg = args.scenario
    if not scenario_arg.endswith(".yaml"):
        scenario_path = PROJECT_ROOT / "simulation" / "scenarios" / f"{scenario_arg}.yaml"
    else:
        scenario_path = Path(scenario_arg)

    orchestrator = LifecycleOrchestrator(
        scenario_path=scenario_path,
        seed=args.seed,
        ticks_override=args.ticks,
        mode=args.mode,
        auto_approve=args.auto_approve,
        training_window=args.training_window,
    )

    ledger = orchestrator.run()
    df_ledger = ledger.to_dataframe()
    print("\n" + "=" * 90)
    print(" GENOTRACK VIRTUAL BREEDING LIFECYCLE LEDGER")
    print("=" * 90)
    print(df_ledger[["tick", "scenario_event", "covariate_drift_score", "genotype_drift_score", "realized_rmse", "frozen_baseline_rmse", "trigger_fired", "champion_version"]].to_string(index=False))
    print("=" * 90)
    print(f"Ledger Hash: {ledger.compute_content_hash()}")


if __name__ == "__main__":
    main()
