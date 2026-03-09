import os
import requests

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def get_token():

    response = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/buy.browse"
        },
        auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET)
    )

    data = response.json()

    token = data.get("access_token")

    print("TOKEN RESPONSE:", data)

    return token


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

    response = requests.get(
        SEARCH_URL,
        headers=headers,
        params=params
    )

    data = response.json()

    print("EBAY RESPONSE:", data)

    items = data.get("itemSummaries", [])

    prices = []
    items_out = []

    for item in items:

        try:

            price = float(item["price"]["value"])

            prices.append(price)

            items_out.append({
                "title": item.get("title"),
                "image": item.get("image", {}).get("imageUrl"),
                "link": item.get("itemWebUrl")
            })

        except:
            pass

    return prices, [], items_out