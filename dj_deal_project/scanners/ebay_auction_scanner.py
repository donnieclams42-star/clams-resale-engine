import requests
from scanners.ebay_auth import get_ebay_token
from utils.logger import log_event
from config import MAX_PRICE

EBAY_MARKET = "EBAY_US"


def scan_ebay_auctions():

    deals = []

    token = get_ebay_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKET
    }

    keywords = [
        "iphone",
        "iphone 13",
        "iphone 14",
        "ps5",
        "nintendo switch",
        "gamecube",
        "pokemon cards",
        "sports cards",
        "milwaukee drill"
    ]

    for term in keywords:

        log_event(f"EBAY_AUCTION_SCAN {term}")

        params = {
            "q": term,
            "limit": 50,
            "filter": "buyingOptions:{AUCTION}",
            "sort": "endingSoonest"
        }

        try:

            r = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers=headers,
                params=params,
                timeout=10
            )

            data = r.json()

            if "itemSummaries" not in data:
                continue

            for item in data["itemSummaries"]:

                try:

                    price = float(item["price"]["value"])

                    if price > MAX_PRICE:
                        continue

                    deals.append({
                        "title": item["title"],
                        "price": price,
                        "link": item["itemWebUrl"],
                        "market": "eBay Auction"
                    })

                except:
                    continue

        except Exception as e:

            log_event(f"EBAY_AUCTION_ERROR {e}")

    log_event(f"EBAY_AUCTION_RESULTS {len(deals)}")

    return deals