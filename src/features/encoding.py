"""
src/features/encoding.py
Ploidy-parameterized dosage encoding (0..ploidy scale).
Vectorized implementation without row-wise loops.
"""
import numpy as np
import pandas as pd


def encode_dosage_vectorized(
    call_matrix: pd.DataFrame,
    marker_meta: pd.DataFrame,
    ploidy: int = 2,
) -> pd.DataFrame:
    """
    Encode an (M markers x N samples) DataFrame of calls into an (N samples x M markers)
    dosage matrix on a 0..ploidy scale.
    Parameters:
        call_matrix: DataFrame with index=marker_id, columns=sample_id, values=call string
        marker_meta: DataFrame with index=marker_id, containing 'ref_allele', 'alt_allele'
        ploidy: Organism ploidy (2 for diploid rice, 6 for hexaploid wheat, etc.)
    Returns:
        DataFrame with index=sample_id, columns=marker_id, values=float dosage in [0, ploidy] or NaN
    """
    # Align markers
    common_markers = call_matrix.index.intersection(marker_meta.index)
    calls = call_matrix.loc[common_markers].values  # shape: (M, N)
    refs = marker_meta.loc[common_markers, "ref_allele"].astype(str).values[:, None]  # shape: (M, 1)
    alts = marker_meta.loc[common_markers, "alt_allele"].astype(str).values[:, None]  # shape: (M, 1)

    # Identify missing calls
    missing_codes = ["N", "NA", "-", "0", "X", "", "None", "nan"]
    is_missing = np.isin(calls, missing_codes) | pd.isna(calls)

    dosage = np.full(calls.shape, np.nan, dtype=np.float32)

    if ploidy == 2:
        # Standard diploid rules:
        # 1. Homozygous alternate -> dosage = 2.0
        is_homo_alt = (calls == alts) & ~is_missing
        dosage[is_homo_alt] = 2.0

        # 2. Homozygous reference -> dosage = 0.0
        is_homo_ref = (calls == refs) & ~is_missing
        dosage[is_homo_ref] = 0.0

        # 3. Heterozygotes (IUPAC codes or explicit 'R','Y','S','W','K','M')
        # IUPAC mapping:
        # R = A/G, Y = C/T, S = G/C, W = A/T, K = G/T, M = A/C
        het_codes = ["R", "Y", "S", "W", "K", "M"]
        is_het = np.isin(calls, het_codes) & ~is_missing
        dosage[is_het] = 1.0

        # 4. Multi-character calls e.g. 'AG', 'GA'
        is_two_char = (np.char.str_len(calls.astype(str)) == 2) & ~is_missing
        if np.any(is_two_char):
            # Check characters
            c_str = calls.astype(str)
            char1 = np.char.mod("%s", np.char.asarray(c_str)[:, :, None])
            # Count occurrences of alternate allele
            # For each cell, count how many characters match alt
            # Vectorized char matching:
            alt_char = alts[:, 0]
            ref_char = refs[:, 0]
            for i in range(calls.shape[0]):
                mask_row = is_two_char[i]
                if not np.any(mask_row):
                    continue
                row_calls = c_str[i, mask_row]
                row_alt = alt_char[i]
                row_ref = ref_char[i]
                c_alt = np.char.count(row_calls, row_alt)
                dosage[i, mask_row] = c_alt.astype(np.float32)
    else:
        # Generalized ploidy > 2:
        # Count alternate allele copies out of ploidy
        c_str = calls.astype(str)
        alt_char = alts[:, 0]
        for i in range(calls.shape[0]):
            row_calls = c_str[i]
            row_alt = alt_char[i]
            row_missing = is_missing[i]
            c_alt = np.char.count(row_calls, row_alt).astype(np.float32)
            c_alt[row_missing] = np.nan
            dosage[i] = c_alt

    # Transpose to (N samples x M markers) per Section 6.3 of spec.md
    dosage_df = pd.DataFrame(
        dosage.T,
        index=call_matrix.columns,
        columns=common_markers,
    )
    return dosage_df
