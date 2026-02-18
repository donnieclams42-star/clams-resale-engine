from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import os
import requests
import base64
from dotenv import load_dotenv
import statistics

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")

DEFAULT_PROFIT = 0.40
LOCAL_FACTOR = 0.80

CONDITION_MULTIPLIERS = {
    "A": 1.0,
    "B": 0.85,
    "C": 0.70,
    "Parts": 0.50
}

app = FastAPI()


# ---------------- AUTH ----------------

def is_authenticated(request: Request):
    return request.cookies.get("clams_auth") == "1"


# ---------------- EBAY TOKEN ----------------

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


# ---------------- SOLD DATA ----------------

def get_sold_data(query):
    try:
        token = get_ebay_token()
        if not token:
            return [], []

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={query}&filter=soldItems:true&limit=50"

        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        prices = []
        items = []

        for item in data.get("itemSummaries", []):
            try:
                price = float(item["price"]["value"])
                image = item.get("image", {}).get("imageUrl", "")
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


# ---------------- LOGIN ----------------

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/app")

    return """
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;">
            <h1 style="color:#00ffcc;">CLAMS</h1>
            <form method="post">
                <input type="password" name="password" placeholder="Enter Password"
                style="padding:15px;width:260px;border-radius:8px;border:none;margin-top:10px;">
                <br><br>
                <button style="padding:12px 40px;background:#00ffcc;border:none;border-radius:8px;font-weight:bold;">
                Enter
                </button>
            </form>
        </div>
    </body>
    </html>
    """


@app.post("/", response_class=HTMLResponse)
def check_password(password: str = Form(...)):
    if password == ACCESS_PASSWORD:
        response = RedirectResponse("/app", status_code=302)
        response.set_cookie(
            key="clams_auth",
            value="1",
            max_age=60 * 60 * 24 * 30,
            httponly=True
        )
        return response

    return "<h2 style='color:red;text-align:center;margin-top:40vh;'>Access Denied</h2>"


# ---------------- MAIN APP ----------------

@app.get("/app", response_class=HTMLResponse)
def main_app(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/")

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:30px;text-align:center;">
        <h1 style="color:#00ffcc;">CLAMS Resale Engine</h1>

        <form action="/search" style="max-width:600px;margin:auto;">
            <input name="q" placeholder="Search item..."
            style="padding:14px;width:100%;margin-bottom:12px;border-radius:8px;border:none;">

            <select name="condition"
            style="padding:14px;width:100%;margin-bottom:12px;border-radius:8px;border:none;">
                <option value="A">A - Excellent</option>
                <option value="B">B - Good</option>
                <option value="C">C - Rough</option>
                <option value="Parts">Parts</option>
            </select>

            <input name="profit" type="number" step="0.01" value="{DEFAULT_PROFIT}"
            style="padding:14px;width:100%;margin-bottom:12px;border-radius:8px;border:none;">

            <button style="padding:14px;width:100%;background:#00ffcc;border:none;border-radius:8px;font-weight:bold;">
            Analyze Deal
            </button>
        </form>
    </body>
    </html>
    """


# ---------------- SEARCH ----------------

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str, condition: str = "A", profit: float = DEFAULT_PROFIT):

    if not is_authenticated(request):
        return RedirectResponse("/")

    prices, items = get_sold_data(q)

    if not prices:
        return "<h2 style='color:white;text-align:center;margin-top:40vh;'>No comps found. Try broader keywords.</h2>"

    prices.sort()
    median_price = statistics.median(prices)
    adjusted = median_price * CONDITION_MULTIPLIERS.get(condition, 1.0)
    local = adjusted * LOCAL_FACTOR
    max_buy = local * (1 - profit)
    sell_target = local / (1 - profit) if profit < 0.99 else median_price

    confidence = min(len(prices) * 2, 100)

    risk_color = "#00ffcc"
    if profit > 0.5:
        risk_color = "#ff4444"
    elif profit > 0.35:
        risk_color = "#ffaa00"

    comp_html = ""
    for item in items[:12]:
        comp_html += f"""
        <div style="width:160px;margin:10px;background:#1a1a1a;padding:10px;border-radius:8px;">
            <a href="{item['link']}" target="_blank">
                <img src="{item['image']}" style="width:100%;height:120px;object-fit:cover;border-radius:6px;">
            </a>
            <div style="margin-top:6px;color:#00ffcc;">${item['price']}</div>
        </div>
        """

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:20px;max-width:1100px;margin:auto;">

        <h2 style="color:#00ffcc;">{q}</h2>

        <div style="display:flex;gap:20px;flex-wrap:wrap;">

            <div style="flex:1;background:#1a1a1a;padding:20px;border-radius:10px;">
                <h3>Median Market</h3>
                <h1>${median_price:.2f}</h1>
            </div>

            <div style="flex:1;background:#1a1a1a;padding:20px;border-radius:10px;">
                <h3 style="color:{risk_color};">Max Buy @ {profit*100:.0f}%</h3>
                <h1 style="color:{risk_color};">${max_buy:.2f}</h1>
            </div>

            <div style="flex:1;background:#1a1a1a;padding:20px;border-radius:10px;">
                <h3>Sell Needed</h3>
                <h1>${sell_target:.2f}</h1>
            </div>

            <div style="flex:1;background:#1a1a1a;padding:20px;border-radius:10px;">
                <h3>Confidence</h3>
                <h1>{confidence}%</h1>
            </div>

        </div>

        <h3 style="margin-top:40px;">Recent Comps</h3>
        <div style="display:flex;flex-wrap:wrap;">
            {comp_html}
        </div>

        <br>
        <a href="/app" style="color:#00ffcc;">Analyze Another</a>

    </body>
    </html>
    """
