"""GitHub Actions 및 CLI 진입점. 구현은 auto_pilot_260508 모듈에 있습니다."""
import random
import time
from datetime import datetime

from auto_pilot_260508 import load_status, run_pipeline, save_status

if __name__ == "__main__":
    status = load_status()

    if not status.get("enabled"):
        print("[Notice] Automation switch is OFF. Stopping task.")
        raise SystemExit(0)

    now = time.time()
    if now < status.get("next_run", 0):
        remaining = int((status["next_run"] - now) / 60)
        print(f"[Wait] Approx. {remaining} minutes left until next run.")
        raise SystemExit(0)

    success = run_pipeline()

    if success:
        interval = random.uniform(4 * 3600, 5 * 3600)
        status["last_run"] = time.time()
        status["next_run"] = time.time() + interval
        save_status(status)
        print(
            f"Next Run Scheduled: {datetime.fromtimestamp(status['next_run']).strftime('%Y-%m-%d %H:%M:%S')}"
        )
