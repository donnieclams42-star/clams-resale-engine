import requests

try:
    from dj_deal_project.scanners.ebay_auth import get_ebay_token
    from dj_deal_project.utils.logger import log_event
    from dj_deal_project.config import MAX_PRICE
except Exception:
    from scanners.ebay_auth import get_ebay_token
    from utils.logger import log_event
    from config import MAX_PRICE

EBAY_MARKET = "EBAY_US"
KEYWORDS = ["iphone", "iphone 13", "iphone 14", "ps5", "nintendo switch", "gamecube", "pokemon cards", "sports cards", "milwaukee drill"]


def scan_ebay_auctions():
    deals = []
    try:
        token = get_ebay_token()
    except Exception as e:
        log_event(f"EBAY_AUCTION_AUTH_ERROR {e}")
        return deals
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKET,
    }
    for term in KEYWORDS:
        log_event(f"EBAY_AUCTION_SCAN {term}")
        params = {"q": term, "limit": 50, "filter": "buyingOptions:{AUCTION}", "sort": "endingSoonest"}
        try:
            r = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search", headers=headers, params=params, timeout=10)
            data = r.json()
            for item in data.get('itemSummaries', []) or []:
                try:
                    price = float(item['price']['value'])
                except Exception:
                    continue
                if price > MAX_PRICE:
                    continue
                deals.append({
                    'title': item.get('title', ''),
                    'price': price,
                    'link': item.get('itemWebUrl', ''),
                    'url': item.get('itemWebUrl', ''),
                    'market': 'eBay Auction',
                    'source': 'eBay Auction',
                    'search_keyword': term,
                })
        except Exception as e:
            log_event(f"EBAY_AUCTION_ERROR {e}")
    log_event(f"EBAY_AUCTION_RESULTS {len(deals)}")
    return deals
