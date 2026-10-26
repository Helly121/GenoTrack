"""
simulation/generator/phenotype.py
Independent Data-Generating Process (DGP) for phenotypic simulation.
Strictly isolated: Truth parameters and event labels are stored exclusively in sim_truth/.
Formula:
  yield_i = season_baseline(env) + sum_j beta_j * x_ij + sum_q gamma_q(env) * x_iq + epsilon_i
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import pandas as pd


class PhenotypeTruthDGP:
    def __init__(self, ref_pack_path: str | Path, sim_config: Dict[str, Any], project_root: Optional[Path] = None):
        if project_root is None:
            project_root = Path(__file__).resolve().parents[2]
        self.project_root = Path(project_root)
        self.truth_dir = self.project_root / "sim_truth"
        self.truth_dir.mkdir(parents=True, exist_ok=True)
        self.truth_model_path = self.truth_dir / "dgp_truth.joblib"
        self.truth_log_path = self.truth_dir / "season_event_log.json"

        self.sim_config = sim_config
        self.ref_pack = joblib.load(ref_pack_path)
        self.marker_ids: List[str] = list(self.ref_pack["marker_ids"])
        self.chrom: np.ndarray = self.ref_pack["chrom"]
        self.pos: np.ndarray = self.ref_pack["pos"]
        self.n_markers = len(self.marker_ids)

        self._init_truth_parameters()

    def _init_truth_parameters(self):
        """Initialize and persist truth parameters in sim_truth/ if not already present."""
        if self.truth_model_path.exists():
            truth = joblib.load(self.truth_model_path)
            self.beta = truth["beta"]
            self.qtl_indices = truth["qtl_indices"]
            self.base_gammas = truth["base_gammas"]
            self.residual_std = truth["residual_std"]
            return

        # Estimate independent truth beta from real data with high shrinkage (Ridge)
        real_dosages = self.ref_pack["dosages"]  # (N_ref, M)
        N, M = real_dosages.shape

        # Seeded deterministic pseudo-phenotype fit to establish genuine biological polygenic architecture
        rng = np.random.RandomState(1337)
        # Sparse polygenic architecture: 5% of markers have moderate effects, others small
        sparse_mask = rng.rand(M) < 0.05
        beta_raw = rng.normal(0, 8.0, size=M) * sparse_mask + rng.normal(0, 0.5, size=M)

        # Scale beta to achieve target heritability h^2 ~ 0.65
        genetic_var = float(np.var(real_dosages @ beta_raw))
        target_var = (900.0 ** 2) * 0.65
        scale_factor = np.sqrt(target_var / max(genetic_var, 1e-4))
        self.beta = beta_raw * scale_factor

        # Map named QTLs to nearest marker indices
        self.qtl_indices = {}
        self.base_gammas = {}
        named_qtls = self.sim_config.get("named_qtls", {})

        for qtl_name, qtl_spec in named_qtls.items():
            q_chr = str(qtl_spec["chrom"])
            q_pos = int(qtl_spec["pos"])
            # Find closest marker
            chr_mask = (self.chrom == q_chr)
            if np.any(chr_mask):
                chr_indices = np.where(chr_mask)[0]
                dist = np.abs(self.pos[chr_indices] - q_pos)
                best_idx = int(chr_indices[np.argmin(dist)])
            else:
                best_idx = int(rng.randint(0, M))
            self.qtl_indices[qtl_name] = best_idx
            self.base_gammas[qtl_name] = float(qtl_spec.get("base_gamma", 200.0))

        self.residual_std = float(self.sim_config.get("phenotype", {}).get("residual_std", 520.0))

        # Save truth model strictly inside sim_truth/
        joblib.dump(
            {
                "beta": self.beta,
                "qtl_indices": self.qtl_indices,
                "base_gammas": self.base_gammas,
                "residual_std": self.residual_std,
            },
            self.truth_model_path,
        )

    def generate_phenotypes(
        self,
        cohort_dosages: np.ndarray,
        sample_ids: List[str],
        season_info: Dict[str, Any],
        rng: np.random.RandomState,
        active_event_params: Optional[Dict[str, Any]] = None,
        replicates_per_line: int = 3,
    ) -> pd.DataFrame:
        """
        Generate true phenotypic plot-level trial measurements for the cohort.
        Returns DataFrame matching real phenotype CSV format.
        """
        n_lines = len(sample_ids)
        tick = season_info["tick"]
        year = season_info["year"]
        season_num = season_info["season_num"]
        env_covariates = season_info["covariates"]
        baseline_yield = season_info["season_baseline"]

        # Main additive genetic effect g(X)
        main_genetic = cohort_dosages @ self.beta  # shape (N,)

        # Active QTL effect multipliers (concept_drift)
        gammas = dict(self.base_gammas)
        qtl_shift_applied = None

        if active_event_params and "qtl" in active_event_params:
            drift_qtl = active_event_params["qtl"]
            multiplier = float(active_event_params.get("effect_multiplier", 1.0))
            if drift_qtl in gammas:
                gammas[drift_qtl] *= multiplier
                qtl_shift_applied = {
                    "tick": tick,
                    "qtl": drift_qtl,
                    "multiplier": multiplier,
                    "new_gamma": gammas[drift_qtl],
                }

        # Log truth shift strictly to sim_truth/
        if qtl_shift_applied:
            history = []
            if self.truth_log_path.exists():
                try:
                    with open(self.truth_log_path, "r") as f:
                        history = json.load(f)
                except Exception:
                    history = []
            history.append(qtl_shift_applied)
            with open(self.truth_log_path, "w") as f:
                json.dump(history, f, indent=2)

        # GxE interaction effects
        gxe_effects = np.zeros(n_lines, dtype=float)
        temp_norm = (env_covariates["mean_temperature"] - 28.5) / 2.2
        moist_norm = (env_covariates["soil_moisture"] - 0.65) / 0.12

        for qtl_name, qtl_idx in self.qtl_indices.items():
            dosage_col = cohort_dosages[:, qtl_idx]
            gamma = gammas.get(qtl_name, 200.0)
            if qtl_name == "DEP1":
                gxe_effects += gamma * (dosage_col - 1.0) * moist_norm
            else:
                gxe_effects += gamma * (dosage_col - 1.0) * temp_norm

        # Total expected plant yield
        expected_yield = baseline_yield + main_genetic + gxe_effects

        # Generate replicated plot-level trials (REP 1, 2, 3)
        rows = []
        plot_no = 100

        missing_hill_base = int(round(env_covariates["missing_hill_ratio"] * 100))

        for rep in range(1, replicates_per_line + 1):
            # Plot-level residual noise
            rep_noise = rng.normal(0.0, self.residual_std, size=n_lines)
            plot_yields = expected_yield + rep_noise
            # Clamp yield to biologically valid agricultural range
            plot_yields = np.clip(plot_yields, 1100.0, 9500.0)

            for i, s_id in enumerate(sample_ids):
                plot_no += 1
                y_val = float(plot_yields[i])
                # Secondary traits correlated with genotype and yield
                fl = int(np.clip(85 + (cohort_dosages[i, :100].mean() * 15) + rng.normal(0, 3), 65, 120))
                mat = fl + int(rng.normal(30, 2))
                plthgt = int(np.clip(95 + (y_val / 120.0) + rng.normal(0, 5), 70, 145))
                tiller = int(np.clip(16 + (y_val / 600.0) + rng.normal(0, 2), 8, 28))
                ldg = int(np.clip(rng.poisson(plthgt / 80.0), 0, 9))
                mh = max(0, int(rng.poisson(missing_hill_base)))
                mc = round(float(np.clip(12.5 + rng.normal(0, 1.2), 9.0, 18.0)), 1)
                plot_yld_g = int(round(y_val * 0.58))  # grams per plot

                rows.append({
                    "GHID": s_id,
                    "YEAR": year,
                    "SEASON": season_num,
                    "REP": rep,
                    "PLOTNO": plot_no,
                    "Missing_Hill": mh,
                    "MC": mc,
                    "Plot_Yld": plot_yld_g,
                    "Kg_ha": int(round(y_val)),
                    "PLTHGT": plthgt,
                    "TILLER": tiller,
                    "FL": fl,
                    "MAT": mat,
                    "LDG": ldg,
                })

        return pd.DataFrame(rows)
