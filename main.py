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


# ---------- FIXED PATHS FOR RENDER ----------

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


# ---------- DEFAULT SETTINGS ----------

DEFAULT_USER_SETTINGS = {
    "platforms": ["facebook", "ebay"],
    "default_profit": 40,
    "local_factor": 80,
    "mode": "simple"
}


def build_default_settings():
    return {
        "platforms": DEFAULT_USER_SETTINGS["platforms"][:],
        "default_profit": DEFAULT_USER_SETTINGS["default_profit"],
        "local_factor": DEFAULT_USER_SETTINGS["local_factor"],
        "mode": DEFAULT_USER_SETTINGS["mode"]
    }


def ensure_user_settings(user: dict):

    if "settings" not in user or not isinstance(user["settings"], dict):
        user["settings"] = build_default_settings()

    settings = user["settings"]

    if "platforms" not in settings or not settings["platforms"]:
        settings["platforms"] = DEFAULT_USER_SETTINGS["platforms"][:]

    if "default_profit" not in settings:
        settings["default_profit"] = DEFAULT_USER_SETTINGS["default_profit"]

    if "local_factor" not in settings:
        settings["local_factor"] = DEFAULT_USER_SETTINGS["local_factor"]

    if "mode" not in settings:
        settings["mode"] = DEFAULT_USER_SETTINGS["mode"]

    return settings


def ensure_user_exists(email: str):

    if email not in users:
        users[email] = {
            "password": "",
            "membership": "PRO",
            "search_count": 0,
            "settings": build_default_settings()
        }

    ensure_user_settings(users[email])

    return users[email]


# ---------- OPENAI CLIENT ----------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------- IMAGE DETECTION ----------

async def detect_item_from_image(photo: UploadFile):

    image_bytes = await photo.read()

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
Identify the product in this image.

Return a short resale search phrase including brand and model if visible.

Examples:
Apple iPhone 12
Sony PlayStation 4 console
Milwaukee M18 cordless drill

Return only the search phrase.
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image_b64}"
                    }
                ]
            }
        ]
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

    users[email] = {
        "password": password,
        "membership": "PRO",
        "search_count": 0,
        "settings": build_default_settings()
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

    user = ensure_user_exists(email)

    if user["password"] and user["password"] != password:
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

    user = ensure_user_exists(email)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": None,
            "generated_listings": None,
            "listing": None,
            "email": email,
            "search_count": user.get("search_count", 0),
            "user_settings": user["settings"]
        },
    )


# ---------- ANALYZE ----------

@app.post("/app", response_class=HTMLResponse)
async def analyze(
    request: Request,
    query: str = Form(""),
    condition: str = Form(...),
    profit: Optional[float] = Form(None),
    local_factor: Optional[float] = Form(None),
    asking_price: Optional[float] = Form(None),
    email: str = Form(""),
    platforms: Optional[List[str]] = Form(None),
    photo: UploadFile = File(None)
):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = ensure_user_exists(email)
    settings = user["settings"]

    if profit is None:
        profit = settings["default_profit"]

    if local_factor is None:
        local_factor = settings["local_factor"]

    if not platforms:
        platforms = settings["platforms"]

    user["search_count"] += 1

    # ---------- IMAGE AI ALWAYS RUNS IF PHOTO EXISTS ----------

    if photo:
        try:
            detected = await detect_item_from_image(photo)

            if detected:
                query = detected

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
                "search_count": user["search_count"],
                "user_settings": settings,
                "error": "No search query detected"
            },
        )

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
            "search_count": user["search_count"],
            "user_settings": settings
        },
    )


# ---------- SETTINGS PAGE ----------

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, email: str = ""):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = ensure_user_exists(email)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "user_settings": user["settings"],
            "success": None
        }
    )


# ---------- SAVE SETTINGS ----------

@app.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    email: str = Form(""),
    mode: str = Form("simple"),
    default_profit: float = Form(40),
    local_factor: float = Form(80),
    platforms: Optional[List[str]] = Form(None)
):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = ensure_user_exists(email)

    if not platforms:
        platforms = ["facebook", "ebay"]

    settings = user["settings"]

    settings["mode"] = mode
    settings["default_profit"] = default_profit
    settings["local_factor"] = local_factor
    settings["platforms"] = platforms

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "user_settings": settings,
            "success": "Settings saved successfully."
        }
    )


# ---------- ACCOUNT ----------

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, email: str = ""):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = ensure_user_exists(email)

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "email": email,
            "user": user
        }
    )