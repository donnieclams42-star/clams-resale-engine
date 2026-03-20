import json
import os
import threading
import time
from datetime import datetime

from temu_scanner import build_temu_seed_items, fetch_temu_items

RESULTS = "temu_flips_results.json"
STATUS = "temu_flips_status.json"
TEMU_SCAN_INTERVAL = int(os.getenv("TEMU_FULL_SCAN_INTERVAL", "86400"))
_runtime = {"stop_requested": False, "running": False}


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _worker_loop(seed_items=None):
    print("[TEMU] Worker loop running")
    last_good = []
    while True:
        if _runtime.get("stop_requested"):
            print("[TEMU] STOPPED")
            _runtime["running"] = False
            break
        try:
            seeds = seed_items or build_temu_seed_items()
            results = fetch_temu_items(seed_items=seeds, should_continue=lambda: not _runtime.get('stop_requested', False))
            if results:
                last_good = results
                save(RESULTS, results)
                save(STATUS, {
                    "status": "live",
                    "running": True,
                    "count": len(results),
                    "message": f"{len(results)} Temu results ready",
                    "last_success": datetime.utcnow().isoformat(),
                })
            elif last_good:
                save(RESULTS, last_good)
                save(STATUS, {
                    "status": "live",
                    "running": True,
                    "count": len(last_good),
                    "message": "No new Temu results; serving last good cache",
                    "last_success": datetime.utcnow().isoformat(),
                })
        except Exception as e:
            print("[TEMU ERROR]", e)
            save(STATUS, {
                "status": "error",
                "running": False,
                "count": len(last_good),
                "message": str(e),
                "last_success": datetime.utcnow().isoformat(),
            })
        print(f"[TEMU] Sleeping {TEMU_SCAN_INTERVAL}s")
        time.sleep(TEMU_SCAN_INTERVAL)


def start_temu_worker(seed_items=None):
    if _runtime.get("running"):
        print("[TEMU] Worker already running")
        return
    print("[TEMU] Starting background worker")
    _runtime["stop_requested"] = False
    _runtime["running"] = True
    thread = threading.Thread(target=_worker_loop, args=(seed_items,), daemon=True, name="temu-worker")
    thread.start()
    return thread


def stop_temu_worker():
    _runtime["stop_requested"] = True
