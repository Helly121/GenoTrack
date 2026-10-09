"""
src/models/baseline.py
Classical Genomic Selection baseline (GxE Ridge regression, approximating multi-environment GBLUP).
"""
from .gxe import GxERidgeModel

def get_baseline_model(**kwargs) -> GxERidgeModel:
    """Return an initialized baseline GxE model instance."""
    return GxERidgeModel(**kwargs)
