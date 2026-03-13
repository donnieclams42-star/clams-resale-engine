from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ebay import search_ebay
from pricing import analyze_market
from listing_generator import generate_listings

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

users = {}

INVITE_CODE = "betatesting123"


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(...)
):

    if invite != INVITE_CODE:
        return {"error": "Invalid invite code"}

    if email not in users:
        users[email] = {"password": password}

    if users[email]["password"] != password:
        return {"error": "Incorrect password"}

    return RedirectResponse("/app", status_code=303)


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(...)
):

    if invite != INVITE_CODE:
        return {"error": "Invalid invite code"}

    users[email] = {"password": password}

    return RedirectResponse("/login", status_code=303)


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": None,
            "generated_listings": None,
            "suggestions": []
        },
    )


@app.post("/app", response_class=HTMLResponse)
async def analyze(
    request: Request,
    query: str = Form(...),
    condition: str = Form(...),
    profit: float = Form(...),
    local_factor: float = Form(...),
    asking_price: float = Form(None)
):

    sold_prices, active_prices, suggestions = search_ebay(query)

    data = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit / 100,
        local_factor / 100,
        asking_price,
    )

    generated_listings = None

    if data:
        generated_listings = generate_listings(
            query,
            condition,
            data["fast_cash"],
            data["market_price"],
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": data,
            "generated_listings": generated_listings,
            "suggestions": suggestions,
        },
    )