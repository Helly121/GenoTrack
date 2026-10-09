"""
tests/test_serve.py
Unit tests for the environment-aware FastAPI serving API.
"""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.serve.app import app, CACHE
from src.models.gxe import GxEXGBoostModel


@pytest.fixture
def mock_serving_assets():
    """Inject mock model and metadata into CACHE for isolated serving tests."""
    rng = np.random.RandomState(42)
    N = 10
    M = 5
    marker_ids = [f"S1_{1000 + i*100}" for i in range(M)]
    sample_ids = [f"A12{i:02d}" for i in range(N)]
    environments = ["2009_DS", "2009_WS"]

    X = rng.binomial(n=2, p=0.3, size=(N, M)).astype(float)
    envs = rng.choice(environments, size=N)
    y = 5000.0 + (X[:, 0] * 30)

    model = GxEXGBoostModel(n_estimators=10, max_depth=2)
    model.fit(X, envs, y)

    CACHE["model"] = model
    CACHE["metadata"] = {
        "crop": "rice",
        "trait": "grain_yield",
        "stage": "Production",
        "mean_r": 0.65,
    }
    CACHE["feature_meta"] = {
        "crop_name": "rice",
        "target_trait": "grain_yield",
        "marker_ids": marker_ids,
        "environments": environments,
    }
    CACHE["dosage_matrix"] = pd.DataFrame(X, index=sample_ids, columns=marker_ids)
    yield
    CACHE["model"] = None


def test_healthcheck_endpoint(mock_serving_assets):
    """Verify /health returns status and production metadata."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["model_loaded"] is True
    assert data["production_metadata"]["crop"] == "rice"


def test_environments_endpoint(mock_serving_assets):
    """Verify /environments returns catalog of trial environments."""
    client = TestClient(app)
    response = client.get("/environments")
    assert response.status_code == 200
    data = response.json()
    assert "across_environments" in data["supported_environments"]
    assert "2009_DS" in data["supported_environments"]


def test_predict_sample_endpoint(mock_serving_assets):
    """Verify /predict/sample returns GxE decomposed prediction and SHAP attributions."""
    client = TestClient(app)
    payload = {
        "sample_id": "A1200",
        "environment": "2009_DS",
    }
    response = client.post("/predict/sample", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["sample_id"] == "A1200"
    assert data["environment"] == "2009_DS"
    assert "predicted_value" in data
    assert "genetic_component" in data
    assert "environmental_effect" in data
    assert len(data["top_contributing_markers"]) > 0
    # Marker should have chrom and pos parsed
    top_m = data["top_contributing_markers"][0]
    assert "marker_id" in top_m
    assert "shap_value" in top_m


def test_predict_dosage_endpoint(mock_serving_assets):
    """Verify /predict/dosage returns prediction for novel genotype vector."""
    client = TestClient(app)
    payload = {
        "dosage_vector": [0.0, 1.0, 2.0, 0.0, 1.0],
        "environment": "across_environments",
    }
    response = client.post("/predict/dosage", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["environment"] == "across_environments"
    assert "predicted_value" in data
