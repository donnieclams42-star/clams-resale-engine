from __future__ import annotations

import logging
import os
import time
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from dealbrain.classify import (
    ALERT_CLASSES,
    CLASS_HOT,
    CLASS_MONSTER,
    CLASS_PASS,
    CLASS_RANK,
    CLASS_RISK,
    CLASS_STRONG,
    CLASS_WATCH,
)
from dealbrain.config import get_config, twilio_account_sid, twilio_auth_credentials, twilio_configured, twilio_message_data
from dealbrain.store import alerts_for, recent_alerts, record_alert

logger = logging.getLogger("market_radar.dealbrain")

DISCORD_WEBHOOK_ENV_NAMES = ("DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK")
SHARED_DISCORD_SENDER = "send_discord_deal_alert"
EXTREME_PRICE_WARNING = "⚠️ EXTREME PRICE — VERIFY ITEM / CONDITION / SCAM RISK"
PHONE_VERIFY_LINES = (
    "⚠️ VERIFY IMEI / ICLOUD / FINANCING / WATER DAMAGE",
    "VERIFY IMEI",
    "VERIFY BLACKLIST",
    "VERIFY FINANCING",
    "VERIFY ICLOUD / ACTIVATION LOCK",
    "VERIFY CARRIER",
    "VERIFY PHONE POWERS ON",
    "VERIFY TOUCH",
    "VERIFY FACE ID / FINGERPRINT",
    "VERIFY CAMERAS",
    "VERIFY CHARGING",
    "CHECK WATER DAMAGE",
)
STRONG_DISCORD_PROFIT = 75.0
IDENTITY_STRONG = {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"}
RISK_RANK = {"LOW": 0, "MEDIUM": 1, "UNKNOWN": 1, "": 1, "HIGH": 2}


def material_price_drop(old_price: Any, new_price: Any) -> bool:
    try:
        old = float(old_price)
        new = float(new_price)
    except Exception:
        return False
    drop = old - new
    if drop <= 0:
        return False
    return drop >= 15 or (old > 0 and (drop / old) >= 0.10)


def material_profit_increase(old_profit: Any, new_profit: Any) -> bool:
    try:
        old = float(old_profit)
        new = float(new_profit)
    except Exception:
        return False
    gain = new - old
    if gain <= 0:
        return False
    return gain >= 25 or (old > 0 and (gain / old) >= 0.20)


def risk_improved(old_risk: Any, new_risk: Any) -> bool:
    return RISK_RANK.get(str(new_risk or "").upper(), 1) < RISK_RANK.get(str(old_risk or "").upper(), 1)


def facebook_source(source: Any) -> bool:
    return str(source or "").lower().startswith("facebook")


def ebay_source(source: Any) -> bool:
    return str(source or "").lower() == "ebay"


def source_badge(source: Any) -> str:
    if facebook_source(source):
        return "FACEBOOK"
    if ebay_source(source):
        return "EBAY"
    return str(source or "UNKNOWN").upper()


def discord_webhook_env_name() -> str:
    for name in DISCORD_WEBHOOK_ENV_NAMES:
        if str(os.getenv(name) or "").strip():
            return name
    return ""


def discord_webhook_url() -> str:
    for name in DISCORD_WEBHOOK_ENV_NAMES:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def discord_configured() -> bool:
    return bool(discord_webhook_url())


def discord_destination_status() -> dict[str, Any]:
    env_name = discord_webhook_env_name()
    configured = bool(env_name)
    return {
        "ebay_configured": configured,
        "facebook_configured": configured,
        "same_destination": True,
        "env_name": env_name,
        "sender": SHARED_DISCORD_SENDER,
    }


def _money(value: Any) -> float:
    try:
        if value in (None, "", "None", "UNKNOWN"):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _stored_money(value: Any) -> str:
    if value in (None, "", "None", "UNKNOWN"):
        return "UNKNOWN"
    try:
        return f"${float(value):.0f}"
    except Exception:
        return "UNKNOWN"


def _listing_id(listing: dict[str, Any]) -> str:
    return str(listing.get("id") or listing.get("listing_id") or "")


def _source_listing_id(listing: dict[str, Any]) -> str:
    return str(listing.get("source_listing_id") or "")


def direct_item_url(listing: dict[str, Any]) -> str:
    source = str(listing.get("source") or "")
    raw = str(listing.get("canonical_url") or listing.get("listing_url") or listing.get("url") or listing.get("link") or "")
    source_id = _source_listing_id(listing)
    if facebook_source(source):
        from marketplace.normalize import canonical_facebook_url, listing_id_from_url
        item_id = source_id or listing_id_from_url(raw)
        if item_id:
            return canonical_facebook_url(raw, item_id)
        if "/marketplace/item/" in raw.lower():
            return canonical_facebook_url(raw)
        return ""
    if ebay_source(source):
        from dealbrain.ebay_normalize import canonical_ebay_url, ebay_item_id
        item_id = source_id or ebay_item_id({"itemId": source_id, "itemWebUrl": raw, "itemHref": raw})
        if not item_id:
            item_id = ebay_item_id({"itemWebUrl": raw})
        if item_id:
            return canonical_ebay_url("", item_id)
        built = canonical_ebay_url(raw, item_id)
        if "ebay.com/sch" in built.lower() or "/sch/" in built.lower():
            return ""
        if "/itm/" in built.lower():
            return built
        return ""
    lower = raw.lower()
    if "ebay.com/sch" in lower or "/marketplace/search" in lower:
        return ""
    return raw


def alert_fingerprint(
    *,
    source: str,
    listing_id: str,
    classification: str,
    price: Any,
    profit: Any,
    risk: str,
) -> str:
    try:
        price_key = f"{float(price):.2f}"
    except Exception:
        price_key = str(price or "")
    try:
        profit_key = f"{round(float(profit or 0) / 5.0) * 5:.0f}"
    except Exception:
        profit_key = str(profit or "")
    return "|".join(
        [
            str(source or ""),
            str(listing_id or ""),
            str(classification or "").upper(),
            price_key,
            profit_key,
            str(risk or "").upper(),
        ]
    )


def _is_phone(listing: dict[str, Any], valuation: dict[str, Any]) -> bool:
    if valuation.get("phone_checklist"):
        return True
    family = str(valuation.get("candidate_product_family") or listing.get("candidate_product_family") or "")
    try:
        from dealbrain.first_profit import is_phone
        if is_phone(family):
            return True
    except Exception:
        pass
    blob = f"{listing.get('title') or ''} {family} {listing.get('category') or ''}".lower()
    return any(token in blob for token in ("iphone", "galaxy s", "pixel ")) and "controller" not in blob


def _extreme_price(listing: dict[str, Any], valuation: dict[str, Any]) -> bool:
    if valuation.get("extreme_anomaly"):
        return True
    status = str(valuation.get("anomaly_status") or "").upper()
    if "EXTREME" in status:
        return True
    reasons = valuation.get("reasons") or listing.get("reasons") or []
    if any("EXTREME" in str(row).upper() for row in reasons):
        return True
    ask = _money(listing.get("asking_price") if listing.get("asking_price") not in (None, "") else valuation.get("asking_price"))
    exit_val = _money(
        valuation.get("conservative_active_exit")
        or valuation.get("conservative_resale")
        or valuation.get("expected_resale")
    )
    discount = _money(valuation.get("discount_pct"))
    cfg = get_config()
    if discount >= float(getattr(cfg, "extreme_discount_pct", 45.0) or 45.0):
        return True
    if exit_val > 0 and ask > 0 and ((exit_val - ask) / exit_val) * 100.0 >= float(getattr(cfg, "extreme_discount_pct", 45.0) or 45.0):
        return True
    return False


def _last_discord_send(listing_id: str) -> dict[str, Any]:
    for row in alerts_for(listing_id, channel="discord"):
        skip = str(row.get("skip_reason") or "")
        if int(row.get("sent") or 0) == 1:
            return row
        if skip == "dry_run":
            return row
    return {}


def should_send_discord(
    listing: dict[str, Any],
    valuation: dict[str, Any],
    *,
    previous_class: str = "",
    previous_price: Any = None,
    previous_profit: Any = None,
    previous_risk: str = "",
) -> tuple[bool, str, str]:
    klass = str(valuation.get("classification") or listing.get("classification") or "").upper()
    source = str(listing.get("source") or valuation.get("source") or "")
    listing_id = _listing_id(listing)
    price = listing.get("asking_price")
    if price in (None, ""):
        price = valuation.get("asking_price")
    profit = valuation.get("expected_profit")
    risk = str(valuation.get("risk") or listing.get("risk") or "").upper()
    ident = str(valuation.get("identity_confidence") or listing.get("identity_confidence") or "").upper()
    url = direct_item_url({**valuation, **listing})

    if valuation.get("verify_identity_alert") or str(valuation.get("feed_lane") or "") == "NEEDS_VERIFICATION":
        profit_val = _money(profit)
        if profit_val >= 100 and ident not in IDENTITY_STRONG:
            last = _last_discord_send(listing_id) if listing_id else {}
            if last and str(last.get("alert_type") or "") == "VERIFY_IDENTITY":
                return False, "", "duplicate_unchanged"
            if not url:
                return False, "", "no_direct_link"
            return True, "VERIFY_IDENTITY", ""
    if klass == CLASS_WATCH:
        return False, "", "watch_no_alert"
    if klass == CLASS_PASS:
        return False, "", "pass_no_alert"
    tags = valuation.get("opportunity_types") or listing.get("opportunity_types") or []
    if not isinstance(tags, list):
        tags = []
    tags_u = {str(t).upper() for t in tags}
    if "REPAIR_ARBITRAGE" in tags_u and valuation.get("repair_alert_ok"):
        if _money(valuation.get("repair_expected_profit") or profit) < float(getattr(get_config(), "first_profit_min_profit", 50) or 50):
            return False, "", "repair_economics_weak"
        if ident not in IDENTITY_STRONG:
            return False, "", "identity_not_strong"
        if not url:
            return False, "", "no_direct_link"
        if str(valuation.get("deal_lane") or listing.get("deal_lane") or "") == "MARKET_RESEARCH" and str(valuation.get("acquisition_type") or "") == "LOCAL_PICKUP":
            return False, "", "remote_pickup_not_actionable"
        last = _last_discord_send(listing_id) if listing_id else {}
        if last and str(last.get("classification") or "") == klass:
            return False, "", "duplicate_unchanged"
        return True, "REPAIR_OPPORTUNITY", ""
    if "MARKET_ARBITRAGE" in tags_u and _money(valuation.get("cross_market_expected_profit") or profit) >= float(getattr(get_config(), "first_profit_min_profit", 50) or 50):
        if str(valuation.get("deal_lane") or "") == "MARKET_RESEARCH" and str(valuation.get("acquisition_type") or "") == "LOCAL_PICKUP":
            return False, "", "remote_pickup_not_actionable"
        if not url:
            return False, "", "no_direct_link"
        return True, "MARKET_ARBITRAGE", ""
    if klass == CLASS_RISK:
        return False, "", "risk_no_alert"
    if klass == CLASS_STRONG:
        if not facebook_source(source):
            return False, "", "below_threshold"
        if _money(profit) < STRONG_DISCORD_PROFIT:
            return False, "", "strong_profit_gate"
        if ident not in IDENTITY_STRONG:
            return False, "", "identity_not_strong"
        if risk == "HIGH":
            return False, "", "risk_high"
        if not url:
            return False, "", "no_direct_link"
    elif klass not in {CLASS_HOT, CLASS_MONSTER}:
        return False, "", "below_threshold"
    if ident not in IDENTITY_STRONG:
        return False, "", "identity_not_strong"
    if not url:
        return False, "", "no_direct_link"

    last = _last_discord_send(listing_id) if listing_id else {}
    last_class = str(previous_class or last.get("classification") or "").upper()
    last_price = previous_price if previous_price not in (None, "") else last.get("price")
    last_profit = previous_profit if previous_profit not in (None, "") else last.get("profit")
    last_risk = str(previous_risk or last.get("risk") or "").upper()
    try:
        amount = None if price in (None, "") else float(price)
    except Exception:
        amount = None
    try:
        last_amount = None if last_price in (None, "") else float(last_price)
    except Exception:
        last_amount = None
    upgrade = CLASS_RANK.get(klass, 0) > CLASS_RANK.get(last_class, 0)
    drop = last_amount is not None and amount is not None and material_price_drop(last_amount, amount)
    profit_up = last_profit not in (None, "") and material_profit_increase(last_profit, profit)
    better_risk = bool(last) and risk_improved(last_risk, risk)
    if last and not upgrade and not drop and not profit_up and not better_risk:
        return False, "", "duplicate_unchanged"
    if drop:
        return True, "PRICE_DROP", ""
    if upgrade and last:
        return True, f"UPGRADE_{klass}", ""
    if klass == CLASS_MONSTER:
        return True, "THRESHOLD_MONSTER", ""
    if klass == CLASS_HOT:
        return True, "THRESHOLD_HOT", ""
    return True, "THRESHOLD_STRONG", ""


def format_discord_deal(deal: dict[str, Any]) -> str:
    listing = deal
    valuation = deal
    klass = str(deal.get("classification") or "HOT").upper()
    source = str(deal.get("source") or "")
    alert_type = str(deal.get("alert_type") or "")
    badge = source_badge(source)
    tags = deal.get("opportunity_types") or []
    if alert_type.upper() == "VERIFY_IDENTITY":
        header = f"🔎 VERIFY IDENTITY — {badge}"
    elif alert_type.upper() == "REPAIR_OPPORTUNITY" or "REPAIR_ARBITRAGE" in {str(t).upper() for t in tags}:
        return _format_repair_discord(deal, badge)
    elif alert_type.upper() == "MARKET_ARBITRAGE" or "MARKET_ARBITRAGE" in {str(t).upper() for t in tags}:
        return _format_market_discord(deal, badge)
    elif alert_type.upper() == "PRICE_DROP":
        header = f"📉 PRICE DROP → {klass} — {badge}"
    elif klass == CLASS_MONSTER:
        header = f"💥 MONSTER DEAL — {badge}"
    elif klass == CLASS_STRONG:
        header = f"💪 STRONG DEAL — {badge}"
    else:
        header = f"🔥 HOT DEAL — {badge}"
    title = str(deal.get("title") or "Deal")[:120]
    ask = _money(deal.get("asking_price"))
    landed = _money(deal.get("landed_cost") or ask)
    conservative = _money(
        deal.get("conservative_active_exit")
        or deal.get("conservative_resale")
        or deal.get("expected_resale")
        or deal.get("net_resale")
    )
    profit = _money(deal.get("expected_profit"))
    roi = _money(deal.get("roi_pct"))
    mos = deal.get("margin_of_safety_percent")
    clean = int(deal.get("clean_comparable_count") or deal.get("clean_sample_count") or 0)
    basis = str(deal.get("valuation_badge") or deal.get("valuation_basis_label") or deal.get("valuation_basis") or "")
    if str(deal.get("valuation_basis") or "").upper() in {"CONSERVATIVE_ACTIVE_EXIT", "ACTIVE_MARKET_ONLY"} or "ACTIVE" in basis.upper():
        basis = "Active-market derived"
    elif not basis:
        basis = "Active-market derived"
    risk = str(deal.get("risk") or "UNKNOWN")
    location = str(deal.get("location_text") or deal.get("market_id") or "")[:80]
    url = direct_item_url(deal)
    open_label = str(deal.get("open_label") or ("OPEN FACEBOOK LISTING" if facebook_source(source) else "OPEN EBAY LISTING" if ebay_source(source) else "OPEN LISTING"))
    first_seen = str(deal.get("first_seen_at") or deal.get("listing_created_at") or "").replace("T", " ")
    if first_seen.endswith("+00:00"):
        first_seen = first_seen.replace("+00:00", " UTC")
    age = deal.get("age_hours")
    if age not in (None, "") and not first_seen:
        try:
            hours = float(age)
            first_seen = f"{int(hours * 60)} min ago" if hours < 1 else f"{hours:.1f} hr ago"
        except Exception:
            first_seen = ""
    elif age not in (None, "") and first_seen:
        try:
            hours = float(age)
            age_txt = f"{int(hours * 60)} min ago" if hours < 1 else f"{hours:.1f} hr ago"
            first_seen = f"{first_seen[:22]} ({age_txt})"
        except Exception:
            pass
    lines = [header, "", title, ""]
    old_ask = deal.get("old_price")
    if alert_type.upper() == "PRICE_DROP" and old_ask not in (None, ""):
        lines.append(f"Old Ask: ${_money(old_ask):.0f}")
        lines.append(f"New Ask: ${ask:.0f}")
    else:
        lines.append(f"Ask: ${ask:.0f}")
    lines.extend(
        [
            f"Landed: ${landed:.0f}",
            f"Conservative Exit: ${conservative:.0f}",
            f"Expected Profit: ${profit:.0f}",
            f"ROI: {roi:.0f}%",
            f"Margin of Safety: {_money(mos):.0f}%",
            "",
            f"Clean Market Comps: {clean}",
            f"Valuation: {basis}",
            "",
            f"Risk: {risk}",
        ]
    )
    if location:
        lines.append(f"Location: {location}")
    metro = str(deal.get("metro_id") or "")
    distance = deal.get("distance_miles")
    acq = str(deal.get("acquisition_type") or "")
    if metro or acq:
        extra = []
        if metro:
            extra.append(metro)
        if distance not in (None, ""):
            extra.append(f"{distance} mi")
        if acq:
            extra.append(acq)
        lines.append("DISTANCE / MARKET: " + " · ".join(extra))
        lines.append(f"ACQUISITION TYPE: {acq or 'UNKNOWN'}")
        if str(deal.get("deal_lane") or "") == "MARKET_RESEARCH":
            lines.append("MARKET RESEARCH DEAL — not a local go-buy")
    if first_seen:
        lines.append(f"First Seen: {first_seen[:48]}")
    if _extreme_price(listing, valuation):
        lines.extend(["", EXTREME_PRICE_WARNING])
    if _is_phone(listing, valuation):
        lines.append("")
        lines.extend(PHONE_VERIFY_LINES)
    lines.extend(["", f"{open_label} <{url}>" if url else open_label])
    if url:
        lines.append(url)
    text = "\n".join(line for line in lines if line is not None).strip()
    return text[:1900]


def _format_repair_discord(deal: dict[str, Any], badge: str) -> str:
    title = str(deal.get("candidate_model") or deal.get("title") or "Item")[:120]
    location = str(deal.get("location_text") or deal.get("metro_id") or "")[:80]
    url = direct_item_url(deal)
    lines = [
        f"🔧 REPAIR OPPORTUNITY — {badge}",
        "",
        f"📍 {location}" if location else "",
        title,
        "",
        f"Ask: {_stored_money(deal.get('asking_price'))}",
        f"Damage: {str(deal.get('repair_type') or 'UNKNOWN').replace('_', ' ')}",
        f"Conservative working exit: {_stored_money(deal.get('working_conservative_exit') or deal.get('WORKING_CONSERVATIVE_EXIT') or deal.get('conservative_active_exit') or deal.get('conservative_resale'))}",
        f"Estimated repair: {_stored_money(deal.get('estimated_repair') or deal.get('TOTAL_REPAIR_COST'))}",
        f"Repair-risk reserve: {_stored_money(deal.get('repair_risk_reserve') or deal.get('REPAIR_RISK_RESERVE'))}",
        f"Expected profit: {_stored_money(deal.get('repair_expected_profit') or deal.get('REPAIR_EXPECTED_PROFIT') or deal.get('expected_profit'))}",
        f"MAX BUY: {_stored_money(deal.get('max_repair_buy') or deal.get('MAX_REPAIR_BUY'))}",
    ]
    acq = str(deal.get("acquisition_type") or "")
    if acq:
        lines.extend(["", f"ACQUISITION TYPE: {acq}"])
    if deal.get("distance_miles") not in (None, ""):
        lines.append(f"DISTANCE / MARKET: {deal.get('metro_id') or ''} · {deal.get('distance_miles')} mi")
    if str(deal.get("deal_lane") or "") == "MARKET_RESEARCH":
        lines.append("MARKET RESEARCH DEAL — transport may kill profit")
    lines.extend(["", "⚠️ VERIFY IMEI / ICLOUD / FINANCING / WATER DAMAGE"])
    for warn in (deal.get("repair_warnings") or deal.get("phone_checklist") or [])[:8]:
        lines.append(str(warn))
    open_label = str(deal.get("open_label") or "OPEN FACEBOOK LISTING")
    lines.extend(["", f"{open_label} <{url}>" if url else open_label])
    if url:
        lines.append(url)
    return "\n".join(line for line in lines if line is not None).strip()[:1900]


def _format_market_discord(deal: dict[str, Any], badge: str) -> str:
    title = str(deal.get("candidate_model") or deal.get("title") or "Item")[:120]
    url = direct_item_url(deal)
    profit = deal.get("cross_market_expected_profit")
    if profit in (None, ""):
        profit = deal.get("expected_profit")
    lines = [
        f"🌎 MARKET ARBITRAGE — {badge}",
        "",
        title,
        "",
        f"Market: {deal.get('metro_id') or deal.get('location_text') or 'UNKNOWN'}",
        f"Ask: {_stored_money(deal.get('asking_price'))}",
        f"National conservative exit: {_stored_money(deal.get('conservative_active_exit') or deal.get('conservative_resale'))}",
        f"Expected profit after shipping: {_stored_money(profit)}",
        f"Acquisition: {deal.get('acquisition_type') or 'UNKNOWN'}",
    ]
    if str(deal.get("deal_lane") or "") == "MARKET_RESEARCH":
        lines.append("MARKET RESEARCH — not a local go-buy")
    open_label = str(deal.get("open_label") or "OPEN LISTING")
    lines.extend(["", f"{open_label} <{url}>" if url else open_label])
    if url:
        lines.append(url)
    return "\n".join(line for line in lines if line is not None).strip()[:1900]


def post_discord_webhook(message: str) -> dict[str, Any]:
    url = discord_webhook_url()
    if not url:
        return {"ok": False, "error": "discord_not_configured", "status": 0}
    if requests is None:
        return {"ok": False, "error": "discord_unavailable", "status": 0}
    payload = {"content": message[:2000]}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if getattr(response, "status_code", 0) == 429:
            time.sleep(2)
            response = requests.post(url, json=payload, timeout=10)
    except Exception:
        logger.info("DISCORD_WEBHOOK_FAILED error=request")
        return {"ok": False, "error": "discord_request_failed", "status": 0}
    status = int(getattr(response, "status_code", 0) or 0)
    if status >= 400:
        logger.info("DISCORD_WEBHOOK_HTTP http=%s", status)
        return {"ok": False, "error": f"discord_http_{status}", "status": status}
    return {"ok": True, "error": "", "status": status}


def send_discord_deal_alert(deal: dict[str, Any]) -> dict[str, Any]:
    """Shared Facebook + eBay Discord sender. Never raises."""
    try:
        body = format_discord_deal(deal)
        posted = post_discord_webhook(body)
        return {
            "ok": bool(posted.get("ok")),
            "error": posted.get("error") or "",
            "payload": body,
            "status": posted.get("status") or 0,
            "sender": SHARED_DISCORD_SENDER,
            "destination": discord_destination_status(),
        }
    except Exception:
        logger.info("DISCORD_DEAL_ALERT_FAILED")
        return {
            "ok": False,
            "error": "discord_exception",
            "payload": "",
            "status": 0,
            "sender": SHARED_DISCORD_SENDER,
            "destination": discord_destination_status(),
        }


def should_send_sms(
    listing_id: str,
    classification: str,
    price: Any,
    previous_class: str = "",
    previous_price: Any = None,
) -> tuple[bool, str, str]:
    cfg = get_config()
    klass = str(classification or "").upper()
    if klass not in ALERT_CLASSES:
        return False, "", "below_threshold"
    if not cfg.sms_enabled:
        return False, "", "instant_disabled"
    try:
        amount = float(price)
    except Exception:
        amount = 0.0
    last = {}
    for row in alerts_for(listing_id, channel="sms"):
        skip = str(row.get("skip_reason") or "")
        if int(row.get("sent") or 0) == 1 or skip == "dry_run":
            last = row
            break
    last_class = str(previous_class or last.get("classification") or "").upper()
    last_price = previous_price if previous_price not in (None, "") else last.get("price")
    try:
        last_amount = None if last_price in (None, "") else float(last_price)
    except Exception:
        last_amount = None
    upgrade = CLASS_RANK.get(klass, 0) > CLASS_RANK.get(last_class, 0)
    drop = last_amount is not None and material_price_drop(last_amount, amount)
    if last and not upgrade and not drop:
        same_class = str(last.get("classification") or last_class).upper() == klass
        if same_class:
            return False, "", "duplicate_unchanged"
    if len(recent_alerts(hours=1, sent_only=True, channel="sms")) >= cfg.sms_max_per_hour:
        return False, "", "rate_limited_hour"
    if len(recent_alerts(hours=24, sent_only=True, channel="sms")) >= cfg.sms_max_per_day:
        return False, "", "rate_limited_day"
    if drop:
        alert_type = "PRICE_DROP"
    elif klass == CLASS_MONSTER:
        alert_type = "THRESHOLD_MONSTER"
    elif klass == CLASS_HOT:
        alert_type = "THRESHOLD_HOT"
    else:
        alert_type = "INSTANT"
    return True, alert_type, ""


def format_sms(listing: dict[str, Any], valuation: dict[str, Any] | None = None) -> str:
    valuation = valuation or {}
    klass = str(valuation.get("classification") or "HOT").upper()
    title = str(listing.get("title") or "Deal")[:80]
    ask = listing.get("asking_price")
    net = valuation.get("net_resale") or valuation.get("expected_net")
    profit = valuation.get("expected_profit")
    roi = valuation.get("roi_pct")
    location = listing.get("location_text") or ""
    url = direct_item_url({**valuation, **listing}) or listing.get("canonical_url") or listing.get("listing_url") or ""
    age = valuation.get("age_hours")
    age_txt = ""
    if age is not None:
        try:
            hours = float(age)
            age_txt = f"{int(hours * 60)} min" if hours < 1 else f"{hours:.1f} hr"
        except Exception:
            age_txt = ""
    header = "💥 MONSTER DEAL" if klass == CLASS_MONSTER else "🔥 HOT DEAL"
    source = str(listing.get("source") or "")
    if source.startswith("facebook"):
        header += " — FACEBOOK"
    elif source == "ebay":
        header += " — EBAY"
    ask = listing.get("asking_price")
    landed = valuation.get("landed_cost") or ask
    conservative = valuation.get("conservative_resale") or valuation.get("expected_resale") or net
    basis = valuation.get("verified_exit_basis") or valuation.get("valuation_grade") or ""
    risk = valuation.get("risk") or ""
    lines = [
        header,
        title,
        f"Ask: ${float(ask or 0):.0f}",
        f"Landed: ${float(landed or 0):.0f}",
        f"Conservative value: ${float(conservative or 0):.0f}",
        f"Evidence: {basis}",
        f"Expected profit: ${float(profit or 0):.0f}",
        f"ROI: {float(roi or 0):.0f}%",
    ]
    if risk:
        lines.append(f"Risk: {risk}")
    if age_txt:
        lines.append(f"Age: {age_txt}")
    if location:
        lines.append(str(location)[:80])
    if url:
        lines.append(str(url))
    return "\n".join(lines)[:1500]


def send_sms(body: str) -> dict[str, Any]:
    if not twilio_configured():
        return {"ok": False, "error": "twilio_not_configured"}
    if requests is None:
        return {"ok": False, "error": "twilio_unavailable"}
    account_sid = twilio_account_sid()
    username, password = twilio_auth_credentials()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    try:
        response = requests.post(
            url,
            auth=(username, password),
            data=twilio_message_data(body),
            timeout=20,
        )
    except Exception:
        logger.info("DEALBRAIN_SMS_FAILED error=request")
        return {"ok": False, "error": "twilio_request_failed"}
    if response.status_code >= 400:
        logger.info("DEALBRAIN_SMS_HTTP http=%s", response.status_code)
        return {"ok": False, "error": f"twilio_http_{response.status_code}"}
    sid = ""
    try:
        sid = str((response.json() or {}).get("sid") or "")
    except Exception:
        sid = ""
    return {"ok": True, "sid": sid}


def _record_discord(
    listing: dict[str, Any],
    valuation: dict[str, Any],
    alert_type: str,
    *,
    sent: bool,
    skip_reason: str,
    extra: dict[str, Any] | None = None,
) -> None:
    listing_id = _listing_id(listing)
    if not listing_id:
        return
    payload = {
        "classification": str(valuation.get("classification") or ""),
        "price": listing.get("asking_price"),
        "profit": valuation.get("expected_profit"),
        "risk": valuation.get("risk") or "",
        "fingerprint": alert_fingerprint(
            source=str(listing.get("source") or ""),
            listing_id=_source_listing_id(listing) or listing_id,
            classification=str(valuation.get("classification") or ""),
            price=listing.get("asking_price"),
            profit=valuation.get("expected_profit"),
            risk=str(valuation.get("risk") or ""),
        ),
    }
    if extra:
        payload.update(extra)
    record_alert(
        listing_id,
        alert_type or "SKIP",
        classification=payload["classification"],
        price=payload["price"],
        profit=payload["profit"],
        sent=sent,
        skip_reason=skip_reason,
        channel="discord",
        extra={"risk": payload.get("risk") or "", "fingerprint": payload.get("fingerprint") or ""},
    )


def maybe_alert(
    listing: dict[str, Any],
    valuation: dict[str, Any],
    previous_class: str = "",
    previous_price: Any = None,
    previous_profit: Any = None,
    previous_risk: str = "",
) -> dict[str, Any]:
    listing_id = _listing_id(listing)
    classification = str(valuation.get("classification") or "")
    price = listing.get("asking_price")
    profit = valuation.get("expected_profit")
    discord: dict[str, Any] = {"sent": False, "reason": "", "alert_type": "", "payload": ""}
    try:
        send_discord, discord_type, discord_reason = should_send_discord(
            listing,
            valuation,
            previous_class=previous_class,
            previous_price=previous_price,
            previous_profit=previous_profit,
            previous_risk=previous_risk,
        )
        discord["alert_type"] = discord_type
        discord["reason"] = discord_reason
        if not send_discord:
            _record_discord(listing, valuation, discord_type or "SKIP", sent=False, skip_reason=discord_reason)
        else:
            deal = {
                **valuation,
                **listing,
                "alert_type": discord_type,
                "old_price": previous_price if discord_type == "PRICE_DROP" else None,
                "classification": classification,
            }
            posted = send_discord_deal_alert(deal)
            discord["payload"] = posted.get("payload") or ""
            discord["sent"] = bool(posted.get("ok"))
            discord["reason"] = "" if posted.get("ok") else str(posted.get("error") or "send_failed")
            discord["destination"] = posted.get("destination") or discord_destination_status()
            discord["sender"] = posted.get("sender") or SHARED_DISCORD_SENDER
            _record_discord(
                listing,
                valuation,
                discord_type,
                sent=bool(posted.get("ok")),
                skip_reason="" if posted.get("ok") else str(posted.get("error") or "send_failed"),
            )
    except Exception:
        logger.info("DEALBRAIN_DISCORD_ISOLATED listing_id=%s", listing_id)
        discord = {"sent": False, "reason": "discord_exception", "alert_type": "", "payload": ""}
        try:
            _record_discord(listing, valuation, "SKIP", sent=False, skip_reason="discord_exception")
        except Exception:
            pass

    send, alert_type, reason = should_send_sms(
        listing_id,
        classification=classification,
        price=price,
        previous_class=previous_class,
        previous_price=previous_price,
    )
    result: dict[str, Any] = {
        "sent": False,
        "reason": reason,
        "alert_type": alert_type,
        "discord_sent": bool(discord.get("sent")),
        "discord_reason": discord.get("reason") or "",
        "discord_alert_type": discord.get("alert_type") or "",
        "discord_payload": discord.get("payload") or "",
        "discord_sender": discord.get("sender") or SHARED_DISCORD_SENDER,
        "discord_destination": discord.get("destination") or discord_destination_status(),
    }
    if not send:
        record_alert(
            listing_id,
            alert_type or "SKIP",
            classification=classification,
            price=price,
            profit=profit,
            sent=False,
            skip_reason=reason,
            channel="sms",
        )
        result["reason"] = reason
        return result
    body = format_sms(listing, valuation)
    cfg = get_config()
    if getattr(cfg, "alert_dry_run", True):
        from dealbrain.store import save_dry_run_alert
        save_dry_run_alert(listing_id, classification, body)
        record_alert(
            listing_id,
            alert_type,
            classification=classification,
            price=price,
            profit=profit,
            sent=False,
            skip_reason="dry_run",
            channel="sms",
        )
        result["reason"] = "dry_run"
        result["payload"] = body
        return result
    sms_result = send_sms(body)
    record_alert(
        listing_id,
        alert_type,
        classification=classification,
        price=price,
        profit=profit,
        sent=bool(sms_result.get("ok")),
        skip_reason="" if sms_result.get("ok") else str(sms_result.get("error") or "send_failed"),
        channel="sms",
    )
    result["sent"] = bool(sms_result.get("ok"))
    result["reason"] = "" if sms_result.get("ok") else sms_result.get("error")
    return result
