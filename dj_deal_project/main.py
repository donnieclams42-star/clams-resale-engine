
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# CONFIG
SCAN_INTERVAL = 60
MAX_DEALS = 5
ENABLE_FACEBOOK = False

# MOCK SCANNERS (replace with your real ones)
def scan_ebay():
    print("[RADAR] EBAY SCAN")
    return [{"title": "Deal "+str(i)} for i in range(20)]

def scan_mercari():
    print("[RADAR] MERCARI SCAN")
    return [{"title": "Mercari "+str(i)} for i in range(10)]

def scan_facebook():
    print("[RADAR] FACEBOOK SCAN")
    time.sleep(2)
    return [{"title": "FB Deal"}]

def send_to_discord(deals):
    print(f"[DISCORD] Sending {len(deals)} deals")

# RADAR LOOP
def run_radar():
    print("[RADAR] STARTED")

    while True:
        try:
            print("[RADAR] NEW CYCLE")

            scan_jobs = {
                "EBAY": scan_ebay,
                "MERCARI": scan_mercari,
            }

            if ENABLE_FACEBOOK:
                scan_jobs["FACEBOOK"] = scan_facebook

            all_deals = []

            with ThreadPoolExecutor(max_workers=len(scan_jobs)) as executor:
                future_map = {
                    executor.submit(job): name
                    for name, job in scan_jobs.items()
                }

                for future in as_completed(future_map, timeout=30):
                    name = future_map[future]
                    try:
                        deals = future.result(timeout=5) or []
                        print(f"[RADAR] {name} returned {len(deals)} deals")
                        all_deals.extend(deals)
                    except Exception as e:
                        print(f"[RADAR ERROR] {name}: {e}")

            top_deals = all_deals[:MAX_DEALS]

            try:
                send_to_discord(top_deals)
            except Exception as e:
                print(f"[DISCORD ERROR] {e}")

            print("[RADAR] SLEEPING...")
            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[RADAR LOOP ERROR] {e}")
            time.sleep(10)

# STARTER
def start_radar():
    thread = threading.Thread(target=run_radar, daemon=True)
    thread.start()
