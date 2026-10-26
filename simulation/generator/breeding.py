"""
simulation/generator/breeding.py
Simulates realistic plant breeding cohorts using recombination under Haldane's model.
Features:
  - Vectorized Haldane recombination along physical chromosome coordinates
  - Genomic selection parent policies (top_predicted vs. random)
  - Single-Seed Descent (SSD) F5-equivalent selfing with realistic residual heterozygosity (~6%)
  - 'genotype_shift' immigrant germplasm introduction
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np


class BreedingCohortGenerator:
    def __init__(self, ref_pack_path: str | Path, sim_config: Dict[str, Any]):
        self.ref_pack_path = Path(ref_pack_path)
        if not self.ref_pack_path.exists():
            raise FileNotFoundError(f"Reference pack not found at {self.ref_pack_path}")

        pack = joblib.load(self.ref_pack_path)
        self.marker_ids: List[str] = list(pack["marker_ids"])
        self.chrom: np.ndarray = pack["chrom"]
        self.pos: np.ndarray = pack["pos"]
        self.ref_allele: np.ndarray = pack["ref_allele"]
        self.alt_allele: np.ndarray = pack["alt_allele"]
        self.reference_dosages: np.ndarray = pack["dosages"]  # shape (N_ref, M)
        self.reference_accession_ids: List[str] = list(pack["accession_ids"])

        self.n_markers = len(self.marker_ids)
        self.cM_per_Mb = float(sim_config.get("genetic_map_cM_per_Mb", 4.0))

        # Current breeding pool of parents
        self.parent_dosages = np.copy(self.reference_dosages)
        self.parent_ids = list(self.reference_accession_ids)

        # Precompute chromosome index slices and recombination intervals
        self.chrom_slices: Dict[str, Tuple[int, int]] = {}
        self.chrom_recomb_probs: Dict[str, np.ndarray] = {}
        self._precompute_recombination()

    def reset(self):
        """Reset breeding candidate pool to initial reference accessions."""
        self.parent_dosages = np.copy(self.reference_dosages)
        self.parent_ids = list(self.reference_accession_ids)

    def _precompute_recombination(self):
        unique_chroms = []
        for c in self.chrom:
            if c not in unique_chroms:
                unique_chroms.append(c)

        # Recombination rate per base pair: (cM_per_Mb / 100) / 1,000,000 = cM_per_Mb * 1e-8
        rate_per_bp = (self.cM_per_Mb / 100.0) / 1_000_000.0

        for c in unique_chroms:
            idx = np.where(self.chrom == c)[0]
            start_idx = int(idx[0])
            end_idx = int(idx[-1]) + 1
            self.chrom_slices[c] = (start_idx, end_idx)

            c_pos = self.pos[start_idx:end_idx]
            if len(c_pos) > 1:
                delta_pos = np.diff(c_pos)
                delta_pos = np.maximum(delta_pos, 1)
                # Genetic distance d in Morgans
                d = rate_per_bp * delta_pos
                # Haldane's mapping function: r = 0.5 * (1 - exp(-2d))
                r = 0.5 * (1.0 - np.exp(-2.0 * d))
                r = np.clip(r, 1e-7, 0.499)
            else:
                r = np.array([], dtype=float)
            self.chrom_recomb_probs[c] = r

    def generate_cohort(
        self,
        tick: int,
        cohort_size: int,
        parent_policy: str,
        rng: np.random.RandomState,
        predicted_yields: Optional[Dict[str, float]] = None,
        active_event_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Simulate a new breeding cohort via crossing and F5 selfing.
        Returns:
            cohort_dosages: np.ndarray of shape (cohort_size, n_markers) with values in {0, 1, 2}
            sample_ids: List of sample names
        """
        n_parents = len(self.parent_ids)

        # 1. Select parent pairs based on policy
        if parent_policy == "top_predicted" and predicted_yields and len(predicted_yields) > 0:
            # Rank current parents by predicted yield
            scores = np.array([predicted_yields.get(pid, 5000.0) for pid in self.parent_ids], dtype=float)
            # Softmax / top quartile weighting to simulate realistic genomic selection
            q75 = np.percentile(scores, 75)
            weights = np.where(scores >= q75, 3.0, 0.5)
            prob = weights / weights.sum()
            p1_indices = rng.choice(n_parents, size=cohort_size, p=prob, replace=True)
            p2_indices = rng.choice(n_parents, size=cohort_size, p=prob, replace=True)
        else:
            p1_indices = rng.choice(n_parents, size=cohort_size, replace=True)
            p2_indices = rng.choice(n_parents, size=cohort_size, replace=True)

        # 2. Vectorized chromosome-by-chromosome crossing and recombination
        cohort_dosages = np.zeros((cohort_size, self.n_markers), dtype=np.float32)

        for c, (start, end) in self.chrom_slices.items():
            r = self.chrom_recomb_probs[c]
            n_chr_markers = end - start

            parent1_chr = self.parent_dosages[p1_indices, start:end]
            parent2_chr = self.parent_dosages[p2_indices, start:end]

            # Parent 1 and Parent 2 allele contributions (each in {0, 1})
            p1_alleles = np.where(parent1_chr >= 1.5, 1.0, np.where(parent1_chr <= 0.5, 0.0, rng.binomial(1, 0.5, size=parent1_chr.shape)))
            p2_alleles = np.where(parent2_chr >= 1.5, 1.0, np.where(parent2_chr <= 0.5, 0.0, rng.binomial(1, 0.5, size=parent2_chr.shape)))

            if len(r) > 0:
                # Recombination breakpoint probability in RILs after F5 selfing (Haldane & Waddington 1936: 2r / (1 + 2r))
                r_ril = np.clip(2.0 * r / (1.0 + 2.0 * r), 1e-7, 0.499)
                crossovers = rng.rand(cohort_size, len(r)) < r_ril[None, :]
                start_strand = rng.binomial(1, 0.5, size=(cohort_size, 1))
                strands = np.hstack([start_strand, np.cumsum(crossovers, axis=1)]) % 2

                # Mosaic chromosome: large blocks alternating between parent 1 and parent 2
                inbred_alleles = np.where(strands == 0, p1_alleles, p2_alleles)
            else:
                inbred_alleles = p1_alleles

            # Near-inbred diploid dosage (0.0 or 2.0)
            f5_dosage = inbred_alleles * 2.0

            # Exact F5 residual heterozygosity (~6.25% = (1/2)^4)
            is_het_residual = rng.rand(cohort_size, n_chr_markers) < 0.0625
            f5_dosage[is_het_residual] = 1.0

            cohort_dosages[:, start:end] = f5_dosage

        # 4. Handle genotype_shift event (immigrant germplasm)
        if active_event_params and "immigrant_fraction" in active_event_params:
            imm_frac = float(active_event_params["immigrant_fraction"])
            n_immigrants = int(round(cohort_size * imm_frac))
            if n_immigrants > 0:
                # Invert or perturb allele frequencies on distinct ancestral linkage blocks
                imm_idx = np.arange(cohort_size - n_immigrants, cohort_size)
                # Resample from opposite allele frequency tails
                af = np.mean(self.reference_dosages, axis=0) / 2.0
                divergent_dosages = np.where(rng.rand(n_immigrants, self.n_markers) < (1.0 - af)[None, :], 2.0, 0.0)
                # Add residual heterozygosity
                het_mask = rng.rand(n_immigrants, self.n_markers) < 0.05
                divergent_dosages[het_mask] = 1.0
                cohort_dosages[imm_idx, :] = divergent_dosages

        # Update candidate breeding parent pool with successful progeny
        sample_ids = [f"S_T{tick}_{i+1:03d}" for i in range(cohort_size)]
        self.parent_dosages = np.vstack([self.parent_dosages, cohort_dosages])
        self.parent_ids.extend(sample_ids)

        # Keep pool bounded to most recent 800 candidates to prevent unbounded memory growth
        if len(self.parent_ids) > 800:
            self.parent_dosages = self.parent_dosages[-800:]
            self.parent_ids = self.parent_ids[-800:]

        return cohort_dosages, sample_ids
