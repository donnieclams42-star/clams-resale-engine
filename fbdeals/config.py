from __future__ import annotations

import os
from typing import Any


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int = 0) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except Exception:
        return default


def env_float(name: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def apify_token() -> str:
    return env_str("APIFY_API_TOKEN") or env_str("APIFY_TOKEN")


def apify_configured() -> bool:
    return bool(apify_token() and (
        env_str("APIFY_FB_MARKETPLACE_ACTOR")
        or env_str("APIFY_FB_TASK_ID")
        or env_str("APIFY_FB_DISCOVERY_NORMAL_TASK_ID")
    ))


def twilio_account_sid() -> str:
    return env_str("TWILIO_ACCOUNT_SID")


def twilio_auth_mode() -> str:
    if twilio_account_sid() and env_str("TWILIO_API_KEY_SID") and env_str("TWILIO_API_KEY_SECRET"):
        return "api_key"
    if twilio_account_sid() and env_str("TWILIO_AUTH_TOKEN"):
        return "auth_token"
    return ""


def twilio_auth_credentials() -> tuple[str, str]:
    if twilio_auth_mode() == "api_key":
        return env_str("TWILIO_API_KEY_SID"), env_str("TWILIO_API_KEY_SECRET")
    return twilio_account_sid(), env_str("TWILIO_AUTH_TOKEN")


def twilio_sender_mode() -> str:
    if env_str("TWILIO_MESSAGING_SERVICE_SID"):
        return "messaging_service"
    if env_str("TWILIO_FROM_NUMBER") or env_str("TWILIO_PHONE_NUMBER"):
        return "from_number"
    return ""


def twilio_from_number() -> str:
    return env_str("TWILIO_FROM_NUMBER") or env_str("TWILIO_PHONE_NUMBER")


def twilio_alert_to_number() -> str:
    return env_str("MARKET_RADAR_ALERT_TO_NUMBER")


def twilio_message_data(body: str) -> dict[str, str]:
    data = {"To": twilio_alert_to_number(), "Body": body}
    if twilio_sender_mode() == "messaging_service":
        data["MessagingServiceSid"] = env_str("TWILIO_MESSAGING_SERVICE_SID")
    elif twilio_from_number():
        data["From"] = twilio_from_number()
    return data


def twilio_configured() -> bool:
    return bool(twilio_auth_mode() and twilio_sender_mode() and twilio_alert_to_number())


def ingest_secret() -> str:
    return env_str("MARKET_RADAR_INGEST_SECRET") or env_str("APIFY_WEBHOOK_SECRET")


def settings() -> dict[str, Any]:
    actor = env_str("APIFY_FB_MARKETPLACE_ACTOR") or env_str("APIFY_FB_RIGEL_ACTOR") or "datascrapers/facebook-marketplace"
    task_id = env_str("APIFY_FB_TASK_ID") or env_str("APIFY_FB_DISCOVERY_NORMAL_TASK_ID")
    return {
        "apify_actor": actor,
        "apify_task_id": task_id,
        "apify_configured": apify_configured(),
        "default_location": env_str("MARKET_RADAR_DEFAULT_LOCATION") or env_str("MARKETPLACE_DEFAULT_LOCATION") or "Atlantic City, New Jersey",
        "default_radius_km": env_int("MARKET_RADAR_DEFAULT_RADIUS_KM", 80),
        "max_items_per_watch": env_int("MARKET_RADAR_MAX_ITEMS_PER_WATCH", 12),
        "max_watches_per_cycle": env_int("MARKET_RADAR_MAX_WATCHES_PER_CYCLE", 2),
        "min_scan_minutes": env_int("MARKET_RADAR_MIN_SCAN_MINUTES", 20),
        "scan_interval_minutes": env_int("MARKET_RADAR_SCAN_INTERVAL_MINUTES", 40),
        "deep_analyze_limit": env_int("MARKET_RADAR_DEEP_ANALYZE_LIMIT", 6),
        "ebay_fee_rate": env_float("MARKET_RADAR_EBAY_FEE_RATE", 0.1325),
        "ebay_fee_fixed": env_float("MARKET_RADAR_EBAY_FEE_FIXED", 0.40),
        "shipping_estimate": env_float("MARKET_RADAR_SHIPPING_ESTIMATE", 12.0),
        "local_pickup_shipping": env_float("MARKET_RADAR_LOCAL_PICKUP_SHIPPING", 0.0),
        "min_profit": env_float("MARKET_RADAR_MIN_PROFIT", 40.0),
        "min_roi_pct": env_float("MARKET_RADAR_MIN_ROI_PCT", 25.0),
        "hot_profit": env_float("MARKET_RADAR_HOT_PROFIT", 80.0),
        "hot_roi_pct": env_float("MARKET_RADAR_HOT_ROI_PCT", 50.0),
        "hot_max_age_hours": env_float("MARKET_RADAR_HOT_MAX_AGE_HOURS", 6.0),
        "watch_profit": env_float("MARKET_RADAR_WATCH_PROFIT", 20.0),
        "watch_roi_pct": env_float("MARKET_RADAR_WATCH_ROI_PCT", 12.0),
        "sms_instant_enabled": env_bool("MARKET_RADAR_SMS_INSTANT", True),
        "sms_digest_enabled": env_bool("MARKET_RADAR_SMS_DIGEST", True),
        "sms_digest_hours": env_int("MARKET_RADAR_SMS_DIGEST_HOURS", 6),
        "sms_max_per_hour": env_int("MARKET_RADAR_SMS_MAX_PER_HOUR", 8),
        "sms_max_per_day": env_int("MARKET_RADAR_SMS_MAX_PER_DAY", 20),
        "price_drop_pct": env_float("MARKET_RADAR_PRICE_DROP_PCT", 0.10),
        "price_drop_amount": env_float("MARKET_RADAR_PRICE_DROP_AMOUNT", 15.0),
        "twilio_configured": twilio_configured(),
        "ingest_secret_present": bool(ingest_secret()),
        "public_base_url": env_str("APP_BASE_URL") or env_str("PUBLIC_BASE_URL") or "https://market-radar.fly.dev",
        "scheduler_enabled": env_bool("MARKETPLACE_ENABLE_SCHEDULER", False),
    }
