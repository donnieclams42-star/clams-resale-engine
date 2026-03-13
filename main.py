from typing import List, Optional

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ebay import search_ebay
from market_analysis import analyze_market
from listing_generator import generate_listings

from openai import OpenAI
import base64
import os


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

users = {}

INVITE_CODE = "betatesting123"

BETA_MODE = True
FREE_LIMIT = 10


# ---------- OPENAI CLIENT ----------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------- IMAGE DETECTION (ACCURACY BOOSTED) ----------

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
You are identifying resale items for an eBay market analysis tool.

Return the BEST SHORT eBay search phrase.

Rules:
- Only return the product search phrase
- Include brand and model if visible
- Electronics: include model + storage if visible
- Tools: include brand and product line
- Do not describe the photo
- Do not add extra words
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
    return FileResponse("static/manifest.json")


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse("static/service-worker.js")


# ---------- ROUTES ----------


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
        users[email] = {
            "password": password,
            "membership": "PRO",
            "search_count": 0
        }

    if users[email]["password"] != password:
        return {"error": "Incorrect password"}

    return RedirectResponse(f"/app?email={email}", status_code=303)


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request, email: str = ""):

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

    user = users.get(email, {})

    if email in users:
        users[email]["search_count"] += 1

    # ---------- IMAGE SEARCH ----------
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


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, email: str = ""):

    user = users.get(email, {})

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "email": email,
            "user": user
        }
    )