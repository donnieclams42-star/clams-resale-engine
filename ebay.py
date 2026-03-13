import os
import requests
import re
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def get_token():

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
        auth=(CLIENT_ID, CLIENT_SECRET)
    )

    if r.status_code != 200:
        print("Token request failed")
        return None

    return r.json()["access_token"]


def clean_query(query):

    query = query.lower()
    query = re.sub(r"[^a-z0-9 ]", "", query)

    return query.strip()


def run_search(query, token):

    headers = {
        "Authorization": f"Bearer {token}"
    }

    params = {
        "q": query,
        "limit": 50,
        "filter": "buyingOptions:{FIXED_PRICE}"
    }

    r = requests.get(SEARCH_URL, headers=headers, params=params)

    if r.status_code != 200:
        return [], []

    items = r.json().get("itemSummaries", [])

    prices = []
    titles = []

    for item in items:
        try:
            price = float(item["price"]["value"])
            prices.append(price)

            title = item.get("title", "")
            titles.append(title)

        except:
            pass

    return prices, titles


def generate_suggestions(titles):

    suggestions = set()

    for title in titles[:15]:

        words = title.lower().split()

        if len(words) >= 2:
            suggestions.add(" ".join(words[:2]))

        if len(words) >= 3:
            suggestions.add(" ".join(words[:3]))

    return list(suggestions)[:5]


def search_ebay(query):

    token = get_token()

    if not token:
        print("No eBay token found")
        return [], [], []

    query = clean_query(query)

    prices, titles = run_search(query, token)

    if prices:
        suggestions = generate_suggestions(titles)
        return prices, prices, suggestions

    print("Primary search empty — trying fallback")

    words = query.split()

    if len(words) > 2:

        relaxed = " ".join(words[:2])

        prices, titles = run_search(relaxed, token)

        if prices:
            suggestions = generate_suggestions(titles)
            return prices, prices, suggestions

    if len(words) > 1:

        relaxed = words[0]

        prices, titles = run_search(relaxed, token)

        if prices:
            suggestions = generate_suggestions(titles)
            return prices, prices, suggestions

    print("No results after fallback")

    return [], [], []