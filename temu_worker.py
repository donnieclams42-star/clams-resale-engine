
import time
import json
import random
import threading
from datetime import datetime
from temu_scanner import fetch_temu_items

RESULTS = "temu_flips_results.json"
STATUS = "temu_flips_status.json"

_runtime = {"stop_requested": False, "running": False}

def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _worker_loop(seed_items):
    print("[TEMU] Worker loop running")

    last_good = []
    last_queries = {}

    while True:
        if _runtime.get("stop_requested"):
            print("[TEMU] STOPPED")
            _runtime["running"] = False
            break

        try:
            filtered_seed = []
            now = time.time()

            for item in (seed_items or []):
                query = (item.get("query") or item.get("label") or item.get("title") or "").strip()
                last_time = last_queries.get(query, 0)

                if now - last_time > 600:
                    filtered_seed.append(item)
                    last_queries[query] = now

            if not filtered_seed:
                filtered_seed = seed_items

            results = fetch_temu_items(seed_items=filtered_seed)

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

        sleep_time = random.randint(90, 180)
        print(f"[TEMU] Sleeping {sleep_time}s")
        time.sleep(sleep_time)

def start_temu_worker(seed_items):
    if _runtime.get("running"):
        print("[TEMU] Worker already running")
        return

    print("[TEMU] Starting background worker")

    _runtime["stop_requested"] = False
    _runtime["running"] = True

    thread = threading.Thread(target=_worker_loop, args=(seed_items,), daemon=True)
    thread.start()

def stop_temu_worker():
    _runtime["stop_requested"] = True
