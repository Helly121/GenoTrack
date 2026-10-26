"""
tests/test_simulation_contracts.py
Unit tests for M0 contracts:
- Ledger schema validation and export
- Scenario config schema validation and rejection of unknown event types
- Deterministic ledger hash verification
"""
import pytest
from simulation.schema import EventType, LedgerRow, ScenarioConfig, ScenarioEvent
from simulation.ledger import SimulationLedger


def test_scenario_loader_valid(tmp_path):
    scenario_yaml = tmp_path / "valid_scenario.yaml"
    scenario_yaml.write_text(
        """
seed: 42
ticks: 8
label_lag: 1
cohort_size: 250
parent_policy: top_predicted
events:
  - tick: 3
    type: covariate_shift
    params:
      mean_temp_delta_c: 2.0
  - tick: 5
    type: concept_drift
    params:
      qtl: Hd1
      effect_multiplier: -0.5
        """
    )
    cfg = ScenarioConfig.from_yaml(scenario_yaml)
    assert cfg.seed == 42
    assert cfg.ticks == 8
    assert cfg.cohort_size == 250
    assert cfg.parent_policy == "top_predicted"
    assert len(cfg.events) == 2
    assert cfg.events[0].type == EventType.COVARIATE_SHIFT
    assert cfg.events[1].type == EventType.CONCEPT_DRIFT


def test_scenario_loader_rejects_unknown_event(tmp_path):
    bad_yaml = tmp_path / "bad_scenario.yaml"
    bad_yaml.write_text(
        """
seed: 42
ticks: 5
events:
  - tick: 2
    type: unknown_space_alien_drift
    params: {}
        """
    )
    with pytest.raises(Exception) as excinfo:
        ScenarioConfig.from_yaml(bad_yaml)
    assert "unknown_space_alien_drift" in str(excinfo.value).lower() or "validation error" in str(excinfo.value).lower()


def test_scenario_loader_rejects_out_of_bounds_tick(tmp_path):
    oob_yaml = tmp_path / "oob_scenario.yaml"
    oob_yaml.write_text(
        """
seed: 42
ticks: 4
events:
  - tick: 10
    type: covariate_shift
        """
    )
    with pytest.raises(ValueError) as excinfo:
        ScenarioConfig.from_yaml(oob_yaml)
    assert "exceeds total scenario ticks" in str(excinfo.value)


def test_shipped_scenarios_exist_and_validate():
    from pathlib import Path
    scenarios_dir = Path("simulation/scenarios")
    for name in ["stable_control.yaml", "storyline_demo.yaml", "random_stress.yaml"]:
        p = scenarios_dir / name
        assert p.exists(), f"Scenario {name} missing!"
        cfg = ScenarioConfig.from_yaml(p)
        assert cfg.ticks >= 1
        assert cfg.cohort_size >= 10


def test_ledger_schema_and_hashing(tmp_path):
    db_file = tmp_path / "test_ledger.db"
    ledger1 = SimulationLedger(db_path=db_file)
    ledger2 = SimulationLedger()

    row = LedgerRow(
        tick=0,
        scenario_event=None,
        n_lines=300,
        covariate_drift_score=0.012,
        genotype_drift_score=0.005,
        prediction_drift_score=0.021,
        labels_arrived_for_tick=None,
        realized_rmse=None,
        realized_r=None,
        trigger_fired=False,
        trigger_reason=None,
        retrain_run_id=None,
        champion_version="1",
        challenger_version=None,
        gate_result=None,
        promoted=False,
        frozen_baseline_rmse=None,
    )

    ledger1.append(row)
    ledger2.append(row)

    # Identical content must yield identical hash
    h1 = ledger1.compute_hash()
    h2 = ledger2.compute_hash()
    assert h1 == h2
    assert len(h1) == 64

    # Verify SQLite and Parquet exports
    df1 = ledger1.to_dataframe()
    assert len(df1) == 1
    assert df1.iloc[0]["tick"] == 0

    pq_file = tmp_path / "test_ledger.parquet"
    ledger1.export_parquet(pq_file)
    assert pq_file.exists()
