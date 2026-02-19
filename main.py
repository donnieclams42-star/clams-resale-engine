from fastapi import FastAPI, Request
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
def search(request: Request, q: str, profit: float = DEFAULT_PROFIT):

    if not is_authenticated(request):
        return RedirectResponse("/")

    sold_prices, active_prices, sold_items = get_market_data(q)
    result = analyze_market(sold_prices, active_prices, "A", profit)

    if not result:
        return "<h2 style='color:white;text-align:center;margin-top:40vh;'>No comps found.</h2>"

    confidence_bar = f"""
    <div style="background:#222;border-radius:6px;overflow:hidden;">
        <div style="width:{result['confidence']}%;background:#00ffc3;height:12px;"></div>
    </div>
    """

    supply_bar_width = min(result["supply_ratio"] * 50, 100)
    supply_bar = f"""
    <div style="background:#222;border-radius:6px;overflow:hidden;">
        <div style="width:{supply_bar_width}%;background:#ffaa00;height:12px;"></div>
    </div>
    """

    volatility_bar_width = min(result["volatility"] * 100, 100)
    volatility_bar = f"""
    <div style="background:#222;border-radius:6px;overflow:hidden;">
        <div style="width:{volatility_bar_width}%;background:#ff4444;height:12px;"></div>
    </div>
    """

    comp_html = ""
    for item in sold_items[:12]:
        comp_html += f"""
        <div style="width:150px;margin:10px;background:#1a1a1a;padding:10px;border-radius:8px;">
            <a href="{item['link']}" target="_blank">
                <img src="{item['image']}" style="width:100%;height:120px;object-fit:cover;border-radius:6px;">
            </a>
            <div style="margin-top:6px;color:#00ffc3;">${item['price']}</div>
        </div>
        """

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:20px;max-width:1100px;margin:auto;">

        <h2 style="color:#00ffc3;">{q}</h2>

        <h3>Sold Median: ${result['sold_median']}</h3>
        <h3>Active Median: ${result['active_median']}</h3>

        <h3>Max Buy: ${result['max_buy']}</h3>
        <h3>Sell Target: ${result['sell_target']}</h3>
        <h3>Undercut At: ${result['undercut']}</h3>

        <h3>Market Pressure: {result['pressure']}</h3>

        <p>Confidence</p>
        {confidence_bar}

        <p>Supply Ratio</p>
        {supply_bar}

        <p>Volatility</p>
        {volatility_bar}

        <h3 style="margin-top:30px;">Recent Sold Comps</h3>
        <div style="display:flex;flex-wrap:wrap;">
            {comp_html}
        </div>

        <br>
        <a href="/app" style="color:#00ffc3;">Analyze Another</a>

    </body>
    </html>
    """


