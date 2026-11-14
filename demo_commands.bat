@echo off
setlocal enabledelayedexpansion
title TerraBreed MLOps Presentation Controller

:MENU
cls
echo ===============================================================================
echo                TERRABREED MLOPS DEMO ^& PRESENTATION CONTROLLER
echo                     "Breeding crops for a changing Earth."
echo ===============================================================================
echo.
echo  LIVE SERVICE URLS:
echo    [1] Scientific Dashboard:    http://localhost:8008/
echo    [2] FastAPI Swagger Docs:    http://localhost:8008/docs
echo    [3] Prometheus Metrics:      http://localhost:8008/metrics
echo    [4] Prometheus Alerts:       http://localhost:9090/alerts
echo    [5] Prometheus Targets:      http://localhost:9090/targets
echo    [6] Grafana Dashboard:       http://localhost:3001  (admin / admin)
echo    [7] MLflow UI:               http://localhost:5000
echo    [8] Metaflow Card Server:    http://localhost:8324
echo.
echo -------------------------------------------------------------------------------
echo  ACTIONS:
echo -------------------------------------------------------------------------------
echo  [SERVICES ^& OBSERVABILITY]
echo    1. Start FastAPI Serving API (Port 8008)
echo    2. Start MLflow Tracking UI (Port 5000)
echo    3. Start Docker Prometheus ^& Grafana Stack (Ports 9090 ^& 3001)
echo    4. Start Continuous Telemetry Generator (Traffic Stream into Grafana)
echo.
echo  [DATA LINEAGE ^& PIPELINE ORCHESTRATION]
echo    5. Display DVC Lineage DAG ^& Data Status (dvc dag ^& dvc status)
echo    6. Run Metaflow End-to-End Pipeline DAG (python pipelines/flow.py run)
echo    7. View Metaflow Validation Gate HTML Card (In Browser)
echo    8. Start Metaflow Card Viewer Server (Port 8324)
echo.
echo  [LIFECYCLE SIMULATION ^& TEST SUITE]
echo    9. Run 16-Season Virtual Breeding Lifecycle Simulation
echo    T. Run Comprehensive Pytest Suite (29/29 Unit Tests)
echo    O. Open All Presentation Web Pages in Browser
echo    0. Exit
echo.
set /p choice="Select an option: "

if /i "%choice%"=="1" goto START_API
if /i "%choice%"=="2" goto START_MLFLOW
if /i "%choice%"=="3" goto START_DOCKER
if /i "%choice%"=="4" goto SEED_TELEMETRY
if /i "%choice%"=="5" goto DVC_STATUS
if /i "%choice%"=="6" goto RUN_PIPELINE
if /i "%choice%"=="7" goto VIEW_CARD
if /i "%choice%"=="8" goto CARD_SERVER
if /i "%choice%"=="9" goto RUN_SIMULATION
if /i "%choice%"=="T" goto RUN_TESTS
if /i "%choice%"=="O" goto OPEN_PAGES
if /i "%choice%"=="0" goto EXIT
goto MENU

:START_API
echo Starting FastAPI Serving Layer on http://localhost:8008...
start "TerraBreed API" python -m uvicorn src.serve.app:app --host 0.0.0.0 --port 8008
timeout /t 3 >nul
goto MENU

:START_MLFLOW
echo Starting MLflow UI on http://localhost:5000...
start "MLflow UI" python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000
timeout /t 3 >nul
goto MENU

:START_DOCKER
echo Starting Docker Prometheus and Grafana containers...
docker compose up -d prometheus grafana
echo Containers started!
echo Prometheus: http://localhost:9090
echo Grafana:    http://localhost:3001 (User: admin / Pass: admin)
pause
goto MENU

:SEED_TELEMETRY
echo Launching continuous telemetry generator in new window (keeps Grafana alive)...
start "TerraBreed Telemetry Stream" python monitoring/traffic_generator.py --url http://localhost:8008 --interval 2.5
echo Traffic generator running! Open Grafana at http://localhost:3001 to view live updates.
pause
goto MENU

:DVC_STATUS
echo ===============================================================================
echo  DVC DATA LINEAGE DIRECTED ACYCLIC GRAPH (DAG)
echo ===============================================================================
dvc dag
echo.
echo ===============================================================================
echo  DVC PIPELINE STATUS ^& DATA INTEGRITY
echo ===============================================================================
dvc status
echo.
echo ===============================================================================
echo  DVC STORAGE REMOTE
echo ===============================================================================
dvc remote list
echo.
pause
goto MENU

:RUN_PIPELINE
echo Running complete Metaflow DAG...
python pipelines/flow.py run
pause
goto MENU

:VIEW_CARD
echo Opening Metaflow Validation Gate card in your default browser...
python -m pipelines.flow card view validation_gate
pause
goto MENU

:CARD_SERVER
echo Starting Metaflow Card Server on port 8324...
start "Metaflow Cards" python -m pipelines.flow card server --port 8324
timeout /t 3 >nul
goto MENU

:RUN_SIMULATION
echo Running 16-Season Virtual Breeding Program Simulation (storyline_demo)...
python simulation/run_lifecycle.py --scenario storyline_demo --mode live --ticks 16
pause
goto MENU

:RUN_TESTS
echo Running Pytest test suite (29 unit tests across adapters, features, GxE, serve, and simulation)...
pytest -v
pause
goto MENU

:OPEN_PAGES
echo Opening all live demo tabs in your default browser...
start http://localhost:8008/
start http://localhost:8008/docs
start http://localhost:5000
start http://localhost:3001
start http://localhost:9090/alerts
goto MENU

:EXIT
echo Exiting presentation controller.
exit /b 0
