from __future__ import annotations

import os
from dataclasses import dataclass


def env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


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


@dataclass
class DealBrainConfig:
    ebay_fee_rate: float
    ebay_fee_fixed: float
    shipping_estimate: float
    local_pickup_shipping: float
    min_profit: float
    min_roi_pct: float
    strong_profit: float
    strong_roi_pct: float
    hot_profit: float
    hot_roi_pct: float
    monster_profit: float
    monster_roi_pct: float
    watch_profit: float
    watch_roi_pct: float
    hot_max_age_hours: float
    anomaly_discount_pct: float
    extreme_discount_pct: float
    deep_max_per_run: int
    sms_enabled: bool
    sms_max_per_hour: int
    sms_max_per_day: int
    ebay_sniper_enabled: bool
    ebay_scheduler_enabled: bool
    ebay_max_queries: int
    ebay_max_items: int
    monster_discount_pct: float
    hot_discount_pct: float
    packaging_cost: float
    insurance_cost: float
    return_reserve_rate: float
    alert_dry_run: bool
    scale_level: int
    level1_max_fb_runs_per_day: int
    level1_max_ebay_calls_per_day: int
    level1_max_stage2_per_day: int
    level1_max_provider_dollars_per_day: float
    first_profit_mode: bool
    first_profit_live: bool
    first_profit_active_haircut: float
    first_profit_phone_haircut: float
    first_profit_repair_haircut: float
    first_profit_min_profit: float
    first_profit_apify_daily_cap_usd: float
    first_profit_return_reserve_rate: float
    first_profit_unknown_inbound_reserve: float
    first_profit_buyer_tax_rate: float
    first_profit_hot_clean_comps: int
    first_profit_monster_clean_comps: int
    first_profit_sample_high: int
    first_profit_sample_medium: int
    first_profit_sample_low: int
    first_profit_hot_discount_pct: float
    first_profit_monster_discount_pct: float
    first_profit_acquisition_friction: float

    @property
    def twilio_ok(self) -> bool:
        return twilio_configured()

    def apify_daily_cap_usd(self) -> float:
        return min(float(self.level1_max_provider_dollars_per_day or 3.0), float(self.first_profit_apify_daily_cap_usd or 0.25))


def get_config() -> DealBrainConfig:
    return DealBrainConfig(
        ebay_fee_rate=env_float("MARKET_RADAR_EBAY_FEE_RATE", 0.1325),
        ebay_fee_fixed=env_float("MARKET_RADAR_EBAY_FEE_FIXED", 0.40),
        shipping_estimate=env_float("MARKET_RADAR_SHIPPING_ESTIMATE", 12.0),
        local_pickup_shipping=env_float("MARKET_RADAR_LOCAL_PICKUP_SHIPPING", 0.0),
        min_profit=env_float("MARKET_RADAR_MIN_PROFIT", 50.0),
        min_roi_pct=env_float("MARKET_RADAR_MIN_ROI_PCT", 25.0),
        strong_profit=env_float("MARKET_RADAR_STRONG_PROFIT", 50.0),
        strong_roi_pct=env_float("MARKET_RADAR_STRONG_ROI_PCT", 25.0),
        hot_profit=env_float("MARKET_RADAR_HOT_PROFIT", 75.0),
        hot_roi_pct=env_float("MARKET_RADAR_HOT_ROI_PCT", 40.0),
        monster_profit=env_float("MARKET_RADAR_MONSTER_PROFIT", 125.0),
        monster_roi_pct=env_float("MARKET_RADAR_MONSTER_ROI_PCT", 60.0),
        watch_profit=env_float("MARKET_RADAR_WATCH_PROFIT", 20.0),
        watch_roi_pct=env_float("MARKET_RADAR_WATCH_ROI_PCT", 12.0),
        hot_max_age_hours=env_float("MARKET_RADAR_HOT_MAX_AGE_HOURS", 6.0),
        anomaly_discount_pct=env_float("DEALBRAIN_ANOMALY_DISCOUNT_PCT", 25.0),
        extreme_discount_pct=env_float("DEALBRAIN_EXTREME_DISCOUNT_PCT", 45.0),
        deep_max_per_run=env_int("DEALBRAIN_DEEP_MAX", 6),
        sms_enabled=env_bool("MARKET_RADAR_SMS_INSTANT", True),
        sms_max_per_hour=env_int("MARKET_RADAR_SMS_MAX_PER_HOUR", 8),
        sms_max_per_day=env_int("MARKET_RADAR_SMS_MAX_PER_DAY", 20),
        ebay_sniper_enabled=env_bool("DEALBRAIN_EBAY_SNIPER_ENABLED", True),
        ebay_scheduler_enabled=env_bool("DEALBRAIN_EBAY_SCHEDULER_ENABLED", False),
        ebay_max_queries=env_int("DEALBRAIN_EBAY_MAX_QUERIES", 3),
        ebay_max_items=env_int("DEALBRAIN_EBAY_MAX_ITEMS", 20),
        monster_discount_pct=env_float("DEALBRAIN_MONSTER_DISCOUNT_PCT", 60.0),
        hot_discount_pct=env_float("DEALBRAIN_HOT_DISCOUNT_PCT", 50.0),
        packaging_cost=env_float("MARKET_RADAR_PACKAGING_COST", 0.0),
        insurance_cost=env_float("MARKET_RADAR_INSURANCE_COST", 0.0),
        return_reserve_rate=env_float("MARKET_RADAR_RETURN_RESERVE_RATE", 0.0),
        alert_dry_run=env_bool("DEALBRAIN_ALERT_DRY_RUN", True),
        scale_level=env_int("DEALBRAIN_SCALE_LEVEL", 0),
        level1_max_fb_runs_per_day=env_int("LEVEL1_MAX_FB_RUNS_PER_DAY", 30),
        level1_max_ebay_calls_per_day=env_int("LEVEL1_MAX_EBAY_CALLS_PER_DAY", 40),
        level1_max_stage2_per_day=env_int("LEVEL1_MAX_STAGE2_PER_DAY", 12),
        level1_max_provider_dollars_per_day=env_float("LEVEL1_MAX_PROVIDER_DOLLARS_PER_DAY", 3.0),
        first_profit_mode=env_bool("FIRST_PROFIT_MODE", True),
        first_profit_live=env_bool("FIRST_PROFIT_LIVE", False),
        first_profit_active_haircut=env_float("FIRST_PROFIT_ACTIVE_HAIRCUT", 0.15),
        first_profit_phone_haircut=env_float("FIRST_PROFIT_PHONE_HAIRCUT", 0.20),
        first_profit_repair_haircut=env_float("FIRST_PROFIT_REPAIR_HAIRCUT", 0.25),
        first_profit_min_profit=env_float("FIRST_PROFIT_MIN_PROFIT", 50.0),
        first_profit_apify_daily_cap_usd=env_float("FIRST_PROFIT_APIFY_DAILY_CAP_USD", 0.50),
        first_profit_return_reserve_rate=env_float("FIRST_PROFIT_RETURN_RESERVE_RATE", 0.02),
        first_profit_unknown_inbound_reserve=env_float("FIRST_PROFIT_UNKNOWN_INBOUND_RESERVE", 12.0),
        first_profit_buyer_tax_rate=env_float("FIRST_PROFIT_BUYER_TAX_RATE", 0.0),
        first_profit_hot_clean_comps=env_int("FIRST_PROFIT_HOT_CLEAN_COMPS", 8),
        first_profit_monster_clean_comps=env_int("FIRST_PROFIT_MONSTER_CLEAN_COMPS", 10),
        first_profit_sample_high=env_int("FIRST_PROFIT_SAMPLE_HIGH", 15),
        first_profit_sample_medium=env_int("FIRST_PROFIT_SAMPLE_MEDIUM", 8),
        first_profit_sample_low=env_int("FIRST_PROFIT_SAMPLE_LOW", 5),
        first_profit_hot_discount_pct=env_float("FIRST_PROFIT_HOT_DISCOUNT_PCT", 50.0),
        first_profit_monster_discount_pct=env_float("FIRST_PROFIT_MONSTER_DISCOUNT_PCT", 60.0),
        first_profit_acquisition_friction=env_float("FIRST_PROFIT_ACQUISITION_FRICTION", 0.0),
    )
