import os
import time
import json
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

ACCESS_TOKEN = None
TOKEN_EXPIRES = 0

# ===== RATE LIMIT PROTECTION =====
LAST_CALL = 0
MIN_DELAY = 2

# ===== CACHE DATABASE =====
DB_FILE = "market_cache.db"
CACHE_TTL = 1800


def init_cache():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS market_cache (
        query TEXT PRIMARY KEY,
        sold_prices TEXT,
        items TEXT,
        timestamp REAL
    )
    """)

    conn.commit()
    conn.close()


def get_cache(query):

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute(
        "SELECT sold_prices, items, timestamp FROM market_cache WHERE query=?",
        (query,)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    sold_prices, items, ts = row

    if time.time() - ts > CACHE_TTL:
        return None

    return {
        "sold_prices": json.loads(sold_prices),
        "active_prices": [],
        "items": json.loads(items),
        "error": None
    }


def save_cache(query, sold_prices, items):

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO market_cache
    (query, sold_prices, items, timestamp)
    VALUES (?, ?, ?, ?)
    """, (
        query,
        json.dumps(sold_prices),
        json.dumps(items),
        time.time()
    ))

    conn.commit()
    conn.close()


def rate_limit():

    global LAST_CALL

    now = time.time()
    wait = MIN_DELAY - (now - LAST_CALL)

    if wait > 0:
        time.sleep(wait)

    LAST_CALL = time.time()


def get_token():

    global ACCESS_TOKEN
    global TOKEN_EXPIRES

    if ACCESS_TOKEN and time.time() < TOKEN_EXPIRES:
        return ACCESS_TOKEN

    try:

        r = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
            timeout=20,
        )

        data = r.json()

        ACCESS_TOKEN = data.get("access_token")

        if not ACCESS_TOKEN:
            print("TOKEN ERROR:", data)
            return None

        TOKEN_EXPIRES = time.time() + data.get("expires_in", 7200) - 60

        print("EBAY TOKEN OK")

        return ACCESS_TOKEN

    except Exception as e:

        print("TOKEN REQUEST FAILED:", e)
        return None


def extract_price(item):

    try:
        return float(item["price"]["value"])
    except:
        pass

    try:
        return float(item["currentBidPrice"]["value"])
    except:
        pass

    try:
        return float(item["discountedPrice"]["value"])
    except:
        pass

    return None


def empty_result(msg=None):

    return {
        "sold_prices": [],
        "active_prices": [],
        "items": [],
        "error": msg
    }


def get_market_data(query):

    query = (query or "").strip().lower()

    if not query:
        return empty_result()

    # ===== CHECK CACHE FIRST =====
    cached = get_cache(query)
    if cached:
        print("CACHE HIT:", query)
        return cached

    token = get_token()

    if not token:
        return empty_result("Token failure")

    rate_limit()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }

    params = {
        "q": query,
        "limit": 50
    }

    try:

        r = requests.get(
            SEARCH_URL,
            headers=headers,
            params=params,
            timeout=20
        )

        print("EBAY STATUS:", r.status_code)

        if r.status_code == 429:

            print("RATE LIMITED — waiting 5 seconds")
            time.sleep(5)

            r = requests.get(
                SEARCH_URL,
                headers=headers,
                params=params,
                timeout=20
            )

        data = r.json()

        items = data.get("itemSummaries", [])

        print("EBAY ITEMS RETURNED:", len(items))

        sold_prices = []
        item_list = []

        for item in items:

            price = extract_price(item)

            if price is None:
                continue

            sold_prices.append(price)

            item_list.append(
                {
                    "title": item.get("title"),
                    "price": price,
                    "image": item.get("image", {}).get("imageUrl"),
                    "link": item.get("itemWebUrl"),
                }
            )

        save_cache(query, sold_prices, item_list)

        return {
            "sold_prices": sold_prices,
            "active_prices": [],
            "items": item_list,
            "error": None
        }

    except Exception as e:

        print("SEARCH FAILED:", e)

        return empty_result(str(e))


# initialize database automatically
init_cache()