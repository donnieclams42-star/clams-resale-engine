import threading
import time

SCAN_INTERVAL = 30

def run_radar_loop():
    print("🔥 RADAR LOOP STARTED")

    while True:
        print("🔥 RADAR HEARTBEAT")

        # SIMULATED SCAN OUTPUT (replace with real scanners if needed)
        print("[SCAN] mercari keyword=iphone")
        print("[EBAY_SCAN] keyword=iphone")
        print("[SMART DEALS] 1")
        print("iPhone cracked | BUY $80 → SELL $300 | PROFIT $220")
        print("-----")

        time.sleep(SCAN_INTERVAL)


def start_radar():
    print("🔥 RADAR STARTED")

    thread = threading.Thread(target=run_radar_loop, daemon=True)
    thread.start()


# FastAPI integration
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
def startup_event():
    start_radar()


@app.get("/")
def root():
    return {"status": "running"}
