from typing import List, Optional
import os
import re
import base64
from datetime import date

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ebay import search_ebay
from market_analysis import analyze_market
from listing_generator import generate_listings

from openai import OpenAI
import stripe
from supabase import create_client, Client


app = FastAPI()


# ---------- FIXED PATHS FOR RENDER ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ---------- FALLBACK USER STORAGE ----------

users = {}

INVITE_CODE = os.getenv("CLAMS_INVITE_CODE", "betatesting123")
BETA_MODE = True
FREE_LIMIT = 5

PRO_PRICE = 19
RESELLER_PRICE = 49

ADMIN_EMAILS = {
    "donnieclams42@gmail.com",
}


# ---------- STRIPE ----------

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "").strip()
STRIPE_RESELLER_PRICE_ID = os.getenv("STRIPE_RESELLER_PRICE_ID", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")


# ---------- SUPABASE ----------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_KEY", "")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------- DEFAULT SETTINGS ----------

DEFAULT_USER_SETTINGS = {
    "platforms": ["facebook", "ebay"],
    "default_profit": 40,
    "local_factor": 80,
    "mode": "simple",
}


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_default_settings():
    return {
        "platforms": DEFAULT_USER_SETTINGS["platforms"][:],
        "default_profit": DEFAULT_USER_SETTINGS["default_profit"],
        "local_factor": DEFAULT_USER_SETTINGS["local_factor"],
        "mode": DEFAULT_USER_SETTINGS["mode"],
    }


def normalize_settings(settings):
    if not isinstance(settings, dict):
        settings = build_default_settings()

    settings = dict(settings)

    if "platforms" not in settings or not settings["platforms"]:
        settings["platforms"] = DEFAULT_USER_SETTINGS["platforms"][:]

    if "default_profit" not in settings:
        settings["default_profit"] = DEFAULT_USER_SETTINGS["default_profit"]

    if "local_factor" not in settings:
        settings["local_factor"] = DEFAULT_USER_SETTINGS["local_factor"]

    if "mode" not in settings:
        settings["mode"] = DEFAULT_USER_SETTINGS["mode"]

    return settings


def is_admin_email(email: str) -> bool:
    return (email or "").strip().lower() in ADMIN_EMAILS


def get_request_email(request: Request, email: str = "") -> str:
    cookie_user = request.cookies.get("clams_user", "")
    if cookie_user:
        return cookie_user.strip().lower()
    return (email or "").strip().lower()


def set_user_cookie(response: RedirectResponse, email: str):
    response.set_cookie(
        key="clams_user",
        value=(email or "").strip().lower(),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        key="clams_auth",
        value="1",
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return response


def normalize_user(user: dict):
    user = dict(user)
    user_email = str(user.get("email", "") or "").strip().lower()
    user["email"] = user_email
    user["membership"] = str(user.get("membership", "FREE")).upper()
    user["search_count"] = int(user.get("search_count") or 0)
    user["settings"] = normalize_settings(user.get("settings") or {})
    user["search_reset_date"] = str(user.get("search_reset_date") or str(date.today()))
    user["is_admin"] = is_admin_email(user_email)
    return user


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip().lower()))


def verify_user_password(user: dict, password: str) -> bool:
    if not user:
        return False
    stored_password = str(user.get("password", "") or "")
    return stored_password == str(password or "")


def change_user_email(old_email: str, new_email: str):
    old_email = (old_email or "").strip().lower()
    new_email = (new_email or "").strip().lower()

    if not old_email or not new_email or old_email == new_email:
        return get_user(old_email)

    user = get_user(old_email)
    if not user:
        return None

    updated_user = dict(user)
    updated_user["email"] = new_email

    if supabase:
        try:
            supabase.table("users").update({"email": new_email}).eq("email", old_email).execute()
            return get_user(new_email)
        except Exception as e:
            print("Supabase change_user_email failed:", e)
            return None

    users[new_email] = updated_user
    if old_email in users:
        del users[old_email]
    return normalize_user(users[new_email])


def get_user(email: str):
    if not email:
        return None

    email = email.strip().lower()

    if supabase:
        try:
            result = supabase.table("users").select("*").eq("email", email).limit(1).execute()
            if result.data:
                return normalize_user(result.data[0])
        except Exception as e:
            print("Supabase get_user failed:", e)
        return None

    if email in users:
        return normalize_user(users[email])

    return None


def create_user_record(email: str, password: str = ""):
    email = (email or "").strip().lower()

    user_record = {
        "email": email,
        "password": password,
        "membership": "FREE",
        "search_count": 0,
        "search_reset_date": str(date.today()),
        "settings": build_default_settings(),
        "stripe_customer_id": None,
    }

    if supabase:
        try:
            supabase.table("users").insert(user_record).execute()
            created = get_user(email)
            return created or normalize_user(user_record)
        except Exception as e:
            print("Supabase create_user_record failed:", e)
            existing = get_user(email)
            if existing:
                return existing
            raise

    users[email] = user_record
    return normalize_user(user_record)


def update_user_record(email: str, updates: dict):
    if not email:
        return None

    email = email.strip().lower()
    updates = dict(updates)

    if "settings" in updates:
        updates["settings"] = normalize_settings(updates["settings"])

    if supabase:
        try:
            supabase.table("users").update(updates).eq("email", email).execute()
            return get_user(email)
        except Exception as e:
            print("Supabase update_user_record failed:", e)
            return get_user(email)

    if email in users:
        users[email].update(updates)
        return normalize_user(users[email])

    return None


def ensure_user_exists(email: str, password: str = ""):
    existing = get_user(email)
    if existing:
        return existing
    return create_user_record(email, password)


def ensure_daily_reset(user: dict):
    today = str(date.today())
    if str(user.get("search_reset_date")) != today:
        user = update_user_record(
            user["email"],
            {
                "search_reset_date": today,
                "search_count": 0,
            },
        )
    return user


def get_membership_limits(user: dict):
    membership = user.get("membership", "FREE").upper()
    is_admin = user.get("is_admin", False)

    if is_admin:
        return {
            "membership": "ADMIN",
            "daily_limit": None,
            "advanced_enabled": True,
            "ai_photo_enabled": True,
            "is_admin": True,
        }

    if membership == "FREE":
        return {
            "membership": "FREE",
            "daily_limit": FREE_LIMIT,
            "advanced_enabled": False,
            "ai_photo_enabled": False,
            "is_admin": False,
        }

    if membership == "PRO":
        return {
            "membership": "PRO",
            "daily_limit": None,
            "advanced_enabled": False,
            "ai_photo_enabled": True,
            "is_admin": False,
        }

    return {
        "membership": "RESELLER",
        "daily_limit": None,
        "advanced_enabled": True,
        "ai_photo_enabled": True,
        "is_admin": False,
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


def deal_temperature_class(label: str):
    label = (label or "").upper()
    if label == "HOT DEAL":
        return "deal-hot"
    if label == "WARM DEAL":
        return "deal-warm"
    if label == "COOL DEAL":
        return "deal-cool"
    return "deal-pass"


def normalize_local_factor(value) -> int:
    try:
        number = int(round(float(value)))
    except Exception:
        return DEFAULT_USER_SETTINGS["local_factor"]

    if number < 40:
        number = 40
    if number > 120:
        number = 120
    return number


def get_plan_ui_context(user: dict):
    plan_info = get_membership_limits(user)
    membership_tier = plan_info["membership"]
    ai_access = "Enabled" if plan_info["ai_photo_enabled"] else "Locked"
    return {
        "plan_info": plan_info,
        "membership_tier": membership_tier,
        "ai_access": ai_access,
        "pro_price": PRO_PRICE,
        "reseller_price": RESELLER_PRICE,
    }


# ---------- OPENAI CLIENT ----------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# ---------- IMAGE DETECTION ----------

async def detect_item_from_image(photo: UploadFile):
    if client is None:
        return ""

    image_bytes = await photo.read()
    if not image_bytes:
        return ""

    mime_type = (getattr(photo, "content_type", "") or "image/jpeg").strip().lower()
    if not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

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
""",
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{image_b64}",
                    },
                ],
            }
        ],
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
    email = request.cookies.get("clams_user", "").strip().lower()
    if email:
        return RedirectResponse(f"/app?email={email}", status_code=303)
    return templates.TemplateResponse("landing.html", {"request": request})


# ---------- LOGIN PAGE ----------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", email: str = "", notice: str = ""):
    cookie_email = request.cookies.get("clams_user", "").strip().lower()
    if cookie_email:
        return RedirectResponse(f"/app?email={cookie_email}", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": error,
            "notice": notice,
            "prefill_email": email,
        },
    )


# ---------- LOGOUT ----------

@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("clams_user")
    response.delete_cookie("clams_auth")
    response.delete_cookie("clams_premium")
    return response


# ---------- SIGNUP PAGE ----------

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: str = "", email: str = "", notice: str = ""):
    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "error": error,
            "notice": notice,
            "prefill_email": email,
        },
    )


# ---------- SIGNUP ----------

@app.post("/signup")
async def signup(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(...),
):
    email = (email or "").strip().lower()
    password = (password or "").strip()
    invite = (invite or "").strip()

    if invite != INVITE_CODE:
        return RedirectResponse(f"/signup?error=Invalid+invite+code&email={email}", status_code=303)

    if not valid_email(email):
        return RedirectResponse("/signup?error=Enter+a+valid+email+address", status_code=303)

    if len(password) < 6:
        return RedirectResponse(f"/signup?error=Password+must+be+at+least+6+characters&email={email}", status_code=303)

    existing = get_user(email)
    if existing:
        return RedirectResponse(f"/login?notice=Account+already+exists.+Please+log+in.&email={email}", status_code=303)

    try:
        create_user_record(email, password)
    except Exception:
        return RedirectResponse(f"/signup?error=Could+not+create+account+right+now&email={email}", status_code=303)

    response = RedirectResponse(f"/app?email={email}", status_code=303)
    set_user_cookie(response, email)
    return response


# ---------- LOGIN ----------

@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(...),
):
    email = (email or "").strip().lower()
    password = (password or "").strip()
    invite = (invite or "").strip()

    if invite != INVITE_CODE:
        return RedirectResponse(f"/login?error=Invalid+invite+code&email={email}", status_code=303)

    if not valid_email(email):
        return RedirectResponse("/login?error=Enter+a+valid+email+address", status_code=303)

    user = get_user(email)
    if not user:
        return RedirectResponse(f"/signup?notice=No+account+found.+Create+one+below.&email={email}", status_code=303)

    if user.get("password") and user["password"] != password:
        return RedirectResponse(f"/login?error=Incorrect+password&email={email}", status_code=303)

    response = RedirectResponse(f"/app?email={email}", status_code=303)
    set_user_cookie(response, email)
    return response


# ---------- BILLING / STRIPE ----------

@app.get("/upgrade/{plan}")
async def upgrade_plan(request: Request, plan: str, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    if plan not in ["pro", "reseller"]:
        return RedirectResponse(f"/account?email={email}", status_code=303)

    price_id = STRIPE_PRO_PRICE_ID if plan == "pro" else STRIPE_RESELLER_PRICE_ID
    if not price_id or not stripe.api_key:
        return RedirectResponse(f"/account?email={email}&error=Billing+is+not+configured+yet", status_code=303)

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{APP_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}&email={email}",
            cancel_url=f"{APP_BASE_URL}/billing/cancel?email={email}",
            metadata={
                "email": email,
                "plan": plan.upper(),
            },
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except Exception as e:
        print("Stripe checkout create failed:", e)
        return RedirectResponse(f"/account?email={email}&error=Unable+to+start+billing+checkout", status_code=303)


@app.get("/billing/success")
async def billing_success(session_id: str = "", email: str = ""):
    email = (email or "").strip().lower()

    if session_id and stripe.api_key:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            metadata = session.get("metadata", {}) or {}
            plan = str(metadata.get("plan", "")).upper()
            account_email = (metadata.get("email") or email or "").strip().lower()
            stripe_customer_id = session.get("customer")

            if account_email and plan in ["PRO", "RESELLER"]:
                update_user_record(
                    account_email,
                    {
                        "membership": plan,
                        "stripe_customer_id": stripe_customer_id,
                    },
                )
                return RedirectResponse(f"/account?email={account_email}&notice=Membership+updated+successfully", status_code=303)
        except Exception as e:
            print("Billing success verification failed:", e)

    return RedirectResponse(f"/account?email={email}", status_code=303)


@app.get("/billing/cancel")
async def billing_cancel(email: str = ""):
    email = (email or "").strip().lower()
    return RedirectResponse(f"/account?email={email}&notice=Billing+checkout+was+canceled", status_code=303)


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        return JSONResponse({"error": "Webhook secret missing"}, status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("Webhook verification failed:", e)
        return JSONResponse({"error": "Invalid webhook"}, status_code=400)

    event_type = event.get("type", "")
    event_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        metadata = event_object.get("metadata") or {}
        email = (metadata.get("email") or event_object.get("customer_email") or "").strip().lower()
        plan = str(metadata.get("plan", "")).upper()
        stripe_customer_id = event_object.get("customer")

        if email and plan in ["PRO", "RESELLER"]:
            update_user_record(
                email,
                {
                    "membership": plan,
                    "stripe_customer_id": stripe_customer_id,
                },
            )

    elif event_type in ["invoice.payment_failed", "customer.subscription.deleted"]:
        stripe_customer_id = event_object.get("customer")

        if stripe_customer_id and supabase:
            result = supabase.table("users").select("*").eq("stripe_customer_id", stripe_customer_id).limit(1).execute()
            if result.data:
                email = result.data[0]["email"]
                update_user_record(email, {"membership": "FREE"})

        elif stripe_customer_id:
            for email, user in users.items():
                if user.get("stripe_customer_id") == stripe_customer_id:
                    update_user_record(email, {"membership": "FREE"})
                    break

    return JSONResponse({"status": "ok"})


# ---------- APP PAGE ----------

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)
    plan_ui = get_plan_ui_context(user)

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
            "free_limit": FREE_LIMIT,
            "pro_price": PRO_PRICE,
            "reseller_price": RESELLER_PRICE,
            **plan_ui,
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
    photo: UploadFile = File(None),
):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)
    settings = user["settings"]
    plan_ui = get_plan_ui_context(user)
    plan_info = plan_ui["plan_info"]

    if profit is None:
        profit = settings["default_profit"]

    if local_factor is None:
        local_factor = settings["local_factor"]

    local_factor = normalize_local_factor(local_factor)

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
                "free_limit": FREE_LIMIT,
                "pro_price": PRO_PRICE,
                "reseller_price": RESELLER_PRICE,
                "error": "Free plan limit reached for today. Upgrade inside Membership & Access for more scans.",
                **plan_ui,
            },
        )

    photo_uploaded = photo is not None and bool(getattr(photo, "filename", ""))

    if photo_uploaded and plan_info["ai_photo_enabled"]:
        try:
            detected = await detect_item_from_image(photo)
            if detected:
                query = detected
        except Exception as e:
            print("Image detection failed:", e)

    query = (query or "").strip()
    numeric_query = re.sub(r"\D", "", query)
    if numeric_query and len(numeric_query) >= 8 and len(numeric_query) <= 14:
        query = numeric_query

    if not query:
        if photo_uploaded and plan_info["ai_photo_enabled"]:
            error_message = "Could not identify the item from that photo. Try a clearer photo or enter a search term."
        elif photo_uploaded and not plan_info["ai_photo_enabled"]:
            error_message = "Photo uploaded, but AI photo detection is available on Pro and Reseller. Enter a search term or upgrade."
        else:
            error_message = "No search query detected."

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
                "free_limit": FREE_LIMIT,
                "pro_price": PRO_PRICE,
                "reseller_price": RESELLER_PRICE,
                "error": error_message,
                **plan_ui,
            },
        )

    user = update_user_record(
        email,
        {
            "search_count": user["search_count"] + 1,
            "search_reset_date": str(date.today()),
        },
    )

    sold_prices, active_prices, suggestions, listing = search_ebay(query)
    data = analyze_market(sold_prices, active_prices, condition, profit / 100, local_factor / 100, asking_price)

    if not data:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "data": None,
                "generated_listings": None,
                "listing": listing,
                "email": email,
                "search_count": user["search_count"],
                "user_settings": user["settings"],
                "user": user,
                "free_limit": FREE_LIMIT,
                "pro_price": PRO_PRICE,
                "reseller_price": RESELLER_PRICE,
                "error": "No usable market data was found for that search. Try a clearer model name or photo.",
                **plan_ui,
            },
        )

    data["deal_score_ui"] = clamp_score(data.get("deal_score", 0))
    data["flip_score_ui"] = clamp_score(data.get("flip_score", 0))
    data["deal_score_class"] = deal_score_class(data["deal_score_ui"])
    data["flip_score_class"] = deal_score_class(data["flip_score_ui"])
    data["deal_temperature"] = data.get("deal_temperature", "PASS")
    data["deal_temperature_class"] = deal_temperature_class(data["deal_temperature"])
    data["query_used"] = query
    data["suggestions"] = suggestions or []

    if asking_price is None:
        data["profit_delta"] = None
        data["profit_margin_percent"] = None

    generated_listings = generate_listings(
        query,
        condition,
        data["fast_cash"],
        data["market_price"],
        platforms,
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
            "user_settings": user["settings"],
            "user": user,
            "free_limit": FREE_LIMIT,
            "pro_price": PRO_PRICE,
            "reseller_price": RESELLER_PRICE,
            **plan_ui,
        },
    )


# ---------- SETTINGS PAGE ----------

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "user_settings": user["settings"],
            "success": None,
        },
    )


# ---------- SAVE SETTINGS ----------

@app.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    email: str = Form(""),
    mode: str = Form("simple"),
    default_profit: float = Form(40),
    local_factor: float = Form(80),
    platforms: Optional[List[str]] = Form(None),
):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    if not platforms:
        platforms = ["facebook", "ebay"]

    settings = user["settings"]
    settings["mode"] = mode
    settings["default_profit"] = default_profit
    settings["local_factor"] = local_factor
    settings["platforms"] = platforms

    user = update_user_record(email, {"settings": settings})

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "user_settings": user["settings"],
            "success": "Settings saved successfully.",
        },
    )


# ---------- ACCOUNT PREFERENCES ----------

@app.post("/account/preferences")
async def save_account_preferences(
    request: Request,
    email: str = Form(""),
    local_factor: float = Form(80),
):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    settings = user["settings"]
    settings["local_factor"] = normalize_local_factor(local_factor)
    update_user_record(email, {"settings": settings})

    return RedirectResponse(f"/account?email={email}&notice=Market+preferences+saved", status_code=303)


# ---------- ACCOUNT ----------

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, email: str = "", error: str = "", notice: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)
    plan_ui = get_plan_ui_context(user)

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "error": error,
            "notice": notice,
            **plan_ui,
        },
    )


@app.post("/change-password")
async def change_password(
    request: Request,
    email: str = Form(""),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)

    if not verify_user_password(user, current_password):
        return RedirectResponse(f"/account?email={email}&error=Current+password+verification+failed", status_code=303)

    if len((new_password or "").strip()) < 6:
        return RedirectResponse(f"/account?email={email}&error=New+password+must+be+at+least+6+characters", status_code=303)

    if new_password != confirm_password:
        return RedirectResponse(f"/account?email={email}&error=New+password+and+confirmation+did+not+match", status_code=303)

    update_user_record(email, {"password": new_password.strip()})
    return RedirectResponse(f"/account?email={email}&notice=Password+updated+successfully", status_code=303)


@app.post("/change-email")
async def change_email(
    request: Request,
    email: str = Form(""),
    current_password: str = Form(...),
    new_email: str = Form(...),
    confirm_email: str = Form(...),
):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    new_email = (new_email or "").strip().lower()
    confirm_email = (confirm_email or "").strip().lower()

    if not verify_user_password(user, current_password):
        return RedirectResponse(f"/account?email={email}&error=Current+password+verification+failed", status_code=303)

    if not valid_email(new_email):
        return RedirectResponse(f"/account?email={email}&error=Enter+a+valid+new+email+address", status_code=303)

    if new_email != confirm_email:
        return RedirectResponse(f"/account?email={email}&error=New+email+and+confirmation+did+not+match", status_code=303)

    if new_email != email and get_user(new_email):
        return RedirectResponse(f"/account?email={email}&error=That+email+is+already+in+use", status_code=303)

    updated = change_user_email(email, new_email)
    if not updated:
        return RedirectResponse(f"/account?email={email}&error=Unable+to+update+email+right+now", status_code=303)

    response = RedirectResponse(f"/account?email={new_email}&notice=Email+updated+successfully", status_code=303)
    set_user_cookie(response, new_email)
    return response
