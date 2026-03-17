
from fastapi import FastAPI
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

app = FastAPI()

# =====================
# CONFIG (FAST + SAFE)
# =====================
SCAN_INTERVAL = 30
DEFAULT_KEYWORDS_PER_CYCLE = 5

ENABLE_EBAY = True
ENABLE_MERCARI = True
ENABLE_OFFERUP = True
ENABLE_FACEBOOK = False
ENABLE_CRAIGSLIST = False

ALERT_TOP_N = 5

KEYWORDS = [
    "iphone",
    "iphone cracked",
    "ipad",
    "macbook",
    "tool lot"
]

# =====================
# MOCK SCANNERS (replace with real ones)
# =====================
def scan_ebay(keyword):
    print(f"[RADAR] EBAY_SCAN keyword={keyword}")
    time.sleep(1)
    return [{"title": f"{keyword} ebay"}]

def scan_mercari(keyword):
    print(f"[RADAR] MERCARI_SCAN keyword={keyword}")
    time.sleep(1)
    return [{"title": f"{keyword} mercari"}]

def scan_offerup(keyword):
    print(f"[RADAR] OFFERUP_SCAN keyword={keyword}")
    time.sleep(1)
    return [{"title": f"{keyword} offerup"}]

def send_to_discord(deals):
    print(f"[DISCORD] Sending {len(deals)} deals")

# =====================
# RADAR LOOP
# =====================
def run_radar():
    print("[RADAR] LOOP STARTED")

    while True:
        try:
            print("[RADAR] NEW CYCLE")

            all_deals = []

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = []

                for keyword in KEYWORDS[:DEFAULT_KEYWORDS_PER_CYCLE]:
                    if ENABLE_EBAY:
                        futures.append(executor.submit(scan_ebay, keyword))
                    if ENABLE_MERCARI:
                        futures.append(executor.submit(scan_mercari, keyword))
                    if ENABLE_OFFERUP:
                        futures.append(executor.submit(scan_offerup, keyword))

                for future in as_completed(futures, timeout=25):
                    try:
                        deals = future.result(timeout=5) or []
                        all_deals.extend(deals)
                    except Exception as e:
                        print(f"[RADAR ERROR] {e}")

            top_deals = all_deals[:ALERT_TOP_N]

            try:
                send_to_discord(top_deals)
            except Exception as e:
                print(f"[DISCORD ERROR] {e}")

            print("[RADAR] SLEEPING...")
            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[RADAR LOOP ERROR] {e}")
            time.sleep(5)

# =====================
# THREAD CONTROL (FIX)
# =====================
radar_thread = None

def start_radar():
    global radar_thread

    if radar_thread and radar_thread.is_alive():
        print("[RADAR] Already running")
        return

    print("[RADAR] Starting thread...")

    radar_thread = threading.Thread(target=run_radar, daemon=True)
    radar_thread.start()

# =====================
# STARTUP HOOK (CRITICAL)
# =====================
@app.on_event("startup")
def startup_event():
    print("🔥 STARTUP EVENT TRIGGERED")
    start_radar()

# =====================
# BASIC ROUTES
# =====================
@app.get("/")
def root():
    return {"status": "CLAMS Radar Running"}

@app.get("/radar")
def radar():
    return {"status": "Radar Active"}
