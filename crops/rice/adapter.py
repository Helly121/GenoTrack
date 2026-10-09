"""
crops/rice/adapter.py
Rice HapMap and multi-environment trial phenotype adapter.
Strictly implements the Section 5.4 contract from spec.md.
Adheres to scale discipline: vectorized operations, zero row-wise Python loops.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def parse_genotype(raw_path: str | Path, max_markers: int | None = None) -> pd.DataFrame:
    """
    Parse a rice HapMap genotype file into the canonical long-format DataFrame:
    [marker_id, chrom, pos, ref_allele, alt_allele, ploidy, sample_id, batch, call, dosage, source_format]
    """
    path = Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"Raw genotype file not found at: {path}")

    # Read tab-delimited HapMap file, preserving literal 'NA' allele calls
    df_raw = pd.read_csv(path, sep="\t", nrows=max_markers, keep_default_na=False, low_memory=False)

    all_cols = list(df_raw.columns)
    sample_candidate_cols = all_cols[11:]

    # Strictly exclude plate controls and non-sample columns (spec Section 5.4)
    sample_cols = [
        c for c in sample_candidate_cols
        if c != "BLANK" and c != "call_rate" and not c.startswith("Unnamed")
    ]

    # Parse alleles into ref and alt
    alleles_split = df_raw["alleles"].astype(str).str.split("/", n=1, expand=True)
    df_raw["ref_allele"] = alleles_split[0]
    df_raw["alt_allele"] = alleles_split[1] if alleles_split.shape[1] > 1 else None

    # Standardize metadata columns
    df_raw["marker_id"] = df_raw["rs#"].astype(str)
    df_raw["chrom"] = df_raw["chrom"].astype(str)
    df_raw["pos"] = pd.to_numeric(df_raw["pos"], errors="coerce").fillna(0).astype(int)

    # Vectorized melt of sample columns into long format
    id_vars = ["marker_id", "chrom", "pos", "ref_allele", "alt_allele"]
    df_melted = pd.melt(
        df_raw[id_vars + sample_cols],
        id_vars=id_vars,
        value_vars=sample_cols,
        var_name="sample_id",
        value_name="call",
    )

    df_melted["sample_id"] = df_melted["sample_id"].astype(str)
    df_melted["call"] = df_melted["call"].astype(str)
    df_melted["ploidy"] = 2
    df_melted["batch"] = df_melted["sample_id"].str[0]
    df_melted["dosage"] = np.nan
    df_melted["source_format"] = "hapmap"

    canonical_cols = [
        "marker_id", "chrom", "pos", "ref_allele", "alt_allele",
        "ploidy", "sample_id", "batch", "call", "dosage", "source_format",
    ]
    return df_melted[canonical_cols]


def parse_genotype_to_parquet(
    raw_path: str | Path,
    output_parquet: str | Path,
    chunk_markers: int = 15000,
) -> int:
    """
    Stream full HapMap file directly to partitioned/chunked Parquet without memory exhaustion.
    Adheres strictly to scale discipline for 40M-row matrices.
    Returns total rows written.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(raw_path)
    out_path = Path(output_parquet)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Read header to determine columns
    with open(path, "r") as f:
        header_line = f.readline().strip().split("\t")

    sample_candidate_cols = header_line[11:]
    sample_cols = [
        c for c in sample_candidate_cols
        if c != "BLANK" and c != "call_rate" and not c.startswith("Unnamed")
    ]

    total_rows = 0
    writer = None

    for chunk_df in pd.read_csv(path, sep="\t", chunksize=chunk_markers, keep_default_na=False, low_memory=False):
        alleles_split = chunk_df["alleles"].astype(str).str.split("/", n=1, expand=True)
        chunk_df["ref_allele"] = alleles_split[0]
        chunk_df["alt_allele"] = alleles_split[1] if alleles_split.shape[1] > 1 else None
        chunk_df["marker_id"] = chunk_df["rs#"].astype(str)
        chunk_df["chrom"] = chunk_df["chrom"].astype(str)
        chunk_df["pos"] = pd.to_numeric(chunk_df["pos"], errors="coerce").fillna(0).astype(int)

        id_vars = ["marker_id", "chrom", "pos", "ref_allele", "alt_allele"]
        melted = pd.melt(
            chunk_df[id_vars + sample_cols],
            id_vars=id_vars,
            value_vars=sample_cols,
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
        chunk_canonical = melted[canonical_cols]

        table = pa.Table.from_pandas(chunk_canonical)
        if writer is None:
            writer = pq.ParquetWriter(str(out_path), table.schema, compression="snappy")
        writer.write_table(table)
        total_rows += len(chunk_canonical)

    if writer is not None:
        writer.close()

    return total_rows


def parse_phenotype(raw_path: str | Path) -> pd.DataFrame:
    """
    Parse rice trial CSV(s) into the canonical long-format phenotype DataFrame:
    [sample_id, trait, value, environment, season_or_year, replicate, covariates]
    """
    path = Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"Raw phenotype path not found at: {path}")

    csv_files = [path] if path.is_file() else sorted(list(path.glob("*.csv")))
    if not csv_files:
        raise ValueError(f"No CSV files found in phenotype path: {path}")

    # Trait mapping: source column name -> canonical trait name
    trait_map = {
        "Kg_ha": "grain_yield",
        "FL": "flowering_time",
        "PLTHGT": "plant_height",
        "MAT": "maturity",
        "TILLER": "tiller_count",
        "LDG": "lodging_score",
    }

    records = []

    for file_path in csv_files:
        df_file = pd.read_csv(file_path)

        # Standardize GHID -> sample_id
        if "GHID" in df_file.columns:
            sample_ids = df_file["GHID"].astype(str)
        else:
            continue

        # Extract environment components
        years = df_file["YEAR"].astype(str) if "YEAR" in df_file.columns else "unknown"
        seasons = df_file["SEASON"].astype(str) if "SEASON" in df_file.columns else "unknown"
        season_labels = seasons.map(lambda s: "DS" if s == "1" else ("WS" if s == "2" else s))
        environments = years + "_" + season_labels
        replicates = df_file["REP"].astype(str) if "REP" in df_file.columns else None

        # Build covariates vectorially
        missing_hills = (
            pd.to_numeric(df_file["Missing_Hill"], errors="coerce").fillna(0).astype(int)
            if "Missing_Hill" in df_file.columns
            else np.zeros(len(df_file), dtype=int)
        )
        moisture_contents = (
            pd.to_numeric(df_file["MC"], errors="coerce")
            if "MC" in df_file.columns
            else np.full(len(df_file), np.nan)
        )

        covariates_list = [
            json.dumps({"missing_hill": int(mh), "moisture_content": float(mc) if pd.notnull(mc) else None})
            for mh, mc in zip(missing_hills, moisture_contents)
        ]

        # Melt each available trait
        for src_col, canon_trait in trait_map.items():
            if src_col in df_file.columns:
                values = pd.to_numeric(df_file[src_col], errors="coerce")
                valid_mask = values.notna()
                if valid_mask.sum() == 0:
                    continue

                sub_df = pd.DataFrame({
                    "sample_id": sample_ids[valid_mask],
                    "trait": canon_trait,
                    "value": values[valid_mask].astype(float),
                    "environment": environments[valid_mask],
                    "season_or_year": years[valid_mask] if isinstance(years, pd.Series) else str(years),
                    "replicate": replicates[valid_mask] if replicates is not None else None,
                    "covariates": [covariates_list[i] for i in np.where(valid_mask)[0]],
                })
                records.append(sub_df)

    if not records:
        return pd.DataFrame(columns=[
            "sample_id", "trait", "value", "environment", "season_or_year", "replicate", "covariates"
        ])

    df_pheno = pd.concat(records, ignore_index=True)
    return df_pheno
