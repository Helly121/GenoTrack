"""
src/serve/app.py
Production FastAPI serving layer for GenoTrack.
Strictly environment-aware per Section 6.8 of spec.md and user feedback.
Exposes /health, /environments, /predict/sample, and /predict/dosage endpoints.
"""
import json
from pathlib import Path
from typing import Optional
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..models.explain import explain_model_predictions

app = FastAPI(
    title="GenoTrack MLOps Genomic Selection API",
    description="Environment-aware genomic prediction service for crop breeding programs.",
    version="0.1.0",
)

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "data" / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# In-memory model cache
CACHE = {
    "model": None,
    "metadata": None,
    "feature_meta": None,
    "dosage_matrix": None,
}


def load_model_assets(crop: str = "rice", trait: str = "grain_yield"):
    """Load production model, feature metadata, and processed dosage matrix."""
    model_file = MODELS_DIR / f"production_{crop}_{trait}.joblib"
    meta_file = MODELS_DIR / f"production_{crop}_{trait}.json"
    feat_file = PROCESSED_DIR / "feature_metadata.json"
    dosage_file = PROCESSED_DIR / "dosage_matrix.parquet"

    if model_file.exists():
        CACHE["model"] = joblib.load(model_file)
    if meta_file.exists():
        with open(meta_file, "r") as f:
            CACHE["metadata"] = json.load(f)
    if feat_file.exists():
        with open(feat_file, "r") as f:
            CACHE["feature_meta"] = json.load(f)
    if dosage_file.exists():
        CACHE["dosage_matrix"] = pd.read_parquet(dosage_file)


@app.on_event("startup")
def startup_event():
    load_model_assets()


# Pydantic Request & Response schemas
class SamplePredictionRequest(BaseModel):
    sample_id: str = Field(..., description="Accession ID present in the processed panel (e.g. 'A1256')")
    environment: str = Field("across_environments", description="Target environment (e.g. '2011_DS') or 'across_environments'")


class DosagePredictionRequest(BaseModel):
    dosage_vector: list[float] = Field(..., description="List of SNP dosages (0..ploidy) matching model markers")
    environment: str = Field("across_environments", description="Target environment (e.g. '2011_DS') or 'across_environments'")


class MarkerAttribution(BaseModel):
    marker_id: str
    chrom: str
    pos: int
    shap_value: float
    dosage: float


class PredictionResponse(BaseModel):
    sample_id: Optional[str] = None
    environment: str
    target_trait: str
    predicted_value: float
    unit: str
    genetic_component: float
    environmental_effect: float
    top_contributing_markers: list[MarkerAttribution]


@app.get("/health")
def healthcheck():
    """Service health and active production model lineage info."""
    model_loaded = CACHE["model"] is not None
    return {
        "status": "healthy" if model_loaded else "degraded",
        "model_loaded": model_loaded,
        "production_metadata": CACHE.get("metadata"),
    }


@app.get("/environments")
def get_environments():
    """Catalog of all supported trial environments."""
    if CACHE["feature_meta"] is None:
        load_model_assets()
    if CACHE["feature_meta"] is None:
        raise HTTPException(status_code=503, detail="Feature metadata not loaded. Pipeline has not been run.")

    envs = CACHE["feature_meta"].get("environments", [])
    return {
        "crop": CACHE["feature_meta"].get("crop_name", "rice"),
        "target_trait": CACHE["feature_meta"].get("target_trait", "grain_yield"),
        "supported_environments": ["across_environments"] + envs,
        "total_trial_environments": len(envs),
    }


@app.post("/predict/sample", response_model=PredictionResponse)
def predict_sample(req: SamplePredictionRequest):
    """Predict phenotypic performance for an existing panel sample across environments."""
    if CACHE["model"] is None or CACHE["dosage_matrix"] is None:
        load_model_assets()
    if CACHE["model"] is None:
        raise HTTPException(status_code=503, detail="No production model loaded.")

    if req.sample_id not in CACHE["dosage_matrix"].index:
        raise HTTPException(
            status_code=404,
            detail=f"Sample ID '{req.sample_id}' not found in processed genotype panel.",
        )

    dosage_row = CACHE["dosage_matrix"].loc[req.sample_id].values
    return _generate_prediction(
        X_sample=dosage_row,
        environment=req.environment,
        sample_id=req.sample_id,
    )


@app.post("/predict/dosage", response_model=PredictionResponse)
def predict_dosage(req: DosagePredictionRequest):
    """Predict phenotypic performance for a novel candidate dosage vector across environments."""
    if CACHE["model"] is None or CACHE["feature_meta"] is None:
        load_model_assets()
    if CACHE["model"] is None:
        raise HTTPException(status_code=503, detail="No production model loaded.")

    expected_len = len(CACHE["feature_meta"]["marker_ids"])
    if len(req.dosage_vector) != expected_len:
        raise HTTPException(
            status_code=422,
            detail=f"Expected dosage vector of length {expected_len}, received {len(req.dosage_vector)}.",
        )

    dosage_row = np.array(req.dosage_vector, dtype=float)
    return _generate_prediction(
        X_sample=dosage_row,
        environment=req.environment,
        sample_id=None,
    )


def _generate_prediction(X_sample: np.ndarray, environment: str, sample_id: Optional[str] = None) -> PredictionResponse:
    model = CACHE["model"]
    feat_meta = CACHE["feature_meta"]

    # Predict using GxE model
    X_2d = X_sample.reshape(1, -1)
    pred_val = float(model.predict(X_2d, environment)[0])

    # Decompose components
    global_mean = getattr(model, "global_mean_", 0.0)
    env_effects = getattr(model, "env_effects_", {})
    env_effect = float(env_effects.get(environment, 0.0))
    genetic_component = pred_val - env_effect

    # SHAP explanations
    attributions = explain_model_predictions(
        model=model,
        X_sample=X_sample,
        env_name=environment,
        feature_metadata=feat_meta,
        top_k=10,
    )

    return PredictionResponse(
        sample_id=sample_id,
        environment=environment,
        target_trait=feat_meta.get("target_trait", "grain_yield"),
        predicted_value=round(pred_val, 2),
        unit="kg_per_ha",
        genetic_component=round(genetic_component, 2),
        environmental_effect=round(env_effect, 2),
        top_contributing_markers=[MarkerAttribution(**a) for a in attributions],
    )
