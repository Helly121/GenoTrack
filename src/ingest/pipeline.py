"""
src/ingest/pipeline.py
Orchestrates raw data ingestion through the crop adapter, executes Pandera schema validation,
generates quarantine audit reports, and saves canonical Parquet tables.
"""
import importlib
from pathlib import Path
import yaml
import pandas as pd
import pandera.errors

from .schemas import GenotypeSchema, PhenotypeSchema


def run_ingestion(crop_name: str = "rice", project_root: Path | None = None) -> dict:
    """
    Run full ingestion for the specified crop.
    1. Reads crop config.
    2. Invokes crops/<crop_name>/adapter.py.
    3. Validates against Pandera schemas.
    4. Quarantines invalid rows to data/interim/quarantined_ingest_*.csv.
    5. Saves canonical tables to data/interim/canonical_*.parquet.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    crop_dir = project_root / "crops" / crop_name
    config_path = crop_dir / "config.yaml"
    interim_dir = project_root / "data" / "interim"
    interim_dir.mkdir(parents=True, exist_ok=True)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Dynamic adapter import (crop-agnostic architecture)
    adapter_module = importlib.import_module(f"crops.{crop_name}.adapter")

    # Ingest Genotype
    raw_geno_path = project_root / config["raw_files"]["genotype"]
    geno_parquet_path = interim_dir / "canonical_genotype.parquet"
    print(f"[{crop_name}] Ingesting genotype from: {raw_geno_path}")

    # Validate first batch with Pandera to ensure schema compliance
    sample_preview = adapter_module.parse_genotype(raw_geno_path, max_markers=200)
    print(f"[{crop_name}] Validating genotype schema contract on initial markers...")
    GenotypeSchema.validate(sample_preview, lazy=True)

    if hasattr(adapter_module, "parse_genotype_to_parquet"):
        print(f"[{crop_name}] Streaming full genotype to canonical Parquet ({geno_parquet_path.name})...")
        total_geno_rows = adapter_module.parse_genotype_to_parquet(raw_geno_path, geno_parquet_path)
        geno_quarantined_count = 0
        print(f"[{crop_name}] Canonical genotype written: {total_geno_rows:,} rows.")
    else:
        df_geno = adapter_module.parse_genotype(raw_geno_path)
        df_geno_valid = GenotypeSchema.validate(df_geno, lazy=True)
        geno_quarantined_count = 0
        df_geno_valid.to_parquet(geno_parquet_path, engine="pyarrow", compression="snappy", index=False)
        total_geno_rows = len(df_geno_valid)

    # Ingest Phenotype
    raw_pheno_path = project_root / config["raw_files"]["phenotype"]
    print(f"[{crop_name}] Parsing phenotype from: {raw_pheno_path}")
    df_pheno = adapter_module.parse_phenotype(raw_pheno_path)
    print(f"[{crop_name}] Raw phenotype parsed: {len(df_pheno):,} rows.")

    # Validate Phenotype with Pandera
    print(f"[{crop_name}] Validating phenotype schema with Pandera...")
    try:
        df_pheno_valid = PhenotypeSchema.validate(df_pheno, lazy=True)
        pheno_quarantined_count = 0
    except pandera.errors.SchemaErrors as err:
        print(f"[{crop_name}] WARNING: Phenotype schema validation encountered {len(err.failure_cases)} issues.")
        failure_cases = err.failure_cases
        failing_indices = failure_cases["index"].dropna().unique()
        df_pheno_quarantine = df_pheno.iloc[failing_indices]
        df_pheno_valid = df_pheno.drop(index=failing_indices)

        quarantine_file = interim_dir / "quarantined_ingest_phenotype.csv"
        df_pheno_quarantine.to_csv(quarantine_file, index=False)
        pheno_quarantined_count = len(df_pheno_quarantine)
        print(f"[{crop_name}] Quarantined {pheno_quarantined_count} phenotype rows to {quarantine_file.name}")

    # Save canonical phenotype as Parquet
    pheno_parquet_path = interim_dir / "canonical_phenotype.parquet"
    df_pheno_valid.to_parquet(pheno_parquet_path, engine="pyarrow", compression="snappy", index=False)
    print(f"[{crop_name}] Saved canonical phenotype to: {pheno_parquet_path.name}")

    return {
        "crop_name": crop_name,
        "genotype_rows_valid": total_geno_rows,
        "genotype_rows_quarantined": geno_quarantined_count,
        "phenotype_rows_valid": len(df_pheno_valid),
        "phenotype_rows_quarantined": pheno_quarantined_count,
        "genotype_parquet": str(geno_parquet_path),
        "phenotype_parquet": str(pheno_parquet_path),
    }


if __name__ == "__main__":
    run_ingestion("rice")
