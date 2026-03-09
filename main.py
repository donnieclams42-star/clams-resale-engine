import os
from html import escape
from urllib.parse import quote_plus

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

import stripe

from ebay import get_market_data
from pricing import analyze_market
from cards import analyze_card, spread_analysis
from auth import (
    is_authenticated,
    is_premium,
    login_success_response,
    premium_success_response,
    logout_response,
)

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
client = None
if OPENAI_KEY:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
SITE_URL = os.getenv("SITE_URL", "https://clams-resale-engine.onrender.com").strip()

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "changeme")


def safe_text(value: str) -> str:
    return escape(value or "")


def format_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def build_listing_pack(query: str, analysis: dict | None, condition: str, market: str) -> dict:
    query = (query or "").strip()
    market = (market or "facebook").strip().lower()

    sell_target = analysis["sell_target"] if analysis else 0
    fast_cash = analysis["fast_cash"] if analysis else 0
    market_price = analysis["market_price"] if analysis else sell_target
    hold_price = analysis["hold_price"] if analysis else 0

    title = query
    if market == "facebook":
        title = f"{query} - Clean / Tested"
    elif market == "ebay":
        title = f"{query} | Condition {condition}"
    elif market == "mercari":
        title = f"{query} - Ready to Ship"
    elif market == "offerup":
        title = f"{query} - Good Deal"
    elif market == "nextdoor":
        title = f"{query} - Local Sale"

    description = (
        f"{query}\n"
        f"Condition: {condition}\n"
        f"Fast Cash: {format_money(fast_cash)}\n"
        f"Market Price: {format_money(market_price)}\n"
        f"Hold Price: {format_money(hold_price)}\n\n"
        f"Clean post. Serious inquiries only."
    )

    cell_friendly = (
        f"{query}\n"
        f"Fast Cash {format_money(fast_cash)}\n"
        f"Market {format_money(market_price)}\n"
        f"Hold {format_money(hold_price)}"
    )

    return {
        "title": title,
        "description": description,
        "cell_description": cell_friendly,
    }


def card_summary_block(query: str) -> str:
    if not query:
        return ""

    try:
        card_results = analyze_card(query)
        spreads = spread_analysis(card_results)

        return f"""
        <div class="card">
            <div class="sectionTitle">Trading Card View</div>
            <div class="metricsGrid">
                <div class="metric"><div class="metricLabel">RAW</div><div class="metricValue">{format_money(card_results.get("raw", 0))}</div></div>
                <div class="metric"><div class="metricLabel">PSA 8</div><div class="metricValue">{format_money(card_results.get("PSA 8", 0))}</div></div>
                <div class="metric"><div class="metricLabel">PSA 9</div><div class="metricValue">{format_money(card_results.get("PSA 9", 0))}</div></div>
                <div class="metric"><div class="metricLabel">PSA 10</div><div class="metricValue">{format_money(card_results.get("PSA 10", 0))}</div></div>
            </div>
            <div style="margin-top:18px;">
                <div><b>9 vs Raw:</b> {spreads.get("9_vs_raw", "-")}</div>
                <div><b>10 vs Raw:</b> {spreads.get("10_vs_raw", "-")}</div>
                <div><b>10 vs 9:</b> {spreads.get("10_vs_9", "-")}</div>
            </div>
        </div>
        """
    except Exception:
        return ""


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    premium_badge = ""
    if is_premium(request):
        premium_badge = '<div class="founderTag">Founder / Premium Active</div>'

    return HTMLResponse(f"""
    <html>
    <head>
        <title>CLAMS - Resale Intelligence Engine</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body {{
                margin: 0;
                font-family: Segoe UI, Arial, sans-serif;
                background: linear-gradient(135deg, #13202a, #203646);
                color: white;
            }}
            .wrap {{
                max-width: 1100px;
                margin: 0 auto;
                padding: 70px 24px 40px 24px;
            }}
            .hero {{
                text-align: center;
                padding: 30px 0 30px 0;
            }}
            .logo {{
                font-size: 60px;
                font-weight: 900;
                background: linear-gradient(90deg, #00cc66, #00aaff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 8px;
            }}
            .sub {{
                font-size: 22px;
                color: #c7d5df;
                margin-bottom: 16px;
            }}
            .pitch {{
                max-width: 760px;
                margin: 0 auto;
                font-size: 18px;
                line-height: 1.6;
                color: #deebf2;
            }}
            .actions {{
                margin-top: 34px;
                display: flex;
                gap: 14px;
                justify-content: center;
                flex-wrap: wrap;
            }}
            .btn {{
                display: inline-block;
                padding: 16px 28px;
                border-radius: 14px;
                text-decoration: none;
                font-weight: 800;
                font-size: 16px;
            }}
            .btnPrimary {{
                background: #00cc66;
                color: #07140d;
            }}
            .btnSecondary {{
                background: #111923;
                color: white;
                border: 1px solid #2f4657;
            }}
            .founderTag {{
                display: inline-block;
                margin-bottom: 18px;
                background: #102a1d;
                color: #73f0aa;
                border: 1px solid #1f7148;
                padding: 10px 16px;
                border-radius: 999px;
                font-weight: 700;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
                gap: 18px;
                margin-top: 42px;
            }}
            .card {{
                background: rgba(10, 18, 24, 0.86);
                border: 1px solid #294151;
                border-radius: 20px;
                padding: 22px;
                box-shadow: 0 0 24px rgba(0, 0, 0, 0.22);
            }}
            .card h3 {{
                margin: 0 0 10px 0;
                color: #86f7b8;
            }}
            .pricing {{
                margin-top: 40px;
                text-align: center;
            }}
            .pricingBox {{
                max-width: 440px;
                margin: 0 auto;
                background: rgba(10, 18, 24, 0.88);
                border: 1px solid #294151;
                border-radius: 22px;
                padding: 28px;
            }}
            .price {{
                font-size: 44px;
                font-weight: 900;
                color: #00cc66;
            }}
            .fine {{
                color: #b4c5cf;
                line-height: 1.6;
            }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="hero">
                {premium_badge}
                <div class="logo">CLAMS</div>
                <div class="sub">Resale Intelligence Engine</div>
                <div class="pitch">
                    Stop guessing what to pay. CLAMS calculates max buy, fast cash, market price,
                    hold price, liquidity, risk, and a simple buy score using live market comps.
                    Then it helps you post faster with built-in listing copy.
                </div>
                <div class="actions">
                    <a class="btn btnPrimary" href="/login">Login</a>
                    <a class="btn btnSecondary" href="/app">Open Dashboard</a>
                    <a class="btn btnSecondary" href="/subscribe">Join Founder Beta</a>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>Max Buy</h3>
                    <div>Know the most you can safely pay before you message a seller.</div>
                </div>
                <div class="card">
                    <h3>Buy Score</h3>
                    <div>Get a fast confidence signal that blends liquidity, consistency, and risk.</div>
                </div>
                <div class="card">
                    <h3>Fast Cash + Market + Hold</h3>
                    <div>Three pricing lanes so you can move inventory how you want.</div>
                </div>
                <div class="card">
                    <h3>Listing Generator</h3>
                    <div>Create clean marketplace-ready titles and descriptions in seconds.</div>
                </div>
            </div>

            <div class="pricing">
                <div class="pricingBox">
                    <div style="font-size:18px;font-weight:800;">Founder Beta</div>
                    <div class="price">$19<span style="font-size:18px;color:#dbe9f0;">/month</span></div>
                    <div class="fine" style="margin-top:10px;">
                        Private access. Early feature influence. Premium pricing engine.
                        Built for real flippers, not theory.
                    </div>
                    <div class="actions" style="margin-top:22px;">
                        <a class="btn btnPrimary" href="/subscribe">Subscribe with Stripe</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request) or is_premium(request):
        return RedirectResponse("/app", status_code=303)

    return HTMLResponse("""
    <html>
    <head>
        <title>CLAMS Access</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body {
                margin: 0;
                font-family: Segoe UI, Arial, sans-serif;
                background: linear-gradient(135deg, #111922, #162735);
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .panel {
                width: 100%;
                max-width: 420px;
                background: rgba(10, 18, 24, 0.92);
                border: 1px solid #294151;
                border-radius: 22px;
                padding: 30px;
                box-shadow: 0 0 30px rgba(0,0,0,0.28);
            }
            .title {
                font-size: 34px;
                font-weight: 900;
                margin-bottom: 8px;
                background: linear-gradient(90deg, #00cc66, #00aaff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            input {
                width: 100%;
                padding: 14px;
                border-radius: 12px;
                border: 1px solid #314a5b;
                background: #0d151d;
                color: white;
                margin-top: 16px;
                box-sizing: border-box;
            }
            button, .subBtn {
                width: 100%;
                padding: 14px;
                border-radius: 12px;
                border: none;
                font-weight: 800;
                margin-top: 16px;
                cursor: pointer;
            }
            button {
                background: #00cc66;
                color: #08140d;
            }
            .subBtn {
                display: block;
                background: #14202b;
                color: white;
                text-decoration: none;
                text-align: center;
            }
            .small {
                color: #b8c7d0;
                margin-top: 12px;
                line-height: 1.5;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="panel">
            <div class="title">CLAMS</div>
            <div>Premium reseller access</div>
            <form method="post" action="/login">
                <input type="password" name="password" required placeholder="Founder password" />
                <button type="submit">Enter Dashboard</button>
            </form>
            <a class="subBtn" href="/subscribe">Join Founder Beta with Stripe</a>
            <div class="small">
                If you're not on the founder password, use the Stripe button to subscribe.
            </div>
        </div>
    </body>
    </html>
    """)


@app.post("/login")
def login(password: str = Form(...)):
    if password == CLAMS_PASSWORD:
        return login_success_response("/app")
    return RedirectResponse("/login", status_code=303)


@app.get("/logout")
def logout():
    return logout_response("/")


@app.get("/subscribe")
def subscribe():
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return RedirectResponse("/login", status_code=303)

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{SITE_URL}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{SITE_URL}/login",
        allow_promotion_codes=True,
    )
    return RedirectResponse(session.url, status_code=303)


@app.get("/subscribe/success")
def subscribe_success(session_id: str = ""):
    if not STRIPE_SECRET_KEY or not session_id:
        return RedirectResponse("/login", status_code=303)

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session and session.get("status") == "complete":
            return premium_success_response("/app")
    except Exception:
        pass

    return RedirectResponse("/login", status_code=303)


@app.get("/billing")
def billing_portal(request: Request):
    if not is_premium(request):
        return RedirectResponse("/login", status_code=303)

    if not STRIPE_SECRET_KEY:
        return RedirectResponse("/app", status_code=303)

    customer_id = request.cookies.get("clams_stripe_customer", "")
    if not customer_id:
        return RedirectResponse("/app", status_code=303)

    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{SITE_URL}/app"
        )
        return RedirectResponse(portal.url, status_code=303)
    except Exception:
        return RedirectResponse("/app", status_code=303)


@app.get("/app", response_class=HTMLResponse)
def app_home(request: Request):
    if not (is_authenticated(request) or is_premium(request)):
        return RedirectResponse("/login", status_code=303)
    return render_page()


@app.post("/app", response_class=HTMLResponse)
def analyze(
    request: Request,
    query: str = Form(...),
    condition: str = Form("A"),
    profit: float = Form(0.40),
    market: str = Form("facebook"),
):
    if not (is_authenticated(request) or is_premium(request)):
        return RedirectResponse("/login", status_code=303)

    sold_prices, active_prices, sold_items = get_market_data(query)

    if not sold_prices:
        return render_page(
            error="No comps found.",
            query=query,
            condition=condition,
            profit=profit,
            market=market,
        )

    analysis = analyze_market(
        sold_prices=sold_prices,
        active_prices=active_prices,
        condition=condition,
        profit=profit,
        local_factor=0.80,
    )

    return render_page(
        query=query,
        analysis=analysis,
        sold_items=sold_items,
        condition=condition,
        profit=profit,
        market=market,
        premium_active=is_premium(request),
    )


@app.post("/ai-enhance")
async def ai_enhance(request: Request):
    data = await request.json()
    query = data.get("query", "")
    text = data.get("text", "")
    mode = data.get("mode", "description")

    if not client:
        return JSONResponse({"content": text})

    try:
        prompt = f"""
Improve this marketplace listing {mode}.
Keep it short, clear, persuasive, and reseller-friendly.

Item: {query}

Current {mode}:
{text}
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return JSONResponse({"content": response.choices[0].message.content})
    except Exception:
        return JSONResponse({"content": text})


@app.get("/health")
def health():
    return {"status": "ok"}


def render_page(
    query: str = "",
    analysis: dict | None = None,
    sold_items: list | None = None,
    error: str | None = None,
    condition: str = "A",
    profit: float = 0.40,
    market: str = "facebook",
    premium_active: bool = False,
):
    sold_items = sold_items or []

    q = safe_text(query)
    error_block = f"<div class='errorBox'>{safe_text(error)}</div>" if error else ""

    primary_image = ""
    primary_title = ""
    primary_link = "#"

    if sold_items:
        primary_image = safe_text(sold_items[0].get("image", ""))
        primary_title = safe_text(sold_items[0].get("title", ""))
        primary_link = safe_text(sold_items[0].get("link", "#"))

    listing = build_listing_pack(query, analysis, condition, market)

    sell_target = analysis["sell_target"] if analysis else 0
    max_buy = analysis["max_buy"] if analysis else 0
    fast_cash = analysis["fast_cash"] if analysis else 0
    market_price = analysis["market_price"] if analysis else 0
    hold_price = analysis["hold_price"] if analysis else 0
    sold_median = analysis["sold_median"] if analysis else 0
    active_median = analysis["active_median"] if analysis else 0
    confidence = analysis["confidence"] if analysis else 0
    liquidity_label = analysis["liquidity_label"] if analysis else "-"
    liquidity_score = analysis["liquidity_score"] if analysis else 0
    risk_level = analysis["risk_level"] if analysis else "-"
    market_balance = analysis["market_balance"] if analysis else "-"
    price_consistency = analysis["price_consistency"] if analysis else "-"
    buy_score = analysis["buy_score"] if analysis else 0
    buy_label = analysis["buy_label"] if analysis else "-"
    sold_count = analysis["sold_count"] if analysis else 0
    active_count = analysis["active_count"] if analysis else 0

    market = (market or "facebook").lower()
    selected_market = {
        "facebook": "",
        "ebay": "",
        "mercari": "",
        "offerup": "",
        "nextdoor": "",
    }
    if market not in selected_market:
        market = "facebook"
    selected_market[market] = "selected"

    premium_banner = """
    <div class="statusPill">Founder / Premium Active</div>
    """ if premium_active else """
    <div class="statusPill statusWarn">Founder Password Access</div>
    """

    sold_gallery = ""
    if sold_items:
        cards = []
        for item in sold_items[:6]:
            item_title = safe_text(item.get("title", ""))
            item_img = safe_text(item.get("image", ""))
            item_link = safe_text(item.get("link", "#"))
            item_price = format_money(item.get("price", 0))

            cards.append(f"""
            <a class="compCard" href="{item_link}" target="_blank">
                <img src="{item_img}" />
                <div class="compTitle">{item_title}</div>
                <div class="compPrice">{item_price}</div>
            </a>
            """)
        sold_gallery = "<div class='compGrid'>" + "".join(cards) + "</div>"

    card_block = card_summary_block(query)

    return HTMLResponse(f"""
    <html>
    <head>
        <title>CLAMS Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body {{
                margin: 0;
                font-family: Segoe UI, Arial, sans-serif;
                background: linear-gradient(135deg, #182632, #213746);
                color: white;
            }}
            .layout {{
                display: grid;
                grid-template-columns: 1.8fr 1fr;
                gap: 22px;
                padding: 22px;
            }}
            @media (max-width: 900px) {{
                .layout {{
                    grid-template-columns: 1fr;
                }}
            }}
            .card {{
                background: rgba(10, 18, 24, 0.88);
                border: 1px solid #294151;
                border-radius: 22px;
                padding: 22px;
                box-shadow: 0 0 24px rgba(0,0,0,0.22);
                margin-bottom: 22px;
            }}
            .title {{
                font-size: 42px;
                font-weight: 900;
                background: linear-gradient(90deg, #00cc66, #00aaff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .subtitle {{
                color: #ccdae2;
                margin-top: 6px;
            }}
            .row {{
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
            }}
            .statusPill {{
                display: inline-block;
                background: #102a1d;
                color: #73f0aa;
                border: 1px solid #1f7148;
                padding: 9px 14px;
                border-radius: 999px;
                font-weight: 700;
                margin-top: 14px;
            }}
            .statusWarn {{
                background: #2b2110;
                color: #ffd77a;
                border-color: #856519;
            }}
            form input, form select {{
                background: #0d151d;
                color: white;
                border: 1px solid #314a5b;
                border-radius: 12px;
                padding: 14px;
                min-width: 180px;
            }}
            form button, .actionBtn {{
                background: #00cc66;
                color: #07140d;
                border: none;
                border-radius: 12px;
                padding: 14px 18px;
                font-weight: 800;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
            }}
            .actionBtn.secondary {{
                background: #14202b;
                color: white;
                border: 1px solid #314a5b;
            }}
            .metricsGrid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 14px;
                margin-top: 16px;
            }}
            .metric {{
                background: #101922;
                border: 1px solid #2d4352;
                border-radius: 16px;
                padding: 16px;
            }}
            .metricLabel {{
                color: #b5c6cf;
                font-size: 13px;
                margin-bottom: 8px;
            }}
            .metricValue {{
                font-size: 24px;
                font-weight: 900;
            }}
            .sectionTitle {{
                font-size: 22px;
                font-weight: 800;
                margin-bottom: 12px;
            }}
            .heroImage {{
                width: 100%;
                max-width: 320px;
                border-radius: 18px;
                display: block;
                margin-bottom: 14px;
            }}
            .scoreWrap {{
                margin-top: 12px;
            }}
            .scoreBar {{
                width: 100%;
                background: #0d151d;
                border-radius: 999px;
                overflow: hidden;
                height: 20px;
                border: 1px solid #314a5b;
            }}
            .scoreFill {{
                height: 100%;
                background: linear-gradient(90deg, #ff5b5b, #ffd05a, #00cc66);
                width: {buy_score}%;
            }}
            .scoreText {{
                margin-top: 10px;
                font-weight: 800;
                color: #e8f2f7;
            }}
            .motivation {{
                line-height: 1.8;
                color: #dfe9ef;
                font-size: 16px;
            }}
            .field {{
                background: #0f151c;
                border: 1px solid #2c4050;
                border-radius: 14px;
                padding: 14px;
                white-space: pre-wrap;
                min-height: 90px;
            }}
            .errorBox {{
                background: #311719;
                border: 1px solid #8a363a;
                color: #ffb8b8;
                padding: 14px;
                border-radius: 14px;
                margin-top: 16px;
            }}
            .compGrid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 14px;
                margin-top: 14px;
            }}
            .compCard {{
                background: #101922;
                border: 1px solid #2d4352;
                border-radius: 14px;
                padding: 10px;
                color: white;
                text-decoration: none;
            }}
            .compCard img {{
                width: 100%;
                border-radius: 12px;
                margin-bottom: 8px;
            }}
            .compTitle {{
                font-size: 13px;
                color: #d7e3ea;
                line-height: 1.35;
                min-height: 52px;
            }}
            .compPrice {{
                margin-top: 8px;
                font-weight: 900;
                color: #72efaa;
            }}
        </style>
        <script>
            async function enhanceField(id, mode) {{
                const el = document.getElementById(id);
                const text = el.innerText;
                const query = document.getElementById("query").value;

                const res = await fetch("/ai-enhance", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{
                        query: query,
                        text: text,
                        mode: mode
                    }})
                }});

                const data = await res.json();
                el.innerText = data.content;
            }}

            function copyField(id) {{
                const txt = document.getElementById(id).innerText;
                navigator.clipboard.writeText(txt);
            }}

            function updatePoster() {{
                const q = document.getElementById("query").value || "";
                const fastCash = "{format_money(fast_cash)}";
                const marketPrice = "{format_money(market_price)}";
                const holdPrice = "{format_money(hold_price)}";

                document.getElementById("posterTitle").innerText = q || "Item";
                document.getElementById("posterFast").innerText = fastCash;
                document.getElementById("posterMarket").innerText = marketPrice;
                document.getElementById("posterHold").innerText = holdPrice;
            }}

            window.onload = updatePoster;
        </script>
    </head>
    <body>
        <div class="layout">
            <div>
                <div class="card">
                    <div class="title">CLAMS</div>
                    <div class="subtitle">Resale Intelligence Dashboard</div>
                    {premium_banner}
                    {error_block}

                    <form method="post" action="/app" style="margin-top:18px;">
                        <div class="row">
                            <input id="query" name="query" value="{q}" placeholder="Search item..." required />
                            <select name="condition">
                                <option value="A" {"selected" if condition == "A" else ""}>Condition A</option>
                                <option value="B" {"selected" if condition == "B" else ""}>Condition B</option>
                                <option value="C" {"selected" if condition == "C" else ""}>Condition C</option>
                                <option value="Parts" {"selected" if condition == "Parts" else ""}>Parts</option>
                            </select>
                            <input type="number" step="0.05" name="profit" value="{profit}" placeholder="Profit %" />
                            <select name="market">
                                <option value="facebook" {selected_market["facebook"]}>Facebook</option>
                                <option value="ebay" {selected_market["ebay"]}>eBay</option>
                                <option value="mercari" {selected_market["mercari"]}>Mercari</option>
                                <option value="offerup" {selected_market["offerup"]}>OfferUp</option>
                                <option value="nextdoor" {selected_market["nextdoor"]}>Nextdoor</option>
                            </select>
                            <button type="submit">Analyze</button>
                        </div>
                    </form>

                    <div class="row" style="margin-top:16px;">
                        <a class="actionBtn secondary" href="/billing">Billing Portal</a>
                        <a class="actionBtn secondary" href="/logout">Logout</a>
                    </div>
                </div>

                <div class="card">
                    <div class="sectionTitle">Pricing Core</div>
                    <div class="metricsGrid">
                        <div class="metric"><div class="metricLabel">Max Buy</div><div class="metricValue">{format_money(max_buy)}</div></div>
                        <div class="metric"><div class="metricLabel">Fast Cash</div><div class="metricValue">{format_money(fast_cash)}</div></div>
                        <div class="metric"><div class="metricLabel">Market Price</div><div class="metricValue">{format_money(market_price)}</div></div>
                        <div class="metric"><div class="metricLabel">Hold Price</div><div class="metricValue">{format_money(hold_price)}</div></div>
                        <div class="metric"><div class="metricLabel">Sold Median</div><div class="metricValue">{format_money(sold_median)}</div></div>
                        <div class="metric"><div class="metricLabel">Active Median</div><div class="metricValue">{format_money(active_median)}</div></div>
                    </div>
                </div>

                <div class="card">
                    <div class="sectionTitle">Decision Engine</div>
                    <div class="metricsGrid">
                        <div class="metric"><div class="metricLabel">Buy Score</div><div class="metricValue">{buy_score}/100</div></div>
                        <div class="metric"><div class="metricLabel">Buy Signal</div><div class="metricValue">{safe_text(buy_label)}</div></div>
                        <div class="metric"><div class="metricLabel">Liquidity</div><div class="metricValue">{safe_text(liquidity_label)} ({liquidity_score})</div></div>
                        <div class="metric"><div class="metricLabel">Risk</div><div class="metricValue">{safe_text(risk_level)}</div></div>
                        <div class="metric"><div class="metricLabel">Market Balance</div><div class="metricValue">{safe_text(market_balance)}</div></div>
                        <div class="metric"><div class="metricLabel">Consistency</div><div class="metricValue">{safe_text(price_consistency)}</div></div>
                        <div class="metric"><div class="metricLabel">Sold Count</div><div class="metricValue">{sold_count}</div></div>
                        <div class="metric"><div class="metricLabel">Active Count</div><div class="metricValue">{active_count}</div></div>
                        <div class="metric"><div class="metricLabel">Confidence</div><div class="metricValue">{confidence}</div></div>
                    </div>

                    <div class="scoreWrap">
                        <div class="scoreBar">
                            <div class="scoreFill"></div>
                        </div>
                        <div class="scoreText">Buy Score: {buy_score}/100 — {safe_text(buy_label)}</div>
                    </div>
                </div>

                <div class="card">
                    <div class="sectionTitle">Listing Generator</div>
                    <div class="row" style="margin-bottom:10px;">
                        <button class="actionBtn" type="button" onclick="copyField('titleField')">Copy Title</button>
                        <button class="actionBtn secondary" type="button" onclick="enhanceField('titleField','title')">AI Title</button>
                    </div>
                    <div id="titleField" class="field">{safe_text(listing["title"])}</div>

                    <div class="row" style="margin:18px 0 10px 0;">
                        <button class="actionBtn" type="button" onclick="copyField('descField')">Copy Description</button>
                        <button class="actionBtn secondary" type="button" onclick="enhanceField('descField','description')">AI Description</button>
                    </div>
                    <div id="descField" class="field">{safe_text(listing["description"])}</div>

                    <div class="row" style="margin:18px 0 10px 0;">
                        <button class="actionBtn" type="button" onclick="copyField('cellField')">Copy Cell Version</button>
                    </div>
                    <div id="cellField" class="field">{safe_text(listing["cell_description"])}</div>
                </div>

                {card_block}

                <div class="card">
                    <div class="sectionTitle">Recent Comps</div>
                    {sold_gallery if sold_gallery else "<div>No comp images yet.</div>"}
                </div>
            </div>

            <div>
                <div class="card">
                    <div class="sectionTitle">Primary Comp</div>
                    <a href="{primary_link}" target="_blank">
                        <img class="heroImage" src="{primary_image}" />
                    </a>
                    <div style="font-weight:700; line-height:1.5;">{primary_title}</div>
                </div>

                <div class="card">
                    <div class="sectionTitle">Quick Poster</div>
                    <div class="field" style="text-align:center;">
                        <div style="font-size:24px;font-weight:900;margin-bottom:10px;" id="posterTitle">{q if q else "Item"}</div>
                        <div><b>Fast Cash:</b> <span id="posterFast">{format_money(fast_cash)}</span></div>
                        <div><b>Market:</b> <span id="posterMarket">{format_money(market_price)}</span></div>
                        <div><b>Hold:</b> <span id="posterHold">{format_money(hold_price)}</span></div>
                    </div>
                </div>

                <div class="card">
                    <div class="sectionTitle">Operator Mindset</div>
                    <div class="motivation">
                        Revenue favors action.<br>
                        Clarity beats emotion.<br>
                        Inventory is trapped cash until it moves.<br>
                        Buy disciplined. Post fast. Repeat.<br>
                        You are not guessing anymore.
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)