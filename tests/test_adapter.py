"""
tests/test_adapter.py
Unit tests for rice adapter and Pandera schema validation.
"""
from pathlib import Path
import pytest
import pandera.errors

from crops.rice.adapter import parse_genotype, parse_phenotype
from src.ingest.schemas import GenotypeSchema, PhenotypeSchema
from tests.fixtures.malformed_data import generate_malformed_genotype


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_malformed_genotype_rejection():
    """Prove that Data CI / Pandera schema actually fails on corrupted calls and coordinates."""
    df_malformed = generate_malformed_genotype()

    with pytest.raises(pandera.errors.SchemaErrors) as excinfo:
        GenotypeSchema.validate(df_malformed, lazy=True)

    errors = excinfo.value.failure_cases
    # Should catch '99.5%' and negative position
    failed_checks = errors["check"].tolist()
    assert len(errors) >= 2, "Expected at least 2 schema failure cases"


def test_rice_adapter_phenotype():
    """Verify phenotype adapter loads CSVs and emits canonical schema with trial covariates."""
    pheno_dir = PROJECT_ROOT / "data" / "raw" / "rice" / "phenotype"
    if not pheno_dir.exists():
        pytest.skip("Raw phenotype data not yet set up.")

    df_pheno = parse_phenotype(pheno_dir)
    assert len(df_pheno) > 0

    expected_cols = [
        "sample_id", "trait", "value", "environment", "season_or_year", "replicate", "covariates"
    ]
    assert list(df_pheno.columns) == expected_cols

    # Verify traits
    traits = df_pheno["trait"].unique().tolist()
    assert "grain_yield" in traits
    assert "flowering_time" in traits

    # Verify environments (e.g. 2009_DS)
    envs = df_pheno["environment"].unique().tolist()
    assert any("2009" in e for e in envs)

    # Validate against Pandera PhenotypeSchema
    df_validated = PhenotypeSchema.validate(df_pheno)
    assert len(df_validated) == len(df_pheno)
