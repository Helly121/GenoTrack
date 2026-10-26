"""
monitoring/policy.py
Config-driven decision policy for triggering adaptive model retraining (M4).
Rules:
  1. Trigger retrain if covariate OR genotype drift persists for K=2 consecutive ticks.
  2. Trigger retrain if rolling realized RMSE degrades > 15% vs. baseline (after label lag).
  3. Enforce cooldown period (min ticks between retrains) and minimum labeled rows.
  4. Data quality incidents trigger alerts/quarantine only — NEVER retrain on bad data.
"""
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import yaml


class LifecyclePolicy:
    def __init__(self, thresholds_path: Optional[str | Path] = None, initial_baseline_rmse: float = 768.8):
        if thresholds_path is None:
            thresholds_path = Path(__file__).resolve().parents[1] / "monitoring" / "thresholds.yaml"
        self.thresholds_path = Path(thresholds_path)
        with open(self.thresholds_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.policy_cfg = cfg.get("policy", {})
        self.perf_cfg = cfg.get("performance", {})

        self.k_consecutive = int(self.policy_cfg.get("consecutive_drift_ticks_k", 2))
        self.cooldown_ticks = int(self.policy_cfg.get("cooldown_ticks", 2))
        self.rmse_degradation_pct = float(self.perf_cfg.get("rmse_degradation_pct_threshold", 15.0))
        self.min_labeled_samples = int(self.perf_cfg.get("min_labeled_samples", 250))

        # Internal policy state
        self.consecutive_drift_count = 0
        self.last_retrain_tick = -999
        self.baseline_rmse = initial_baseline_rmse
        self.total_retrains = 0

    def evaluate_retrain_trigger(
        self,
        tick: int,
        drift_result: Dict[str, Any],
        realized_rmse: Optional[float] = None,
        labeled_samples_count: int = 0,
        manual_trigger: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate whether an automated retraining run should be dispatched for tick t.
        Returns (trigger_fired, trigger_reason).
        """
        if manual_trigger:
            return True, "Manual operator dispatch"

        # Check cooldown constraint
        ticks_since_retrain = tick - self.last_retrain_tick
        in_cooldown = (ticks_since_retrain < self.cooldown_ticks)

        # 1. Performance decay evaluation (only valid if harvest ground-truth labels arrived)
        if realized_rmse is not None and labeled_samples_count >= self.min_labeled_samples:
            pct_degradation = ((realized_rmse - self.baseline_rmse) / self.baseline_rmse) * 100.0
            if pct_degradation >= self.rmse_degradation_pct:
                if in_cooldown:
                    return False, f"Performance decay ({pct_degradation:.1f}%), but cooldown active ({ticks_since_retrain}/{self.cooldown_ticks} ticks)"
                return True, f"Realized performance decay: RMSE degraded by {pct_degradation:.1f}% ({realized_rmse:.1f} vs baseline {self.baseline_rmse:.1f} kg/ha)"

        # 2. Continuous drift accumulation (Covariate or Genotype)
        drift_active = drift_result.get("is_covariate_drift", False) or drift_result.get("is_genotype_drift", False)

        if drift_active:
            self.consecutive_drift_count += 1
            if self.consecutive_drift_count >= self.k_consecutive:
                if in_cooldown:
                    return False, f"Persistent drift active (K={self.consecutive_drift_count}), but cooldown active ({ticks_since_retrain}/{self.cooldown_ticks} ticks)"
                drift_type = "covariate" if drift_result.get("is_covariate_drift") else "genotype subpopulation"
                reason = f"Persistent {drift_type} drift for K={self.consecutive_drift_count} consecutive seasons"
                return True, reason
        else:
            self.consecutive_drift_count = 0

        # Data-quality incidents raise alerts only, never trigger retraining
        if drift_result.get("is_data_quality_alert", False):
            return False, "Data quality incident isolated to quarantine — retrain blocked"

        return False, None

    def record_retrain(self, tick: int, new_realized_rmse: Optional[float] = None):
        """Record successful retraining execution and update cooldown tracker."""
        self.last_retrain_tick = tick
        self.consecutive_drift_count = 0
        self.total_retrains += 1
        if new_realized_rmse is not None and new_realized_rmse > 400.0:
            self.baseline_rmse = min(self.baseline_rmse, new_realized_rmse)
