
import os
import requests

# ------------------------------------------------------------------
# eBay Search Module
# This file restores the search_ebay() function expected by main.py
# It safely queries eBay Browse API and returns the values required
# by the CLAMS / Market Radar engine.
# ------------------------------------------------------------------

EBAY_OAUTH_TOKEN = os.getenv("EBAY_OAUTH_TOKEN", "")


def search_ebay(query):
    """
    Search eBay listings using the Browse API.

    Returns:
        sold_prices: list[float]
        active_prices: list[float]
        suggestions: list[str]
        listing: str | None
    """

    sold_prices = []
    active_prices = []
    suggestions = []
    listing = None

    if not query:
        return sold_prices, active_prices, suggestions, listing

    try:

        endpoint = "https://api.ebay.com/buy/browse/v1/item_summary/search"

        headers = {
            "Authorization": f"Bearer {EBAY_OAUTH_TOKEN}",
            "Content-Type": "application/json"
        }

        params = {
            "q": query,
            "limit": 20
        }

        response = requests.get(endpoint, headers=headers, params=params, timeout=10)

        if response.status_code != 200:
            return sold_prices, active_prices, suggestions, listing

        data = response.json()

        items = data.get("itemSummaries", [])

        for item in items:

            price_data = item.get("price", {})
            price = price_data.get("value")

            if price:
                try:
                    active_prices.append(float(price))
                except Exception:
                    pass

            title = item.get("title")
            if title:
                suggestions.append(title)

        if suggestions:
            listing = suggestions[0]

    except Exception as e:
        print("eBay search failed:", e)

    return sold_prices, active_prices, suggestions, listing
