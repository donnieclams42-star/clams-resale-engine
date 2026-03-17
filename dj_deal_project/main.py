
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================
# SPEED CONFIG (ACTIVE)
# =====================
SCAN_INTERVAL = 30
ENABLE_FACEBOOK = False
ENABLE_CRAIGSLIST = False

KEYWORDS = [
    "iphone",
    "iphone cracked",
    "ipad",
    "macbook",
    "tool lot"
]

# =====================
# MOCK SCANNERS (REPLACE WITH YOUR REAL ONES IF NEEDED)
# =====================
def scan_ebay(keyword):
    print(f"[RADAR] EBAY SCAN keyword={keyword}")
    time.sleep(1)
    return [{"title": f"{keyword} deal"}]

def scan_mercari(keyword):
    print(f"[RADAR] MERCARI SCAN keyword={keyword}")
    time.sleep(1)
    return [{"title": f"{keyword} mercari"}]

def send_to_discord(deals):
    print(f"[DISCORD] Sending {len(deals)} deals")

# =====================
# RADAR LOOP (FAST MODE)
# =====================
def run_radar():
    print("[RADAR] STARTED (FAST MODE)")

    while True:
        try:
            print("[RADAR] NEW CYCLE")

            all_deals = []

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []

                for keyword in KEYWORDS:
                    futures.append(executor.submit(scan_ebay, keyword))
                    futures.append(executor.submit(scan_mercari, keyword))

                for future in as_completed(futures, timeout=20):
                    try:
                        deals = future.result(timeout=3) or []
                        all_deals.extend(deals)
                    except Exception as e:
                        print(f"[RADAR ERROR] {e}")

            top_deals = all_deals[:5]

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
# START THREAD
# =====================
def start_radar():
    thread = threading.Thread(target=run_radar, daemon=True)
    thread.start()
