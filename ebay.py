import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

PLACEHOLDER_IMAGE = "https://via.placeholder.com/300x200?text=No+Image"


def get_ebay_token():
    try:
        credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }

        response = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers=headers,
            data=data,
            timeout=10
        )

        if response.status_code != 200:
            return None

        return response.json().get("access_token")
    except:
        return None


def get_market_data(query):

    token = get_ebay_token()
    if not token:
        return [], [], []

    headers = {"Authorization": f"Bearer {token}"}

    # --- SOLD ITEMS (WITH IMAGES) ---
    sold_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={query}&filter=soldItems:true&limit=50"
    )

    sold_response = requests.get(sold_url, headers=headers, timeout=10)
    sold_data = sold_response.json()

    sold_prices = []
    sold_items = []

    for item in sold_data.get("itemSummaries", []):
        try:
            price = float(item["price"]["value"])
            image = item.get("image", {}).get("imageUrl") or PLACEHOLDER_IMAGE
            link = item.get("itemWebUrl", "#")

            sold_prices.append(price)
            sold_items.append({
                "price": price,
                "image": image,
                "link": link
            })
        except:
            continue

    # --- ACTIVE PRICES ONLY ---
    active_url = (
        "https://api.ebay.com/buy/browse/v1/it
