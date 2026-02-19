from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from dotenv import load_dotenv

from auth import is_authenticated
from ebay import get_market_data
from pricing import analyze_market

load_dotenv()

ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD")
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
            <h1 style="color:#00ffc3;">CLAMS</h1>
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


@app.get("/app", response_class=HTMLResponse)
def main_app(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/")

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:30px;text-align:center;">

        <h1 style="color:#00ffc3;">CLAMS Market Intelligence</h1>

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

    sold_prices, active_prices = get_market_data(q)
    result = analyze_market(sold_prices, active_prices, condition, profit)

    if not result:
        return "<h2 style='color:white;text-align:center;margin-top:40vh;'>No comps found.</h2>"

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:20px;max-width:1000px;margin:auto;">

        <h2 style="color:#00ffc3;">{q}</h2>

        <div style="background:#1a1a1a;padding:20px;border-radius:10px;margin-bottom:20px;">
            <h3>📦 Sold Median: ${result['sold_median']}</h3>
            <h3>🏷 Active Median: ${result['active_median']}</h3>
        </div>

        <div style="background:#1a1a1a;padding:20px;border-radius:10px;margin-bottom:20px;">
            <h3>💰 Max Buy: ${result['max_buy']}</h3>
            <h3>🎯 Sell Target: ${result['sell_target']}</h3>
            <h3>💡 Undercut Active At: ${result['undercut']}</h3>
        </div>

        <div style="background:#1a1a1a;padding:20px;border-radius:10px;">
            <h3>📊 Supply Ratio: {result['supply_ratio']}</h3>
            <h3>🔥 Market Pressure: {result['pressure']}</h3>
            <h3>⚡ Volatility: {result['volatility']}</h3>
        </div>

        <br>
        <a href="/app" style="color:#00ffc3;">Analyze Another</a>

    </body>
    </html>
    """
