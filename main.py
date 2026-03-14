from typing import List, Optional
import os
import base64
from datetime import date

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ebay import search_ebay
from market_analysis import analyze_market
from listing_generator import generate_listings

from openai import OpenAI
import stripe


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
FREE_LIMIT = 5

PRO_PRICE = 19
RESELLER_PRICE = 49


# ---------- STRIPE ----------

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")
STRIPE_RESELLER_PRICE_ID = os.getenv("STRIPE_RESELLER_PRICE_ID", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")


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


def ensure_daily_reset(user: dict):
    today = str(date.today())

    if user.get("search_reset_date") != today:
        user["search_reset_date"] = today
        user["search_count"] = 0

    return user


def ensure_user_exists(email: str):

    if email not in users:
        users[email] = {
            "password": "",
            "membership": "FREE",
            "search_count": 0,
            "search_reset_date": str(date.today()),
            "settings": build_default_settings()
        }

    ensure_user_settings(users[email])
    ensure_daily_reset(users[email])

    return users[email]


def get_membership_limits(user: dict):
    membership = user.get("membership", "FREE").upper()

    if membership == "FREE":
        return {
            "membership": "FREE",
            "daily_limit": FREE_LIMIT,
            "advanced_enabled": False,
            "ai_photo_enabled": False
        }

    if membership == "PRO":
        return {
            "membership": "PRO",
            "daily_limit": None,
            "advanced_enabled": False,
            "ai_photo_enabled": True
        }

    return {
        "membership": "RESELLER",
        "daily_limit": None,
        "advanced_enabled": True,
        "ai_photo_enabled": True
    }


def clamp_score(value):
    try:
        number = int(round(float(value)))
    except Exception:
        return 0

    if number < 0:
        return 0
    if number > 100:
        return 100
    return number


def deal_score_class(score):
    score = clamp_score(score)

    if score >= 80:
        return "score-strong"
    if score >= 60:
        return "score-medium"
    return "score-weak"


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
    except Exception:
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
        "membership": "FREE",
        "search_count": 0,
        "search_reset_date": str(date.today()),
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


# ---------- BILLING / STRIPE ----------

@app.get("/upgrade/{plan}")
async def upgrade_plan(plan: str, email: str = ""):

    if plan not in ["pro", "reseller"]:
        return RedirectResponse(f"/app?email={email}", status_code=303)

    price_id = STRIPE_PRO_PRICE_ID if plan == "pro" else STRIPE_RESELLER_PRICE_ID

    if not price_id:
        return RedirectResponse(f"/app?email={email}", status_code=303)

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{APP_BASE_URL}/billing/success?email={email}&plan={plan}",
        cancel_url=f"{APP_BASE_URL}/billing/cancel?email={email}",
        metadata={
            "email": email,
            "plan": plan.upper()
        }
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@app.get("/billing/success")
async def billing_success(email: str = "", plan: str = ""):

    user = ensure_user_exists(email)

    if plan.lower() == "pro":
        user["membership"] = "PRO"
    elif plan.lower() == "reseller":
        user["membership"] = "RESELLER"

    return RedirectResponse(f"/app?email={email}", status_code=303)


@app.get("/billing/cancel")
async def billing_cancel(email: str = ""):
    return RedirectResponse(f"/app?email={email}", status_code=303)


# ---------- APP PAGE ----------

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request, email: str = ""):

    cookie_user = request.cookies.get("clams_user")

    if not email and cookie_user:
        email = cookie_user

    user = ensure_user_exists(email)
    plan_info = get_membership_limits(user)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": None,
            "generated_listings": None,
            "listing": None,
            "email": email,
            "search_count": user.get("search_count", 0),
            "user_settings": user["settings"],
            "user": user,
            "plan_info": plan_info,
            "free_limit": FREE_LIMIT,
            "pro_price": PRO_PRICE,
            "reseller_price": RESELLER_PRICE
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
    plan_info = get_membership_limits(user)

    if profit is None:
        profit = settings["default_profit"]

    if local_factor is None:
        local_factor = settings["local_factor"]

    if not platforms:
        platforms = settings["platforms"]

    if plan_info["daily_limit"] is not None and user["search_count"] >= plan_info["daily_limit"]:
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
                "user": user,
                "plan_info": plan_info,
                "free_limit": FREE_LIMIT,
                "pro_price": PRO_PRICE,
                "reseller_price": RESELLER_PRICE,
                "error": f"Free plan limit reached for today. Upgrade to Pro or Reseller for more scans."
            },
        )

    user["search_count"] += 1

    if photo and plan_info["ai_photo_enabled"]:
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
                "user": user,
                "plan_info": plan_info,
                "free_limit": FREE_LIMIT,
                "pro_price": PRO_PRICE,
                "reseller_price": RESELLER_PRICE,
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
        data["deal_score_ui"] = clamp_score(data.get("deal_score", 0))
        data["flip_score_ui"] = clamp_score(data.get("flip_score", 0))
        data["deal_score_class"] = deal_score_class(data["deal_score_ui"])
        data["flip_score_class"] = deal_score_class(data["flip_score_ui"])

        if asking_price is not None:
            try:
                market_price = float(data.get("market_price", 0))
                profit_delta = round(market_price - float(asking_price), 2)
                data["profit_delta"] = profit_delta

                if float(asking_price) > 0:
                    data["profit_margin_percent"] = round((profit_delta / float(asking_price)) * 100, 1)
                else:
                    data["profit_margin_percent"] = 0
            except Exception:
                data["profit_delta"] = None
                data["profit_margin_percent"] = None
        else:
            data["profit_delta"] = None
            data["profit_margin_percent"] = None

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
            "user_settings": settings,
            "user": user,
            "plan_info": plan_info,
            "free_limit": FREE_LIMIT,
            "pro_price": PRO_PRICE,
            "reseller_price": RESELLER_PRICE
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