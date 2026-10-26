"""
simulation/generator/environment.py
Generates realistic multi-environment trial (MET) seasonal covariates for simulated cohorts.
Covariates:
  - mean_temperature (deg C)
  - solar_radiation (MJ/m^2/day)
  - soil_moisture (fraction)
  - precipitation (mm)
  - soil_nitrogen (kg/ha)
  - missing_hill_ratio (fraction)
Supports 'covariate_shift' events with parameter deltas and scalers.
"""
from typing import Any, Dict, Optional
import numpy as np


class EnvironmentGenerator:
    def __init__(self, sim_config: Dict[str, Any]):
        self.config = sim_config
        self.cov_dists = sim_config.get("covariate_distributions", {})
        self.season_effects = sim_config.get("phenotype", {}).get("season_effects", {
            "DS": {"mean": 6200.0, "std": 650.0},
            "WS": {"mean": 4200.0, "std": 850.0},
        })

    def sample_season(
        self,
        tick: int,
        rng: np.random.RandomState,
        active_event_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Sample season covariates for a given tick.
        Season alternates between Dry Season (DS, even ticks) and Wet Season (WS, odd ticks).
        """
        season_type = "DS" if (tick % 2 == 0) else "WS"
        year = 2026 + (tick // 2)
        env_name = f"{year}_{season_type}"

        # Sample baseline distributions
        sampled = {}
        for cov_name, dist in self.cov_dists.items():
            mean = dist["mean"]
            std = dist["std"]
            low = dist.get("min", -np.inf)
            high = dist.get("max", np.inf)

            # Seasonal adjustments
            if season_type == "DS":
                if cov_name == "solar_radiation":
                    mean += 2.5
                elif cov_name == "precipitation":
                    mean = max(15.0, mean * 0.35)
                elif cov_name == "soil_moisture":
                    mean -= 0.10
            else:  # WS
                if cov_name == "solar_radiation":
                    mean -= 2.5
                elif cov_name == "precipitation":
                    mean *= 1.6
                elif cov_name == "soil_moisture":
                    mean += 0.10

            val = float(rng.normal(mean, std))
            val = float(np.clip(val, low, high))
            sampled[cov_name] = val

        # Apply covariate_shift event parameters if present
        if active_event_params:
            if "mean_temp_delta_c" in active_event_params:
                sampled["mean_temperature"] += float(active_event_params["mean_temp_delta_c"])
            if "rainfall_scale" in active_event_params:
                sampled["precipitation"] *= float(active_event_params["rainfall_scale"])
            if "solar_radiation_delta" in active_event_params:
                sampled["solar_radiation"] += float(active_event_params["solar_radiation_delta"])
            if "soil_moisture_scale" in active_event_params:
                sampled["soil_moisture"] *= float(active_event_params["soil_moisture_scale"])
            if "missing_hill_spike" in active_event_params:
                sampled["missing_hill_ratio"] = float(active_event_params["missing_hill_spike"])

        # Determine macro-environment yield baseline
        base_stats = self.season_effects.get(season_type, {"mean": 5200.0, "std": 800.0})
        # Baseline modulated by radiation and temperature
        temp_effect = (sampled["mean_temperature"] - 28.5) * (-45.0)  # heat stress penalty
        rad_effect = (sampled["solar_radiation"] - 18.5) * 85.0       # radiation bonus
        season_baseline = float(base_stats["mean"] + temp_effect + rad_effect)

        return {
            "tick": tick,
            "year": year,
            "season": season_type,
            "season_num": 1 if season_type == "DS" else 2,
            "environment": env_name,
            "season_baseline": season_baseline,
            "covariates": sampled,
        }
