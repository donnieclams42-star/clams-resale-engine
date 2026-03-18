import requests
import statistics

from config import (
    EBAY_MARKET,
    HTTP_TIMEOUT,
    MAX_PRICE,
    MIN_PRICE,
)
from keywords.keyword_engine import get_keywords_for_cycle
from scanners.ebay_auth import get_ebay_token
from utils.logger import log_event
from utils.model_parser import is_deal_candidate, normalize_text

SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
UNDERPRICED_FACTOR = 0.72


def _safe_price(item: dict) -> float | None:
    try:
        return float(((item or {}).get("price") or {}).get("value"))
    except Exception:
        return None


def _build_deal(item: dict, keyword: str, baseline: float) -> dict | None:
    title = str((item or {}).get("title") or "").strip()
    if not title:
        return None

    normalized_title = normalize_text(title)
    if not is_deal_candidate(normalized_title):
        return None

    price = _safe_price(item)
    if price is None or price < MIN_PRICE or price > MAX_PRICE:
        return None

    if baseline <= 0 or price >= round(baseline * UNDERPRICED_FACTOR, 2):
        return None

    url = str((item or {}).get("itemWebUrl") or "").strip()
    if not url:
        return None

    image_url = str((((item or {}).get("image") or {}).get("imageUrl")) or "").strip()

    return {
        "title": title,
        "price": round(price, 2),
        "link": url,
        "url": url,
        "image": image_url,
        "market": "eBay",
        "source": "eBay",
        "search_keyword": keyword,
        "baseline_price": round(baseline, 2),
        "candidate_strength": "underpriced",
    }


def scan_ebay() -> list[dict]:
    deals: list[dict] = []
    seen_links: set[str] = set()

    try:
        token = get_ebay_token()
    except Exception as e:
        log_event(f"EBAY_AUTH_ERROR error={e}")
        return deals

    if not token:
        log_event("EBAY_AUTH_ERROR missing_token")
        return deals

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKET,
    }

    keywords = get_keywords_for_cycle("ebay")

    for keyword in keywords:
        log_event(f"SCAN ebay keyword={keyword}")
        params = {
            "q": keyword,
            "limit": 30,
            "filter": "buyingOptions:{FIXED_PRICE}",
            "sort": "newlyListed",
        }

        try:
            response = requests.get(SEARCH_URL, headers=headers, params=params, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            items = (response.json() or {}).get("itemSummaries", []) or []
        except Exception as e:
            log_event(f"EBAY_SCAN_ERROR keyword={keyword} error={e}")
            continue

        prices = [p for p in (_safe_price(item) for item in items) if p is not None and MIN_PRICE <= p <= MAX_PRICE]
        if len(prices) < 3:
            continue

        baseline = float(statistics.median(prices))

        for item in items:
            deal = _build_deal(item, keyword, baseline)
            if not deal:
                continue

            link = deal["link"]
            if link in seen_links:
                continue
            seen_links.add(link)
            deals.append(deal)

    log_event(f"EBAY_SCAN_RESULT deals={len(deals)}")
    return deals
