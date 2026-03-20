
import time, random, threading

from dj_deal_project.scanners.ebay_scanner import run_ebay_scan
from dj_deal_project.scanners.mercari_scanner import run_mercari_scan
from dj_deal_project.scanners.offerup_scanner import run_offerup_scan
from temu_worker import start_temu_worker


def radar_loop():
    while True:
        try:
            print("[WORKER] Running scan cycle")

            run_ebay_scan()
            run_mercari_scan()
            run_offerup_scan()

            sleep_time = random.randint(60, 180)
            print(f"[WORKER] Sleeping {sleep_time}s")
            time.sleep(sleep_time)

        except Exception as e:
            print(f"[WORKER ERROR] {e}")
            time.sleep(10)


def start_worker():
    print("[WORKER] Starting system")

    threading.Thread(target=start_temu_worker, daemon=True).start()

    radar_loop()


if __name__ == "__main__":
    start_worker()
