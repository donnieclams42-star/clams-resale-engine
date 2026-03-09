import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from ebay import get_market_data

load_dotenv()

app = FastAPI()

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD", "clams")
STRIPE_LINK = os.getenv("STRIPE_LINK", "#")


def render_dashboard(query="", sell_target=0, max_buy=0, buy_score=0, image=""):

    return f"""
    <html>
    <head>
    <title>CLAMS Engine</title>
    </head>

    <body style="font-family:Arial;background:#111;color:white;text-align:center">

    <h1>CLAMS Resale Engine</h1>

    <form method="post" action="/app">

    <input
    name="query"
    placeholder="Search item (ex: iphone 11)"
    value="{query}"
    style="padding:10px;width:260px;border-radius:6px;border:none;"
    required
    >

    <br><br>

    <button type="submit" style="padding:10px 20px">
    Analyze
    </button>

    </form>

    <br><br>

    <h2>Buy Score: {buy_score}</h2>
    <h2>Sell Target: ${sell_target}</h2>
    <h2>Max Buy: ${max_buy}</h2>

    {"<img src='" + image + "' width='200'>" if image else ""}

    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def landing():

    return f"""
    <html>
    <head>
    <title>CLAMS Engine</title>
    </head>

    <body style="font-family:Arial;background:#111;color:white;text-align:center">

    <h1>CLAMS Resale Intelligence Engine</h1>

    <p>Find profitable flips using live market data.</p>

    <br>

    <a href="{STRIPE_LINK}">
    <button style="padding:15px 30px;font-size:20px">
    Subscribe $19/month
    </button>
    </a>

    <br><br>

    <a href="/login">
    Launch CLAMS
    </a>

    </body>
    </html>
    """


@app.get("/login")
def login():

    return HTMLResponse("""
    <h2>CLAMS Login</h2>

    <form method="post" action="/login">

    <input name="password" placeholder="Password">

    <button type="submit">Enter</button>

    </form>
    """)


@app.post("/login")
def login_post(password: str = Form(...)):

    if password == CLAMS_PASSWORD:

        response = RedirectResponse("/app", status_code=303)

        response.set_cookie("auth", "1")

        return response

    return HTMLResponse("Wrong password")


@app.get("/app", response_class=HTMLResponse)
def dashboard(request: Request):

    if request.cookies.get("auth") != "1":
        return RedirectResponse("/login")

    return HTMLResponse(render_dashboard())


@app.post("/app", response_class=HTMLResponse)
def analyze(request: Request, query: str = Form(...)):

    if request.cookies.get("auth") != "1":
        return RedirectResponse("/login")

    print("SEARCH:", query)

    sold_prices, active_prices, sold_items = get_market_data(query)

    print("RESULT COUNT:", len(sold_prices))

    if not sold_prices:

        return HTMLResponse(render_dashboard(
            query=query,
            sell_target=0,
            max_buy=0,
            buy_score=0
        ))

    sold_prices.sort()

    median_price = sold_prices[len(sold_prices)//2]

    sell_target = round(median_price * 0.9, 2)

    max_buy = round(sell_target * 0.6, 2)

    buy_score = int((sell_target - max_buy) / sell_target * 100)

    image = sold_items[0]["image"] if sold_items else ""

    return HTMLResponse(render_dashboard(
        query=query,
        sell_target=sell_target,
        max_buy=max_buy,
        buy_score=buy_score,
        image=image
    ))