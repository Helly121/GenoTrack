# Rice Diversity Crop Pack

## Dataset Overview
- **Crop:** Rice (*Oryza sativa*), diploid (`ploidy = 2`).
- **Genotype Data:** Single Nucleotide Polymorphism (SNP) dataset formatted as HapMap (`MET_crfilt_.75_allchrom.hmp.txt`).
  - Contains 108,025 markers across 12 rice chromosomes.
  - 368 biological rice accessions organized in genotyping batches identified by sample ID prefixes (`A`, `B`, `M`).
  - Plate control `BLANK` and non-sample column `call_rate` are explicitly excluded during ingestion.
- **Phenotype & Environment Data:** 8 Replicated Yield Trials (RYT) spanning 2009 to 2012 across Dry Season (DS, Season 1) and Wet Season (WS, Season 2).
  - Evaluates primary target trait `grain_yield` (`Kg_ha`) alongside `FL` (days to flowering), `MAT` (maturity), `PLTHGT` (plant height), `TILLER` (tiller count), and `LDG` (lodging score).
  - Captures trial-level covariates: `Missing_Hill` and `MC` (grain moisture content).

## Data Cleaning & Processing Notes
1. **Ploidy-parameterized dosage:** Allele calls are mapped to dosages `0.0`, `1.0`, `2.0` based on the alternate allele count using vectorized array operations.
2. **Quality Control:** Filters markers with missingness > 20% or Minor Allele Frequency (MAF) < 0.05. Quarantined records are preserved in `data/interim/`.
3. **Patterson-Standardized PCA:** Subpopulation structure is resolved using allele-frequency-standardized PCA to avoid spurious high-variance marker dominance.
4. **Mandatory G×E Architecture:** Models explicitly capture shared genetic effects and environment-specific interaction components.
