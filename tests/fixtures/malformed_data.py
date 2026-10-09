"""
tests/fixtures/malformed_data.py
Generates deliberately malformed genotype data to test Data CI and Pandera quarantine.
"""
import pandas as pd

def generate_malformed_genotype() -> pd.DataFrame:
    """Return a DataFrame with intentional schema violations."""
    return pd.DataFrame([
        # Valid row
        {
            "marker_id": "M_0001",
            "chrom": "1",
            "pos": 1000,
            "ref_allele": "A",
            "alt_allele": "G",
            "ploidy": 2,
            "sample_id": "A1201",
            "batch": "A",
            "call": "A",
            "dosage": None,
            "source_format": "hapmap",
        },
        # Invalid row: numerical call (format corruption)
        {
            "marker_id": "M_0002",
            "chrom": "1",
            "pos": 2000,
            "ref_allele": "C",
            "alt_allele": "T",
            "ploidy": 2,
            "sample_id": "A1202",
            "batch": "A",
            "call": "99.5%",  # ILLEGAL: stray QC percentage in call column
            "dosage": None,
            "source_format": "hapmap",
        },
        # Invalid row: negative position
        {
            "marker_id": "M_0003",
            "chrom": "1",
            "pos": -50,  # ILLEGAL: negative position
            "ref_allele": "T",
            "alt_allele": "C",
            "ploidy": 2,
            "sample_id": "A1203",
            "batch": "A",
            "call": "T",
            "dosage": None,
            "source_format": "hapmap",
        },
    ])
