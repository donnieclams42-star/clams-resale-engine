import os
import requests
import re
import time
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
TOKEN_CACHE_SECONDS = 7100
SEARCH_CACHE_SECONDS = 21600

_TOKEN_CACHE = {
    "token": None,
    "expires_at": 0,
}

_SEARCH_CACHE = {}


def get_token():
    now = time.time()

    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["token"]

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }

    r = requests.post(
        TOKEN_URL,
        headers=headers,
        data=data,
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=20,
    )

    if r.status_code != 200:
        print("Token request failed")
        return None

    token = r.json().get("access_token")
    expires_in = int(r.json().get("expires_in", TOKEN_CACHE_SECONDS))

    if token:
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = now + max(60, min(expires_in - 60, TOKEN_CACHE_SECONDS))

    return token


def clean_query(query):
    query = (query or "").lower()
    query = re.sub(r"[^a-z0-9 ]", "", query)
    query = re.sub(r"\s+", " ", query)
    return query.strip()


def is_barcode_query(query):
    query = re.sub(r"\D", "", query or "")
    return 8 <= len(query) <= 14


def normalize_barcode(query):
    return re.sub(r"\D", "", query or "")


def _prune_search_cache(now):
    expired_keys = [key for key, value in _SEARCH_CACHE.items() if now >= value["expires_at"]]
    for key in expired_keys:
        _SEARCH_CACHE.pop(key, None)


def run_search(query, token, gtin=None):
    headers = {
        "Authorization": f"Bearer {token}"
    }

    params = {
        "limit": 50,
        "filter": "buyingOptions:{FIXED_PRICE}"
    }

    if gtin:
        params["gtin"] = gtin
    else:
        params["q"] = query

    r = requests.get(SEARCH_URL, headers=headers, params=params, timeout=20)

    if r.status_code != 200:
        print("Search request failed:", r.status_code, r.text[:300])
        return [], [], None

    items = r.json().get("itemSummaries", [])

    prices = []
    titles = []
    verified_listing = None

    for item in items:
        try:
            price = float(item["price"]["value"])
            title = item.get("title", "")

            prices.append(price)
            titles.append(title)

            if verified_listing is None:
                verified_listing = {
                    "title": title,
                    "price": price,
                    "image": item.get("image", {}).get("imageUrl", ""),
                    "url": item.get("itemWebUrl", "")
                }
        except Exception:
            pass

    return prices, titles, verified_listing


def generate_suggestions(titles):
    suggestions = set()

    for title in titles[:15]:
        words = title.lower().split()

        if len(words) >= 2:
            suggestions.add(" ".join(words[:2]))

        if len(words) >= 3:
            suggestions.add(" ".join(words[:3]))

    return list(suggestions)[:5]


def cache_result(key, result, now):
    _SEARCH_CACHE[key] = {
        "expires_at": now + SEARCH_CACHE_SECONDS,
        "data": result,
    }
    return result


def search_ebay(query):
    query = clean_query(query)

    if not query:
        return [], [], [], None

    now = time.time()
    _prune_search_cache(now)

    cached = _SEARCH_CACHE.get(query)
    if cached and now < cached["expires_at"]:
        return cached["data"]

    token = get_token()

    if not token:
        return [], [], [], None

    # Barcode / UPC / EAN path first
    if is_barcode_query(query):
        barcode = normalize_barcode(query)
        barcode_cache_key = f"gtin:{barcode}"
        cached_barcode = _SEARCH_CACHE.get(barcode_cache_key)

        if cached_barcode and now < cached_barcode["expires_at"]:
            return cached_barcode["data"]

        prices, titles, listing = run_search(query="", token=token, gtin=barcode)
        if prices:
            suggestions = generate_suggestions(titles)
            result = (prices, prices[:], suggestions, listing)
            cache_result(barcode_cache_key, result, now)
            cache_result(query, result, now)
            return result

        # Fallback: some listings still respond better to raw keyword barcode searches
        prices, titles, listing = run_search(query=barcode, token=token)
        if prices:
            suggestions = generate_suggestions(titles)
            result = (prices, prices[:], suggestions, listing)
            cache_result(barcode_cache_key, result, now)
            cache_result(query, result, now)
            return result

    prices, titles, listing = run_search(query, token)

    if prices:
        suggestions = generate_suggestions(titles)
        result = (prices, prices[:], suggestions, listing)
        return cache_result(query, result, now)

    words = query.split()

    if len(words) > 1:
        relaxed = words[0]
        cached_relaxed = _SEARCH_CACHE.get(relaxed)

        if cached_relaxed and now < cached_relaxed["expires_at"]:
            return cached_relaxed["data"]

        prices, titles, listing = run_search(relaxed, token)

        if prices:
            suggestions = generate_suggestions(titles)
            result = (prices, prices[:], suggestions, listing)
            return cache_result(relaxed, result, now)

    return [], [], [], None
