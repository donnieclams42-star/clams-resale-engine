from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from ebay import get_market_data
from pricing import analyze_market

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def home():
    return render_page()


@app.post("/", response_class=HTMLResponse)
def analyze(
    query: str = Form(...),
    condition: str = Form("A"),
    profit_margin: float = Form(40.0),
    platform: str = Form("facebook"),
):
    sold_prices, active_prices, sold_items = get_market_data(query)

    if not sold_prices:
        return render_page(error="No comps found.")

    profit_decimal = float(profit_margin) / 100

    analysis = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit_decimal
    )

    # Posting Mode Calculations
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
        platform=platform
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

    # Basic rule-based category detection
    electronics_keywords = ["iphone", "samsung", "laptop", "tablet", "camera"]
    fitness_keywords = ["dumbbell", "bench", "barbell", "weights"]
    collectible_keywords = ["vintage", "collectible", "limited", "rare", "lot"]

    category = "general"

    lower_query = query.lower()

    if any(k in lower_query for k in electronics_keywords):
        category = "electronics"
    elif any(k in lower_query for k in fitness_keywords):
        category = "fitness"
    elif any(k in lower_query for k in collectible_keywords):
        category = "collectible"

    # Platform formatting
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

    elif platform == "mercari":
        title = f"{query_clean} - Great Deal"
        description = (
            f"{condition_text} {query_clean}.\n"
            f"Ships fast.\n"
            f"Open to reasonable offers."
        )

    elif platform == "offerup":
        title = f"{query_clean} - Must Go"
        description = (
            f"{query_clean} in {condition_text.lower()}.\n"
            f"Cash preferred.\n"
            f"Fast pickup gets priority."
        )

    elif platform == "nextdoor":
        title = f"{query_clean} for Sale"
        description = (
            f"{query_clean} available locally.\n"
            f"{condition_text}.\n"
            f"Message if interested."
        )

    else:  # craigslist
        title = f"{query_clean} - Priced To Sell"
        description = (
            f"{query_clean}\n"
            f"{condition_text}\n"
            f"Serious inquiries only.\n"
            f"Email if interested."
        )

    return f"TITLE:\n{title}\n\nPRICE:\n${price}\n\nDESCRIPTION:\n{description}"


def render_page(query="", analysis=None, fast_cash=None,
                market_price=None, hold_price=None,
                listing_text=None, platform="facebook", error=None):

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

            select, input {{
                padding:10px;
                border-radius:8px;
                border:none;
                margin:5px;
            }}

            button {{
                padding:10px 20px;
                border-radius:8px;
                border:none;
                background:#00cc66;
                font-weight:bold;
            }}

            .listing {{
                width:600px;
                margin:30px auto;
                text-align:left;
            }}

            textarea {{
                width:100%;
                padding:10px;
                border-radius:8px;
                border:none;
                font-family:monospace;
            }}

            .error {{
                color:red;
                margin:20px;
            }}
        </style>
    </head>

    <body>

        <h1>CLAMS Resale Engine</h1>

        <form method="post">
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

    </body>
    </html>
    """
