from typing import List, Optional
import os
import re
import sys
import json
import time
import threading
import base64
from uuid import uuid4
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ebay import search_ebay
from market_analysis import analyze_market
from listing_generator import generate_listings

from dj_deal_project.utils.model_parser import normalize_text, detect_category, is_accessory_listing


try:
    from openai import OpenAI
except Exception:
    OpenAI = None

import stripe
from supabase import create_client, Client

app = FastAPI()


# ---------- FIXED PATHS FOR RENDER ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)



# ---------- RADAR INTEGRATION ----------

RADAR_DIR = os.path.join(BASE_DIR, "dj_deal_project")
RADAR_CACHE_DIR = os.path.join(BASE_DIR, "cache")
RADAR_RESULTS_FILE = os.path.join(RADAR_CACHE_DIR, "radar_results.json")
RADAR_STATUS_FILE = os.path.join(RADAR_CACHE_DIR, "radar_status.json")
RADAR_ANALYSIS_CACHE_FILE = os.path.join(RADAR_CACHE_DIR, "radar_analysis_cache.json")
os.makedirs(RADAR_CACHE_DIR, exist_ok=True)

_radar_thread = None
_radar_started = False
_radar_lock = threading.Lock()
_radar_file_lock = threading.Lock()
_radar_cycle_count = 0


def _read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    with _radar_file_lock:
        tmp_path = f"{path}.{uuid4().hex}.tmp"
        for attempt in range(5):
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp_path, path)
                return
            except PermissionError:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                time.sleep(0.15 * (attempt + 1))
        raise


def get_radar_status():
    status = _read_json_file(RADAR_STATUS_FILE, {}) or {}
    last_success = status.get("last_success")
    live = False
    if last_success:
        try:
            last_dt = datetime.fromisoformat(last_success)
            live = (datetime.utcnow() - last_dt).total_seconds() < 3600
        except Exception:
            live = False
    status.setdefault("status", "idle")
    status.setdefault("message", "Radar idle")
    status.setdefault("sources", [])
    status.setdefault("deals_found_today", 0)
    status["live"] = live
    return status


def get_radar_results(limit=None):
    deals = _read_json_file(RADAR_RESULTS_FILE, []) or []
    if limit is not None:
        return deals[:limit]
    return deals


def _category_label(raw: str) -> str:
    mapping = {
        "phone": "Phones",
        "console": "Gaming",
        "tool": "Tools",
        "cards": "Cards & Collectibles",
        "electronics": "Electronics",
        "liquidation": "Local Lots / Bulk",
        "repair": "Parts / Repair",
        "other": "Other Deals",
    }
    return mapping.get((raw or "other").lower(), "Other Deals")


def _assign_deal_category(deal: dict) -> str:
    title = normalize_text(str(deal.get("title") or ""))
    keyword = normalize_text(str(deal.get("search_keyword") or ""))
    text = f"{title} {keyword}".strip()
    base = detect_category(text)
    if any(term in text for term in ["repair", "for parts", "parts", "broken", "cracked", "not working", "as is", "untested"]):
        return "repair" if base not in {"cards"} else "cards"
    if any(term in text for term in ["lot", "bundle", "collection", "mixed lot", "bulk", "garage sale", "moving sale", "estate sale", "cleanout"]):
        if base in {"tool", "cards", "electronics", "console", "phone"}:
            return base
        return "liquidation"
    return base or "other"


def _confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(value or "").strip().lower(), 0)


def _deal_sort_key(deal: dict):
    return (
        float(deal.get("edge_score") or deal.get("deal_score") or 0),
        float(deal.get("profit") or 0),
        _confidence_rank(deal.get("confidence")),
    )


def build_radar_page_context(limit: int = 50) -> dict:
    deals = get_radar_results(limit=limit)
    for deal in deals:
        category_key = str(deal.get("category") or "").strip().lower() or _assign_deal_category(deal)
        deal["category"] = category_key
        deal["category_label"] = _category_label(category_key)
        deal["display_image"] = str(deal.get("image") or deal.get("image_url") or "").strip()
    top_deals = sorted(deals, key=_deal_sort_key, reverse=True)[:6]
    grouped = []
    bucket_order = ["phone", "console", "tool", "cards", "electronics", "repair", "liquidation", "other"]
    for key in bucket_order:
        items = [deal for deal in deals if deal.get("category") == key]
        if not items:
            continue
        items = sorted(items, key=_deal_sort_key, reverse=True)[:12]
        grouped.append({"key": key, "label": _category_label(key), "deals": items})
    return {"radar_status": get_radar_status(), "radar_deals": deals, "radar_top_deals": top_deals, "radar_groups": grouped}


def get_radar_dashboard_context(limit=4):
    return build_radar_page_context(limit=limit)


def _update_radar_status(**kwargs):
    current = get_radar_status()
    current.update(kwargs)
    current["updated_at"] = datetime.utcnow().isoformat()
    _write_json_file(RADAR_STATUS_FILE, current)


def _get_analysis_cache():
    return _read_json_file(RADAR_ANALYSIS_CACHE_FILE, {}) or {}


def _set_analysis_cache(cache):
    _write_json_file(RADAR_ANALYSIS_CACHE_FILE, cache)


def _clean_radar_query(deal: dict) -> str:
    query = str(deal.get("search_keyword") or "").strip().lower()
    source = str(deal.get("source") or deal.get("market") or "").strip().lower()
    title = str(deal.get("title") or "").lower()
    title = re.sub(r"\$[\d,]+(?:\.\d{1,2})?", " ", title)
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    cleaned_title = " ".join(title.split()[:6])
    if source == "facebook" and cleaned_title:
        return cleaned_title
    if query:
        return query
    return cleaned_title


def _is_loose_fb_candidate(deal: dict, profit: float, margin: float) -> bool:
    source = str(deal.get("source") or deal.get("market") or "").strip().lower()
    if source != "facebook":
        return False
    title = str(deal.get("title") or "").lower()
    keyword = str(deal.get("search_keyword") or "").lower()
    text = f"{title} {keyword}".strip()
    trigger_terms = [
        "bundle", "lot", "broken", "cracked", "untested", "as is", "for parts", "parts only",
        "locked", "icloud", "no power", "must sell", "moving", "garage sale", "estate", "cheap",
        "no charger", "no cords", "random electronics", "junk drawer", "tool bundle", "video game lot",
    ]
    low_price = float(deal.get("price") or 0) <= 120
    triggered = any(term in text for term in trigger_terms)
    return triggered and (profit >= 10 or margin >= 0.05 or low_price)


def _source_enabled_for_cycle(source_name: str, cycle_count: int, radar_config) -> bool:
    name = source_name.lower()
    if name == "ebay":
        return bool(getattr(radar_config, "ENABLE_EBAY", True)) and (cycle_count % max(1, int(getattr(radar_config, "EBAY_SCAN_FREQUENCY", 1) or 1)) == 0)
    if name == "mercari":
        return bool(getattr(radar_config, "ENABLE_MERCARI", True)) and (cycle_count % max(1, int(getattr(radar_config, "MERCARI_SCAN_FREQUENCY", 1) or 1)) == 0)
    if name == "offerup":
        return bool(getattr(radar_config, "ENABLE_OFFERUP", True)) and (cycle_count % max(1, int(getattr(radar_config, "OFFERUP_SCAN_FREQUENCY", 2) or 2)) == 0)
    if name == "facebook":
        return bool(getattr(radar_config, "ENABLE_FACEBOOK", True)) and (cycle_count % max(1, int(getattr(radar_config, "FB_SCAN_FREQUENCY", 8) or 8)) == 0)
    return False


def _build_vetted_deal(deal: dict, analysis_cache: dict, radar_config):
    query = _clean_radar_query(deal)
    if not query:
        return None
    now_ts = time.time()
    cache_ttl = int(getattr(radar_config, "RADAR_ANALYSIS_CACHE_SECONDS", 21600) or 21600)
    cached = analysis_cache.get(query)
    prices = []
    listing = None
    if cached and now_ts - float(cached.get("ts", 0)) < cache_ttl:
        prices = cached.get("prices", []) or []
        listing = cached.get("listing")
    else:
        prices, _active_prices, _suggestions, listing = search_ebay(query)
        analysis_cache[query] = {"ts": now_ts, "prices": prices, "listing": listing}
    if not prices:
        return None
    asking_price = float(deal.get("price") or 0)
    if asking_price <= 0:
        return None
    analysis = analyze_market(prices, [], "A", 0.30, getattr(radar_config, "LOCAL_RESALE_FACTOR", 0.82), asking_price=asking_price)
    if not analysis:
        return None
    profit = float(analysis.get("profit_delta") or 0)
    margin = profit / asking_price if asking_price > 0 else 0
    source_name = str(deal.get("source") or deal.get("market") or "").strip().lower()
    min_profit = float(getattr(radar_config, "MIN_PROFIT", 10) or 10)
    min_margin = float(getattr(radar_config, "RADAR_MIN_MARGIN", 0.10) or 0.10)
    if source_name == "facebook":
        min_profit = float(getattr(radar_config, "FB_MIN_PROFIT", 10) or 10)
        min_margin = float(getattr(radar_config, "FB_MIN_MARGIN", 0.05) or 0.05)
    elif source_name == "ebay":
        min_profit = float(getattr(radar_config, "EBAY_MIN_PROFIT", min_profit) or min_profit)
        min_margin = float(getattr(radar_config, "EBAY_MIN_MARGIN", min_margin) or min_margin)
    elif source_name == "mercari":
        min_profit = float(getattr(radar_config, "MERCARI_MIN_PROFIT", min_profit) or min_profit)
        min_margin = float(getattr(radar_config, "MERCARI_MIN_MARGIN", min_margin) or min_margin)
    elif source_name == "offerup":
        min_profit = float(getattr(radar_config, "OFFERUP_MIN_PROFIT", min_profit) or min_profit)
        min_margin = float(getattr(radar_config, "OFFERUP_MIN_MARGIN", min_margin) or min_margin)
    if profit < min_profit or margin < min_margin:
        if source_name != "facebook" or not _is_loose_fb_candidate(deal, profit, margin):
            return None
    result = dict(deal)
    result["market_value"] = round(float(analysis.get("local_market_value") or analysis.get("market_price") or 0), 2)
    result["resale"] = result["market_value"]
    result["profit"] = round(profit, 2)
    result["score"] = round(margin, 2)
    result["deal_score"] = int(analysis.get("deal_score") or 0)
    result["edge_score"] = int(analysis.get("deal_score") or 0)
    result["confidence"] = analysis.get("confidence") or ("High" if len(prices) >= 12 else "Medium" if len(prices) >= 6 else "Low")
    result["source"] = result.get("source") or result.get("market") or ""
    result["url"] = result.get("url") or result.get("link") or (listing or {}).get("url") or ""
    result["best_market"] = analysis.get("best_platform") or "Facebook Marketplace"
    result["sold_count"] = int(analysis.get("sold_count") or len(prices))
    result["category"] = _assign_deal_category(result)
    result["category_label"] = _category_label(result["category"])
    result["display_image"] = str(result.get("image") or result.get("image_url") or "").strip()
    return result


def _run_radar_cycle():
    global _radar_cycle_count
    _radar_cycle_count += 1

    if RADAR_DIR not in sys.path:
        sys.path.insert(0, RADAR_DIR)

    import config as radar_config
    from scanners.ebay_scanner import scan_ebay
    from scanners.mercari_scanner import scan_mercari
    from scanners.offerup_scanner import scan_offerup
    from scanners.fb_scanner import scan_facebook
    from filters.scam_filter import is_scam_listing
    from alerts.discord_alert import send_discord_alert
    from utils.seen_deals import filter_new

    source_state = get_radar_status().get("source_state", {}) or {}
    scanner_jobs = []
    possible_jobs = [
        ("eBay", scan_ebay),
        ("Mercari", scan_mercari),
        ("OfferUp", scan_offerup),
        ("Facebook", scan_facebook),
    ]
    now = time.time()
    for label, fn in possible_jobs:
        state = source_state.get(label, {}) or {}
        cooldown_until = float(state.get("cooldown_until", 0) or 0)
        if cooldown_until and now < cooldown_until:
            continue
        if _source_enabled_for_cycle(label, _radar_cycle_count, radar_config):
            scanner_jobs.append((label, fn))

    if not scanner_jobs:
        _update_radar_status(message="All sources are idle or cooling down", sources=[], source_state=source_state)
        return []

    raw_deals = []
    active_sources = []
    with ThreadPoolExecutor(max_workers=len(scanner_jobs)) as executor:
        futures = {executor.submit(fn): label for label, fn in scanner_jobs}
        for future in as_completed(futures):
            label = futures[future]
            try:
                deals = future.result() or []
                raw_deals.extend(deals)
                active_sources.append(label)
                _update_radar_status(message=f"{label} returned {len(deals)} raw deals", source_state=source_state)
                source_state[label] = {"last_success": datetime.utcnow().isoformat(), "cooldown_until": 0, "last_error": ""}
            except Exception as e:
                cooldown = int(getattr(radar_config, "SOURCE_FAILURE_COOLDOWN_SECONDS", 1800) or 1800)
                source_state[label] = {"last_error": str(e), "cooldown_until": now + cooldown}
                _update_radar_status(last_error=f"{label}: {e}")

    new_deals = filter_new(raw_deals)
    _update_radar_status(
        raw_deals_this_cycle=len(raw_deals),
        new_raw_deals_this_cycle=len(new_deals),
    )
    analysis_cache = _get_analysis_cache()
    max_calls = int(getattr(radar_config, "RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE", 6) or 6)
    approved = []
    analysis_calls = 0

    for deal in sorted(new_deals, key=lambda d: float(d.get("price") or 999999)):
        title = str(deal.get("title", "") or "")
        if title and is_scam_listing(title):
            continue
        query = _clean_radar_query(deal)
        if not query:
            continue
        if is_accessory_listing(str(deal.get("title") or ""), str(deal.get("search_keyword") or query)):
            continue
        cached = analysis_cache.get(query)
        fresh_cache = bool(cached and time.time() - float(cached.get("ts", 0)) < float(getattr(radar_config, "RADAR_ANALYSIS_CACHE_SECONDS", 21600) or 21600))
        if not fresh_cache:
            if analysis_calls >= max_calls:
                continue
            analysis_calls += 1
        try:
            result = _build_vetted_deal(deal, analysis_cache, radar_config)
            if not result:
                continue
            approved.append(result)
        except Exception as e:
            _update_radar_status(last_error=f"analysis: {e}")

    _set_analysis_cache(analysis_cache)

    # Do NOT persistently filter approved deals a second time.
    # raw_deals were already deduped via filter_new(raw_deals) above.
    # A second persistent filter here can hide legitimate approved deals.
    seen_cycle = set()
    unique_approved = []
    for deal in approved:
        key = (
            str(deal.get("url") or deal.get("link") or "").strip().lower(),
            str(deal.get("title") or "").strip().lower(),
            round(float(deal.get("price") or 0), 2),
        )
        if key in seen_cycle:
            continue
        seen_cycle.add(key)
        unique_approved.append(deal)

    approved = unique_approved
    approved.sort(key=_deal_sort_key, reverse=True)
    approved = approved[:50]
    _write_json_file(RADAR_RESULTS_FILE, approved)

    status_msg = (
        f"{len(approved)} vetted deals ready from {len(new_deals)} new raw deals (analysis calls: {analysis_calls})"
        if approved else
        f"No vetted deals in the latest cycle ({len(new_deals)} new raw deals scanned, analysis calls: {analysis_calls})"
    )
    _update_radar_status(
        running=True,
        live=True,
        status="live",
        message=status_msg,
        last_cycle=datetime.utcnow().isoformat(),
        last_success=datetime.utcnow().isoformat(),
        deals_found_today=len(approved),
        sources=active_sources,
        source_state=source_state,
        analysis_calls_this_cycle=analysis_calls,
        last_error="",
    )

    if approved:
        alert_errors = []
        for deal in approved[: min(3, len(approved))]:
            try:
                send_discord_alert(deal)
            except Exception as e:
                alert_errors.append(str(e))
        if alert_errors:
            _update_radar_status(last_error="; ".join(alert_errors[:3]))

    return approved


def _radar_background_loop():
    while True:
        try:
            _update_radar_status(running=True, status="scanning", message="Scanning for vetted deals...")
            deals = _run_radar_cycle()
            wait_time = int(getattr(__import__("config"), "SCAN_INTERVAL", 900) or 900) if deals else max(900, int(getattr(__import__("config"), "SCAN_INTERVAL", 900) or 900))
        except Exception as e:
            _update_radar_status(running=False, status="error", message="Radar hit an error", last_error=str(e), last_cycle=datetime.utcnow().isoformat())
            wait_time = 1800
        time.sleep(wait_time)


@app.on_event("startup")
def start_radar_background_worker():
    global _radar_thread, _radar_started
    if os.getenv("RADAR_AUTOSTART", "1") != "1":
        _update_radar_status(running=False, status="disabled", message="Radar autostart is disabled")
        return
    with _radar_lock:
        if _radar_started:
            return
        _radar_started = True
        _radar_thread = threading.Thread(target=_radar_background_loop, daemon=True, name="clams-radar-worker")
        _radar_thread.start()
        try:
            _update_radar_status(running=True, status="starting", message="Radar worker booting...")
        except Exception:
            pass


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
client = OpenAI(api_key=OPENAI_API_KEY) if (OpenAI is not None and OPENAI_API_KEY) else None

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
    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

    return templates.TemplateResponse("landing.html", {"request": request})


# ---------- LOGIN PAGE ----------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", email: str = "", notice: str = ""):
    cookie_email = request.cookies.get("clams_user", "").strip().lower()
    if cookie_email:
        return RedirectResponse(f"/app?email={cookie_email}", status_code=303)

    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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
    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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

    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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
            **get_radar_dashboard_context(),
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
        
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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
                **get_radar_dashboard_context(),
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

        
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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
                **get_radar_dashboard_context(),
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

    try:
        sold_prices, active_prices, suggestions, listing = search_ebay(query)
        data = analyze_market(sold_prices, active_prices, condition, profit / 100, local_factor / 100, asking_price)

        if not data:
            
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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
                    **get_radar_dashboard_context(),
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
    except Exception as e:
        print("Analyze failed:", e)
        
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

    return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "data": None,
                "generated_listings": None,
                "listing": None,
                "email": email,
                "search_count": user["search_count"],
                "user_settings": user["settings"],
                "user": user,
                "free_limit": FREE_LIMIT,
                "pro_price": PRO_PRICE,
                "reseller_price": RESELLER_PRICE,
                "error": "Search failed on the server. Try the item name manually or try the photo again.",
                **get_radar_dashboard_context(),
                **plan_ui,
            },
        )

    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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
            **get_radar_dashboard_context(),
            **plan_ui,
        },
    )


# ---------- RADAR PAGE ----------

@app.get("/radar", response_class=HTMLResponse)
async def radar_page(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)
    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

    return templates.TemplateResponse(
        "radar.html",
        {
            "request": request,
            "email": email,
            "user": user,
            **build_radar_page_context(limit=50),
        },
    )


# ---------- SETTINGS PAGE ----------



@app.get("/radar/test-discord")
async def radar_test_discord(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    try:
        if RADAR_DIR not in sys.path:
            sys.path.insert(0, RADAR_DIR)

        from alerts.discord_alert import send_discord_alert

        test_deal = {
            "title": "CLAMS Radar Discord Test",
            "price": 0,
            "market_value": 100,
            "profit": 100,
            "confidence": "high",
            "source": "System Test",
            "url": f"{request.base_url}radar?email={email}",
            "edge_score": 100,
        }

        ok = bool(send_discord_alert(test_deal))
        status = get_radar_status()
        status["last_discord_test"] = datetime.utcnow().isoformat()
        status["discord_test_ok"] = ok
        status["message"] = "Discord test notification sent" if ok else "Discord test attempted but alert module reported failure"
        _write_json_file(RADAR_STATUS_FILE, status)

        return JSONResponse({
            "ok": ok,
            "message": "Discord test notification sent" if ok else "Discord test attempted but alert module reported failure"
        })
    except Exception as e:
        status = get_radar_status()
        status["last_discord_test"] = datetime.utcnow().isoformat()
        status["discord_test_ok"] = False
        status["last_error"] = f"Discord test failed: {e}"
        _write_json_file(RADAR_STATUS_FILE, status)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)

    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)

    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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

    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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

    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

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


# ---------- TEMU FLIPS / ADMIN EXTENSIONS ----------

TEMU_RESULTS_FILE = os.path.join(RADAR_CACHE_DIR, "temu_flips_results.json")
TEMU_STATUS_FILE = os.path.join(RADAR_CACHE_DIR, "temu_flips_status.json")
_temu_thread = None
_temu_started = False
_temu_lock = threading.Lock()


def _read_temu_results():
    return _read_json_file(TEMU_RESULTS_FILE, []) or []


def _write_temu_results(items):
    _write_json_file(TEMU_RESULTS_FILE, items)


def _update_temu_status(**kwargs):
    current = _read_json_file(TEMU_STATUS_FILE, {}) or {}
    current.update(kwargs)
    current["updated_at"] = datetime.utcnow().isoformat()
    _write_json_file(TEMU_STATUS_FILE, current)


def get_temu_status():
    status = _read_json_file(TEMU_STATUS_FILE, {}) or {}
    status.setdefault("status", "idle")
    status.setdefault("message", "Temu-flips idle")
    status.setdefault("count", 0)
    return status


def _temu_seed_items():
    return [
        {"query": "led strip lights kit", "label": "LED Light Kits", "category": "home gadgets"},
        {"query": "magnetic phone mount", "label": "Phone Mounts", "category": "car gadgets"},
        {"query": "car organizer seat gap", "label": "Car Organizers", "category": "car gadgets"},
        {"query": "usb desk fan mini", "label": "Mini Gadgets", "category": "home gadgets"},
        {"query": "pet grooming glove", "label": "Pet Items", "category": "pet"},
        {"query": "silicone air fryer liners", "label": "Kitchen Gadgets", "category": "kitchen"},
        {"query": "makeup brush cleaner bowl", "label": "Beauty Tools", "category": "beauty"},
        {"query": "portable vacuum cleaner mini", "label": "Portable Gadgets", "category": "home gadgets"},
        {"query": "under cabinet lights motion sensor", "label": "Lighting", "category": "home gadgets"},
        {"query": "drawer organizer set", "label": "Organizers", "category": "home gadgets"},
        {"query": "resistance bands set", "label": "Fitness Accessories", "category": "fitness"},
        {"query": "cable clips organizer", "label": "Desk Accessories", "category": "office"},
    ]


def _looks_like_temu_flip_title(title: str) -> bool:
    title_n = normalize_text(title)
    hot_terms = [
        "led", "rgb", "usb", "portable", "wireless", "organizer", "holder", "mount",
        "grooming", "liner", "vacuum", "sensor", "light", "mini", "beauty", "pet"
    ]
    reject_terms = [
        "iphone", "samsung", "ps5", "ps4", "xbox", "nintendo", "graphics card", "gpu",
        "cartridge", "disc", "hoodie", "shirt", "bag", "knob", "switch", "sensor replacement"
    ]
    return any(term in title_n for term in hot_terms) and not any(term in title_n for term in reject_terms)


def _estimate_supplier_cost(avg_price: float) -> float:
    if avg_price <= 12:
        return round(avg_price * 0.28, 2)
    if avg_price <= 20:
        return round(avg_price * 0.24, 2)
    return round(avg_price * 0.22, 2)


def _build_temu_flip_from_query(seed: dict):
    query = seed["query"]
    prices, _active, _suggestions, listing = search_ebay(query)
    if not prices or len(prices) < 8:
        return None
    avg_price = round(sum(prices[:20]) / min(len(prices), 20), 2)
    sold_count = len(prices)
    if avg_price < 8 or avg_price > 40:
        return None
    est_cost = _estimate_supplier_cost(avg_price)
    fees = round(avg_price * 0.15, 2)
    shipping = 5.00
    profit = round(avg_price - fees - shipping - est_cost, 2)
    sell_through = min(0.95, max(0.45, sold_count / 40.0))
    if profit < 10 or sell_through < 0.60:
        return None
    title = listing.get("title") if isinstance(listing, dict) else query.title()
    if not _looks_like_temu_flip_title(title):
        return None
    try:
        from urllib.parse import quote_plus
        search_q = quote_plus(title)
    except Exception:
        search_q = title.replace(" ", "+")
    confidence = "HIGH" if sell_through >= 0.75 and profit >= 14 else "MEDIUM"
    trend = "🔥 HOT FLIP" if confidence == "HIGH" else "✅ GOOD FLIP"
    return {
        "title": title,
        "category_label": seed.get("label") or "Temu-flip",
        "category": seed.get("category") or "temu-flip",
        "avg_price": avg_price,
        "est_cost": est_cost,
        "profit": profit,
        "sell_through": round(sell_through, 2),
        "sell_through_pct": int(round(sell_through * 100)),
        "confidence": confidence,
        "trend": trend,
        "ebay_url": listing.get("url") if isinstance(listing, dict) else "",
        "temu_search_url": f"https://www.temu.com/search_result.html?search_key={search_q}",
        "google_search_url": f"https://www.google.com/search?q=temu+{search_q}",
        "score": round((sell_through * 40) + (profit * 2), 2),
    }


def _run_temu_cycle():
    items = []
    for seed in _temu_seed_items():
        try:
            item = _build_temu_flip_from_query(seed)
            if item:
                items.append(item)
        except Exception:
            continue
    items.sort(key=lambda x: (x.get("score", 0), x.get("profit", 0)), reverse=True)
    items = items[:20]
    _write_temu_results(items)
    _update_temu_status(
        status="live",
        message=f"{len(items)} Temu-flips ready",
        count=len(items),
        last_success=datetime.utcnow().isoformat(),
    )
    return items


def _temu_background_loop():
    while True:
        try:
            _update_temu_status(status="scanning", message="Scanning Temu-flips candidates...")
            _run_temu_cycle()
            wait_time = int(os.getenv("TEMU_FLIPS_INTERVAL", "900") or 900)
        except Exception as e:
            _update_temu_status(status="error", message="Temu-flips hit an error", last_error=str(e))
            wait_time = 1800
        time.sleep(wait_time)


@app.on_event("startup")
def start_temu_background_worker():
    global _temu_thread, _temu_started
    if os.getenv("TEMU_FLIPS_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        _update_temu_status(status="disabled", message="Temu-flips disabled")
        return
    with _temu_lock:
        if _temu_started:
            return
        _temu_started = True
        _temu_thread = threading.Thread(target=_temu_background_loop, daemon=True, name="clams-temu-worker")
        _temu_thread.start()


def get_radar_dashboard_context(limit=4):
    ctx = build_radar_page_context(limit=limit)
    deals = ctx.get("radar_deals") or []
    ctx["radar_has_hits"] = bool(deals)
    ctx["radar_indicator_count"] = len(deals)
    return ctx


@app.get("/temu", response_class=HTMLResponse)
async def temu_page(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)
    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)
    items = _read_temu_results()
    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

    return templates.TemplateResponse(
        "temu_flips.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "temu_flips": items,
            "top_flips": items[:5],
            "temu_status": get_temu_status(),
        },
    )


@app.get("/api/clear-deals")
async def clear_deals(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)
    try:
        from dj_deal_project.utils.seen_deals import clear_seen_cache, load_seen
        clear_seen_cache()
        _write_json_file(RADAR_RESULTS_FILE, [])
        _write_temu_results([])
        _update_radar_status(message="Deals cleared manually", deals_found_today=0)
        _update_temu_status(message="Temu-flips cleared manually", count=0)
        return RedirectResponse(f"/app?email={email}", status_code=303)
    except Exception:
        return RedirectResponse(f"/app?email={email}", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, email: str = ""):
    email = get_request_email(request, email)
    if not email:
        return RedirectResponse("/login", status_code=303)
    user = ensure_user_exists(email)
    user = ensure_daily_reset(user)
    if not user.get("is_admin"):
        return RedirectResponse(f"/app?email={email}", status_code=303)
    seen_counts = {"total": 0}
    try:
        from dj_deal_project.utils.seen_deals import load_seen
        seen = load_seen()
        seen_counts = {
            "links": len(seen.get("links", {})),
            "fingerprints": len(seen.get("fingerprints", {})),
            "titles": len(seen.get("titles", {})),
        }
        seen_counts["total"] = sum(seen_counts.values())
    except Exception:
        pass
    
    temu_access = {
        "visible_count": len(flips),
        "all_count": len(flips)
    }
    membership_tier = user.get("membership", "FREE")

    return templates.TemplateResponse(
        "admin_panel.html",
        {
            "request": request,
            "email": email,
            "user": user,
            "radar_status": get_radar_status(),
            "radar_count": len(get_radar_results()),
            "temu_count": len(_read_temu_results()),
            "seen_counts": seen_counts,
        },
    )
