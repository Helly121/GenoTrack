"""
simulation/generator/writer.py
Emits simulated cohorts in exact real-world formats:
1. Standard 11-column HapMap genotype text format (tab-delimited).
2. Multi-environment trial phenotype CSV format.
Supports data_quality anomalies (call corruption, missing hill spikes).
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


# IUPAC Degenerate Heterozygote lookup table
IUPAC_HET_MAP = {
    ("A", "G"): "R", ("G", "A"): "R",
    ("C", "T"): "Y", ("T", "C"): "Y",
    ("G", "C"): "S", ("C", "G"): "S",
    ("A", "T"): "W", ("T", "A"): "W",
    ("G", "T"): "K", ("T", "G"): "K",
    ("A", "C"): "M", ("C", "A"): "M",
}


def get_iupac_het(ref: str, alt: str) -> str:
    return IUPAC_HET_MAP.get((ref.upper(), alt.upper()), "R")


class SimulationWriter:
    def __init__(self, ref_pack: Dict[str, Any]):
        self.marker_ids = ref_pack["marker_ids"]
        self.chrom = ref_pack["chrom"]
        self.pos = ref_pack["pos"]
        self.ref_allele = ref_pack["ref_allele"]
        self.alt_allele = ref_pack["alt_allele"]
        self.n_markers = len(self.marker_ids)

        # Precompute allele strings
        self.alleles_str = [f"{r}/{a}" for r, a in zip(self.ref_allele, self.alt_allele)]
        self.het_codes = [get_iupac_het(r, a) for r, a in zip(self.ref_allele, self.alt_allele)]

    def write_genotype_hapmap(
        self,
        cohort_dosages: np.ndarray,  # shape (N_samples, M_markers)
        sample_ids: List[str],
        output_path: str | Path,
        rng: np.random.RandomState,
        active_event_params: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Write cohort genotypes to HapMap text format.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        N, M = cohort_dosages.shape

        # Transpose dosages to (M markers x N samples)
        d_trans = cohort_dosages.T  # shape (M, N)

        # Convert continuous dosages to discrete call strings
        calls = np.empty((M, N), dtype=object)

        # Mask background missing calls (~1.5%)
        bg_missing_mask = rng.rand(M, N) < 0.015

        for j in range(M):
            ref = str(self.ref_allele[j])
            alt = str(self.alt_allele[j])
            het = self.het_codes[j]
            row_d = d_trans[j]

            # Vectorized assignment
            row_calls = np.where(row_d >= 1.5, alt, np.where(row_d <= 0.5, ref, het))
            row_calls[bg_missing_mask[j]] = "NA"
            calls[j] = row_calls

        # Handle data_quality event (corrupted calls)
        if active_event_params and "corrupted_calls_fraction" in active_event_params:
            corrupt_frac = float(active_event_params["corrupted_calls_fraction"])
            corrupt_mask = rng.rand(M, N) < corrupt_frac
            calls[corrupt_mask] = "?"  # invalid non-IUPAC symbol caught by Pandera QC

        # Build metadata frame
        df_meta = pd.DataFrame({
            "rs#": self.marker_ids,
            "alleles": self.alleles_str,
            "chrom": self.chrom,
            "pos": self.pos,
            "strand": "+",
            "assembly#": "NA",
            "center": "NA",
            "protLSID": "NA",
            "assayLSID": "NA",
            "panelLSID": "NA",
            "QCcode": "NA",
        })

        df_samples = pd.DataFrame(calls, columns=sample_ids)
        df_hmp = pd.concat([df_meta, df_samples], axis=1)

        # Write tab-delimited text
        df_hmp.to_csv(out, sep="\t", index=False)
        return out

    def write_phenotype_csv(
        self,
        df_phenotype: pd.DataFrame,
        output_path: str | Path,
    ) -> Path:
        """
        Write trial phenotypes to CSV.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df_phenotype.to_csv(out, index=False)
        return out
