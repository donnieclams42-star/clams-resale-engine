import base64
import requests
from config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET

url = "https://api.ebay.com/identity/v1/oauth2/token"

credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()

headers = {
    "Authorization": f"Basic {encoded_credentials}",
    "Content-Type": "application/x-www-form-urlencoded"
}

data = {
    "grant_type": "client_credentials",
    "scope": "https://api.ebay.com/oauth/api_scope"
}

response = requests.post(url, headers=headers, data=data)

print("STATUS:", response.status_code)
print("RESPONSE:")
print(response.text)