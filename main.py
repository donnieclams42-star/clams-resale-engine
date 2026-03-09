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

CLAMS_PASSWORD = os.getenv("CLAMS_PASSWORD","changeme")

STRIPE_LINK = os.getenv("STRIPE_LINK","https://buy.stripe.com")


# ---------------- BUY SCORE ---------------- #

def calculate_buy_score(analysis):

    if not analysis:
        return 0

    profit_margin = analysis["profit_margin"]
    liquidity = analysis["liquidity"]
    risk = analysis["risk"]

    score = 50

    score += profit_margin * 30
    score += liquidity * 20
    score -= risk * 25

    score = max(0,min(100,int(score)))

    return score


# ---------------- LANDING PAGE ---------------- #

@app.get("/", response_class=HTMLResponse)
def landing():

    return f"""
<html>

<head>

<title>CLAMS Resale Engine</title>

<style>

body {{
background:linear-gradient(135deg,#1e2a33,#223544);
font-family:Segoe UI;
color:white;
text-align:center;
padding-top:120px;
}}

h1 {{
font-size:60px;
background:linear-gradient(90deg,#00cc66,#00aaff);
-webkit-background-clip:text;
-webkit-text-fill-color:transparent;
}}

button {{
padding:16px 40px;
border:none;
border-radius:10px;
font-size:18px;
font-weight:bold;
cursor:pointer;
margin:10px;
}}

.primary {{
background:#00cc66;
color:black;
}}

.secondary {{
background:#0077ff;
color:white;
}}

.footer {{
margin-top:80px;
opacity:0.6;
}}

</style>

</head>

<body>

<h1>CLAMS</h1>

<h2>Resale Intelligence Engine</h2>

<p>Know what to pay before you buy.</p>

<p>Sell Targets • Max Buy Price • Market Risk • Profit Score</p>

<a href="/login">
<button class="primary">Launch CLAMS</button>
</a>

<a href="{STRIPE_LINK}">
<button class="secondary">Subscribe $19/mo</button>
</a>

<div class="footer">

<a href="/terms">Terms</a> |
<a href="/privacy">Privacy</a> |
<a href="/contact">Contact</a>

</div>

</body>

</html>
"""


# ---------------- LOGIN ---------------- #

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    if is_authenticated(request):
        return RedirectResponse("/app",status_code=303)

    return """
<html>

<body style="background:#111;color:white;text-align:center;padding-top:150px;font-family:Segoe UI;">

<h2>CLAMS Access</h2>

<form method="post" action="/login">

<input type="password" name="password" placeholder="Password"
style="padding:12px;border-radius:8px;border:none;width:260px;" required>

<br><br>

<button type="submit"
style="padding:12px 40px;background:#00cc66;border:none;border-radius:8px;font-weight:bold;">
Enter
</button>

</form>

</body>

</html>
"""


@app.post("/login")
def login(password:str=Form(...)):

    if password == CLAMS_PASSWORD:
        return login_success_response("/app")

    return RedirectResponse("/login",status_code=303)


@app.get("/logout")
def logout():
    return logout_response("/")


# ---------------- DASHBOARD ---------------- #

@app.get("/app",response_class=HTMLResponse)
def dashboard(request:Request):

    if not is_authenticated(request):
        return RedirectResponse("/login",status_code=303)

    return render_dashboard()


@app.post("/app",response_class=HTMLResponse)
def analyze(request:Request,
            query:str=Form(...),
            condition:str=Form("A"),
            profit:float=Form(0.40)):

    sold_prices,active_prices,sold_items = get_market_data(query)

    if not sold_prices:
        return render_dashboard(error="No comps found.",query=query)

    analysis = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit,
        0.80
    )

    buy_score = calculate_buy_score(analysis)

    return render_dashboard(
        query=query,
        analysis=analysis,
        sold_items=sold_items,
        buy_score=buy_score
    )


# ---------------- AI LISTING ---------------- #

@app.post("/ai-enhance")
async def ai_enhance(request:Request):

    data = await request.json()

    text = data.get("text","")

    if not client:
        return JSONResponse({"content":text})

    try:

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":text}],
            temperature=0.7
        )

        return JSONResponse({"content":response.choices[0].message.content})

    except:
        return JSONResponse({"content":text})


# ---------------- HEALTH ---------------- #

@app.get("/health")
def health():
    return {"status":"ok"}


# ---------------- LEGAL PAGES ---------------- #

@app.get("/terms",response_class=HTMLResponse)
def terms():
    return """
<h2>Terms of Service</h2>
<p>CLAMS provides resale market analysis tools.</p>
<p>Users make their own buying and selling decisions.</p>
<p>No guarantees of profit are provided.</p>
"""


@app.get("/privacy",response_class=HTMLResponse)
def privacy():
    return """
<h2>Privacy Policy</h2>
<p>CLAMS does not sell user data.</p>
<p>Payment information is securely handled by Stripe.</p>
"""


@app.get("/contact",response_class=HTMLResponse)
def contact():
    return """
<h2>Contact</h2>
<p>Email: clamsengine@gmail.com</p>
<p>Support response time: 24 hours</p>
"""


# ---------------- DASHBOARD RENDER ---------------- #

def render_dashboard(query="",analysis=None,sold_items=None,buy_score=0,error=None):

    sell_target = analysis["sell_target"] if analysis else 0
    max_buy = analysis["max_buy"] if analysis else 0

    image=""
    title=""
    link=""

    if sold_items:
        image=sold_items[0]["image"]
        title=sold_items[0]["title"]
        link=sold_items[0]["link"]

    return f"""
<html>

<head>

<style>

body {{
background:#1e2a33;
font-family:Segoe UI;
color:white;
padding:40px;
}}

.card {{
background:#111;
padding:20px;
border-radius:14px;
margin-bottom:25px;
}}

.score {{
font-size:48px;
font-weight:bold;
color:#00cc66;
}}

</style>

</head>

<body>

<h1>CLAMS Dashboard</h1>

<div class="card">

<form method="post" action="/app">

<input name="query" value="{query}" placeholder="Search item..." required>

<button type="submit">Analyze</button>

</form>

</div>

<div class="card">

<h2>Buy Score</h2>

<div class="score">{buy_score}/100</div>

</div>

<div class="card">

Sell Target: ${sell_target}<br>
Max Buy: ${max_buy}

</div>

<div class="card">

<a href="{link}" target="_blank">
<img src="{image}" style="max-width:260px;border-radius:12px;">
</a>

<p>{title}</p>

</div>

<div class="card">

<h3>Momentum</h3>

<p>Keep scanning markets. Every flip builds capital.</p>

</div>

</body>

</html>
"""