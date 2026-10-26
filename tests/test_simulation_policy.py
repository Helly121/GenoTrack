"""
tests/test_simulation_policy.py
Unit tests for M4 Decision Policy, Retraining Triggers, and Ledger Integrity.
"""
from pathlib import Path
import pytest
from monitoring.policy import LifecyclePolicy
from simulation.schema import LedgerRow
from simulation.ledger import SimulationLedger


def test_policy_drift_triggers_after_k_consecutive_ticks(tmp_path):
    policy = LifecyclePolicy()
    assert policy.k_consecutive == 2

    drift_active = {"is_covariate_drift": True, "is_genotype_drift": False, "is_data_quality_alert": False}
    drift_inactive = {"is_covariate_drift": False, "is_genotype_drift": False, "is_data_quality_alert": False}

    # Tick 1: first drift observation -> no trigger
    fired, reason = policy.evaluate_retrain_trigger(tick=1, drift_result=drift_active)
    assert not fired
    assert policy.consecutive_drift_count == 1

    # Tick 2: second consecutive drift -> trigger fires
    fired, reason = policy.evaluate_retrain_trigger(tick=2, drift_result=drift_active)
    assert fired
    assert "consecutive" in reason.lower()

    # Reset drift
    fired, _ = policy.evaluate_retrain_trigger(tick=3, drift_result=drift_inactive)
    assert not fired
    assert policy.consecutive_drift_count == 0


def test_policy_cooldown_enforcement():
    policy = LifecyclePolicy()
    drift_active = {"is_covariate_drift": True, "is_genotype_drift": False, "is_data_quality_alert": False}

    # Tick 1: Retrain occurs
    policy.record_retrain(tick=1, new_realized_rmse=950.0)
    assert policy.last_retrain_tick == 1
    assert policy.total_retrains == 1

    # Tick 2 (during cooldown of 2 ticks): should be blocked
    policy.consecutive_drift_count = 2
    fired, reason = policy.evaluate_retrain_trigger(tick=2, drift_result=drift_active)
    assert not fired
    assert "cooldown active" in reason.lower()

    # Tick 3 (cooldown elapsed: 3 - 1 = 2 >= 2): can trigger
    fired, reason = policy.evaluate_retrain_trigger(tick=3, drift_result=drift_active)
    assert fired


def test_policy_performance_decay_trigger():
    policy = LifecyclePolicy(initial_baseline_rmse=1000.0)
    drift_inactive = {"is_covariate_drift": False, "is_genotype_drift": False, "is_data_quality_alert": False}

    # Realized RMSE within tolerance (1100 <= 1000 * 1.25)
    fired, reason = policy.evaluate_retrain_trigger(
        tick=5,
        drift_result=drift_inactive,
        realized_rmse=1100.0,
        labeled_samples_count=300,
    )
    assert not fired

    # Realized RMSE degraded beyond 25% (1350 > 1000 * 1.25)
    fired, reason = policy.evaluate_retrain_trigger(
        tick=5,
        drift_result=drift_inactive,
        realized_rmse=1350.0,
        labeled_samples_count=300,
    )
    assert fired
    assert "realized performance decay" in reason.lower()


def test_policy_data_quality_blocks_retraining():
    policy = LifecyclePolicy()
    dq_result = {
        "is_covariate_drift": False,
        "is_genotype_drift": False,
        "is_data_quality_alert": True,
    }
    fired, reason = policy.evaluate_retrain_trigger(tick=4, drift_result=dq_result)
    assert not fired
    assert "quarantine" in reason.lower()


def test_ledger_export_all_formats(tmp_path):
    ledger = SimulationLedger()
    row = LedgerRow(
        tick=0,
        scenario_event=None,
        n_lines=300,
        covariate_drift_score=0.04,
        genotype_drift_score=0.01,
        prediction_drift_score=0.05,
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
    ledger.append(row)

    sqlite_file = tmp_path / "ledger.db"
    parquet_file = tmp_path / "ledger.parquet"
    csv_file = tmp_path / "ledger.csv"

    ledger.export_all(sqlite_path=sqlite_file, parquet_path=parquet_file, csv_path=csv_file)

    assert sqlite_file.exists()
    assert parquet_file.exists()
    assert csv_file.exists()

    df_csv = ledger.to_dataframe()
    assert len(df_csv) == 1
    assert df_csv.iloc[0]["n_lines"] == 300
