"""
tests/fixtures/synthetic_crop.py
Generates mock crop datasets for testing, parameterized across ploidy (ploidy=2 and ploidy=6).
"""
import numpy as np
import pandas as pd


def generate_synthetic_genotype(
    n_markers: int = 50,
    n_samples: int = 20,
    ploidy: int = 2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate a synthetic call matrix and marker metadata.
    Returns:
        (call_matrix, marker_meta)
    """
    rng = np.random.RandomState(random_state)
    marker_ids = [f"M_{i:04d}" for i in range(n_markers)]
    sample_ids = [f"S_{j:03d}" for j in range(n_samples)]

    ref_alleles = rng.choice(["A", "C", "G", "T"], size=n_markers)
    alt_alleles = []
    bases = ["A", "C", "G", "T"]
    for r in ref_alleles:
        rem = [b for b in bases if b != r]
        alt_alleles.append(rng.choice(rem))

    marker_meta = pd.DataFrame({
        "chrom": rng.choice(["1", "2", "3"], size=n_markers),
        "pos": rng.randint(1000, 500000, size=n_markers),
        "ref_allele": ref_alleles,
        "alt_allele": alt_alleles,
    }, index=marker_ids)

    if ploidy == 2:
        # Calls: Ref (A), Alt (B), Het (R, Y, etc.), Missing (N)
        possible_calls = ["REF", "ALT", "HET", "N"]
        p = [0.6, 0.25, 0.1, 0.05]
    else:
        # Hexaploid
        possible_calls = [f"ALT_{k}" for k in range(ploidy + 1)] + ["N"]
        p = [1.0 / len(possible_calls)] * len(possible_calls)

    calls = np.empty((n_markers, n_samples), dtype=object)
    for i in range(n_markers):
        ref = marker_meta.loc[marker_ids[i], "ref_allele"]
        alt = marker_meta.loc[marker_ids[i], "alt_allele"]
        if ploidy == 2:
            c_types = rng.choice(possible_calls, size=n_samples, p=p)
            for j, ct in enumerate(c_types):
                if ct == "REF":
                    calls[i, j] = ref
                elif ct == "ALT":
                    calls[i, j] = alt
                elif ct == "HET":
                    calls[i, j] = "R" if set([ref, alt]) == {"A", "G"} else "Y"
                else:
                    calls[i, j] = "N"
        else:
            # Multi-character calls for higher ploidy
            for j in range(n_samples):
                k = rng.randint(0, ploidy + 1)
                calls[i, j] = (alt * k) + (ref * (ploidy - k))

    call_matrix = pd.DataFrame(calls, index=marker_ids, columns=sample_ids)
    return call_matrix, marker_meta
