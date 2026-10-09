"""
src/ingest/schemas.py
Pandera schema definitions for canonical genotype and phenotype tables.
Crop-agnostic data quality contracts per Section 5.1, 5.2, and 6.1 of spec.md.
"""
import pandera.pandas as pa
from pandera.typing import Series
from typing import Optional

# Standard DNA single-base alleles + IUPAC ambiguity codes for heterozygotes
# A, C, G, T, R (A/G), Y (C/T), S (G/C), W (A/T), K (G/T), M (A/C), N, NA, -, 0, X
VALID_CALLS_REGEX = r"^[ACGTMRWSYKN0X\-]+$|^NA$|^nan$"
VALID_ALLELE_REGEX = r"^[ACGTN\-]+$|^NA$|^nan$"

class GenotypeSchema(pa.DataFrameModel):
    marker_id: Series[str] = pa.Field(coerce=True, nullable=False)
    chrom: Series[str] = pa.Field(coerce=True, nullable=False)
    pos: Series[int] = pa.Field(ge=0, coerce=True, nullable=False)
    ref_allele: Series[str] = pa.Field(str_matches=VALID_ALLELE_REGEX, coerce=True, nullable=False)
    alt_allele: Optional[Series[str]] = pa.Field(str_matches=VALID_ALLELE_REGEX, coerce=True, nullable=True)
    ploidy: Series[int] = pa.Field(ge=1, coerce=True, nullable=False)
    sample_id: Series[str] = pa.Field(coerce=True, nullable=False)
    batch: Optional[Series[str]] = pa.Field(coerce=True, nullable=True)
    call: Series[str] = pa.Field(str_matches=VALID_CALLS_REGEX, coerce=True, nullable=True)
    dosage: Optional[Series[float]] = pa.Field(coerce=True, nullable=True)
    source_format: Series[str] = pa.Field(coerce=True, nullable=False)

    class Config:
        strict = True
        coerce = True


class PhenotypeSchema(pa.DataFrameModel):
    sample_id: Series[str] = pa.Field(coerce=True, nullable=False)
    trait: Series[str] = pa.Field(coerce=True, nullable=False)
    value: Series[float] = pa.Field(coerce=True, nullable=False)
    environment: Optional[Series[str]] = pa.Field(coerce=True, nullable=True)
    season_or_year: Optional[Series[str]] = pa.Field(coerce=True, nullable=True)
    replicate: Optional[Series[str]] = pa.Field(coerce=True, nullable=True)
    covariates: Optional[Series[str]] = pa.Field(coerce=True, nullable=True)

    class Config:
        strict = True
        coerce = True
