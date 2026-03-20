import time

from temu_worker import start_temu_worker

try:
    from dj_deal_project import config as cfg
    from dj_deal_project.scanners.ebay_scanner import run_ebay_scan
    from dj_deal_project.scanners.DISABLED_MERCARI_scanner import run_DISABLED_MERCARI_scan
    from dj_deal_project.scanners.DISABLED_OFFERUP_scanner import run_DISABLED_OFFERUP_scan
    from dj_deal_project.scanners.fb_scanner import run_facebook_scan
    from dj_deal_project.scanners.craigslist_scanner import run_craigslist_scan
except Exception:
    import config as cfg
    from scanners.ebay_scanner import run_ebay_scan
    from scanners.DISABLED_MERCARI_scanner import run_DISABLED_MERCARI_scan
    from scanners.DISABLED_OFFERUP_scanner import run_DISABLED_OFFERUP_scan
    from scanners.fb_scanner import run_facebook_scan
    from scanners.craigslist_scanner import run_craigslist_scan


def radar_loop():
    while True:
        try:
            print("[WORKER] Running scan cycle")
            if getattr(cfg, 'ENABLE_EBAY', True):
                run_ebay_scan()
            if getattr(cfg, 'ENABLE_DISABLED_MERCARI', True):
                run_DISABLED_MERCARI_scan()
            if getattr(cfg, 'ENABLE_DISABLED_OFFERUP', True):
                run_DISABLED_OFFERUP_scan()
            if getattr(cfg, 'ENABLE_FACEBOOK', True):
                run_facebook_scan()
            if getattr(cfg, 'ENABLE_CRAIGSLIST', True):
                run_craigslist_scan()
            sleep_time = int(getattr(cfg, 'SCAN_INTERVAL', 90) or 90)
            print(f"[WORKER] Sleeping {sleep_time}s")
            time.sleep(sleep_time)
        except Exception as e:
            print(f"[WORKER ERROR] {e}")
            time.sleep(15)


def start_worker():
    print("[WORKER] Starting system")
    start_temu_worker()
    radar_loop()


if __name__ == "__main__":
    start_worker()
