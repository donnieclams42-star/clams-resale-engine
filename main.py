# ===============================
# CLAMS Engine – Posting FINAL LOCKED
# Marketplace intact + Generator intact
# YouTube restored + Volume + Lighter UI
# ===============================

import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from ebay import get_market_data
from pricing import analyze_market
from auth import is_authenticated, login_success_response, logout_response
from openai import OpenAI

app = FastAPI()
client = OpenAI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "changeme")


# ---------------- AUTH ---------------- #

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/app", status_code=303)

    return """
    <html><body style="background:#111;color:white;font-family:Segoe UI;text-align:center;padding-top:150px;">
    <h2>CLAMS Access</h2>
    <form method="post" action="/login">
    <input type="password" name="password" required style="padding:12px;border-radius:8px;border:none;width:250px;">
    <br><br>
    <button type="submit" style="padding:12px 30px;border:none;border-radius:8px;background:#00cc66;font-weight:bold;color:black;">
    Enter</button></form></body></html>
    """


@app.post("/login")
def login(password: str = Form(...)):
    if password == CLAMS_PASSWORD:
        return login_success_response("/app")
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout():
    return logout_response("/")


# ---------------- MAIN ---------------- #

@app.get("/app", response_class=HTMLResponse)
def app_home(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return render_page()


@app.post("/app", response_class=HTMLResponse)
def analyze(request: Request, query: str = Form(...),
            condition: str = Form("A"),
            profit: float = Form(0.40)):

    if not is_authenticated(request):
        return RedirectResponse("/", status_code=303)

    sold_prices, active_prices, sold_items = get_market_data(query)

    if not sold_prices:
        return render_page(error="No comps found.", query=query)

    analysis = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit,
        0.80
    )

    return render_page(
        query=query,
        analysis=analysis,
        sold_items=sold_items,
        condition=condition,
        profit=profit
    )


# ---------------- AI ---------------- #

@app.post("/ai-enhance")
async def ai_enhance(request: Request):
    data = await request.json()
    query = data.get("query", "")
    text = data.get("text", "")
    mode = data.get("mode", "description")

    try:
        prompt = f"""
        Improve this marketplace listing {mode}.
        Keep it clean, high converting, platform appropriate.
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

    except:
        return JSONResponse({"content": text})


# ---------------- RENDER ---------------- #

def render_page(query="", analysis=None, sold_items=None,
                error=None, condition="A", profit=0.40):

    sell_price = analysis['sell_target'] if analysis else 0
    max_buy = analysis['max_buy'] if analysis else 0
    profit_percent = round(profit * 100, 1)

    primary_image = ""
    primary_title = ""
    primary_link = ""

    if sold_items:
        primary_image = sold_items[0].get("image", "")
        primary_title = sold_items[0].get("title", "")
        primary_link = sold_items[0].get("link", "#")

    error_block = f"<div style='color:#ff6b6b;margin:15px 0;'>{error}</div>" if error else ""

    return f"""
<html>
<head>
<title>CLAMS Engine</title>

<style>
body {{
    margin:0;
    font-family:Segoe UI;
    background:linear-gradient(135deg,#1e2a33,#223544);
    color:white;
}}

.layout {{ display:flex; }}
.main {{ width:75%; padding:40px; }}
.sidebar {{ width:25%; background:#18242d; padding:40px; }}

.header {{
    font-size:42px;
    font-weight:900;
    background:linear-gradient(90deg,#00cc66,#00aaff);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}}

.card {{
    background:#1a1f26;
    padding:20px;
    border-radius:18px;
    margin-bottom:25px;
    box-shadow:0 0 20px rgba(0,0,0,0.5);
}}

.toggle {{ background:#222;color:white;padding:6px 12px;margin:4px;border-radius:8px; }}
.toggle.active {{ background:#00cc66;color:black; }}

.field {{
    background:#0f1318;
    padding:12px;
    border-radius:10px;
    white-space:pre-wrap;
    margin-top:10px;
}}

.copyBtn {{
    background:#00cc66;
    color:black;
    padding:6px 10px;
    border-radius:8px;
    margin:4px;
}}

.green {{ color:#00cc66;font-weight:bold; }}
.red {{ color:#ff4d4d;font-weight:bold; }}
</style>

<script src="https://www.youtube.com/iframe_api"></script>

<script>

let activeMarket = "facebook";
let activeFormat = "cell";
let player;

function onYouTubeIframeAPIReady() {{
    player = new YT.Player('ytplayer');
}}

function toggleMute() {{
    if (player) {{
        if (player.isMuted()) {{
            player.unMute();
        }} else {{
            player.mute();
        }}
    }}
}}

function setVolume(v) {{
    if (player) {{
        player.setVolume(v);
    }}
}}

function setMarket(m) {{
    activeMarket = m;
    document.querySelectorAll(".marketBtn")
        .forEach(b => b.classList.remove("active"));
    document.getElementById(m).classList.add("active");
    generateContent();
}}

function setFormat(f) {{
    activeFormat = f;
    document.querySelectorAll(".formatBtn")
        .forEach(b => b.classList.remove("active"));
    document.getElementById(f + "Btn").classList.add("active");
    generateContent();
}}

function generateContent() {{
    let q = "{query}";
    let price = {sell_price};

    let title = q;
    let desc = q + "\\nPrice: $" + price;

    document.getElementById("titleField").innerText = title;
    document.getElementById("descField").innerText = desc;
}}

function enhanceField(id, mode) {{
    fetch("/ai-enhance", {{
        method:"POST",
        headers:{{"Content-Type":"application/json"}},
        body:JSON.stringify({{
            query:"{query}",
            text:document.getElementById(id).innerText,
            mode:mode
        }})
    }})
    .then(res=>res.json())
    .then(data=>document.getElementById(id).innerText = data.content);
}}

function copyField(id) {{
    navigator.clipboard.writeText(document.getElementById(id).innerText);
}}

function calculateNet() {{
    let sell = {sell_price};
    let costPaid = parseFloat(document.getElementById("costPaid").value) || 0;
    let realProfit = sell - costPaid;

    let rp = document.getElementById("realProfit");
    rp.innerText = realProfit.toFixed(2);
    rp.className = realProfit >= 0 ? "green" : "red";
}}

window.onload = function() {{
    setMarket("facebook");
    setFormat("cell");
}};
</script>
</head>

<body>

<div class="layout">

<div class="main">

<div class="header">CLAMS Engine</div>

<form method="post" action="/app">
<input name="query" value="{query}" placeholder="Search item..." required>
<input type="number" step="0.05" name="profit" value="{profit}">
<button type="submit">Analyze</button>
</form>

{error_block}

<div class="card">
Profit Target: {profit_percent}%<br>
Sell Target: ${sell_price}
</div>

<div class="card">
<a href="{primary_link}" target="_blank">
<img src="{primary_image}" style="max-width:300px;border-radius:14px;">
</a>
<div style="margin-top:10px;font-weight:bold;">{primary_title}</div>
</div>

<div class="card">
<h3>Marketplace</h3>

<button id="facebook" class="toggle marketBtn active" onclick="setMarket('facebook')">Facebook</button>
<button id="ebay" class="toggle marketBtn" onclick="setMarket('ebay')">eBay</button>
<button id="mercari" class="toggle marketBtn" onclick="setMarket('mercari')">Mercari</button>
<button id="offerup" class="toggle marketBtn" onclick="setMarket('offerup')">OfferUp</button>
<button id="nextdoor" class="toggle marketBtn" onclick="setMarket('nextdoor')">Nextdoor</button>

<br><br>

Cost Paid:
<input type="number" id="costPaid" step="0.01" oninput="calculateNet()">

<br><br>

Real Profit: $<span id="realProfit">0.00</span>
</div>

<div class="card">
<h3>Format</h3>

<button id="cellBtn" class="toggle formatBtn active" onclick="setFormat('cell')">📱 Cell Friendly</button>
<button id="fullBtn" class="toggle formatBtn" onclick="setFormat('full')">🧾 Full Professional</button>

<h4>Title</h4>
<div id="titleField" class="field"></div>
<button class="copyBtn" onclick="copyField('titleField')">Copy Title</button>
<button class="copyBtn" onclick="enhanceField('titleField','title')">AI Enhance Title</button>

<h4>Description</h4>
<div id="descField" class="field"></div>
<button class="copyBtn" onclick="copyField('descField')">Copy Description</button>
<button class="copyBtn" onclick="enhanceField('descField','description')">AI Enhance Description</button>

</div>

</div>

<div class="sidebar">

<div style="font-size:28px;font-weight:bold;margin-bottom:30px;">
Revenue Favors Action.<br>
Clarity Beats Emotion.<br>
Cash Flow = Freedom.<br>
Execute.
</div>

<div class="card" style="background:#111;">
<h3 style="margin-top:0;">Focus Playlist</h3>

<iframe id="ytplayer"
width="100%"
height="200"
src="https://www.youtube.com/embed/videoseries?list=PL09-WNqi3rR43uLLwHzAj2XLfjKrwC8ru&enablejsapi=1"
frameborder="0"
allow="autoplay; encrypted-media"
allowfullscreen>
</iframe>

<br>

<button class="copyBtn" onclick="toggleMute()">🔇 Mute / Unmute</button>

<br><br>

Volume:
<input type="range" min="0" max="100" value="50" onchange="setVolume(this.value)">

</div>

</div>

</div>

</body>
</html>
"""