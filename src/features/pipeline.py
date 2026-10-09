"""
src/features/pipeline.py
Feature engineering orchestrator:
1. Vectorized ploidy dosage encoding.
2. Missing dosage imputation.
3. Patterson-standardized PCA subpopulation clustering.
4. Inner join with target phenotype and environment annotations.
5. Save model-ready datasets and feature metadata to data/processed/.
"""
import json
from pathlib import Path
import yaml
import numpy as np
import pandas as pd

from .encoding import encode_dosage_vectorized
from .imputation import impute_dosage
from .split import compute_population_clusters


def run_features(
    crop_name: str = "rice",
    target_trait: str | None = None,
    project_root: Path | None = None,
) -> dict:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    config_path = project_root / "crops" / crop_name / "config.yaml"
    traits_path = project_root / "crops" / crop_name / "traits.yaml"
    interim_dir = project_root / "data" / "interim"
    processed_dir = project_root / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    with open(traits_path, "r") as f:
        traits_cfg = yaml.safe_load(f)

    # Determine target trait
    if target_trait is None:
        for t_name, t_meta in traits_cfg.get("traits", {}).items():
            if t_meta.get("primary_target", False):
                target_trait = t_name
                break
    if target_trait is None:
        target_trait = "grain_yield"

    ploidy = int(config.get("ploidy", 2))
    imputation_strategy = config["qc"].get("imputation_strategy", "per_marker_mean")
    n_folds = int(config["cv"].get("n_folds", 5))
    min_cluster_size = int(config["cv"].get("min_cluster_size", 15))

    # Load cleaned phenotype table
    pheno_file = interim_dir / "cleaned_phenotype.parquet"
    if not pheno_file.exists():
        raise FileNotFoundError("Cleaned phenotype file not found in data/interim/. Run QC first.")
    df_pheno = pd.read_parquet(pheno_file)

    # 1. Vectorized Dosage Encoding
    raw_geno_path = project_root / config["raw_files"]["genotype"]
    manifest_path = processed_dir / "manifest.json"
    print(f"[{crop_name}] Loading filtered marker layout for dosage encoding (ploidy={ploidy})...")

    df_raw = pd.read_csv(raw_geno_path, sep="\t", keep_default_na=False, low_memory=False)
    # Exclude quarantined samples and markers
    q_sample_file = interim_dir / "quarantined_samples_missingness.csv"
    q_samples = pd.read_csv(q_sample_file)["sample_id"].tolist() if q_sample_file.exists() else []

    valid_samples = [c for c in df_raw.columns[11:] if c not in q_samples and c != "BLANK" and c != "call_rate" and not c.startswith("Unnamed")]

    q_miss_file = interim_dir / "quarantined_markers_missingness.csv"
    q_maf_file = interim_dir / "quarantined_markers_maf.csv"
    q_miss = pd.read_csv(q_miss_file)["marker_id"].tolist() if q_miss_file.exists() else []
    q_maf = pd.read_csv(q_maf_file)["marker_id"].tolist() if q_maf_file.exists() else []
    bad_markers = set(q_miss).union(set(q_maf))

    valid_mask = ~df_raw["rs#"].astype(str).isin(bad_markers)
    df_clean_raw = df_raw[valid_mask].reset_index(drop=True)

    call_matrix = df_clean_raw.set_index("rs#")[valid_samples]
    alleles_split = df_clean_raw["alleles"].astype(str).str.split("/", n=1, expand=True)
    marker_meta = pd.DataFrame({
        "chrom": df_clean_raw["chrom"].astype(str).values,
        "pos": pd.to_numeric(df_clean_raw["pos"], errors="coerce").fillna(0).astype(int).values,
        "ref_allele": alleles_split[0].values,
        "alt_allele": alleles_split[1].values if alleles_split.shape[1] > 1 else None,
    }, index=df_clean_raw["rs#"].astype(str).values)

    dosage_raw = encode_dosage_vectorized(call_matrix, marker_meta, ploidy=ploidy)
    print(f"[{crop_name}] Dosage matrix encoded: shape {dosage_raw.shape} (samples x markers).")

    # 2. Dosage Imputation
    print(f"[{crop_name}] Imputing missing dosages using '{imputation_strategy}' strategy...")
    dosage_imputed = impute_dosage(dosage_raw, strategy=imputation_strategy)

    # 3. Patterson-scaled PCA Subpopulation Clustering
    print(f"[{crop_name}] Computing Patterson-standardized PCA and subpopulation clusters...")
    clusters = compute_population_clusters(
        dosage_imputed,
        n_clusters=n_folds,
        n_pcs=10,
        ploidy=ploidy,
        min_cluster_size=min_cluster_size,
    )

    # Save clean dosage matrix
    dosage_path = processed_dir / "dosage_matrix.parquet"
    dosage_imputed.to_parquet(dosage_path, engine="pyarrow", compression="snappy")
    print(f"[{crop_name}] Saved dosage matrix to: {dosage_path.name}")

    # 4. Filter Phenotype to Target Trait
    df_pheno_target = df_pheno[df_pheno["trait"] == target_trait].copy()
    if len(df_pheno_target) == 0:
        raise ValueError(f"No records found in phenotype data for target trait '{target_trait}'.")

    # Parse covariates column if present
    covariate_dfs = []
    for cov_str in df_pheno_target["covariates"]:
        if pd.notnull(cov_str):
            try:
                covariate_dfs.append(json.loads(cov_str))
            except Exception:
                covariate_dfs.append({})
        else:
            covariate_dfs.append({})
    cov_df = pd.DataFrame(covariate_dfs, index=df_pheno_target.index)
    # Prefix covariate column names
    cov_df.columns = [f"cov_{c}" for c in cov_df.columns]

    # Combine target phenotype with covariates
    df_pheno_full = pd.concat([df_pheno_target, cov_df], axis=1)

    # Inner Join with Dosage Matrix on sample_id
    genotype_samples = set(dosage_imputed.index)
    phenotype_samples = set(df_pheno_full["sample_id"].unique())
    common_samples = sorted(list(genotype_samples.intersection(phenotype_samples)))
    unmapped_pheno = phenotype_samples - genotype_samples
    if unmapped_pheno:
        print(f"[{crop_name}] Notice: {len(unmapped_pheno)} phenotype sample IDs not found in genotype data.")

    df_pheno_filtered = df_pheno_full[df_pheno_full["sample_id"].isin(common_samples)].copy()
    df_pheno_filtered["subpopulation_cluster"] = df_pheno_filtered["sample_id"].map(clusters)

    # Save aligned clean dosage matrix (float32)
    dosage_path = processed_dir / "dosage_matrix.parquet"
    dosage_clean = dosage_imputed.loc[common_samples].astype(np.float32)
    dosage_clean.to_parquet(dosage_path, engine="pyarrow", compression="snappy")
    print(f"[{crop_name}] Saved clean dosage matrix to: {dosage_path.name}")

    # Save lightweight model dataset
    model_dataset = df_pheno_filtered.reset_index(drop=True)
    model_dataset_path = processed_dir / f"model_dataset_{target_trait}.parquet"
    model_dataset.to_parquet(model_dataset_path, engine="pyarrow", compression="snappy", index=False)
    print(f"[{crop_name}] Saved model-ready dataset: {len(model_dataset):,} rows across {len(common_samples):,} genotypes.")

    # Save feature metadata
    metadata = {
        "crop_name": crop_name,
        "target_trait": target_trait,
        "ploidy": ploidy,
        "n_samples": len(common_samples),
        "n_markers": len(dosage_imputed.columns),
        "n_observations": len(model_dataset),
        "environments": sorted(df_pheno_filtered["environment"].unique().tolist()),
        "subpopulation_cluster_counts": {
            str(k): int(v) for k, v in clusters.value_counts().items()
        },
        "marker_ids": list(dosage_imputed.columns),
    }
    meta_path = processed_dir / "feature_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"[{crop_name}] Saved feature metadata to: {meta_path.name}")

    return {
        "target_trait": target_trait,
        "n_samples": len(common_samples),
        "n_markers": len(dosage_imputed.columns),
        "n_observations": len(model_dataset),
        "environments_count": len(metadata["environments"]),
        "dosage_matrix_path": str(dosage_path),
        "model_dataset_path": str(model_dataset_path),
    }


if __name__ == "__main__":
    run_features("rice")
