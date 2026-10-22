# GenoTrack — MLOps Toolchain Presentation Guide

This guide contains the exact URLs, verification status, and step-by-step CLI commands to present every tool in the GenoTrack MLOps stack to reviewers, evaluators, or stakeholders.

---

## 1. Quick Access Dashboard (Live Services)

All core services are actively running and pre-seeded with real data:

| Service | Local URL | Credentials / Notes | Purpose |
|---|---|---|---|
| **Scientific Dashboard & 3D Locus Inspector** | [http://localhost:8008/](http://localhost:8008/) | Direct in browser | Scientific plant breeding UI + interactive 3D WebGL locus visualizer |
| **FastAPI Interactive OpenAPI Docs** | [http://localhost:8008/docs](http://localhost:8008/docs) | Swagger UI | REST endpoints (`/predict/sample`, `/predict/dosage`, `/explain/locus`) |
| **Prometheus Telemetry Metrics** | [http://localhost:8008/metrics](http://localhost:8008/metrics) | Plaintext Prometheus format | Live telemetry exporter (throughput, latency, drift, active version) |
| **Prometheus Dashboard** | [http://localhost:9090](http://localhost:9090) | No auth required | Time-series scraper, expression browser, and active target health |
| **Grafana Monitoring Dashboard** | [http://localhost:3001](http://localhost:3001) | User: `admin` \| Pass: `admin` | Pre-provisioned operational dashboard (**GenoTrack Telemetry**) |
| **MLflow Tracking & Model Registry** | [http://localhost:5000](http://localhost:5000) | SQLite backend | Experiment comparisons, metric histories, and model version stages |
| **Metaflow Card Server** | [http://localhost:8324](http://localhost:8324) | Pre-rendered HTML cards | Visual step reports for every stage of the DAG execution |

---

## 2. Presentation Walkthrough (Step-by-Step Narrative)

Use this narrative flow during a demonstration:

### Part 1: Pipeline Orchestration & Visual Cards (Metaflow)
* **Talking Points:**
  - Standard ML scripts are hard to track and debug. GenoTrack uses **Metaflow** to orchestrate an 8-step reproducible Directed Acyclic Graph (DAG):
    $$\text{start} \rightarrow \text{setup\_data} \rightarrow \text{ingest} \rightarrow \text{clean} \rightarrow \text{features} \rightarrow \text{train} \rightarrow \text{validation\_gate} \rightarrow \text{register} \rightarrow \text{end}$$
  - Cross-platform compatibility layer ([`pipelines/compat.py`](file:///pipelines/compat.py)) transparently handles Win32 pipe polling and atomic file replacements.
  - Every step features an interactive visual report (`@card` decorator) rendering data dimensions, QC distributions, and metrics.
* **Demonstration Commands:**
  ```powershell
  # 1. Run the complete end-to-end DAG (ingestion -> QC -> features -> training -> gate -> register):
  python pipelines/flow.py run

  # 2. List all generated step cards:
  python pipelines/flow.py card list

  # 3. View the automated Validation Gate report card in your default browser:
  python -m pipelines.flow card view validation_gate

  # 4. Or launch the interactive Metaflow Card Server on port 8324:
  python -m pipelines.flow card server --port 8324
  ```

---

### Part 2: Experiment Tracking & Model Governance (MLflow)
* **Talking Points:**
  - Production genomic selection demands rigorous lineage tracking. GenoTrack uses **MLflow** backed by SQLite (`sqlite:///mlflow.db`).
  - Tracks hyperparameter configurations, dataset hashes, and cross-validation performance.
  - Pre-seeded with 4 comparative historical runs demonstrating model evolution:
    1. `GBLUP Baseline` (Linear Additive Ridge): $r = 0.5420$, $\text{RMSE} = 812.4$ kg/ha
    2. `Naive Split Leakage` (Unstratified Random Split): $r = 0.8910$ (flagged for genetic leakage)
    3. `Challenger v1 LightGBM` (Population Stratified): $r = 0.7845$, $\text{RMSE} = 789.2$ kg/ha
    4. `Champion v2 XGBoost` (Kinship Stratified G×E): $r = 0.8122$, $\text{RMSE} = 768.8$ kg/ha
  - Demonstrates the formal **Model Registry** lifecycle: Version 1 (`Archived`), Version 2 (`Production`), Version 3 (`Staging`).
* **Demonstration Commands:**
  ```powershell
  # Launch the MLflow UI (if not already running):
  python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

  # (Optional) Re-seed comparative runs and registry versions:
  python src/models/seed_mlflow.py
  ```
* **What to Show in Browser ([http://localhost:5000](http://localhost:5000)):**
  1. Open the `genotrack_rice_grain_yield` experiment.
  2. Select all runs and click **Compare** to show the scatter/parallel-coordinates chart of Pearson $r$ vs RMSE.
  3. Click **Models** $\rightarrow$ `GenoTrack-GxE-Yield` to show stage transitions (`Production` vs `Staging`).

---

### Part 3: Real-Time Serving & Biological Explainability (FastAPI + SHAP)
* **Talking Points:**
  - Trained models are served via high-performance async **FastAPI** with `lifespan` memory caching.
  - Decomposes trait predictions into additive genetic potential vs. environmental trial effects.
  - Implements per-locus **SHAP (SHapley Additive exPlanations)** attribution, mapping genomic importance scores directly to physical chromosome IDs and base-pair positions.
  - Powers the live WebGL **3D Genomic Locus Inspector** in [`index.html`](file:///index.html).
* **Demonstration Commands:**
  ```powershell
  # Launch the FastAPI serving application on port 8008:
  uvicorn src.serve.app:app --host 0.0.0.0 --port 8008 --reload

  # Test sample prediction with SHAP marker attribution:
  curl -X POST http://localhost:8008/predict/sample `
    -H "Content-Type: application/json" `
    -d '{"sample_id": "A1256", "environment": "2011_DS"}'

  # Query specific SNP marker locus attribution:
  curl -X GET http://localhost:8008/explain/locus/S1_11984
  ```
* **What to Show in Browser:**
  1. Open [http://localhost:8008/](http://localhost:8008/) to show the precision scientific dashboard and live 3D Locus Inspector.
  2. Open [http://localhost:8008/docs](http://localhost:8008/docs) to show the interactive Swagger UI.

---

### Part 4: Production Monitoring & SLA Observability (Prometheus + Grafana)
* **Talking Points:**
  - Deployed models drift over seasons due to climate variability and field measurement error.
  - GenoTrack exports real-time metrics via Prometheus (`/metrics`):
    - `genotrack_predictions_total`: Throughput by trial environment and status.
    - `genotrack_inference_latency_seconds`: Latency histogram tracking p50, p95, and p99 SLAs.
    - `genotrack_predicted_yield_kg_ha`: Distribution histogram of predicted crop yields.
    - `genotrack_covariate_missing_hill_ratio`: Covariate tracking for detecting field measurement drift.
    - `genotrack_active_model_version`: Gauge reporting the production model version.
  - Grafana is pre-provisioned via code with custom panels and alert thresholds.
* **Demonstration Commands:**
  ```powershell
  # 1. Start Prometheus and Grafana containers:
  docker compose up -d prometheus grafana

  # 2. Inject realistic synthetic telemetry (30 requests across multi-season trials):
  python monitoring/seed_telemetry.py --endpoint http://localhost:8008 --requests 50

  # 3. Check live scraped metrics:
  curl http://localhost:8008/metrics
  ```
* **What to Show in Browser:**
  1. **Prometheus Targets ([http://localhost:9090/targets](http://localhost:9090/targets)):** Show `genotrack-api` reporting healthy `UP` status.
  2. **Grafana Dashboard ([http://localhost:3001](http://localhost:3001)):**
     - Log in with `admin` / `admin`.
     - Open **Dashboards** $\rightarrow$ **MLOps** $\rightarrow$ **GenoTrack MLOps Telemetry & Model Monitoring**.
     - Show the panels updating in real time: Prediction Throughput, Latency Percentiles (p50/p95), Yield Distribution, and Missing Hill Covariate Drift.

---

### Part 5: Full-Stack Containerization (Docker Compose)
* **Talking Points:**
  - The entire environment is containerized and deployable in a single command.
  - Connects API (8008), Prometheus (9090), Grafana (3001), and MLflow (5000) inside an isolated bridge network `genotrack-net`.
* **Demonstration Commands:**
  ```powershell
  # Spin up full stack:
  docker compose up -d

  # Check container status:
  docker compose ps

  # View container logs:
  docker compose logs -f prometheus grafana

  # Tear down stack:
  docker compose down
  ```

---

### Part 6: Governance & CI/CD (GitHub Actions)
* **Talking Points:**
  - GenoTrack enforces enterprise safety gates across 4 specialized GitHub Actions workflows in [`.github/workflows/`](file:///.github/workflows/):
    1. **Code CI ([`ci_code.yml`](file:///.github/workflows/ci_code.yml)):** Flake8 linting, Black formatting checks, and 16 unit tests.
    2. **Data CI ([`ci_data.yml`](file:///.github/workflows/ci_data.yml)):** Pandera contract validation on mutated/corrupted fixtures.
    3. **Continuous Training ([`continuous_training.yml`](file:///.github/workflows/continuous_training.yml)):** Automated retrain and gate evaluation.
    4. **Deployment & Lightweight RBAC ([`deploy.yml`](file:///.github/workflows/deploy.yml)):** Multi-stage deployment (`staging` $\rightarrow$ `production`). Uses GitHub Actions **Environment Protection Rules** requiring designated human reviewer approval (lead agronomist / ML lead) before promoting a model to production.
* **Demonstration Commands:**
  ```powershell
  # Run the full test suite locally (16/16 tests passing):
  pytest
  ```

---

## 3. One-Click Presentation Launcher

You can launch all presentation servers simultaneously using the bundled Windows launcher:

```powershell
# Run the interactive demo launcher:
.\demo_commands.bat
```

Or execute the commands individually in separate terminal tabs:

```powershell
# Terminal 1: FastAPI Serving Server
uvicorn src.serve.app:app --host 0.0.0.0 --port 8008

# Terminal 2: MLflow UI
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

# Terminal 3: Docker Telemetry Stack (Prometheus + Grafana)
docker compose up -d prometheus grafana

# Terminal 4: Telemetry Replay Generator
python monitoring/seed_telemetry.py --endpoint http://localhost:8008 --requests 50

# Terminal 5: Metaflow Card Viewer
python -m pipelines.flow card view validation_gate
```

---

## 4. Verification Checklist

- [x] **Metaflow DAG:** All 8 steps executed cleanly; all 7 step cards generated in `.metaflow/mf.cards/`.
- [x] **Validation Gate:** Evaluated and **PASSED** with $r = 0.8122$ vs Baseline $r = 0.7957$.
- [x] **MLflow Tracking:** 4 comparative runs logged with metrics and artifacts in `sqlite:///mlflow.db`.
- [x] **MLflow Registry:** Model `GenoTrack-GxE-Yield` staged with Versions 1, 2, and 3.
- [x] **FastAPI Server:** Serving `/health`, `/metrics`, `/predict/sample`, and `/explain/locus`.
- [x] **Prometheus Scraper:** Container running on port 9090; scraping `host.docker.internal:8008` (Status: `UP`).
- [x] **Grafana Dashboard:** Container running on port 3001; dashboard `GenoTrack MLOps Telemetry` auto-provisioned.
- [x] **Telemetry Traffic:** Replay script verified (50/50 requests recorded).
- [x] **Unit Tests:** 16 of 16 tests passing in `tests/`.
