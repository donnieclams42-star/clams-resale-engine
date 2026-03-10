import os
import requests
import time

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

ACCESS_TOKEN = None
TOKEN_EXPIRES = 0


# ==========================
# GET EBAY ACCESS TOKEN
# ==========================
def get_token():

    global ACCESS_TOKEN
    global TOKEN_EXPIRES

    # reuse token if valid
    if ACCESS_TOKEN and time.time() < TOKEN_EXPIRES:
        return ACCESS_TOKEN

    try:

        response = requests.post(
            TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope"
            },
            auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
            timeout=15
        )

        data = response.json()

        ACCESS_TOKEN = data.get("access_token")

        if not ACCESS_TOKEN:
            print("EBAY TOKEN ERROR:", data)
            return None

        expires_in = data.get("expires_in", 7200)

        TOKEN_EXPIRES = time.time() + expires_in - 60

        print("EBAY TOKEN OK")

        return ACCESS_TOKEN

    except Exception as e:

        print("TOKEN REQUEST FAILED:", e)
        return None


# ==========================
# MARKET DATA SEARCH
# ==========================
def get_market_data(query):

    token = get_token()

    if not token:
        print("NO EBAY TOKEN")
        return [], [], []

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }

    params = {
        "q": query,
        "limit": 25
    }

    try:

        response = requests.get(
            SEARCH_URL,
            headers=headers,
            params=params,
            timeout=15
        )

        data = response.json()

        items = data.get("itemSummaries", [])

        print("EBAY ITEMS FOUND:", len(items))

        prices = []
        items_out = []

        for item in items:

            try:

                price = float(item["price"]["value"])

                prices.append(price)

                items_out.append({
                    "title": item.get("title"),
                    "price": price,
                    "image": item.get("image", {}).get("imageUrl"),
                    "link": item.get("itemWebUrl")
                })

            except Exception:
                continue

        print("VALID PRICES:", len(prices))

        return prices, [], items_out

    except Exception as e:

        print("EBAY SEARCH FAILED:", e)

        return [], [], []