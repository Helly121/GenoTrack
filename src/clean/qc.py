"""
src/clean/qc.py
Generic, crop-agnostic quality control filtering:
1. Missingness filter (markers and samples).
2. Minor Allele Frequency (MAF) filter.
3. Batch-effect confounding check.
4. Quarantine export for all rejected markers and samples.
5. manifest.json generation for auditability.
Scale-disciplined implementation using vectorized 2D array broadcasting.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import stats
import yaml


def compute_file_hash(filepath: Path) -> str:
    """Compute sha256 hash of a file for lineage tracking."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_qc(crop_name: str = "rice", project_root: Path | None = None) -> dict:
    """
    Run generic QC pipeline on canonical interim tables.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    config_path = project_root / "crops" / crop_name / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    raw_geno_path = project_root / config["raw_files"]["genotype"]
    interim_dir = project_root / "data" / "interim"
    processed_dir = project_root / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    pheno_path = interim_dir / "canonical_phenotype.parquet"
    if not pheno_path.exists():
        raise FileNotFoundError("Canonical phenotype table not found. Run ingestion first.")

    raw_data_hash = compute_file_hash(raw_geno_path)
    config_hash = compute_file_hash(config_path)

    missingness_thresh = float(config["qc"].get("missingness_threshold", 0.20))
    maf_thresh = float(config["qc"].get("maf_threshold", 0.05))

    print(f"[{crop_name}] Loading raw matrix layout for vectorized QC...")
    df_raw = pd.read_csv(raw_geno_path, sep="\t", keep_default_na=False, low_memory=False)
    sample_cols = [c for c in df_raw.columns[11:] if c != "BLANK" and c != "call_rate" and not c.startswith("Unnamed")]

    n_raw_markers = len(df_raw)
    n_raw_samples = len(sample_cols)
    print(f"[{crop_name}] Initial count: {n_raw_markers:,} markers across {n_raw_samples:,} samples.")

    # 1. Missingness Evaluation in 2D array space
    call_matrix = df_raw[sample_cols].values
    missing_codes = ["N", "NA", "-", "0", "X", "", "nan", "None"]
    is_missing = np.isin(call_matrix, missing_codes)

    # Sample missingness
    sample_miss = is_missing.mean(axis=0)
    sample_miss_series = pd.Series(sample_miss, index=sample_cols)
    failing_samples = sample_miss_series[sample_miss_series > missingness_thresh].index.tolist()

    if failing_samples:
        df_sample_quarantine = pd.DataFrame({
            "sample_id": failing_samples,
            "missingness": sample_miss_series[failing_samples].values,
            "reason": f"missingness > {missingness_thresh}",
        })
        sample_quarantine_path = interim_dir / "quarantined_samples_missingness.csv"
        df_sample_quarantine.to_csv(sample_quarantine_path, index=False)
        print(f"[{crop_name}] Quarantined {len(failing_samples)} samples to {sample_quarantine_path.name}")
    else:
        print(f"[{crop_name}] All samples passed missingness threshold ({missingness_thresh}).")

    valid_samples = [s for s in sample_cols if s not in failing_samples]
    valid_sample_idx = [i for i, s in enumerate(sample_cols) if s not in failing_samples]

    # Filter out failing samples
    call_matrix = call_matrix[:, valid_sample_idx]
    is_missing = is_missing[:, valid_sample_idx]

    # Marker missingness
    marker_miss = is_missing.mean(axis=1)
    marker_ids = df_raw["rs#"].astype(str).values
    marker_miss_series = pd.Series(marker_miss, index=marker_ids)
    failing_markers_miss = marker_miss_series[marker_miss_series > missingness_thresh].index.tolist()

    if failing_markers_miss:
        df_marker_quarantine = pd.DataFrame({
            "marker_id": failing_markers_miss,
            "missingness": marker_miss_series[failing_markers_miss].values,
            "reason": f"missingness > {missingness_thresh}",
        })
        marker_quarantine_path = interim_dir / "quarantined_markers_missingness.csv"
        df_marker_quarantine.to_csv(marker_quarantine_path, index=False)
        print(f"[{crop_name}] Quarantined {len(failing_markers_miss):,} markers for missingness.")
    else:
        print(f"[{crop_name}] All markers passed missingness threshold.")

    valid_marker_mask = marker_miss <= missingness_thresh
    call_matrix = call_matrix[valid_marker_mask]
    is_missing = is_missing[valid_marker_mask]
    df_filtered_markers = df_raw[valid_marker_mask].reset_index(drop=True)

    # 2. Vectorized MAF calculation on retained markers
    print(f"[{crop_name}] Computing vectorized Minor Allele Frequency (MAF)...")
    alleles_split = df_filtered_markers["alleles"].astype(str).str.split("/", n=1, expand=True)
    alt_alleles = (alleles_split[1] if alleles_split.shape[1] > 1 else alleles_split[0]).values[:, None]

    alt_matches = (call_matrix == alt_alleles).astype(int) * 2
    het_mask = np.isin(call_matrix, ["R", "Y", "S", "W", "K", "M"])
    alt_counts = np.where(het_mask, 1, alt_matches)
    alt_counts[is_missing] = 0

    total_called = (~is_missing).sum(axis=1) * 2
    total_alt = alt_counts.sum(axis=1)

    alt_freq = np.divide(total_alt, total_called, out=np.zeros_like(total_alt, dtype=float), where=total_called > 0)
    maf = np.minimum(alt_freq, 1.0 - alt_freq)
    maf_series = pd.Series(maf, index=df_filtered_markers["rs#"].astype(str).values)

    failing_markers_maf = maf_series[maf_series < maf_thresh].index.tolist()

    if failing_markers_maf:
        df_maf_quarantine = pd.DataFrame({
            "marker_id": failing_markers_maf,
            "maf": maf_series[failing_markers_maf].values,
            "reason": f"maf < {maf_thresh}",
        })
        maf_quarantine_path = interim_dir / "quarantined_markers_maf.csv"
        df_maf_quarantine.to_csv(maf_quarantine_path, index=False)
        print(f"[{crop_name}] Quarantined {len(failing_markers_maf):,} markers for MAF < {maf_thresh}.")

    final_marker_mask = (maf >= maf_thresh)
    final_retained_df = df_filtered_markers[final_marker_mask].reset_index(drop=True)
    final_valid_markers = final_retained_df["rs#"].astype(str).tolist()

    print(f"[{crop_name}] QC complete: {len(final_valid_markers):,} markers and {len(valid_samples):,} samples retained.")

    # 3. Stream Cleaned Genotype to Parquet
    print(f"[{crop_name}] Streaming cleaned genotype to interim Parquet...")
    cleaned_geno_path = interim_dir / "cleaned_genotype.parquet"
    writer = None
    chunk_size = 15000

    for start_idx in range(0, len(final_retained_df), chunk_size):
        chunk_df = final_retained_df.iloc[start_idx : start_idx + chunk_size].copy()
        chunk_alleles = chunk_df["alleles"].astype(str).str.split("/", n=1, expand=True)
        chunk_df["ref_allele"] = chunk_alleles[0]
        chunk_df["alt_allele"] = chunk_alleles[1] if chunk_alleles.shape[1] > 1 else None
        chunk_df["marker_id"] = chunk_df["rs#"].astype(str)
        chunk_df["chrom"] = chunk_df["chrom"].astype(str)
        chunk_df["pos"] = pd.to_numeric(chunk_df["pos"], errors="coerce").fillna(0).astype(int)

        id_vars = ["marker_id", "chrom", "pos", "ref_allele", "alt_allele"]
        melted = pd.melt(
            chunk_df[id_vars + valid_samples],
            id_vars=id_vars,
            value_vars=valid_samples,
            var_name="sample_id",
            value_name="call",
        )
        melted["sample_id"] = melted["sample_id"].astype(str)
        melted["call"] = melted["call"].astype(str)
        melted["ploidy"] = 2
        melted["batch"] = melted["sample_id"].str[0]
        melted["dosage"] = np.nan
        melted["source_format"] = "hapmap"

        canonical_cols = [
            "marker_id", "chrom", "pos", "ref_allele", "alt_allele",
            "ploidy", "sample_id", "batch", "call", "dosage", "source_format",
        ]
        table = pa.Table.from_pandas(melted[canonical_cols])
        if writer is None:
            writer = pq.ParquetWriter(str(cleaned_geno_path), table.schema, compression="snappy")
        writer.write_table(table)

    if writer is not None:
        writer.close()
    print(f"[{crop_name}] Saved cleaned genotype Parquet: {cleaned_geno_path.name}")

    # 4. Clean Phenotype Table
    df_pheno = pd.read_parquet(pheno_path)
    cleaned_pheno = df_pheno[df_pheno["sample_id"].isin(valid_samples)].copy()
    cleaned_pheno_path = interim_dir / "cleaned_phenotype.parquet"
    cleaned_pheno.to_parquet(cleaned_pheno_path, engine="pyarrow", compression="snappy", index=False)
    print(f"[{crop_name}] Saved cleaned phenotype Parquet: {cleaned_pheno_path.name}")

    # 5. Batch-effect Confounding Check
    print(f"[{crop_name}] Running batch-effect confounding diagnostics...")
    batch_effects_report = {}
    sample_batch_map = {s: s[0] for s in valid_samples}
    cleaned_pheno["batch"] = cleaned_pheno["sample_id"].map(sample_batch_map)

    for trait_name, group in cleaned_pheno.groupby("trait"):
        batch_groups = [vals["value"].dropna().values for _, vals in group.groupby("batch") if len(vals) > 5]
        if len(batch_groups) > 1:
            try:
                f_stat, p_val = stats.f_oneway(*batch_groups)
                batch_effects_report[trait_name] = {
                    "f_stat": float(f_stat) if not np.isnan(f_stat) else None,
                    "p_value": float(p_val) if not np.isnan(p_val) else None,
                    "confounding_flag": bool(p_val < 0.01) if not np.isnan(p_val) else False,
                }
            except Exception:
                pass

    # 6. Write manifest.json
    manifest = {
        "crop_name": crop_name,
        "data_hash": raw_data_hash,
        "config_hash": config_hash,
        "qc_thresholds": {
            "missingness_threshold": missingness_thresh,
            "maf_threshold": maf_thresh,
        },
        "counts": {
            "raw_markers": n_raw_markers,
            "retained_markers": len(final_valid_markers),
            "quarantined_markers_missingness": len(failing_markers_miss),
            "quarantined_markers_maf": len(failing_markers_maf),
            "raw_samples": n_raw_samples,
            "retained_samples": len(valid_samples),
            "quarantined_samples": len(failing_samples),
        },
        "batch_effects_audit": batch_effects_report,
    }

    manifest_path = processed_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[{crop_name}] Saved manifest audit to: {manifest_path.name}")

    return manifest


if __name__ == "__main__":
    run_qc("rice")
