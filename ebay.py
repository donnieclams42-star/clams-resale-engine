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


def fetch_items(query, sold=True):
    try:
        token = get_ebay_token()
        if not token:
            return [], []

        headers = {"Authorization": f"Bearer {token}"}
        filter_param = "soldItems:true" if sold else "soldItems:false"

        url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={query}&filter={filter_param}&limit=50"

        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        prices = []
        items = []

        for item in data.get("itemSummaries", []):
            try:
                price = float(item["price"]["value"])
                image = item.get("image", {}).get("imageUrl")

                if not image:
                    image = PLACEHOLDER_IMAGE

                link = item.get("itemWebUrl", "#")

                prices.append(price)
                items.append({
                    "price": price,
                    "image": image,
                    "link": link
                })

            except:
                continue

        return prices, items

    except:
        return [], []


def get_market_data(query):
    sold_prices, sold_items = fetch_items(query, sold=True)
    active_prices, _ = fetch_items(query, sold=False)
    return sold_prices, active_prices, sold_items
