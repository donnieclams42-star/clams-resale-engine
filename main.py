import os
from html import escape

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ebay import get_market_data
from pricing import analyze_market

load_dotenv()

app = FastAPI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "clams")
STRIPE_LINK = os.getenv("STRIPE_LINK", "").strip()


def badge_class(label: str) -> str:
    label = (label or "").upper()
    if any(x in label for x in ["STRONG", "LOW", "FAST", "GOOD", "STEAL", "GREAT", "RISING", "VERY HOT"]):
        return "good"
    if any(x in label for x in ["MODERATE", "BALANCED", "WEAK", "MEDIUM", "STABLE", "BORDERLINE"]):
            return "warn"
    return "bad"


def selected_attr(current: str, value: str) -> str:
    return "selected" if str(current) == str(value) else ""


def fmt_money(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def fmt_plain(value) -> str:
    if value is None:
        return "N/A"
    return str(value)


def human_error_message(error_code: str) -> str:
    if not error_code:
        return ""
    if error_code == "RATE_LIMITED":
        return "eBay temporarily rate-limited this app. CLAMS is working, but eBay is throttling requests right now. Try again after the rate-limit window resets, or avoid repeating the same search back-to-back."
    if error_code == "NO_RESULTS":
        return "No market data came back for that search. Try a broader keyword or a cleaner product name."
    if error_code == "EBAY_ENV_MISSING":
        return "eBay credentials are not loaded locally."
    if error_code.startswith("BROWSE_HTTP_"):
        return f"eBay search returned an API error: {error_code}."
    if error_code.startswith("TOKEN_"):
        return f"Token error: {error_code}."
    return f"Search error: {error_code}"


def render_dashboard(
    query="",
    condition="A",
    profit="40",
    local_factor="85",
    asking_price="",
    data=None,
    image="",
    listing_title="",
    listing_link="",
    note="",
):
    q = escape(query or "")
    condition = escape(condition or "A")
    profit = escape(str(profit or "40"))
    local_factor = escape(str(local_factor or "85"))
    asking_price = escape(str(asking_price or ""))
    listing_title_safe = escape(listing_title or "")
    listing_link_safe = escape(listing_link or "")
    note_safe = escape(note or "")

    stripe_cta = ""
    if STRIPE_LINK:
        stripe_cta = f'<a class="cta-secondary" href="{escape(STRIPE_LINK)}" target="_blank">Founder Pricing — $19/month</a>'

    result_html = ""
    if data:
        buy_badge = badge_class(data["buy_label"])
        risk_badge = badge_class(data["risk_level"])
        flip_badge = badge_class(data["flip_speed"])
        sniper_badge = badge_class(data["sniper_label"])
        trend_badge = badge_class(data["trend_label"])
        sell_through_badge = badge_class(data["sell_through_label"])

        listing_block = ""
        if image or listing_title or listing_link:
            listing_block = f"""
            <div class="listing-card">
                <div class="listing-image-wrap">
                    {"<img class='listing-image' src='" + escape(image) + "' alt='listing image'>" if image else "<div class='listing-image placeholder'>No image</div>"}
                </div>
                <div class="listing-info">
                    <div class="eyebrow">REFERENCE LISTING</div>
                    <h3>{listing_title_safe if listing_title_safe else "Market reference"}</h3>
                    <p class="muted">Current pulled listing for visual comp reference.</p>
                    {f"<a class='listing-link' href='{listing_link_safe}' target='_blank'>Open Listing ↗</a>" if listing_link_safe else ""}
                </div>
            </div>
            """

        result_html = f"""
        <section class="hero-results">
            <div class="hero-left">
                <div class="eyebrow">DECISION PANEL</div>
                <h2>{escape(data["buy_label"])}</h2>
                <p class="hero-copy">
                    Flip speed is <span class="inline-pill {flip_badge}">{escape(data["flip_speed"])}</span>,
                    risk is <span class="inline-pill {risk_badge}">{escape(data["risk_level"])}</span>,
                    and liquidity is trending <strong>{escape(data["liquidity_label"])}</strong>.
                </p>
            </div>
            <div class="hero-right">
                <div class="score-ring">
                    <div class="score-ring-inner">
                        <span class="score-number">{data["buy_score"]}</span>
                        <span class="score-label">Buy Score</span>
                    </div>
                </div>
            </div>
        </section>

        <section class="stats-grid">
            <div class="stat-card glow-blue">
                <div class="stat-label">Sell Target</div>
                <div class="stat-value">{fmt_money(data["sell_target"])}</div>
                <div class="stat-sub">Target resale number</div>
            </div>

            <div class="stat-card glow-green">
                <div class="stat-label">Max Buy</div>
                <div class="stat-value">{fmt_money(data["max_buy"])}</div>
                <div class="stat-sub">Ceiling buy price</div>
            </div>

            <div class="stat-card glow-gold">
                <div class="stat-label">Estimated Margin</div>
                <div class="stat-value">{fmt_money(data["estimated_margin"])}</div>
                <div class="stat-sub">Target spread</div>
            </div>

            <div class="stat-card glow-purple">
                <div class="stat-label">ROI</div>
                <div class="stat-value">{data["roi_percent"]}%</div>
                <div class="stat-sub">Projected return</div>
            </div>
        </section>

        <section class="pricing-bands">
            <div class="band band-fast">
                <div class="band-top">⚡ Fast Cash</div>
                <div class="band-price">{fmt_money(data["fast_cash"])}</div>
                <div class="band-copy">Move it fast / strongest cash-speed lane</div>
            </div>

            <div class="band band-market">
                <div class="band-top">📊 Market Price</div>
                <div class="band-price">{fmt_money(data["market_price"])}</div>
                <div class="band-copy">Balanced competitive lane</div>
            </div>

            <div class="band band-hold">
                <div class="band-top">💎 Hold Price</div>
                <div class="band-price">{fmt_money(data["hold_price"])}</div>
                <div class="band-copy">Best patience / upside lane</div>
            </div>
        </section>

        <section class="intel-grid">
            <div class="intel-card">
                <div class="intel-title">Market Health</div>
                <div class="intel-row"><span>Demand</span><strong>{escape(data["demand_label"])}</strong></div>
                <div class="intel-row"><span>Market Balance</span><strong>{escape(data["market_balance"])}</strong></div>
                <div class="intel-row"><span>Liquidity</span><strong>{escape(data["liquidity_label"])}</strong></div>
                <div class="intel-row"><span>Flip Speed</span><strong>{escape(data["flip_speed"])}</strong></div>
            </div>

            <div class="intel-card">
                <div class="intel-title">Price Behavior</div>
                <div class="intel-row"><span>Consistency</span><strong>{escape(data["price_consistency"])}</strong></div>
                <div class="intel-row"><span>Volatility</span><strong>{data["volatility_percent"]}%</strong></div>
                <div class="intel-row"><span>Price Spread</span><strong>{fmt_money(data["spread_low_to_high"])}</strong></div>
                <div class="intel-row"><span>Trend</span><strong>{escape(data["trend_label"])}</strong></div>
                <div class="intel-row"><span>Risk Level</span><strong>{escape(data["risk_level"])}</strong></div>
            </div>

            <div class="intel-card">
                <div class="intel-title">Comp Snapshot</div>
                <div class="intel-row"><span>Sold Median</span><strong>{fmt_money(data["sold_median"])}</strong></div>
                <div class="intel-row"><span>Sold Low</span><strong>{fmt_money(data["sold_low"])}</strong></div>
                <div class="intel-row"><span>Sold High</span><strong>{fmt_money(data["sold_high"])}</strong></div>
                <div class="intel-row"><span>Active Median</span><strong>{fmt_money(data["active_median"])}</strong></div>
            </div>

            <div class="intel-card">
                <div class="intel-title">Decision Inputs</div>
                <div class="intel-row"><span>Sold Count</span><strong>{data["sold_count"]}</strong></div>
                <div class="intel-row"><span>Active Count</span><strong>{data["active_count"]}</strong></div>
                <div class="intel-row"><span>Supply Ratio</span><strong>{fmt_plain(data["supply_ratio"])}</strong></div>
                <div class="intel-row"><span>Local Factor</span><strong>{data["local_factor_percent"]}%</strong></div>
                <div class="intel-row"><span>Condition Impact</span><strong>{data["condition_impact_percent"]}%</strong></div>
            </div>
        </section>

        {listing_block}
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>CLAMS Resale Engine</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {{
            --bg-1:#07111f;
            --bg-2:#0b1728;
            --panel:#122033;
            --panel-2:#18283f;
            --line:rgba(255,255,255,.08);
            --text:#e8eef8;
            --muted:#9fb0c7;
            --blue:#5ea3ff;
            --green:#34d399;
            --gold:#fbbf24;
            --purple:#a78bfa;
            --cyan:#22d3ee;
            --red:#f87171;
        }}
        * {{ box-sizing:border-box; }}
        body {{
            margin:0;
            font-family:Arial, Helvetica, sans-serif;
            color:var(--text);
            background:
                radial-gradient(circle at top left, rgba(94,163,255,.10), transparent 28%),
                radial-gradient(circle at top right, rgba(52,211,153,.08), transparent 24%),
                linear-gradient(180deg, var(--bg-1), var(--bg-2));
        }}
        .wrap {{
            max-width:1400px;
            margin:0 auto;
            padding:28px 22px 60px;
        }}
        .topbar {{
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:20px;
            margin-bottom:28px;
        }}
        .brand h1 {{
            margin:0;
            font-size:34px;
        }}
        .brand p {{
            margin:8px 0 0;
            color:var(--muted);
            font-size:15px;
        }}
        .top-actions {{
            display:flex;
            gap:10px;
            flex-wrap:wrap;
        }}
        .chip {{
            padding:10px 14px;
            border:1px solid var(--line);
            background:rgba(255,255,255,.03);
            border-radius:999px;
            color:var(--muted);
            font-size:13px;
        }}
        .cta-secondary {{
            display:inline-block;
            padding:14px 18px;
            border-radius:14px;
            background:rgba(255,255,255,.03);
            border:1px solid rgba(255,255,255,.08);
            color:#e8eef8;
            text-decoration:none;
            font-weight:bold;
        }}
        .hero {{
            background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.02));
            border:1px solid var(--line);
            border-radius:24px;
            padding:26px;
            box-shadow:0 18px 60px rgba(0,0,0,.28);
        }}
        .eyebrow {{
            color:var(--cyan);
            font-size:12px;
            letter-spacing:1.8px;
            font-weight:bold;
            margin-bottom:10px;
        }}
        .hero h2 {{
            margin:0;
            font-size:42px;
            line-height:1.05;
        }}
        .hero p {{
            color:var(--muted);
            font-size:16px;
            margin-top:12px;
            max-width:850px;
        }}
        .search-shell {{
            margin-top:24px;
            background:rgba(255,255,255,.025);
            border:1px solid var(--line);
            border-radius:20px;
            padding:18px;
        }}
        .search-form {{
            display:grid;
            grid-template-columns:2fr .9fr .9fr .9fr 1fr auto;
            gap:12px;
            align-items:end;
        }}
        .field {{
            display:flex;
            flex-direction:column;
            text-align:left;
            gap:8px;
        }}
        .field label {{
            font-size:12px;
            color:var(--muted);
            letter-spacing:.7px;
            font-weight:bold;
            text-transform:uppercase;
        }}
        .field input, .field select {{
            height:52px;
            border-radius:14px;
            border:1px solid rgba(255,255,255,.08);
            background:#0e1a2b;
            color:var(--text);
            padding:0 16px;
            font-size:16px;
            outline:none;
        }}
        .analyze-btn {{
            height:52px;
            padding:0 24px;
            border:none;
            border-radius:14px;
            background:linear-gradient(135deg, var(--blue), #3b82f6);
            color:white;
            font-size:16px;
            font-weight:bold;
            cursor:pointer;
        }}
        .helper-note {{
            margin-top:12px;
            color:var(--muted);
            font-size:13px;
        }}
        .error-banner {{
            margin-top:18px;
            padding:14px 16px;
            border-radius:16px;
            background:rgba(248,113,113,.10);
            color:#fecaca;
            border:1px solid rgba(248,113,113,.22);
            font-size:14px;
        }}
        .hero-results {{
            margin-top:28px;
            display:grid;
            grid-template-columns:1.4fr .8fr;
            gap:20px;
            align-items:center;
        }}
        .hero-left {{ text-align:left; }}
        .hero-right {{
            display:flex;
            justify-content:flex-end;
        }}
        .score-ring {{
            width:180px;
            height:180px;
            border-radius:50%;
            background:
                radial-gradient(circle at center, #0f1a2a 58%, transparent 59%),
                conic-gradient(var(--blue), var(--green), var(--gold), var(--blue));
            display:flex;
            align-items:center;
            justify-content:center;
        }}
        .score-ring-inner {{
            width:132px;
            height:132px;
            border-radius:50%;
            background:#0b1523;
            display:flex;
            flex-direction:column;
            align-items:center;
            justify-content:center;
            border:1px solid var(--line);
        }}
        .score-number {{
            font-size:44px;
            font-weight:bold;
        }}
        .score-label {{
            margin-top:6px;
            font-size:12px;
            color:var(--muted);
            text-transform:uppercase;
        }}
        .stats-grid {{
            margin-top:24px;
            display:grid;
            grid-template-columns:repeat(4, 1fr);
            gap:16px;
        }}
        .stat-card {{
            background:var(--panel);
            border:1px solid var(--line);
            border-radius:22px;
            padding:22px;
        }}
        .glow-blue {{ box-shadow:0 12px 28px rgba(94,163,255,.12); }}
        .glow-green {{ box-shadow:0 12px 28px rgba(52,211,153,.12); }}
        .glow-gold {{ box-shadow:0 12px 28px rgba(251,191,36,.12); }}
        .glow-purple {{ box-shadow:0 12px 28px rgba(167,139,250,.12); }}
        .stat-label {{
            color:var(--muted);
            font-size:13px;
            text-transform:uppercase;
            letter-spacing:1px;
        }}
        .stat-value {{
            margin-top:12px;
            font-size:32px;
            font-weight:bold;
        }}
        .stat-sub {{
            margin-top:8px;
            color:var(--muted);
            font-size:13px;
        }}
        .pricing-bands {{
            margin-top:20px;
            display:grid;
            grid-template-columns:repeat(3, 1fr);
            gap:16px;
        }}
        .band {{
            border-radius:22px;
            padding:22px;
            border:1px solid var(--line);
            background:var(--panel-2);
        }}
        .band-fast {{ box-shadow:0 10px 28px rgba(52,211,153,.12); }}
        .band-market {{ box-shadow:0 10px 28px rgba(94,163,255,.12); }}
        .band-hold {{ box-shadow:0 10px 28px rgba(167,139,250,.12); }}
        .band-top {{
            color:var(--muted);
            font-size:14px;
            text-transform:uppercase;
            letter-spacing:1px;
        }}
        .band-price {{
            margin-top:12px;
            font-size:36px;
            font-weight:bold;
        }}
        .band-copy {{
            margin-top:10px;
            color:var(--muted);
            font-size:14px;
        }}
        .intel-grid {{
            margin-top:20px;
            display:grid;
            grid-template-columns:repeat(4, 1fr);
            gap:16px;
        }}
        .intel-card {{
            background:rgba(255,255,255,.025);
            border:1px solid var(--line);
            border-radius:22px;
            padding:20px;
        }}
        .intel-title {{
            font-size:15px;
            font-weight:bold;
            margin-bottom:14px;
        }}
        .intel-row {{
            display:flex;
            justify-content:space-between;
            gap:10px;
            padding:10px 0;
            border-top:1px solid rgba(255,255,255,.06);
            color:var(--muted);
            font-size:14px;
        }}
        .intel-row:first-of-type {{
            border-top:none;
            padding-top:0;
        }}
        .intel-row strong {{
            color:var(--text);
            text-align:right;
        }}
        .listing-card {{
            margin-top:20px;
            display:grid;
            grid-template-columns:280px 1fr;
            gap:20px;
            background:rgba(255,255,255,.025);
            border:1px solid var(--line);
            border-radius:24px;
            padding:18px;
        }}
        .listing-image-wrap {{
            background:#0f1a2b;
            border:1px solid rgba(255,255,255,.06);
            border-radius:18px;
            display:flex;
            align-items:center;
            justify-content:center;
            min-height:240px;
            overflow:hidden;
        }}
        .listing-image {{
            width:100%;
            height:100%;
            object-fit:contain;
            display:block;
        }}
        .placeholder {{
            color:var(--muted);
            font-size:14px;
        }}
        .listing-info {{
            text-align:left;
            display:flex;
            flex-direction:column;
            justify-content:center;
        }}
        .listing-info h3 {{
            margin:0;
            font-size:24px;
        }}
        .muted {{
            color:var(--muted);
        }}
        .listing-link {{
            display:inline-block;
            margin-top:12px;
            color:#8ec5ff;
            text-decoration:none;
            font-weight:bold;
        }}
        .footer-note {{
            margin-top:18px;
            color:var(--muted);
            font-size:13px;
        }}
        @media (max-width: 1180px) {{
            .stats-grid, .intel-grid {{
                grid-template-columns:repeat(2, 1fr);
            }}
            .search-form {{
                grid-template-columns:1fr 1fr;
            }}
            .analyze-btn {{
                width:100%;
            }}
            .hero-results {{
                grid-template-columns:1fr;
            }}
            .hero-right {{
                justify-content:center;
            }}
        }}
        @media (max-width: 780px) {{
            .topbar {{
                flex-direction:column;
                align-items:flex-start;
            }}
            .stats-grid, .pricing-bands, .intel-grid {{
                grid-template-columns:1fr;
            }}
            .listing-card {{
                grid-template-columns:1fr;
            }}
            .search-form {{
                grid-template-columns:1fr;
            }}
            .hero h2 {{
                font-size:32px;
            }}
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="topbar">
            <div class="brand">
                <h1>CLAMS Resale Engine</h1>
                <p>Resale intelligence built for fast flips, better buys, and cleaner decisions.</p>
            </div>
            <div class="top-actions">
                <div class="chip">Desktop-first</div>
                <div class="chip">Fast-cash ready</div>
                <div class="chip">Founder Pricing $19/mo</div>
            </div>
        </div>

        <section class="hero">
            <div class="eyebrow">RESALE INTELLIGENCE PLATFORM</div>
            <h2>Search faster. Price cleaner. Buy smarter.</h2>
            <p>
                Built to blend fast sourcing decisions, market-signal clarity, and local-flip practicality.
                Type a product, set condition, lock your target margin, and CLAMS gives you an immediate buying lane.
            </p>

            <div class="top-actions" style="margin-top:18px;">
                {stripe_cta}
            </div>

            <div class="search-shell">
                <form class="search-form" method="post" action="/app">
                    <div class="field">
                        <label>Search Query</label>
                        <input name="query" value="{q}" placeholder="iphone 11, ps5 console, dewalt tile saw" required>
                    </div>

                    <div class="field">
                        <label>Condition</label>
                        <select name="condition">
                            <option value="A" {selected_attr(condition, "A")}>A / Excellent</option>
                            <option value="B" {selected_attr(condition, "B")}>B / Good</option>
                            <option value="C" {selected_attr(condition, "C")}>C / Rough</option>
                            <option value="Parts" {selected_attr(condition, "Parts")}>Parts / Repair</option>
                        </select>
                    </div>

                    <div class="field">
                        <label>Profit Target</label>
                        <select name="profit">
                            <option value="30" {selected_attr(profit, "30")}>30%</option>
                            <option value="40" {selected_attr(profit, "40")}>40%</option>
                            <option value="50" {selected_attr(profit, "50")}>50%</option>
                            <option value="60" {selected_attr(profit, "60")}>60%</option>
                        </select>
                    </div>

                    <div class="field">
                        <label>Local Factor</label>
                        <select name="local_factor">
                            <option value="75" {selected_attr(local_factor, "75")}>75%</option>
                            <option value="80" {selected_attr(local_factor, "80")}>80%</option>
                            <option value="85" {selected_attr(local_factor, "85")}>85%</option>
                            <option value="90" {selected_attr(local_factor, "90")}>90%</option>
                            <option value="100" {selected_attr(local_factor, "100")}>100%</option>
                        </select>
                    </div>

                    <div class="field">
                        <label>Asking Price</label>
                        <input name="asking_price" value="{asking_price}" placeholder="Optional ask price">
                    </div>

                    <button class="analyze-btn" type="submit">Analyze</button>
                </form>

                <div class="helper-note">
                    Defaulted for real-world flips: quick visual comps, buy ceiling, and pricing lanes that make sense in the field.
                </div>

                {f'<div class="error-banner">{note_safe}</div>' if note_safe else ''}
            </div>

            {result_html}
        </section>
    </div>
</body>
</html>
    """


@app.get("/", response_class=HTMLResponse)
def landing():
    stripe_button = ""
    if STRIPE_LINK:
        stripe_button = f'<a class="cta-secondary" href="{escape(STRIPE_LINK)}" target="_blank">Founder Pricing — $19/month</a>'

    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>CLAMS Resale Engine</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            margin:0;
            min-height:100vh;
            display:flex;
            align-items:center;
            justify-content:center;
            background:
                radial-gradient(circle at top left, rgba(94,163,255,.12), transparent 25%),
                radial-gradient(circle at bottom right, rgba(52,211,153,.10), transparent 25%),
                linear-gradient(180deg, #07111f, #0b1728);
            color:#e8eef8;
            font-family:Arial, Helvetica, sans-serif;
        }}
        .panel {{
            width:min(980px, 92vw);
            background:rgba(255,255,255,.03);
            border:1px solid rgba(255,255,255,.08);
            border-radius:28px;
            padding:42px;
            text-align:center;
            box-shadow:0 20px 70px rgba(0,0,0,.28);
        }}
        .eyebrow {{
            color:#22d3ee;
            font-size:12px;
            font-weight:bold;
            letter-spacing:1.8px;
        }}
        h1 {{
            margin:14px 0 0;
            font-size:50px;
            line-height:1.05;
        }}
        p {{
            color:#9fb0c7;
            max-width:760px;
            margin:16px auto 0;
            font-size:17px;
            line-height:1.6;
        }}
        .cta-row {{
            display:flex;
            justify-content:center;
            gap:12px;
            flex-wrap:wrap;
            margin-top:30px;
        }}
        .cta-primary, .cta-secondary {{
            display:inline-block;
            padding:15px 22px;
            border-radius:14px;
            text-decoration:none;
            font-weight:bold;
        }}
        .cta-primary {{
            background:linear-gradient(135deg, #5ea3ff, #3b82f6);
            color:white;
        }}
        .cta-secondary {{
            background:rgba(255,255,255,.03);
            border:1px solid rgba(255,255,255,.08);
            color:#e8eef8;
        }}
    </style>
</head>
<body>
    <div class="panel">
        <div class="eyebrow">FOUNDER RELEASE</div>
        <h1>CLAMS Resale Intelligence Engine</h1>
        <p>
            Built for resellers who need one clean screen to decide what to buy, what to pay,
            how fast it should move, and where the pricing lane really is.
        </p>

        <div class="cta-row">
            <a class="cta-primary" href="/login">Launch CLAMS</a>
            {stripe_button}
        </div>
    </div>
</body>
</html>
    """


@app.get("/login", response_class=HTMLResponse)
def login():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>CLAMS Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            margin:0;
            min-height:100vh;
            display:flex;
            align-items:center;
            justify-content:center;
            background:linear-gradient(180deg, #07111f, #0b1728);
            color:#e8eef8;
            font-family:Arial, Helvetica, sans-serif;
        }
        .card {
            width:min(420px, 92vw);
            background:rgba(255,255,255,.03);
            border:1px solid rgba(255,255,255,.08);
            border-radius:24px;
            padding:28px;
            box-shadow:0 18px 60px rgba(0,0,0,.28);
        }
        h2 { margin:0 0 10px; }
        p { color:#9fb0c7; font-size:14px; margin:0 0 18px; }
        input {
            width:100%;
            height:50px;
            border-radius:14px;
            border:1px solid rgba(255,255,255,.08);
            background:#0e1a2b;
            color:#e8eef8;
            padding:0 14px;
            font-size:16px;
            box-sizing:border-box;
        }
        button {
            margin-top:14px;
            width:100%;
            height:50px;
            border:none;
            border-radius:14px;
            background:linear-gradient(135deg, #5ea3ff, #3b82f6);
            color:white;
            font-size:16px;
            font-weight:bold;
            cursor:pointer;
        }
    </style>
</head>
<body>
    <form class="card" method="post" action="/login">
        <h2>CLAMS Login</h2>
        <p>Enter your password to open the resale engine.</p>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Enter</button>
    </form>
</body>
</html>
    """


@app.post("/login")
def login_post(password: str = Form(...)):
    if password == CLAMS_PASSWORD:
        resp = RedirectResponse("/app", status_code=303)
        resp.set_cookie("auth", "1", httponly=True, samesite="lax")
        return resp
    return HTMLResponse("<h3 style='font-family:Arial'>Wrong password</h3>")


@app.get("/app", response_class=HTMLResponse)
def dashboard(request: Request):
    if request.cookies.get("auth") != "1":
        return RedirectResponse("/login")

    return HTMLResponse(
        render_dashboard(
            condition="A",
            profit="40",
            local_factor="85",
            note="Start with something broad like iphone 11, ps5 console, or dewalt tile saw.",
        )
    )


@app.post("/app", response_class=HTMLResponse)
def analyze(
    request: Request,
    query: str = Form(...),
    condition: str = Form(...),
    profit: str = Form(...),
    local_factor: str = Form(...),
    asking_price: str = Form(""),
):
    if request.cookies.get("auth") != "1":
        return RedirectResponse("/login")

    print("SEARCH:", query)

    market = get_market_data(query)

    sold_prices = market["sold_prices"]
    active_prices = market["active_prices"]
    sold_items = market["items"]
    market_error = market["error"]

    if market_error:
        return HTMLResponse(
            render_dashboard(
                query=query,
                condition=condition,
                profit=profit,
                local_factor=local_factor,
                asking_price=asking_price,
                note=human_error_message(market_error),
            )
        )

    result = analyze_market(
        sold_prices=sold_prices,
        active_prices=active_prices,
        condition=condition,
        profit=float(profit) / 100.0,
        local_factor=float(local_factor) / 100.0,
        asking_price=asking_price,
    )

    if not result:
        return HTMLResponse(
            render_dashboard(
                query=query,
                condition=condition,
                profit=profit,
                local_factor=local_factor,
                asking_price=asking_price,
                note="Market analysis failed on that set. Try another search term.",
            )
        )

    image = ""
    listing_title = ""
    listing_link = ""

    if sold_items:
        first = sold_items[0]
        image = first.get("image", "") or ""
        listing_title = first.get("title", "") or ""
        listing_link = first.get("link", "") or ""

    return HTMLResponse(
        render_dashboard(
            query=query,
            condition=condition,
            profit=profit,
            local_factor=local_factor,
            asking_price=asking_price,
            data=result,
            image=image,
            listing_title=listing_title,
            listing_link=listing_link,
        )
    )