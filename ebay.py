import os
import requests
import base64
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded"
}


def get_token():
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

    return r.json().get("access_token")


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
        "&limit=50"
        "&fieldgroups=EXTENDED"
    )

    active_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}"
        "&limit=50"
        "&fieldgroups=EXTENDED"
    )

    sold_r = requests.get(sold_url, headers=headers).json()
    active_r = requests.get(active_url, headers=headers).json()

    sold_prices = []
    sold_items = []

    for item in sold_r.get("itemSummaries", []):
        try:
            price = float(item["price"]["value"])
            image = item.get("image", {}).get("imageUrl")
            link = item.get("itemWebUrl", "#")

            sold_prices.append(price)

            if image:
                sold_items.append({
                    "price": price,
                    "image": image,
                    "link": link
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
