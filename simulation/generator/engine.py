"""
simulation/generator/engine.py
Unified SimulationEngine coordinating:
  1. Breeding cohort generation (Haldane recombination + SSD selfing)
  2. Seasonal environmental covariate sampling
  3. Ground-truth phenotype simulation via independent DGP (sim_truth/)
  4. Real-format HapMap and phenotype CSV file writing
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import yaml

from simulation.schema import ScenarioConfig, ScenarioEvent
from simulation.generator.breeding import BreedingCohortGenerator
from simulation.generator.environment import EnvironmentGenerator
from simulation.generator.phenotype import PhenotypeTruthDGP
from simulation.generator.writer import SimulationWriter


class SimulationEngine:
    def __init__(
        self,
        crop_name: str = "rice",
        project_root: Optional[Path] = None,
    ):
        if project_root is None:
            project_root = Path(__file__).resolve().parents[2]
        self.project_root = Path(project_root)
        self.crop_name = crop_name

        # Load crop simulation config
        sim_yaml_path = self.project_root / "crops" / crop_name / "sim.yaml"
        if not sim_yaml_path.exists():
            raise FileNotFoundError(f"Crop simulation config not found at: {sim_yaml_path}")
        with open(sim_yaml_path, "r", encoding="utf-8") as f:
            self.sim_config = yaml.safe_load(f)

        # Reference pack path
        self.ref_pack_path = self.project_root / "data" / "processed" / "sim_reference_pack.joblib"
        if not self.ref_pack_path.exists():
            raise FileNotFoundError(f"Simulation reference pack not found at: {self.ref_pack_path}")

        # Initialize sub-generators
        self.breeding_gen = BreedingCohortGenerator(self.ref_pack_path, self.sim_config)
        self.env_gen = EnvironmentGenerator(self.sim_config)
        self.pheno_dgp = PhenotypeTruthDGP(self.ref_pack_path, self.sim_config, self.project_root)

        ref_pack = joblib.load(self.ref_pack_path)
        self.writer = SimulationWriter(ref_pack)

    def reset(self):
        """Reset internal generator state to tick 0 baseline."""
        self.breeding_gen.reset()

    def generate_season_tick(
        self,
        tick: int,
        scenario: ScenarioConfig,
        output_dir: Path | str,
        predicted_yields: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Execute generation for a single virtual season tick.
        Produces planting-time genotype HapMap and harvest-time phenotype CSV.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Deterministic tick RNG: seed combined with tick for byte-identical reproducibility
        tick_seed = int((scenario.seed * 10007 + tick * 37) % (2**31 - 1))
        rng = np.random.RandomState(tick_seed)

        # Find any active event for this tick
        active_event: Optional[ScenarioEvent] = None
        for ev in scenario.events:
            if ev.tick == tick:
                active_event = ev
                break

        active_params = active_event.params if active_event else None
        event_type_str = active_event.type.value if active_event else None

        # 1. Sample seasonal environment
        season_info = self.env_gen.sample_season(
            tick=tick,
            rng=rng,
            active_event_params=active_params if event_type_str == "covariate_shift" else None,
        )

        # 2. Simulate breeding cohort
        cohort_dosages, sample_ids = self.breeding_gen.generate_cohort(
            tick=tick,
            cohort_size=scenario.cohort_size,
            parent_policy=scenario.parent_policy,
            rng=rng,
            predicted_yields=predicted_yields,
            active_event_params=active_params if event_type_str == "genotype_shift" else None,
        )

        # 3. Simulate true harvest phenotypes via independent DGP
        df_phenotypes = self.pheno_dgp.generate_phenotypes(
            cohort_dosages=cohort_dosages,
            sample_ids=sample_ids,
            season_info=season_info,
            rng=rng,
            active_event_params=active_params if event_type_str == "concept_drift" else None,
        )

        # 4. Write files
        hmp_path = out_dir / "genotype.hmp.txt"
        pheno_path = out_dir / "phenotype.csv"

        genotype_params = active_params if event_type_str == "data_quality" else None
        self.writer.write_genotype_hapmap(
            cohort_dosages=cohort_dosages,
            sample_ids=sample_ids,
            output_path=hmp_path,
            rng=rng,
            active_event_params=genotype_params,
        )

        self.writer.write_phenotype_csv(
            df_phenotype=df_phenotypes,
            output_path=pheno_path,
        )

        return {
            "tick": tick,
            "season_info": season_info,
            "sample_ids": sample_ids,
            "cohort_dosages": cohort_dosages,
            "df_phenotypes": df_phenotypes,
            "genotype_path": str(hmp_path),
            "phenotype_path": str(pheno_path),
            "event_type": event_type_str,
            "event_params": active_params,
        }
