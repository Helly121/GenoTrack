"""
monitoring/seed_telemetry.py
Pre-populates Prometheus metrics and Grafana dashboard panels with realistic traffic:
- Simulates multi-environment prediction requests (dry season vs. wet season).
- Varies accession sample IDs across subpopulation batches.
- Injects realistic sub-second latency distributions.
- Injects covariate drift values (e.g. missing hill ratios) to show alert bounds.
Supports both direct TestClient in-memory injection and live HTTP requests.
"""
import sys
import time
import random
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from src.serve.app import app, load_model_assets


def seed_telemetry_traffic(n_requests: int = 120, target_url: str | None = None):
    print(f"Starting GenoTrack Telemetry Seeder ({n_requests} simulated inferences)...")
    load_model_assets()

    environments = ["2009_DS", "2009_WS", "2010_DS", "2010_WS", "2011_DS", "2011_WS", "across_environments"]
    sample_ids = ["A1203", "A1256", "B1005", "B1012", "M1345", "M1463"]

    if target_url:
        import requests
        client = None
    else:
        client = TestClient(app)

    success_count = 0
    error_count = 0

    for i in range(n_requests):
        env = random.choice(environments)
        sample = random.choice(sample_ids)
        missing_hill_ratio = round(random.uniform(0.01, 0.22), 3)

        payload = {
            "sample_id": sample,
            "environment": env,
            "covariates": {"missing_hill": missing_hill_ratio, "moisture": 12.4},
        }

        try:
            if target_url:
                resp = requests.post(f"{target_url}/predict/sample", json=payload, timeout=5)
                status_code = resp.status_code
            else:
                resp = client.post("/predict/sample", json=payload)
                status_code = resp.status_code

            if status_code == 200:
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            error_count += 1

        if (i + 1) % 25 == 0 or (i + 1) == n_requests:
            print(f"  [Progress] {i + 1}/{n_requests} requests processed ({success_count} success, {error_count} error)")

    print(f"\nTelemetry Seeding Complete! {success_count} metrics recorded for Prometheus/Grafana.")


if __name__ == "__main__":
    url_arg = sys.argv[1] if len(sys.argv) > 1 else None
    seed_telemetry_traffic(n_requests=100, target_url=url_arg)
