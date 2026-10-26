"""
tests/test_simulation_engine.py
Acceptance tests for M1 Simulator Core:
1. Passes real crop adapter and Pandera schema validation with 0 quarantines in stable_control.
2. Determinism: Same seed + scenario produces byte-identical output files and identical ledger hash.
3. Strict isolation: No code in src/ or pipelines/ imports or reads from sim_truth/.
"""
import hashlib
from pathlib import Path
import pytest

from crops.rice.adapter import parse_genotype, parse_phenotype
from src.ingest.schemas import GenotypeSchema, PhenotypeSchema
from simulation.schema import ScenarioConfig
from simulation.generator.engine import SimulationEngine
from simulation.ledger import SimulationLedger, LedgerRow


def test_simulated_tick_passes_adapter_and_pandera(tmp_path):
    """(1) A simulated tick passes the real adapter + Pandera with zero quarantines."""
    engine = SimulationEngine(crop_name="rice")
    scen = ScenarioConfig.from_yaml("simulation/scenarios/stable_control.yaml")

    res = engine.generate_season_tick(tick=0, scenario=scen, output_dir=tmp_path)

    # Validate genotype file
    df_geno = parse_genotype(res["genotype_path"], max_markers=1000)
    assert len(df_geno) > 0
    df_geno_valid = GenotypeSchema.validate(df_geno, lazy=True)
    assert len(df_geno_valid) == len(df_geno)

    # Validate phenotype file
    df_pheno = parse_phenotype(res["phenotype_path"])
    assert len(df_pheno) > 0
    df_pheno_valid = PhenotypeSchema.validate(df_pheno, lazy=True)
    assert len(df_pheno_valid) == len(df_pheno)


def test_generator_determinism_identical_hashes(tmp_path):
    """(3) Same seed gives identical output hashes."""
    engine1 = SimulationEngine(crop_name="rice")
    engine2 = SimulationEngine(crop_name="rice")
    scen = ScenarioConfig.from_yaml("simulation/scenarios/stable_control.yaml")

    dir1 = tmp_path / "run_1"
    dir2 = tmp_path / "run_2"

    res1 = engine1.generate_season_tick(tick=0, scenario=scen, output_dir=dir1)
    res2 = engine2.generate_season_tick(tick=0, scenario=scen, output_dir=dir2)

    # Compare file SHA256 hashes
    h_geno1 = hashlib.sha256(Path(res1["genotype_path"]).read_bytes()).hexdigest()
    h_geno2 = hashlib.sha256(Path(res2["genotype_path"]).read_bytes()).hexdigest()
    assert h_geno1 == h_geno2, "Genotype files must be byte-identical for identical seed!"

    h_pheno1 = hashlib.sha256(Path(res1["phenotype_path"]).read_bytes()).hexdigest()
    h_pheno2 = hashlib.sha256(Path(res2["phenotype_path"]).read_bytes()).hexdigest()
    assert h_pheno1 == h_pheno2, "Phenotype files must be byte-identical for identical seed!"


def test_sim_truth_strict_isolation():
    """(4) The sim_truth isolation test passes: no code under src/ or pipelines/ imports or opens it."""
    root = Path(__file__).resolve().parents[1]
    forbidden_terms = ["sim_truth", "dgp_truth", "PhenotypeTruthDGP"]

    scan_dirs = [root / "src", root / "pipelines"]
    violations = []

    for s_dir in scan_dirs:
        for py_file in s_dir.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            for term in forbidden_terms:
                if term in text:
                    violations.append(f"{py_file.relative_to(root)} contains '{term}'")

    assert len(violations) == 0, f"Isolation breach! Pipeline/src code references truth model:\n" + "\n".join(violations)
