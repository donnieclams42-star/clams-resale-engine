import os
import requests
import base64
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

PLACEHOLDER_IMAGE = "https://via.placeholder.com/300x200/111111/00ffc3?text=NO+IMAGE"


def get_ebay_token():
    try:
        if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
            return None

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

        r = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers=headers,
            data=data,
            timeout=10
        )

        if r.status_code != 200:
            return None

        return r.json().get("access_token")
    except Exception:
        return None


def resolve_image(item: dict) -> str:
    """
    eBay Browse API item summaries are inconsistent across listing types.
    This resolver checks multiple known locations.
    """
    try:
        # 1) Standard "image"
        img = item.get("image")
        if isinstance(img, dict):
            if img.get("imageUrl"):
                return img["imageUrl"]
            # Some responses use templates like ...{size}...
            if img.get("imageUrlTemplate"):
                return img["imageUrlTemplate"].replace("{size}", "300")

        # 2) Additional images array
        add = item.get("additionalImages")
        if isinstance(add, list) and add:
            if isinstance(add[0], dict) and add[0].get("imageUrl"):
                return add[0]["imageUrl"]

        # 3) Thumbnails array
        thumbs = item.get("thumbnailImages")
        if isinstance(thumbs, list) and thumbs:
            if isinstance(thumbs[0], dict) and thumbs[0].get("imageUrl"):
                return thumbs[0]["imageUrl"]

        # 4) Sometimes "itemGroupHref" indicates variations/cat group (no image in summary)
        if item.get("itemGroupHref"):
            return PLACEHOLDER_IMAGE

        return PLACEHOLDER_IMAGE
    except Exception:
        return PLACEHOLDER_IMAGE


def safe_get_json(url: str, headers: dict) -> dict:
    """
    Prevents crashes when eBay returns HTML, empty body, 4xx/5xx, or rate limits.
    """
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json() if r.content else {}
    except Exception:
        return {}


def get_market_data(query: str):
    token = get_ebay_token()
    if not token:
        return [], [], []

    headers = {"Authorization": f"Bearer {token}"}

    q = quote(query)

    sold_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}&filter=soldItems:true&limit=50"
    )
    active_url = (
        "https://api.ebay.com/buy/browse/v1/item_summary/search"
        f"?q={q}&limit=50"
    )

    sold_data = safe_get_json(sold_url, headers)
    active_data = safe_get_json(active_url, headers)

    sold_prices = []
    sold_items = []

    for item in sold_data.get("itemSummaries", []) or []:
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
    for item in active_data.get("itemSummaries", []) or []:
        try:
            active_prices.append(float(item["price"]["value"]))
        except Exception:
            continue

    return sold_prices, active_prices, sold_items
