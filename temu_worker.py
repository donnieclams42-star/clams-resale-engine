
import time
import json
from datetime import datetime
from temu_scanner import fetch_temu_items

RESULTS = "temu_flips_results.json"
STATUS = "temu_flips_status.json"

_runtime = {"stop_requested": False}

def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def start_temu_worker(seed_items):
    print("[TEMU] Worker started")

    last_good = []

    while True:
        if _runtime.get("stop_requested"):
            print("[TEMU] STOPPED")
            break

        try:
            results = fetch_temu_items(seed_items=seed_items)

            if results:
                last_good = results
                save(RESULTS, results)

                save(STATUS, {
                    "status": "live",
                    "count": len(results),
                    "last_success": datetime.utcnow().isoformat()
                })
            else:
                if last_good:
                    save(RESULTS, last_good)

        except Exception as e:
            print("[TEMU ERROR]", e)

        time.sleep(60)
