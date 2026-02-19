from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from dotenv import load_dotenv

from auth import is_authenticated
from ebay import get_market_data
from pricing import analyze_market

load_dotenv()

DEFAULT_PROFIT = 0.40
app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/app")

    return """
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;">
            <h1 style="color:#00ffc3;font-size:40px;">CLAMS</h1>
            <form method="post">
                <input type="password" name="password" placeholder="Enter Password"
                style="padding:15px;width:260px;border-radius:8px;border:none;margin-top:10px;">
                <br><br>
                <button style="padding:12px 40px;background:#00ffc3;border:none;border-radius:8px;font-weight:bold;">
                Enter
                </button>
            </form>
        </div>
    </body>
    </html>
    """


@app.get("/app", response_class=HTMLResponse)
def main_app(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/")

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:20px;text-align:center;">
        <h1 style="color:#00ffc3;">CLAMS Market Intelligence</h1>

        <form action="/search" style="max-width:600px;margin:auto;">
            <input name="q" placeholder="Search item..."
            style="padding:14px;width:100%;margin-bottom:12px;border-radius:8px;border:none;">

            <select name="condition"
            style="padding:14px;width:100%;margin-bottom:12px;border-radius:8px;border:none;">
                <option value="A">Like New (A)</option>
                <option value="B">Good (B)</option>
                <option value="C">Worn (C)</option>
                <option value="Parts">For Parts</option>
            </select>

            <input name="profit" type="number" step="0.01" value="{DEFAULT_PROFIT}"
            style="padding:14px;width:100%;margin-bottom:12px;border-radius:8px;border:none;">

            <button style="padding:14px;width:100%;background:#00ffc3;border:none;border-radius:8px;font-weight:bold;">
            Analyze Market
            </button>
        </form>
    </body>
    </html>
    """


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str, condition: str = "A", profit: float = DEFAULT_PROFIT):

    if not is_authenticated(request):
        return RedirectResponse("/")

    sold_prices, active_prices, sold_items = get_market_data(q)
    result = analyze_market(sold_prices, active_prices, condition, profit)

    if not result:
        return "<h2 style='color:white;text-align:center;margin-top:40vh;'>No comps found.</h2>"

    fast_price = round(result["sell_target"] * 0.85, 2)
    hold_price = round(result["sell_target"] * 1.15, 2)

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:20px;max-width:1100px;margin:auto;text-align:center;">
        <h2 style="color:#00ffc3;">{q}</h2>

        <div style="background:#1a1a1a;padding:15px;border-radius:12px;margin-bottom:20px;">
            <h3>BUY BELOW: ${result['max_buy']}</h3>
            <h3>MARKET PRICE: ${result['sell_target']}</h3>
            <h3>FAST SALE: ${fast_price}</h3>
            <h3>HOLD PRICE: ${hold_price}</h3>
        </div>

        <h3>Market Pressure: {result['pressure']}</h3>

        <br><br>
        <a href="/app" style="color:#00ffc3;">New Search</a>
    </body>
    </html>
    """
