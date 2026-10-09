"""
src/models/challenger.py
Gradient-boosted challenger model (GxE XGBoost).
"""
from .gxe import GxEXGBoostModel

def get_challenger_model(**kwargs) -> GxEXGBoostModel:
    """Return an initialized challenger GxE model instance."""
    return GxEXGBoostModel(**kwargs)
