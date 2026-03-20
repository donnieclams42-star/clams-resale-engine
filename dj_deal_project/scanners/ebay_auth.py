import time
import requests

try:
    from dj_deal_project.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET
except Exception:
    from config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET

_token_cache = {
    "access_token": None,
    "expires_at": 0
}

def get_ebay_token() -> str:
    now = time.time()

    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    url = "https://api.ebay.com/identity/v1/oauth2/token"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }

    response = requests.post(
        url,
        headers=headers,
        data=data,
        auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
        timeout=20
    )
    response.raise_for_status()

    payload = response.json()
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 7200))

    # refresh a little early
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = now + max(300, expires_in - 300)

    return access_token