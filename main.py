import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from ebay import get_market_data
from pricing import analyze_market
from auth import is_authenticated, login_success_response, logout_response

OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = None
if OPENAI_KEY:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "changeme")


# ---------------- LANDING ---------------- #

@app.get("/", response_class=HTMLResponse)
def landing():

    return """
    <html>
    <head>
    <title>CLAMS Engine</title>

    <style>

    body{
        margin:0;
        font-family:Segoe UI;
        background:linear-gradient(135deg,#1e2a33,#223544);
        color:white;
        text-align:center;
        padding-top:120px;
    }

    h1{
        font-size:56px;
        background:linear-gradient(90deg,#00cc66,#00aaff);
        -webkit-background-clip:text;
        -webkit-text-fill-color:transparent;
    }

    .cta{
        padding:16px 40px;
        background:#00cc66;
        color:black;
        border:none;
        border-radius:10px;
        font-size:18px;
        font-weight:bold;
        cursor:pointer;
        margin-top:30px;
    }

    </style>
    </head>

    <body>

    <h1>CLAMS</h1>

    <h2>Resale Intelligence Engine</h2>

    <p>Find max buy prices, sell targets, and profitable flips instantly.</p>

    <a href="/login">
    <button class="cta">Launch CLAMS</button>
    </a>

    </body>
    </html>
    """


# ---------------- LOGIN ---------------- #

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    if is_authenticated(request):
        return RedirectResponse("/app", status_code=303)

    return """
    <html>
    <body style="background:#111;color:white;font-family:Segoe UI;text-align:center;padding-top:150px;">

    <h2>CLAMS Access</h2>

    <form method="post" action="/login">

    <input type="password" name="password"
    style="padding:12px;border-radius:8px;border:none;width:250px;" required>

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

    text = data.get("text","")

    if not client:
        return JSONResponse({"content": text})

    try:

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":text}],
            temperature=0.7
        )

        return JSONResponse({"content":response.choices[0].message.content})

    except:

        return JSONResponse({"content": text})


# ---------------- HEALTH ---------------- #

@app.get("/health")
def health():
    return {"status":"ok"}


# ---------------- PAGE RENDER ---------------- #

def render_page(query="",analysis=None,sold_items=None,error=None,condition="A",profit=0.40):

    sell_price = analysis["sell_target"] if analysis else 0
    max_buy = analysis["max_buy"] if analysis else 0

    image = ""
    title = ""
    link = ""

    if sold_items:
        image = sold_items[0]["image"]
        title = sold_items[0]["title"]
        link = sold_items[0]["link"]

    return f"""
    <html>

    <head>

    <style>

    body {{
        font-family:Segoe UI;
        background:#1e2a33;
        color:white;
        padding:40px;
    }}

    .card {{
        background:#111;
        padding:20px;
        border-radius:14px;
        margin-bottom:25px;
    }}

    button {{
        padding:10px 16px;
        border:none;
        border-radius:8px;
        background:#00cc66;
        font-weight:bold;
    }}

    </style>

    </head>

    <body>

    <h1>CLAMS Dashboard</h1>

    <form method="post" action="/app">

    <input name="query" value="{query}" placeholder="Search item..." required>

    <input type="number" step="0.05" name="profit" value="{profit}">

    <button type="submit">Analyze</button>

    </form>

    <div class="card">

    Sell Target: ${sell_price}<br>
    Max Buy: ${max_buy}

    </div>

    <div class="card">

    <a href="{link}" target="_blank">
    <img src="{image}" style="max-width:250px;border-radius:12px;">
    </a>

    <p>{title}</p>

    </div>

    </body>

    </html>
    """