"""
src/serve/app.py
Production FastAPI serving layer for GenoTrack.
Strictly environment-aware per Section 6.8 of spec.md.
Exposes /health, /environments, /predict/sample, /predict/dosage,
/explain/locus/{marker_id}, and Prometheus /metrics endpoints.
Also serves the interactive GenoTrack dashboard at / and /dashboard.
"""
from contextlib import asynccontextmanager
import json
import time
from pathlib import Path
from typing import Optional
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from ..models.explain import explain_model_predictions

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "data" / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INDEX_HTML = PROJECT_ROOT / "index.html"

# In-memory model cache
CACHE = {
    "model": None,
    "metadata": None,
    "feature_meta": None,
    "dosage_matrix": None,
}

# -------------------------------------------------------------
# Prometheus Telemetry Metrics
# -------------------------------------------------------------
REGISTRY = prometheus_client.REGISTRY

PREDICTIONS_COUNTER = Counter(
    "genotrack_predictions_total",
    "Total genomic predictions served",
    ["environment", "target_trait", "status"],
)

INFERENCE_LATENCY = Histogram(
    "genotrack_inference_latency_seconds",
    "Model inference latency in seconds",
    ["endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

PREDICTED_YIELD_HIST = Histogram(
    "genotrack_predicted_yield_kg_ha",
    "Distribution of predicted grain yield in kg/ha",
    ["environment"],
    buckets=[2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000],
)

COVARIATE_DRIFT = Gauge(
    "genotrack_covariate_missing_hill_ratio",
    "Observed ratio of missing hill covariates in request batch",
    ["environment"],
)

MODEL_VERSION_GAUGE = Gauge(
    "genotrack_active_model_version",
    "Currently loaded production model registry version",
    ["crop", "trait", "version"],
)


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
            # Update Prometheus active version
            version_str = str(CACHE["metadata"].get("version", "2"))
            MODEL_VERSION_GAUGE.labels(crop=crop, trait=trait, version=version_str).set(1)
    if feat_file.exists():
        with open(feat_file, "r") as f:
            CACHE["feature_meta"] = json.load(f)
    if dosage_file.exists():
        CACHE["dosage_matrix"] = pd.read_parquet(dosage_file)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler replacing deprecated startup event."""
    load_model_assets()
    yield


app = FastAPI(
    title="GenoTrack MLOps Genomic Selection API",
    description="Environment-aware genomic prediction service and observability engine for crop breeding programs.",
    version="1.0.0",
    lifespan=lifespan,
)


# -------------------------------------------------------------
# Static Dashboard Endpoints
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the GenoTrack web dashboard directly from the application."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return HTMLResponse("<h2>GenoTrack dashboard file index.html not found.</h2>", status_code=404)


# -------------------------------------------------------------
# Prometheus Telemetry Endpoint
# -------------------------------------------------------------
@app.get("/metrics")
def metrics():
    """Prometheus exposition endpoint scraping internal application telemetry."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# -------------------------------------------------------------
# Pydantic Request & Response Schemas
# -------------------------------------------------------------
class SamplePredictionRequest(BaseModel):
    sample_id: str = Field(..., description="Accession ID present in the processed panel (e.g. 'A1256')")
    environment: str = Field("across_environments", description="Target environment (e.g. '2011_DS') or 'across_environments'")
    covariates: Optional[dict] = Field(default=None, description="Optional agronomic trial covariates (missing_hill, moisture)")


class DosagePredictionRequest(BaseModel):
    dosage_vector: list[float] = Field(..., description="List of SNP dosages (0..ploidy) matching model markers")
    environment: str = Field("across_environments", description="Target environment (e.g. '2011_DS') or 'across_environments'")
    covariates: Optional[dict] = Field(default=None, description="Optional agronomic trial covariates (missing_hill, moisture)")


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


# -------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------
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


@app.get("/explain/locus/{marker_id}")
def explain_locus(marker_id: str):
    """Retrieve biological annotation and locus attribution info for a specific SNP marker."""
    if CACHE["feature_meta"] is None:
        load_model_assets()
    if CACHE["feature_meta"] is None:
        raise HTTPException(status_code=503, detail="Feature metadata not loaded.")

    marker_ids = CACHE["feature_meta"].get("marker_ids", [])
    if marker_id not in marker_ids:
        raise HTTPException(status_code=404, detail=f"Marker '{marker_id}' not found in model features.")

    chrom = "unknown"
    pos = 0
    if "_" in marker_id:
        parts = marker_id.split("_")
        chrom = parts[0].replace("S", "")
        try:
            pos = int(parts[1])
        except ValueError:
            pass

    return {
        "marker_id": marker_id,
        "chromosome": chrom,
        "physical_position": pos,
        "feature_index": marker_ids.index(marker_id),
        "target_trait": CACHE["feature_meta"].get("target_trait", "grain_yield"),
        "crop": CACHE["feature_meta"].get("crop_name", "rice"),
    }


@app.post("/predict/sample", response_model=PredictionResponse)
def predict_sample(req: SamplePredictionRequest):
    """Predict phenotypic performance for an existing panel sample across environments."""
    start_time = time.perf_counter()
    if CACHE["model"] is None or CACHE["dosage_matrix"] is None:
        load_model_assets()
    if CACHE["model"] is None:
        PREDICTIONS_COUNTER.labels(environment=req.environment, target_trait="grain_yield", status="error").inc()
        raise HTTPException(status_code=503, detail="No production model loaded.")

    if req.sample_id not in CACHE["dosage_matrix"].index:
        PREDICTIONS_COUNTER.labels(environment=req.environment, target_trait="grain_yield", status="error").inc()
        raise HTTPException(
            status_code=404,
            detail=f"Sample ID '{req.sample_id}' not found in processed genotype panel.",
        )

    # Track missing hill covariate drift if passed
    if req.covariates and "missing_hill" in req.covariates:
        COVARIATE_DRIFT.labels(environment=req.environment).set(float(req.covariates["missing_hill"]))

    dosage_row = CACHE["dosage_matrix"].loc[req.sample_id].values
    resp = _generate_prediction(
        X_sample=dosage_row,
        environment=req.environment,
        sample_id=req.sample_id,
    )

    duration = time.perf_counter() - start_time
    INFERENCE_LATENCY.labels(endpoint="/predict/sample").observe(duration)
    PREDICTIONS_COUNTER.labels(environment=req.environment, target_trait=resp.target_trait, status="success").inc()
    PREDICTED_YIELD_HIST.labels(environment=req.environment).observe(resp.predicted_value)
    return resp


@app.post("/predict/dosage", response_model=PredictionResponse)
def predict_dosage(req: DosagePredictionRequest):
    """Predict phenotypic performance for a novel candidate dosage vector across environments."""
    start_time = time.perf_counter()
    if CACHE["model"] is None or CACHE["feature_meta"] is None:
        load_model_assets()
    if CACHE["model"] is None:
        PREDICTIONS_COUNTER.labels(environment=req.environment, target_trait="grain_yield", status="error").inc()
        raise HTTPException(status_code=503, detail="No production model loaded.")

    expected_len = len(CACHE["feature_meta"]["marker_ids"])
    if len(req.dosage_vector) != expected_len:
        PREDICTIONS_COUNTER.labels(environment=req.environment, target_trait="grain_yield", status="error").inc()
        raise HTTPException(
            status_code=422,
            detail=f"Expected dosage vector of length {expected_len}, received {len(req.dosage_vector)}.",
        )

    # Track missing hill covariate drift if passed
    if req.covariates and "missing_hill" in req.covariates:
        COVARIATE_DRIFT.labels(environment=req.environment).set(float(req.covariates["missing_hill"]))

    dosage_row = np.array(req.dosage_vector, dtype=float)
    resp = _generate_prediction(
        X_sample=dosage_row,
        environment=req.environment,
        sample_id=None,
    )

    duration = time.perf_counter() - start_time
    INFERENCE_LATENCY.labels(endpoint="/predict/dosage").observe(duration)
    PREDICTIONS_COUNTER.labels(environment=req.environment, target_trait=resp.target_trait, status="success").inc()
    PREDICTED_YIELD_HIST.labels(environment=req.environment).observe(resp.predicted_value)
    return resp


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
