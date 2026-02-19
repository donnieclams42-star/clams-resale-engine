from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from dotenv import load_dotenv

from auth import is_authenticated, login_success_response, logout_response
from ebay import get_market_data
from pricing import analyze_market

load_dotenv()

ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "")
DEFAULT_PROFIT = 0.40

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/app")

    return """
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;width:320px;">
            <div style="font-size:42px;font-weight:900;color:#00ffc3;letter-spacing:2px;">CLAMS</div>
            <div style="color:#9aa0a6;margin-top:8px;">Private Market Intelligence</div>

            <form method="post" style="margin-top:18px;">
                <input type="password" name="password" placeholder="Enter Password"
                style="padding:15px;width:100%;border-radius:10px;border:none;margin-top:10px;font-size:16px;">
                <button style="margin-top:12px;padding:14px;width:100%;background:#00ffc3;border:none;border-radius:10px;font-weight:900;font-size:16px;">
                    Enter
                </button>
            </form>
        </div>
    </body>
    </html>
    """


@app.post("/", response_class=HTMLResponse)
def login_submit(password: str = Form("")):
    if ACCESS_PASSWORD and password == ACCESS_PASSWORD:
        return login_success_response("/app")

    return HTMLResponse("""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;width:340px;">
            <div style="font-size:42px;font-weight:900;color:#00ffc3;letter-spacing:2px;">CLAMS</div>
            <div style="margin-top:14px;color:#ff6666;font-weight:bold;">Wrong password</div>
            <a href="/" style="display:inline-block;margin-top:16px;color:#00ffc3;">Try again</a>
        </div>
    </body>
    </html>
    """, status_code=401)


@app.get("/logout")
def logout():
    return logout_response("/")


@app.get("/app", response_class=HTMLResponse)
def main_app(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/")

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:18px;text-align:center;">

        <div style="max-width:820px;margin:0 auto;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:10px;">
                <div style="text-align:left;">
                    <div style="font-size:30px;font-weight:900;color:#00ffc3;">CLAMS</div>
                    <div style="color:#9aa0a6;margin-top:2px;">Market Intelligence</div>
                </div>
                <a href="/logout" style="color:#00ffc3;text-decoration:none;font-weight:bold;">Logout</a>
            </div>

            <form action="/search" style="background:#141414;padding:14px;border-radius:14px;">

                <input name="q" placeholder="Search item..."
                style="padding:14px;width:100%;margin-bottom:10px;border-radius:10px;border:none;font-size:16px;">

                <div style="display:flex;gap:10px;flex-wrap:wrap;">
                    <select name="condition"
                    style="padding:14px;flex:1;min-width:180px;border-radius:10px;border:none;font-size:16px;">
                        <option value="A">Like New (A)</option>
                        <option value="B">Good (B)</option>
                        <option value="C">Worn (C)</option>
                        <option value="Parts">For Parts</option>
                    </select>

                    <input name="profit" type="number" step="0.01" value="{DEFAULT_PROFIT}"
                    style="padding:14px;flex:1;min-width:180px;border-radius:10px;border:none;font-size:16px;"
                    />
                </div>

                <button style="margin-top:10px;padding:14px;width:100%;background:#00ffc3;border:none;border-radius:10px;font-weight:900;font-size:16px;">
                    Analyze Market
                </button>

                <div style="margin-top:10px;color:#9aa0a6;font-size:13px;">
                    Profit example: 0.40 = 40%
                </div>

            </form>
        </div>
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
        return f"""
        <html>
        <body style="background:#0f0f0f;color:white;font-family:Arial;padding:22px;text-align:center;">
            <div style="max-width:700px;margin:18vh auto;background:#141414;padding:18px;border-radius:14px;">
                <div style="font-size:26px;font-weight:900;color:#00ffc3;">No comps found</div>
                <div style="color:#9aa0a6;margin-top:8px;">Try a simpler search (brand + model).</div>
                <a href="/app" style="display:inline-block;margin-top:14px;color:#00ffc3;font-weight:bold;text-decoration:none;">Back</a>
            </div>
        </body>
        </html>
        """

    # Pricing ladder (UI-first)
    sell_target = float(result["sell_target"])
    fast_price = round(sell_target * 0.85, 2)
    hold_price = round(sell_target * 1.15, 2)

    # bars
    confidence = int(result["confidence"])
    supply_bar_width = min(float(result["supply_ratio"]) * 50, 100)
    volatility_bar_width = min(float(result["volatility"]) * 100, 100)

    def bar(label, width, color):
        return f"""
        <div style="margin-top:12px;text-align:left;">
            <div style="color:#9aa0a6;font-size:13px;margin-bottom:6px;">{label}</div>
            <div style="background:#222;border-radius:10px;overflow:hidden;height:12px;">
                <div style="width:{width}%;background:{color};height:12px;"></div>
            </div>
        </div>
        """

    comp_html = ""
    for item in (sold_items[:12] if sold_items else []):
        comp_html += f"""
        <a href="{item.get('link', '#')}" target="_blank" style="text-decoration:none;">
            <div style="width:160px;margin:8px;background:#141414;padding:10px;border-radius:12px;display:inline-block;vertical-align:top;">
                <img src="{item.get('image')}" style="width:100%;height:120px;object-fit:cover;border-radius:10px;background:#0b0b0b;">
                <div style="margin-top:8px;color:#00ffc3;font-weight:900;font-size:16px;">${item.get('price')}</div>
            </div>
        </a>
        """

    return f"""
    <html>
    <body style="background:#0f0f0f;color:white;font-family:Arial;padding:18px;text-align:center;">

        <div style="max-width:1100px;margin:0 auto;">

            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
                <div style="text-align:left;">
                    <div style="font-size:28px;font-weight:900;color:#00ffc3;">{q}</div>
                    <div style="color:#9aa0a6;margin-top:3px;">
                        Condition: <b style="color:white;">{condition}</b> • Profit: <b style="color:white;">{profit}</b>
                    </div>
                </div>
                <a href="/app" style="color:#00ffc3;text-decoration:none;font-weight:bold;">New Search</a>
            </div>

            <div style="margin-top:14px;background:#141414;padding:14px;border-radius:14px;">
                <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;">

                    <div style="min-width:200px;background:#0b0b0b;padding:12px;border-radius:12px;">
                        <div style="color:#9aa0a6;font-size:13px;">BUY BELOW</div>
                        <div style="font-size:26px;font-weight:900;color:#00ffc3;">${result['max_buy']}</div>
                    </div>

                    <div style="min-width:200px;background:#0b0b0b;padding:12px;border-radius:12px;">
                        <div style="color:#9aa0a6;font-size:13px;">MARKET</div>
                        <div style="font-size:26px;font-weight:900;color:white;">${result['sell_target']}</div>
                    </div>

                    <div style="min-width:200px;background:#0b0b0b;padding:12px;border-radius:12px;">
                        <div style="color:#9aa0a6;font-size:13px;">FAST SALE</div>
                        <div style="font-size:26px;font-weight:900;color:#00ffc3;">${fast_price}</div>
                    </div>

                    <div style="min-width:200px;background:#0b0b0b;padding:12px;border-radius:12px;">
                        <div style="color:#9aa0a6;font-size:13px;">HOLD</div>
                        <div style="font-size:26px;font-weight:900;color:white;">${hold_price}</div>
                    </div>

                </div>

                <div style="margin-top:14px;text-align:left;">
                    <div style="font-weight:900;font-size:16px;">Market Pressure: <span style="color:#00ffc3;">{result['pressure']}</span></div>
                    {bar("Confidence", confidence, "#00ffc3")}
                    {bar("Supply Ratio", supply_bar_width, "#ffaa00")}
                    {bar("Volatility", volatility_bar_width, "#ff4444")}
                </div>
            </div>

            <div style="margin-top:18px;text-align:left;">
                <div style="font-size:18px;font-weight:900;margin-bottom:10px;">Recent Sold Listings</div>
                <div style="display:flex;flex-wrap:wrap;justify-content:flex-start;">
                    {comp_html}
                </div>
            </div>

        </div>
    </body>
    </html>
    """
