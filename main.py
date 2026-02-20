from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from ebay import get_market_data
from pricing import analyze_market

app = FastAPI()

PRESETS = {
    "aggressive": {"profit": 0.25, "local": 0.75},
    "balanced": {"profit": 0.40, "local": 0.80},
    "collector": {"profit": 0.55, "local": 0.90},
}


@app.get("/", response_class=HTMLResponse)
def home():
    return render_page()


@app.post("/", response_class=HTMLResponse)
def analyze(
    query: str = Form(...),
    condition: str = Form("A"),
    preset: str = Form("balanced"),
    platform: str = Form("facebook"),
):

    sold_prices, active_prices, sold_items = get_market_data(query)

    if not sold_prices:
        return render_page(error="No comps found.")

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

    listing_text = generate_listing(
        query=query,
        condition=condition,
        price=fast_cash,
        platform=platform
    )

    return render_page(
        query=query,
        analysis=analysis,
        fast_cash=fast_cash,
        market_price=market_price,
        hold_price=hold_price,
        listing_text=listing_text,
        platform=platform,
        preset=preset
    )


def generate_listing(query, condition, price, platform):
    query_clean = query.strip().title()

    condition_map = {
        "A": "Excellent condition",
        "B": "Good condition",
        "C": "Fair condition",
        "Parts": "For parts or repair"
    }

    condition_text = condition_map.get(condition, "Good condition")

    if platform == "facebook":
        title = f"{query_clean} - {condition_text}"
        description = (
            f"{query_clean} available.\n"
            f"{condition_text}.\n"
            f"Fully functional.\n"
            f"Priced to sell at ${price}.\n"
            f"Local pickup preferred. Shipping available."
        )
    elif platform == "ebay":
        title = f"{query_clean} | {condition_text} | Fast Shipping"
        description = (
            f"{query_clean}\n\n"
            f"Condition: {condition_text}\n"
            f"Tested and fully working.\n"
            f"Ships quickly and securely.\n"
            f"Buy with confidence."
        )
    else:
        title = f"{query_clean}"
        description = f"{condition_text} {query_clean}"

    return f"TITLE:\n{title}\n\nPRICE:\n${price}\n\nDESCRIPTION:\n{description}"


def render_page(query="", analysis=None, fast_cash=None,
                market_price=None, hold_price=None,
                listing_text=None, platform="facebook",
                preset="balanced", error=None):

    pricing_block = ""
    if fast_cash:
        pricing_block = f"""
        <div class="bar fast">🔥 FAST CASH: ${fast_cash}</div>
        <div class="bar market">⚖ MARKET: ${market_price}</div>
        <div class="bar hold">💎 HOLD MAX: ${hold_price}</div>
        """

    listing_block = ""
    if listing_text:
        listing_block = f"""
        <div class="listing">
            <h3>Generated Listing</h3>
            <textarea rows="12">{listing_text}</textarea>
        </div>
        """

    error_block = f"<div class='error'>{error}</div>" if error else ""

    return f"""
    <html>
    <head>
        <title>CLAMS Resale Engine</title>
        <style>
            body {{ background:#111; color:white; font-family:Arial; text-align:center; padding:40px; }}
            h1 {{ font-size:40px; color:#00ffcc; }}

            .preset-btn {{
                padding:10px 20px;
                margin:5px;
                border-radius:8px;
                border:none;
                font-weight:bold;
                cursor:pointer;
            }}

            .active {{ background:#00cc66; }}
            .inactive {{ background:#444; color:white; }}

            .bar {{ width:500px; margin:10px auto; padding:15px; font-size:20px; border-radius:10px; }}
            .fast {{ background:#c0392b; }}
            .market {{ background:#2980b9; }}
            .hold {{ background:#27ae60; }}

            input, select {{ padding:10px; border-radius:8px; border:none; margin:5px; }}
            button {{ padding:10px 20px; border-radius:8px; border:none; background:#00cc66; font-weight:bold; }}

            .listing {{ width:600px; margin:30px auto; text-align:left; }}
            textarea {{ width:100%; padding:10px; border-radius:8px; border:none; font-family:monospace; }}
            .error {{ color:red; margin:20px; }}
        </style>
    </head>

    <body>

        <h1>CLAMS Resale Engine</h1>

        <form method="post">
            <input type="hidden" name="preset" id="presetInput" value="{preset}">

            <div>
                <button type="button" class="preset-btn {'active' if preset=='aggressive' else 'inactive'}" onclick="setPreset('aggressive')">Aggressive</button>
                <button type="button" class="preset-btn {'active' if preset=='balanced' else 'inactive'}" onclick="setPreset('balanced')">Balanced</button>
                <button type="button" class="preset-btn {'active' if preset=='collector' else 'inactive'}" onclick="setPreset('collector')">Collector</button>
            </div>

            <br>

            <input name="query" value="{query}" placeholder="Search item..." required>
            <select name="condition">
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
                <option value="Parts">Parts</option>
            </select>

            <select name="platform">
                <option value="facebook">Facebook Marketplace</option>
                <option value="ebay">eBay</option>
                <option value="mercari">Mercari</option>
                <option value="offerup">OfferUp</option>
                <option value="nextdoor">Nextdoor</option>
                <option value="craigslist">Craigslist</option>
            </select>

            <button type="submit">Analyze & Generate</button>
        </form>

        {error_block}
        {pricing_block}
        {listing_block}

        <script>
            function setPreset(mode) {{
                localStorage.setItem("clamsPreset", mode);
                document.getElementById("presetInput").value = mode;
                location.reload();
            }}

            window.onload = function() {{
                const saved = localStorage.getItem("clamsPreset") || "balanced";
                document.getElementById("presetInput").value = saved;
            }};
        </script>

    </body>
    </html>
    """