"""
monitoring/traffic_generator.py
Continuous background telemetry traffic generator for live Grafana presentations.
Simulates realistic plant breeding trial queries submitted across seasons.
Runs gently (1 request every 2-3 seconds) to provide active real-time dashboard data.
"""
import argparse
import random
import sys
import time
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_IDS = [
    "A1254", "A1255", "A1256", "A1257", "A1258",
    "A1259", "A1260", "A1261", "A1262", "A1263",
    "A1264", "A1265", "A1266", "A1267", "A1268",
]

ENVIRONMENTS = [
    "2009_DS", "2009_WS",
    "2010_DS", "2010_WS",
    "2011_DS", "2011_WS",
    "across_environments",
]


def run_traffic_loop(target_url: str = "http://localhost:8008", interval: float = 2.5, max_requests: int | None = None):
    url = f"{target_url.rstrip('/')}/predict/sample"
    print(f"GenoTrack Continuous Telemetry Generator started.")
    print(f"Targeting: {url} | Interval: {interval}s")
    print("Press CTRL+C to stop.\n", flush=True)

    count = 0
    while True:
        try:
            count += 1
            env = random.choice(ENVIRONMENTS)
            sample = random.choice(SAMPLE_IDS)
            # Occasional drift spike for demonstration
            if random.random() < 0.15:
                missing_hill = round(random.uniform(0.18, 0.24), 3)
            else:
                missing_hill = round(random.uniform(0.02, 0.14), 3)

            payload = {
                "sample_id": sample,
                "environment": env,
                "covariates": {
                    "missing_hill": missing_hill,
                    "moisture": round(random.uniform(11.8, 13.5), 1),
                },
            }

            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                yield_val = data.get("predicted_value", 0)
                print(f"[{count:04d}] OK: {sample} in {env:<20} -> Yield: {yield_val:.1f} kg/ha (Drift: {missing_hill*100:.1f}%)", flush=True)
            else:
                print(f"[{count:04d}] ERR {resp.status_code}: {resp.text[:80]}", flush=True)

            if max_requests and count >= max_requests:
                print(f"Completed {max_requests} requests.")
                break

            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nTraffic generator stopped.")
            break
        except Exception as e:
            print(f"[{count:04d}] Connection error: {e}", flush=True)
            time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live continuous telemetry generator for Grafana.")
    parser.add_argument("--url", default="http://localhost:8008", help="GenoTrack API base URL")
    parser.add_argument("--interval", type=float, default=2.5, help="Seconds between requests (default: 2.5)")
    parser.add_argument("--count", type=int, default=None, help="Stop after N requests (default: run indefinitely)")
    args = parser.parse_args()

    run_traffic_loop(target_url=args.url, interval=args.interval, max_requests=args.count)
