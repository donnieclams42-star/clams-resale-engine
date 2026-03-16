import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

from alerts.discord_alert import send_discord_alert
from filters.profit_filter import evaluate_profit
from filters.scam_filter import is_scam_listing
from scanners.craigslist_scanner import scan_craigslist
from scanners.ebay_auction_scanner import scan_ebay_auctions
from scanners.ebay_scanner import scan_ebay
from scanners.fb_scanner import scan_facebook
from scanners.mercari_scanner import scan_mercari
from scanners.offerup_scanner import scan_offerup
from utils.logger import log_event
from utils.seen_deals import filter_new


SCAN_INTERVAL = getattr(config, "SCAN_INTERVAL", 60)
FB_SCAN_FREQUENCY = getattr(config, "FB_SCAN_FREQUENCY", 3)
ALERT_TOP_N = getattr(config, "ALERT_TOP_N", 5)

ENABLE_EBAY = getattr(config, "ENABLE_EBAY", True)
ENABLE_EBAY_AUCTIONS = getattr(config, "ENABLE_EBAY_AUCTIONS", True)
ENABLE_MERCARI = getattr(config, "ENABLE_MERCARI", True)
ENABLE_CRAIGSLIST = getattr(config, "ENABLE_CRAIGSLIST", True)
ENABLE_OFFERUP = getattr(config, "ENABLE_OFFERUP", False)


def _run_named_scan(name: str, func):
    log_event(f"{name} SCAN START")
    deals = func() or []
    log_event(f"{name} SCAN DONE deals={len(deals)}")
    return deals


def run_market_scans(cycle: int) -> list[dict]:
    all_deals: list[dict] = []
    scan_jobs = []

    if ENABLE_EBAY:
        scan_jobs.append(("EBAY", scan_ebay))

    if ENABLE_EBAY_AUCTIONS:
        scan_jobs.append(("EBAY_AUCTIONS", scan_ebay_auctions))

    if ENABLE_MERCARI:
        scan_jobs.append(("MERCARI", scan_mercari))

    if ENABLE_CRAIGSLIST:
        scan_jobs.append(("CRAIGSLIST", scan_craigslist))

    if ENABLE_OFFERUP:
        scan_jobs.append(("OFFERUP", scan_offerup))

    if cycle % FB_SCAN_FREQUENCY == 0:
        scan_jobs.append(("FACEBOOK", scan_facebook))
        log_event("FACEBOOK SCAN ACTIVE THIS CYCLE")
    else:
        log_event("FACEBOOK SKIPPED THIS CYCLE")

    if not scan_jobs:
        log_event("NO SCANNERS ENABLED")
        return all_deals

    log_event("STARTING PARALLEL SCANS")

    with ThreadPoolExecutor(max_workers=len(scan_jobs)) as executor:
        future_map = {
            executor.submit(_run_named_scan, name, func): name
            for name, func in scan_jobs
        }

        for future in as_completed(future_map):
            name = future_map[future]
            try:
                deals = future.result() or []
                all_deals.extend(deals)
            except Exception as e:
                log_event(f"{name} ERROR {e}")

    return all_deals


def process_deals(deals: list[dict]) -> list[dict]:
    profitable: list[dict] = []

    for deal in deals:
        title = str(deal.get("title", "")).strip()

        if not title:
            continue

        if is_scam_listing(title):
            continue

        try:
            evaluated = evaluate_profit(deal)
        except Exception as e:
            log_event(f"PROFIT_FILTER_ERROR title={title[:80]} error={e}")
            continue

        if not evaluated:
            continue

        profitable.append(evaluated)

    profitable.sort(
        key=lambda d: (
            d.get("score", 0),
            d.get("profit", 0),
            d.get("resale", 0),
        ),
        reverse=True,
    )

    return profitable


def send_top_alerts(deals: list[dict]) -> int:
    if not deals:
        return 0

    sent = 0
    top_deals = deals[:ALERT_TOP_N]

    for deal in top_deals:
        try:
            send_discord_alert(deal)
            sent += 1
        except Exception as e:
            log_event(f"ALERT ERROR {e}")

    return sent


def main() -> None:
    cycle = 0

    log_event("D&J DEAL RADAR STARTED")

    while True:
        cycle += 1
        log_event(f"SCAN CYCLE {cycle}")

        raw_deals = run_market_scans(cycle)
        log_event(f"RAW DEALS FOUND {len(raw_deals)}")

        # First dedupe pass: stop repeated raw listings immediately
        unique_raw = filter_new(raw_deals)
        log_event(f"UNIQUE RAW DEALS {len(unique_raw)}")

        profitable = process_deals(unique_raw)
        log_event(f"PROFITABLE DEALS {len(profitable)}")

        # Optional second dedupe pass after enrichment
        fresh_profitable = filter_new(profitable)
        log_event(f"FRESH PROFITABLE DEALS {len(fresh_profitable)}")

        sent_count = send_top_alerts(fresh_profitable)
        log_event(f"ALERTS SENT {sent_count}")

        if len(fresh_profitable) >= 15:
            log_event("HIGH ACTIVITY MARKET")
            wait_time = 10
        else:
            wait_time = SCAN_INTERVAL

        log_event(f"WAITING {wait_time} SECONDS")
        time.sleep(wait_time)


if __name__ == "__main__":
    main()