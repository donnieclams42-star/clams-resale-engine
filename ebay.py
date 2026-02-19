import os
import requests
import base64
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

PLACEHOLDER_IMAGE = "https://ir.ebaystatic.com/cr/v/c1/placeholder-300x200.png"


# --------------------------------------------------
# TOKEN
# --------------------------------------------------
def get_ebay_token():
    try:
        creds = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
        encoded = base64.b64encode(creds.encode()).decode()

        r = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=15,
        )

        if r.status_code != 200:
            print("TOKEN FAIL:", r.text)
            return None

        return r.json().get("access_token")

    except Exception as e:
        print("TOKEN ERROR:", e)
        return None


# --------------------------------------------------
# SAFE REQUEST
# --------------------------------------------------
def safe_get(url, headers):
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("REQUEST ERROR:", e)
        return {}


# --------------------------------------------------
# IMAGE RESOLVER (handles all ebay formats)
# --------------------------------------------------
def resolve_image(item):
    try:
        # primary
        if item.get("image", {}).get("imageUrl"):
            return item["image"]["imageUrl"]

        # template image
        if item.get("image", {}).get("imageUrlTemplate"):
            return item["image"]["imageUrlTemplate"].replace("{size}", "300")

        # thumbnails
        thumbs = item.get("thumbnailImages")
        if isinstance(thumbs, list) and thumbs:
            if thumbs[0].get("imageUrl"):
                return thumbs[0]["imageUrl"]

        # additional images
        add = item.get("additionalImages")
        if isinstance(add, list) and add:
            if add[0].get("imageUrl"):
                return add[0]["imageUrl"]

        # group listings often have no images
        return PLACEHOLDER_IMAGE

    except Exception:
        return PLACEHOLDER_IMAGE


# --------------------------------------------------
# MARKET DATA
# --------------------------------------------------
def get_market_data(query):
    token = get_ebay_token()
    if not token:
        return [], [], []

    headers = {"Authorization": f"Bearer {token}"}
    q = quote(query)

    # IMPORTANT: force US marketplace or sold items vanish
    sold_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}&filter=soldItems:true&limit=50&contextualLocation=country%3DUS"
    )

    active_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}&limit=50&contextualLocation=country%3DUS"
    )

    sold_data = safe_get(sold_url, headers)
    active_data = safe_get(active_url, headers)

    sold_prices = []
    sold_items = []

    for item in sold_data.get("itemSummaries", []):
        try:
            price = float(item["price"]["value"])
            image = resolve_image(item)
            link = item.get("itemWebUrl", "#")

            sold_prices.append(price)
            sold_items.append({
                "price": price,
                "image": image,
                "link": link
            })
        except Exception:
            continue

    active_prices = []
    for item in active_data.get("itemSummaries", []):
        try:
            active_prices.append(float(item["price"]["value"]))
        except Exception:
            continue

    return sold_prices, active_prices, sold_items
