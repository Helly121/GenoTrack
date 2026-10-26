"""
monitoring/drift_detector.py
Real-time drift detection for continuous breeding simulation (M3).
Operates strictly on reduced representations (spec Section 2, M3):
  1. Covariate drift: 6 environmental covariates + top-20 genotype PCs + mean allele frequency shift.
  2. Genotype drift: Domain classifier AUC (reference vs. current) on top PCs.
  3. Prediction drift: Kolmogorov-Smirnov test on predicted yield distribution.
  4. Data quality monitoring: Quarantine rates and missing-hill spikes.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
import yaml


class CohortDriftDetector:
    def __init__(
        self,
        reference_dosages: np.ndarray,
        reference_covariates_df: pd.DataFrame,
        reference_predictions: np.ndarray,
        thresholds_path: Optional[str | Path] = None,
        k_pcs: int = 20,
    ):
        self.k_pcs = min(k_pcs, reference_dosages.shape[0] - 1, reference_dosages.shape[1])
        self.reference_dosages = reference_dosages
        self.ref_af = np.mean(reference_dosages, axis=0) / 2.0
        self.ref_covariates = reference_covariates_df
        self.ref_predictions = reference_predictions

        # Fit PCA on reference genotypes
        self.pca = PCA(n_components=self.k_pcs, random_state=42)
        self.ref_pcs = self.pca.fit_transform(reference_dosages)

        # Load thresholds
        if thresholds_path is None:
            thresholds_path = Path(__file__).resolve().parents[1] / "monitoring" / "thresholds.yaml"
        self.thresholds_path = Path(thresholds_path)
        with open(self.thresholds_path, "r", encoding="utf-8") as f:
            self.thresholds = yaml.safe_load(f)

    def evaluate_tick_drift(
        self,
        current_dosages: np.ndarray,
        current_season_covariates: Dict[str, float],
        current_predictions: np.ndarray,
        quarantined_records_count: int = 0,
        missing_hill_ratio: float = 0.0,
        environment: str = "",
    ) -> Dict[str, Any]:
        """
        Evaluate drift for the current cohort arriving at tick t.
        """
        alerts: List[str] = []
        drift_cfg = self.thresholds.get("drift", {})

        # -------------------------------------------------------------
        # 1. Covariate Drift (6 env covariates + top PCs)
        # -------------------------------------------------------------
        current_pcs = self.pca.transform(current_dosages)
        drifted_features = []

        # (a) Environmental covariates vs. reference distributions
        env_drift_count = 0
        total_env_features = len(current_season_covariates)
        is_ds = ("_DS" in str(environment)) or ("_DS" in str(current_season_covariates.get("environment", "")))

        for cov_name, current_val in current_season_covariates.items():
            if cov_name in self.ref_covariates.columns:
                ref_vals = self.ref_covariates[cov_name].dropna().values
                if len(ref_vals) > 0:
                    ref_mean = float(np.mean(ref_vals))
                    ref_std = float(np.std(ref_vals)) if np.std(ref_vals) > 1e-4 else 1.0

                    # Adjust expected baseline for natural seasonal cycle (DS vs WS)
                    if is_ds:
                        if cov_name == "solar_radiation":
                            ref_mean += 2.5
                        elif cov_name == "precipitation":
                            ref_mean = max(15.0, ref_mean * 0.35)
                        elif cov_name == "soil_moisture":
                            ref_mean -= 0.10
                    else:
                        if cov_name == "solar_radiation":
                            ref_mean -= 2.5
                        elif cov_name == "precipitation":
                            ref_mean *= 1.6
                        elif cov_name == "soil_moisture":
                            ref_mean += 0.10

                    z_score = abs(current_val - ref_mean) / ref_std
                    climate_thresh = float(drift_cfg.get("climate_z_score_threshold", 1.25))
                    # Significant climate drift outlier (z > climate_thresh)
                    if z_score > climate_thresh:
                        env_drift_count += 1
                        drifted_features.append(f"env:{cov_name} (z={z_score:.2f})")

        # (b) Mean absolute allele frequency shift
        current_af = np.mean(current_dosages, axis=0) / 2.0
        delta_af = float(np.mean(np.abs(current_af - self.ref_af)))
        maf_threshold = float(drift_cfg.get("allele_frequency_maf_delta_threshold", 0.06))
        af_drift_count = 0
        if delta_af > maf_threshold:
            af_drift_count = 1
            drifted_features.append(f"genotype:delta_af ({delta_af:.3f} > {maf_threshold})")

        # (c) Top PCA distributions (Multiple-testing-aware KS test: p < 0.005 and effect size ks_stat > threshold)
        pc_drift_count = 0
        p_val_thresh = float(drift_cfg.get("covariate_drift_p_value", 0.005))
        ks_stat_thresh = float(drift_cfg.get("covariate_drift_ks_stat_threshold", 0.26))

        for pc_idx in range(self.k_pcs):
            ks_stat, p_val = stats.ks_2samp(self.ref_pcs[:, pc_idx], current_pcs[:, pc_idx])
            if p_val < p_val_thresh and ks_stat > ks_stat_thresh:
                pc_drift_count += 1
                drifted_features.append(f"pc:{pc_idx+1} (ks={ks_stat:.2f})")

        total_tested = total_env_features + self.k_pcs + 1
        total_drifted_features = env_drift_count + pc_drift_count + af_drift_count
        covariate_drift_score = float(total_drifted_features / max(total_tested, 1))
        share_threshold = float(drift_cfg.get("covariate_drift_share_threshold", 0.35))

        # -------------------------------------------------------------
        # 2. Genotype / Population Drift (Domain Classifier AUC with L2 Regularization)
        # -------------------------------------------------------------
        n_ref = len(self.ref_pcs)
        n_curr = len(current_pcs)
        X_domain = np.vstack([self.ref_pcs, current_pcs])
        y_domain = np.hstack([np.zeros(n_ref), np.ones(n_curr)])

        try:
            # Regularized logistic regression (C=0.1) prevents sample-size overfitting
            clf = LogisticRegression(C=0.1, max_iter=200, random_state=42)
            clf.fit(X_domain, y_domain)
            probs = clf.predict_proba(X_domain)[:, 1]
            auc_score = float(roc_auc_score(y_domain, probs))
        except Exception:
            auc_score = 0.50

        # AUC = 0.5 indicates identical distributions; AUC >= 0.75 + delta_af > 0.05 indicates immigrant germplasm shift
        genotype_drift_score = max(0.0, float(auc_score - 0.5) * 2.0)
        auc_thresh = float(drift_cfg.get("genotype_domain_classifier_auc_threshold", 0.75))
        maf_delta_thresh = float(drift_cfg.get("allele_frequency_maf_delta_threshold", 0.075))
        is_genotype_drift = (auc_score >= auc_thresh and delta_af > 0.05) or (delta_af > 0.08)

        if is_genotype_drift:
            alerts.append(f"Genotype subpopulation drift detected (Domain AUC={auc_score:.3f}, delta_af={delta_af:.3f})")

        # -------------------------------------------------------------
        # 3. Prediction Drift (Kolmogorov-Smirnov on Yield)
        # -------------------------------------------------------------
        if len(self.ref_predictions) > 0 and len(current_predictions) > 0:
            ks_stat, p_val_pred = stats.ks_2samp(self.ref_predictions, current_predictions)
            pred_p_thresh = float(drift_cfg.get("prediction_drift_p_value", 0.005))
            pred_ks_thresh = float(drift_cfg.get("prediction_drift_ks_threshold", 0.25))
            is_prediction_drift = (p_val_pred < pred_p_thresh) and (ks_stat > pred_ks_thresh)
            prediction_drift_score = float(ks_stat)
            if is_prediction_drift:
                alerts.append(f"Prediction yield drift detected (KS stat={ks_stat:.3f}, p={p_val_pred:.3f})")
        else:
            prediction_drift_score = 0.0
            is_prediction_drift = False

        # Evaluate is_covariate_drift with joint prediction corroboration
        is_covariate_drift = (covariate_drift_score >= share_threshold) or (env_drift_count >= 2 and prediction_drift_score > 0.30)
        if is_covariate_drift:
            alerts.append(f"Covariate drift detected (score={covariate_drift_score:.3f}): {', '.join(drifted_features[:4])}")


        # -------------------------------------------------------------
        # 4. Data Quality Alerts (Quarantine & Missing Hills)
        # -------------------------------------------------------------
        is_data_quality_alert = False
        if quarantined_records_count > 0:
            is_data_quality_alert = True
            alerts.append(f"Data Quality Incident: {quarantined_records_count} records failed Pandera QC and were quarantined.")

        if missing_hill_ratio > 0.15:
            is_data_quality_alert = True
            alerts.append(f"Data Quality Incident: Severe field missing-hill spike ({missing_hill_ratio*100:.1f}%).")

        return {
            "covariate_drift_score": round(covariate_drift_score, 4),
            "genotype_drift_score": round(genotype_drift_score, 4),
            "prediction_drift_score": round(prediction_drift_score, 4),
            "is_covariate_drift": is_covariate_drift,
            "is_genotype_drift": is_genotype_drift,
            "is_prediction_drift": is_prediction_drift,
            "is_data_quality_alert": is_data_quality_alert,
            "domain_classifier_auc": round(auc_score, 4),
            "delta_af": round(delta_af, 4),
            "drifted_features": drifted_features,
            "alerts": alerts,
        }

    def update_reference(self, new_dosages: np.ndarray, new_predictions: np.ndarray):
        """
        Update the reference window to the training window of the current champion (M3).
        """
        self.reference_dosages = new_dosages
        self.ref_af = np.mean(new_dosages, axis=0) / 2.0
        self.ref_pcs = self.pca.transform(new_dosages)
        self.ref_predictions = new_predictions

