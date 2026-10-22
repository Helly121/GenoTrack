"""
monitoring/seed_telemetry.py
Pre-populates Prometheus metrics and Grafana dashboard panels with realistic traffic:
- Simulates multi-environment prediction requests (dry season vs. wet season).
- Varies accession sample IDs across subpopulation batches.
- Injects realistic sub-second latency distributions.
- Injects covariate drift values (e.g. missing hill ratios) to show alert bounds.
Supports both direct TestClient in-memory injection and live HTTP requests.
"""
import argparse
import random
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_available_samples() -> list[str]:
    """Retrieve actual sample IDs from processed dosage matrix or feature metadata."""
    dosage_path = PROJECT_ROOT / "data" / "processed" / "dosage_matrix.parquet"
    if dosage_path.exists():
        try:
            import pandas as pd
            # Read index only without loading 67,000 columns
            df = pd.read_parquet(dosage_path, columns=[])
            return list(df.index[:30])
        except Exception:
            pass
    return ["A1254", "A1255", "A1256", "A1257", "A1258", "A1259", "A1260", "A1261", "A1262", "A1263"]


def seed_telemetry_traffic(n_requests: int = 100, target_url: str | None = None):
    print(f"Starting GenoTrack Telemetry Seeder ({n_requests} simulated inferences)...", flush=True)

    environments = ["2009_DS", "2009_WS", "2010_DS", "2010_WS", "2011_DS", "2011_WS", "across_environments"]
    sample_ids = get_available_samples()

    if target_url:
        import requests
        target_url = target_url.rstrip("/")
        if target_url.endswith("/predict/sample"):
            url = target_url
        else:
            url = f"{target_url}/predict/sample"
        client = None
    else:
        from src.serve.app import app, load_model_assets
        from fastapi.testclient import TestClient
        load_model_assets()
        client = TestClient(app)
        url = "/predict/sample"

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
                resp = requests.post(url, json=payload, timeout=10)
                status_code = resp.status_code
            else:
                resp = client.post(url, json=payload)
                status_code = resp.status_code

            if status_code == 200:
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            error_count += 1

        if (i + 1) % 25 == 0 or (i + 1) == n_requests:
            print(f"  [Progress] {i + 1}/{n_requests} requests processed ({success_count} success, {error_count} error)", flush=True)

    print(f"\nTelemetry Seeding Complete! {success_count} metrics recorded for Prometheus/Grafana.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic telemetry into GenoTrack serving API.")
    parser.add_argument("--endpoint", "-e", type=str, default=None, help="Base API URL (e.g. http://localhost:8008 or http://localhost:8000)")
    parser.add_argument("--requests", "-n", type=int, default=100, help="Number of simulated requests (default: 100)")
    args = parser.parse_args()

    seed_telemetry_traffic(n_requests=args.requests, target_url=args.endpoint)
