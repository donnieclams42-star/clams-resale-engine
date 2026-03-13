from typing import List, Optional
import os
import base64

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ebay import search_ebay
from market_analysis import analyze_market
from listing_generator import generate_listings

from openai import OpenAI


app = FastAPI()


# ---------- PATH FIX (CRITICAL FOR RENDER) ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ---------- USER STORAGE ----------

users = {}

INVITE_CODE = "betatesting123"

BETA_MODE = True
FREE_LIMIT = 10


# ---------- OPENAI CLIENT ----------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------- IMAGE DETECTION ----------

async def detect_item_from_image(photo: UploadFile):

    image_bytes = await photo.read()

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1",
        input=[{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": """
Return the best short resale search phrase.
Include brand and model if visible.
Do not describe the image.
Return only the search phrase.
"""
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_b64}"
                }
            ]
        }]
    )

    try:
        detected = response.output_text.strip()
    except:
        detected = ""

    return detected


# ---------- PWA ROUTES ----------

@app.get("/manifest.json")
async def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"))


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "service-worker.js"))


# ---------- LANDING ----------

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):

    email = request.cookies.get("clams_user")

    if email:
        return RedirectResponse(f"/app?email={email}")

    return templates.TemplateResponse(
        "landing.html",
        {"request": request}
    )


# ---------- LOGIN PAGE ----------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):

    email = request.cookies.get("clams_user")

    if email:
        return RedirectResponse(f"/app?email={email}")

    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


# ---------- SIGNUP PAGE ----------

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):

    return templates.TemplateResponse(
        "signup.html",
        {"request": request}
    )


# ---------- SIGNUP ----------

@app.post("/signup")
async def signup(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(...)
):

    if invite != INVITE_CODE:
        return {"error": "Invalid invite code"}

    if email in users:
        return {"error": "Account already exists"}

    users[email] = {
        "password": password,
        "membership": "PRO",
        "search_count": 0
    }

    response = RedirectResponse(f"/app?email={email}", status_code=303)

    response.set_cookie(
        key="clams_user",
        value=email,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax"
    )

    return response


# ---------- LOGIN ----------

@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(...)
):

    if invite != INVITE_CODE:
        return {"error": "Invalid invite code"}

    if email not in users:
        users[email] = {
            "password": password,
            "membership": "PRO",
            "search_count": 0
        }

    if users[email]["password"] != password:
        return {"error": "Incorrect password"}

    response = RedirectResponse(f"/app?email={email}", status_code=303)

    response.set_cookie(
        key="clams_user",
        value=email,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax"
    )

    return response


# ---------- APP PAGE ----------

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request, email: str = ""):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = users.get(email, {})

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": None,
            "generated_listings": None,
            "listing": None,
            "email": email,
            "search_count": user.get("search_count", 0)
        },
    )


# ---------- ANALYZE ----------

@app.post("/app", response_class=HTMLResponse)
async def analyze(
    request: Request,
    query: str = Form(""),
    condition: str = Form(...),
    profit: float = Form(...),
    local_factor: float = Form(...),
    asking_price: Optional[float] = Form(None),
    email: str = Form(""),
    platforms: Optional[List[str]] = Form(None),
    photo: UploadFile = File(None)
):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = users.get(email, {})

    if email in users:
        users[email]["search_count"] += 1

    if photo and not query:
        try:
            query = await detect_item_from_image(photo)
        except Exception as e:
            print("Image detection failed:", e)

    if not query:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "data": None,
                "generated_listings": None,
                "listing": None,
                "email": email,
                "search_count": user.get("search_count", 0),
                "error": "No search query detected"
            },
        )

    if not platforms:
        platforms = ["facebook", "ebay"]

    sold_prices, active_prices, suggestions, listing = search_ebay(query)

    data = analyze_market(
        sold_prices,
        active_prices,
        condition,
        profit / 100,
        local_factor / 100,
        asking_price
    )

    generated_listings = None

    if data:
        generated_listings = generate_listings(
            query,
            condition,
            data["fast_cash"],
            data["market_price"],
            platforms
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": data,
            "generated_listings": generated_listings,
            "listing": listing,
            "email": email,
            "search_count": user.get("search_count", 0)
        },
    )


# ---------- ACCOUNT ----------

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, email: str = ""):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = users.get(email, {})

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "email": email,
            "user": user
        }
    )