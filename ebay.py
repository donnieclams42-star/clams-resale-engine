import os
import requests
import base64
import time
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0
}


def get_token():
    # Return cached token if still valid
    if TOKEN_CACHE["access_token"] and time.time() < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["access_token"]

    creds = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded = base64.b64encode(creds.encode()).decode()

    r = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }
    )

    data = r.json()

    if "access_token" not in data:
        print("TOKEN ERROR:", data)
        return None

    TOKEN_CACHE["access_token"] = data["access_token"]
    TOKEN_CACHE["expires_at"] = time.time() + data.get("expires_in", 7200) - 60

    return TOKEN_CACHE["access_token"]


def extract_image(item):
    return (
        item.get("image", {}).get("imageUrl")
        or (item.get("thumbnailImages") or [{}])[0].get("imageUrl")
        or (item.get("additionalImages") or [{}])[0].get("imageUrl")
    )


def get_market_data(query):
    token = get_token()
    if not token:
        return [], [], []

    headers = {"Authorization": f"Bearer {token}"}
    q = quote(query)

    sold_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}"
        "&filter=soldItems:true"
        "&limit=30"
        "&fieldgroups=EXTENDED"
    )

    active_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}"
        "&limit=30"
        "&fieldgroups=EXTENDED"
    )

    sold_r = requests.get(sold_url, headers=headers).json()
    active_r = requests.get(active_url, headers=headers).json()

    raw_items = sold_r.get("itemSummaries", [])
    sold_prices = []
    sold_items = []

    for item in raw_items:
        try:
            price = float(item["price"]["value"])
            sold_prices.append(price)

            sold_items.append({
                "price": price,
                "image": extract_image(item),
                "link": item.get("itemWebUrl", "#"),
                "title": item.get("title", "")
            })
        except:
            continue

    active_prices = []
    for item in active_r.get("itemSummaries", []):
        try:
            active_prices.append(float(item["price"]["value"]))
        except:
            continue

    return sold_prices, active_prices, sold_items
