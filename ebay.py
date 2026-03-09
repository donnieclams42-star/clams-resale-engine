import os
import requests
from statistics import median

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
            "scope": "https://api.ebay.com/oauth/api_scope"
        },
        auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET)
    )

    data = response.json()

    return data.get("access_token")


def get_market_data(query):

    token = get_token()

    if not token:
        print("EBAY TOKEN FAILED")
        return [], [], []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    params = {
        "q": query,
        "limit": 20,
        "filter": "soldItems"
    }

    response = requests.get(SEARCH_URL, headers=headers, params=params)

    data = response.json()

    items = data.get("itemSummaries", [])

    sold_prices = []
    active_prices = []
    sold_items = []

    for item in items:

        price = float(item["price"]["value"])

        sold_prices.append(price)

        sold_items.append({
            "title": item["title"],
            "image": item["image"]["imageUrl"],
            "link": item["itemWebUrl"]
        })

    return sold_prices, active_prices, sold_items