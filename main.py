import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from ebay import get_market_data
from pricing import analyze_market
from auth import is_authenticated, login_success_response, logout_response

app = FastAPI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "changeme")

PRESETS = {
    "aggressive": {"profit": 0.25, "local": 0.75},
    "balanced": {"profit": 0.40, "local": 0.80},
    "collector": {"profit": 0.55, "local": 0.90},
}

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/app", status_code=303)

    return """
    <html>
    <body style="background:#111;color:white;font-family:Arial;text-align:center;padding-top:150px;">
        <h2>CLAMS Beta Access</h2>
        <form method="post" action="/login">
            <input type="password" name="password" placeholder="Enter Password" required
                   style="padding:10px;border-radius:6px;border:none;">
            <br><br>
            <button type="submit" style="padding:10px 20px;border:none;border-radius:6px;background:#00cc66;font-weight:bold;color:black;">
                Enter
            </button>
        </form>
    </body>
    </html>
    """

@app.post("/login")
def login(password: str = Form(...)):
    if password == CLAMS_PASSWORD:
        return login_success_response("/app")
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
def logout():
    return logout_response("/")

@app.get("/app", response_class=HTMLResponse)
def app_home(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return render_page()

@app.post("/app", response_class=HTMLResponse)
def analyze(
    request: Request,
    query: str = Form(...),
    condition: str = Form("A"),
    preset: str = Form("balanced"),
):
    if not is_authenticated(request):
        return RedirectResponse("/", status_code=303)

    sold_prices, active_prices, sold_items = get_market_data(query)

    if not sold_prices:
        return render_page(error="No comps found.", preset=preset)

    preset_config = PRESETS.get(preset, PRESETS["balanced"])
    profit = preset_config["profit"]
    local_factor = preset_config["local"]

    analysis = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit,
        local_factor
    )

    fast_cash = analysis["undercut"]
    market_price = analysis["sell_target"]
    hold_price = round(analysis["sell_target"] * 1.15, 2)

    return render_page(
        query=query,
        fast_cash=fast_cash,
        market_price=market_price,
        hold_price=hold_price,
        preset=preset
    )

def render_page(query="", fast_cash=None,
                market_price=None, hold_price=None,
                preset="balanced", error=None):

    pricing_block = ""
    if fast_cash:
        pricing_block = f"""
        <div class="bar fast">🔥 FAST CASH: ${fast_cash}</div>
        <div class="bar market">⚖ MARKET: ${market_price}</div>
        <div class="bar hold">💎 HOLD MAX: ${hold_price}</div>
        """

    error_block = f"<div style='color:red;margin:20px;'>{error}</div>" if error else ""

    return f"""
    <html>
    <head>
        <title>CLAMS Resale Engine</title>
        <style>
            body {{
                background:#111;
                color:white;
                font-family:Arial;
                text-align:center;
                padding:40px;
            }}

            h1 {{
                font-size:40px;
                color:#00ffcc;
            }}

            .preset-btn {{
                padding:10px 20px;
                margin:5px;
                border-radius:8px;
                border:none;
                font-weight:bold;
                cursor:pointer;
                background:#333;
                color:white;
                transition:all 0.2s ease;
            }}

            .preset-btn:hover {{
                transform:scale(1.05);
            }}

            .bar {{
                width:500px;
                margin:10px auto;
                padding:15px;
                font-size:20px;
                border-radius:10px;
            }}

            .fast {{ background:#c0392b; }}
            .market {{ background:#2980b9; }}
            .hold {{ background:#27ae60; }}

            input, select {{
                padding:10px;
                border-radius:8px;
                border:none;
                margin:5px;
            }}

            button.submit {{
                padding:10px 20px;
                border-radius:8px;
                border:none;
                background:#00cc66;
                font-weight:bold;
                color:black;
            }}
        </style>
    </head>

    <body>

        <h1>CLAMS Resale Engine</h1>

        <form method="post" action="/app">
            <input type="hidden" name="preset" id="presetInput" value="{preset}">

            <button type="button" class="preset-btn" id="btn-aggressive"
                    onclick="changePreset('aggressive')">
                Aggressive
            </button>

            <button type="button" class="preset-btn" id="btn-balanced"
                    onclick="changePreset('balanced')">
                Balanced
            </button>

            <button type="button" class="preset-btn" id="btn-collector"
                    onclick="changePreset('collector')">
                Collector
            </button>

            <br><br>

            <input name="query" value="{query}" placeholder="Search item..." required>

            <select name="condition">
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
                <option value="Parts">Parts</option>
            </select>

            <button type="submit" class="submit">Analyze</button>
        </form>

        {error_block}
        {pricing_block}

        <br><br>
        <a href="/logout" style="color:#888;">Logout</a>

        <script>
            function highlight(mode) {{
                const presets = ['aggressive','balanced','collector'];

                presets.forEach(p => {{
                    const btn = document.getElementById('btn-' + p);
                    btn.style.background = '#333';
                    btn.style.color = 'white';
                }});

                const active = document.getElementById('btn-' + mode);
                active.style.background = '#00cc66';
                active.style.color = 'black';
            }}

            function changePreset(mode) {{
                document.getElementById("presetInput").value = mode;
                highlight(mode);
            }}

            window.onload = function() {{
                highlight("{preset}");
            }};
        </script>

    </body>
    </html>
    """