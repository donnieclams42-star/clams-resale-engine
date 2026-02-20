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
        hold_price=hold_price
    )


# ---------------- UI ---------------- #

def render_page(query="", preset="balanced", analysis=None,
                fast_cash=None, market_price=None,
                hold_price=None, error=None):

    marketing_block = ""
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

        posting_block = f"""
        <div class="panel">
            <h3>Pricing Strategy</h3>

            <div class="preset-row">
                <button class="preset" onclick="setPreset('aggressive')">Aggressive</button>
                <button class="preset" onclick="setPreset('balanced')">Balanced</button>
                <button class="preset" onclick="setPreset('collector')">Collector</button>
            </div>

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

            h1 {{
                font-size:38px;
                letter-spacing:2px;
                margin-bottom:30px;
            }}

            .toggle {{
                margin-bottom:25px;
            }}

            .toggle button {{
                padding:10px 30px;
                border:none;
                border-radius:6px;
                margin:5px;
                font-weight:bold;
                cursor:pointer;
                background:#2a2a2a;
                color:white;
            }}

            .toggle-active {{
                background:#00cc66;
                color:black;
            }}

            .panel {{
                background:rgba(20,20,20,.95);
                padding:30px;
                border-radius:12px;
                width:650px;
                margin:20px auto;
                text-align:left;
            }}

            .grid {{
                display:grid;
                grid-template-columns:1fr 1fr;
                gap:15px;
            }}

            .grid div span {{
                display:block;
                font-size:13px;
                color:#aaa;
            }}

            .grid div b {{
                font-size:18px;
            }}

            .bar {{
                padding:15px;
                border-radius:8px;
                margin-top:15px;
                font-weight:bold;
            }}

            .fast {{ background:#b02a2a; }}
            .market {{ background:#1f5fa9; }}
            .hold {{ background:#1e7e34; }}

            .preset-row {{
                margin-bottom:20px;
                text-align:center;
            }}

            .preset {{
                padding:8px 20px;
                margin:5px;
                border:none;
                border-radius:6px;
                background:#333;
                color:white;
                cursor:pointer;
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

            .error {{
                color:#ff6b6b;
                margin:15px;
            }}
        </style>
    </head>

    <body>

        <h1>CLAMS RESALE ENGINE</h1>

        <div class="toggle">
            <button id="marketingBtn" class="toggle-active"
                    onclick="switchView('marketing')">MARKETING</button>
            <button id="postingBtn"
                    onclick="switchView('posting')">POSTING</button>
        </div>

        <form method="post" action="/app">
            <input type="hidden" name="preset" id="presetInput" value="{preset}">
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

        <div id="marketingView">
            {marketing_block}
        </div>

        <div id="postingView" style="display:none;">
            {posting_block}
        </div>

        <br><br>
        <a href="/logout" style="color:#aaa;">Logout</a>

        <script>
            function switchView(view) {{
                const m = document.getElementById("marketingView");
                const p = document.getElementById("postingView");
                const mb = document.getElementById("marketingBtn");
                const pb = document.getElementById("postingBtn");

                if(view === "marketing") {{
                    m.style.display = "block";
                    p.style.display = "none";
                    mb.classList.add("toggle-active");
                    pb.classList.remove("toggle-active");
                }} else {{
                    m.style.display = "none";
                    p.style.display = "block";
                    pb.classList.add("toggle-active");
                    mb.classList.remove("toggle-active");
                }}
            }}

            function setPreset(mode) {{
                document.getElementById("presetInput").value = mode;
                document.querySelectorAll(".preset").forEach(btn => {{
                    btn.style.background = "#333";
                }});
                event.target.style.background = "#00cc66";
            }}
        </script>

    </body>
    </html>
    """