# ===============================
# CLAMS Engine – Launch Build
# ===============================

import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from ebay import get_market_data
from pricing import analyze_market
from auth import is_authenticated, login_success_response, logout_response
from cards import analyze_card, spread_analysis
from openai import OpenAI

app = FastAPI()
client = OpenAI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "changeme")


# ---------------- LANDING PAGE ---------------- #

@app.get("/", response_class=HTMLResponse)
def landing():

    return """
    <html>
    <head>
    <title>CLAMS – Resale Intelligence</title>

    <style>

    body{
        font-family:Segoe UI;
        background:#0f1720;
        color:white;
        text-align:center;
        padding:80px;
    }

    h1{
        font-size:52px;
        background:linear-gradient(90deg,#00cc66,#00aaff);
        -webkit-background-clip:text;
        -webkit-text-fill-color:transparent;
    }

    .box{
        max-width:850px;
        margin:auto;
        margin-top:60px;
    }

    .cta{
        margin-top:40px;
        padding:18px 40px;
        background:#00cc66;
        color:black;
        border:none;
        border-radius:10px;
        font-size:18px;
        font-weight:bold;
        cursor:pointer;
    }

    </style>
    </head>

    <body>

    <h1>CLAMS</h1>

    <h2>Resale Intelligence Engine</h2>

    <div class="box">

    <p>
    Stop guessing what to pay.
    </p>

    <p>
    CLAMS calculates max buy price, sell targets,
    liquidity, and risk using live market comps.
    </p>

    <p>
    Built for resellers who want faster decisions
    and higher profits.
    </p>

    <br>

    <a href="/login">
    <button class="cta">Launch CLAMS</button>
    </a>

    </div>

    </body>
    </html>
    """


# ---------------- LOGIN PAGE ---------------- #

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    if is_authenticated(request):
        return RedirectResponse("/app", status_code=303)

    return """
    <html>
    <body style="background:#111;color:white;font-family:Segoe UI;text-align:center;padding-top:150px;">
    <h2>CLAMS Access</h2>

    <form method="post" action="/login">

    <input type="password" name="password" required
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

    return RedirectResponse("/login", status_code=303)


@app.get("/logout")
def logout():
    return logout_response("/")


# ---------------- MAIN APP ---------------- #

@app.get("/app", response_class=HTMLResponse)
def app_home(request: Request):

    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)

    return render_page()


@app.post("/app", response_class=HTMLResponse)
def analyze(request: Request,
            query: str = Form(...),
            condition: str = Form("A"),
            profit: float = Form(0.40)):

    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)

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


# ---------------- AI LISTING ENHANCER ---------------- #

@app.post("/ai-enhance")
async def ai_enhance(request: Request):

    data = await request.json()

    query = data.get("query","")
    text = data.get("text","")
    mode = data.get("mode","description")

    try:

        prompt = f"""
        Improve this marketplace listing {mode}.
        Keep it short, clear, and high converting.

        Item: {query}

        {mode}:
        {text}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.7
        )

        return JSONResponse({"content":response.choices[0].message.content})

    except:

        return JSONResponse({"content":text})


# ---------------- HEALTH CHECK ---------------- #

@app.get("/health")
def health():
    return {"status":"ok"}


# ---------------- PAGE RENDER ---------------- #

def render_page(query="", analysis=None, sold_items=None,
                error=None, condition="A", profit=0.40):

    sell_price = analysis['sell_target'] if analysis else 0
    max_buy = analysis['max_buy'] if analysis else 0

    primary_image = ""
    primary_title = ""
    primary_link = ""

    if sold_items:
        primary_image = sold_items[0].get("image","")
        primary_title = sold_items[0].get("title","")
        primary_link = sold_items[0].get("link","#")

    error_block = f"<div style='color:#ff6b6b'>{error}</div>" if error else ""

    return f"""
    <html>

    <head>

    <title>CLAMS Engine</title>

    <style>

    body{{
    font-family:Segoe UI;
    background:#18242d;
    color:white;
    padding:40px;
    }}

    .card{{
    background:#111;
    padding:20px;
    border-radius:14px;
    margin-bottom:25px;
    }}

    .green{{color:#00cc66;font-weight:bold}}
    .red{{color:#ff4444;font-weight:bold}}

    </style>

    </head>

    <body>

    <h1>CLAMS Engine</h1>

    <form method="post" action="/app">

    <input name="query" value="{query}" placeholder="Search item..." required>

    <input type="number" step="0.05" name="profit" value="{profit}">

    <button type="submit">Analyze</button>

    </form>

    {error_block}

    <div class="card">

    Sell Target: <b>${sell_price}</b><br>
    Max Buy: <b>${max_buy}</b>

    </div>

    <div class="card">

    <a href="{primary_link}" target="_blank">
    <img src="{primary_image}" style="max-width:250px;border-radius:10px;">
    </a>

    <div>{primary_title}</div>

    </div>

    </body>

    </html>
    """