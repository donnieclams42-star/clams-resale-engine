print("🔥 EBAY PATCH LOADED")

import requests

from keywords.keyword_engine import get_keywords_for_cycle
from utils.logger import log_event
from scanners.ebay_auth import get_ebay_token
from config import EBAY_MARKET, MAX_PRICE, HTTP_TIMEOUT


def scan_ebay() -> list[dict]:
    deals: list[dict] = []

    keywords = get_keywords_for_cycle("ebay")
    token = get_ebay_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKET,
    }

    for keyword in keywords:
        log_event(f"EBAY_SCAN keyword={keyword}")

        try:
            response = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers=headers,
                params={"q": keyword, "limit": 20},
                timeout=HTTP_TIMEOUT,
            )

            if response.status_code != 200:
                log_event(f"EBAY_SCAN_STATUS {response.status_code} keyword={keyword}")
                continue

            data = response.json()
            items = data.get("itemSummaries", [])

            for item in items:
                try:
                    price = float(item["price"]["value"])
                except Exception:
                    continue

                if price > MAX_PRICE:
                    continue

                deals.append(
                    {
                        "title": str(item.get("title", "")).lower(),
                        "price": price,
                        "link": item.get("itemWebUrl", ""),
                        "market": "eBay",
                        "search_keyword": keyword,
                    }
                )

        except Exception as e:
            log_event(f"EBAY_SCAN_ERROR keyword={keyword} error={e}")

    log_event(f"EBAY_SCAN_RESULT deals={len(deals)}")
    return deals