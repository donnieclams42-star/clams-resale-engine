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

# ---------------- LOGIN ---------------- #

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
                   style="padding:12px;border-radius:8px;border:none;width:250px;">
            <br><br>
            <button type="submit"
                    style="padding:12px 30px;border:none;border-radius:8px;background:#00cc66;font-weight:bold;color:black;">
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

# ---------------- APP ---------------- #

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
        preset=preset,
        analysis=analysis,
        fast_cash=fast_cash,
        market_price=market_price,
        hold_price=hold_price,
        sold_items=sold_items[:12]
    )

# ---------------- UI ---------------- #

def render_page(query="", preset="balanced", analysis=None,
                fast_cash=None, market_price=None,
                hold_price=None, sold_items=None,
                error=None):

    marketing_block = ""
    comps_block = ""
    posting_block = ""

    if analysis:
        marketing_block = f"""
        <div class="panel">
            <h3>Market Intelligence</h3>
            <div class="grid">
                <div><span>Sold Median</span><b>${analysis["sold_median"]}</b></div>
                <div><span>Active Median</span><b>${analysis["active_median"]}</b></div>
                <div><span>Supply Ratio</span><b>{analysis["supply_ratio"]}</b></div>
                <div><span>Market Pressure</span><b>{analysis["pressure"]}</b></div>
                <div><span>Volatility</span><b>{analysis["volatility"]}</b></div>
                <div><span>Confidence</span><b>{analysis["confidence"]}%</b></div>
            </div>
        </div>
        """

        if sold_items:
            cards = ""
            for item in sold_items:
                cards += f"""
                <div class="comp-card" onclick="selectComp(this)">
                    <img src="{item['image'] or ''}" />
                    <div class="comp-info">
                        <p>{item['title'][:60]}</p>
                        <b>${item['price']}</b>
                    </div>
                </div>
                """

            comps_block = f"""
            <div class="panel">
                <h3>Select Best Match</h3>
                <div class="comp-grid">
                    {cards}
                </div>
            </div>
            """

        posting_block = f"""
        <div class="panel">
            <h3>Pricing Strategy</h3>
            <div class="bar fast">FAST CASH — ${fast_cash}</div>
            <div class="bar market">MARKET — ${market_price}</div>
            <div class="bar hold">HOLD MAX — ${hold_price}</div>
        </div>
        """

    error_block = f"<div class='error'>{error}</div>" if error else ""

    return f"""
    <html>
    <head>
        <title>CLAMS Resale Engine</title>
        <style>
            body {{
                margin:0;
                font-family:Arial, Helvetica, sans-serif;
                color:white;
                background:linear-gradient(rgba(0,0,0,.75), rgba(0,0,0,.85)),
                url('https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?q=80&w=1920&auto=format&fit=crop');
                background-size:cover;
                background-attachment:fixed;
                text-align:center;
                padding:40px;
            }}

            h1 {{ font-size:38px; margin-bottom:30px; }}

            .panel {{
                background:rgba(20,20,20,.95);
                padding:30px;
                border-radius:12px;
                width:750px;
                margin:20px auto;
                text-align:left;
            }}

            .grid {{
                display:grid;
                grid-template-columns:1fr 1fr;
                gap:15px;
            }}

            .grid span {{ font-size:13px; color:#aaa; }}

            .bar {{
                padding:15px;
                border-radius:8px;
                margin-top:15px;
                font-weight:bold;
            }}

            .fast {{ background:#b02a2a; }}
            .market {{ background:#1f5fa9; }}
            .hold {{ background:#1e7e34; }}

            .comp-grid {{
                display:grid;
                grid-template-columns:repeat(3, 1fr);
                gap:15px;
            }}

            .comp-card {{
                background:#222;
                border-radius:10px;
                overflow:hidden;
                cursor:pointer;
                transition:0.2s ease;
            }}

            .comp-card:hover {{
                transform:scale(1.03);
            }}

            .comp-card.selected {{
                outline:3px solid #00cc66;
            }}

            .comp-card img {{
                width:100%;
                height:150px;
                object-fit:cover;
                background:#000;
            }}

            .comp-info {{
                padding:10px;
            }}

            input, select {{
                padding:10px;
                border-radius:6px;
                border:none;
                margin:5px;
            }}

            button.submit {{
                padding:10px 25px;
                border-radius:6px;
                border:none;
                background:#00cc66;
                font-weight:bold;
                color:black;
            }}

            .error {{ color:#ff6b6b; margin:15px; }}
        </style>
    </head>

    <body>

        <h1>CLAMS RESALE ENGINE</h1>

        <form method="post" action="/app">
            <input type="hidden" name="preset" value="{preset}">
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
        {marketing_block}
        {comps_block}
        {posting_block}

        <br><br>
        <a href="/logout" style="color:#aaa;">Logout</a>

        <script>
            function selectComp(card) {{
                document.querySelectorAll('.comp-card').forEach(c => {{
                    c.classList.remove('selected');
                }});
                card.classList.add('selected');
            }}
        </script>

    </body>
    </html>
    """