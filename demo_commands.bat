@echo off
setlocal enabledelayedexpansion
title GenoTrack MLOps Presentation Controller

:MENU
cls
echo ===============================================================================
echo                GENOTRACK MLOPS DEMO ^& PRESENTATION CONTROLLER
echo ===============================================================================
echo.
echo  LIVE SERVICE URLS:
echo    [1] Scientific Dashboard:  http://localhost:8008/
echo    [2] FastAPI Swagger Docs:  http://localhost:8008/docs
echo    [3] Prometheus Metrics:    http://localhost:8008/metrics
echo    [4] Prometheus UI:         http://localhost:9090
echo    [5] Grafana Dashboard:     http://localhost:3001  (admin / admin)
echo    [6] MLflow UI:             http://localhost:5000
echo    [7] Metaflow Card Server:  http://localhost:8324
echo.
echo -------------------------------------------------------------------------------
echo  ACTIONS:
echo -------------------------------------------------------------------------------
echo    1. Start FastAPI Serving API (Port 8008)
echo    2. Start MLflow Tracking UI (Port 5000)
echo    3. Start Docker Prometheus ^& Grafana Stack (Ports 9090 ^& 3001)
echo    4. Seed Synthetic Telemetry Traffic (50 Requests into Grafana)
echo    5. View Metaflow Validation Gate HTML Card (In Browser)
echo    6. Start Metaflow Card Viewer Server (Port 8324)
echo    7. Run Metaflow End-to-End Pipeline DAG (python pipelines/flow.py run)
echo    8. Run Comprehensive Pytest Suite (16/16 Unit Tests)
echo    9. Open All Presentation Web Pages in Browser
echo    0. Exit
echo.
set /p choice="Select an option (0-9): "

if "%choice%"=="1" goto START_API
if "%choice%"=="2" goto START_MLFLOW
if "%choice%"=="3" goto START_DOCKER
if "%choice%"=="4" goto SEED_TELEMETRY
if "%choice%"=="5" goto VIEW_CARD
if "%choice%"=="6" goto CARD_SERVER
if "%choice%"=="7" goto RUN_PIPELINE
if "%choice%"=="8" goto RUN_TESTS
if "%choice%"=="9" goto OPEN_PAGES
if "%choice%"=="0" goto EXIT
goto MENU

:START_API
echo Starting FastAPI Serving Layer on http://localhost:8008...
start "GenoTrack API" python -m uvicorn src.serve.app:app --host 0.0.0.0 --port 8008
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
start "GenoTrack Telemetry Stream" python monitoring/traffic_generator.py --url http://localhost:8008 --interval 2.5
echo Traffic generator running! Open Grafana at http://localhost:3001 to view live updates.
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

:RUN_PIPELINE
echo Running complete Metaflow DAG (GenoTrackFlow)...
python pipelines/flow.py run
pause
goto MENU

:RUN_TESTS
echo Running Pytest test suite...
pytest -v
pause
goto MENU

:OPEN_PAGES
echo Opening all live demo tabs in your default browser...
start http://localhost:8008/
start http://localhost:8008/docs
start http://localhost:5000
start http://localhost:3001
start http://localhost:9090
goto MENU

:EXIT
echo Exiting presentation controller.
exit /b 0
