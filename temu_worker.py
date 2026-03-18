
import time
from temu_scanner import fetch_temu_items

def start_temu_worker():
    print("[TEMU] Background worker started")

    while True:
        try:
            print("[TEMU] Running daily scan...")
            fetch_temu_items()
            print("[TEMU] Scan complete")
        except Exception as e:
            print("[TEMU ERROR]", e)

        time.sleep(86400)  # 24 hours
