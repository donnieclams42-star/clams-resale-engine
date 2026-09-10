from __future__ import annotations

import logging
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from .config import (
    settings,
    twilio_account_sid,
    twilio_auth_credentials,
    twilio_configured,
    twilio_message_data,
)
from .store import alerts_for, db_path, latest_valuation, record_alert, recent_alerts

logger = logging.getLogger("market_radar.marketplace")

CLASS_RANK = {"PASS": 0, "WATCH": 1, "RISK": 2, "BUY": 3, "HOT": 4}
_LAST_POSITIVE: dict[tuple[str, int], tuple[str, float]] = {}


def material_price_drop(old_price: Any, new_price: Any) -> bool:
    try:
        old = float(old_price)
        new = float(new_price)
    except Exception:
        return False
    drop = old - new
    if drop <= 0:
        return False
    cfg = settings()
    amount = float(cfg.get("price_drop_amount") or 15)
    pct = float(cfg.get("price_drop_pct") or 0.10)
    return drop >= amount or (old > 0 and (drop / old) >= pct)


def _memory_key(listing_id: int) -> tuple[str, int]:
    return (db_path(), int(listing_id))


def _last_sent(listing_id: int) -> dict[str, Any]:
    for row in alerts_for(listing_id):
        if int(row.get("sent") or 0) == 1 and not row.get("skip_reason") and str(row.get("channel") or "sms") == "sms":
            return row
    remembered = _LAST_POSITIVE.get(_memory_key(int(listing_id)))
    if remembered:
        return {"classification": remembered[0], "price": remembered[1], "sent": 1}
    return {}


def should_send_sms(
    listing_id: int,
    classification: str,
    price: Any,
    previous_class: str = "",
    previous_price: Any = None,
) -> tuple[bool, str, str]:
    cfg = settings()
    rank = CLASS_RANK.get(str(classification or "").upper(), 0)
    if rank < CLASS_RANK["BUY"]:
        return False, "", "below_threshold"
    if not cfg.get("sms_instant_enabled", True):
        return False, "", "instant_disabled"
    try:
        amount = float(price)
    except Exception:
        amount = 0.0
    last = _last_sent(int(listing_id))
    last_class = str(previous_class or last.get("classification") or "").upper()
    if not last_class:
        valuation = latest_valuation(listing_id) or {}
        last_class = str(valuation.get("classification") or "").upper()
    last_price = previous_price if previous_price not in (None, "") else last.get("price")
    try:
        last_amount = None if last_price in (None, "") else float(last_price)
    except Exception:
        last_amount = None
    upgrade = CLASS_RANK.get(str(classification).upper(), 0) > CLASS_RANK.get(last_class, 0)
    drop = last_amount is not None and material_price_drop(last_amount, amount)
    if last and not upgrade and not drop:
        same_class = str(last.get("classification") or last_class).upper() == str(classification).upper()
        same_price = last_amount is not None and abs(last_amount - amount) < 0.50
        if same_class and same_price:
            return False, "", "duplicate_unchanged"
        if same_class and not drop:
            return False, "", "duplicate_unchanged"
    hour_count = len(recent_alerts(hours=1, channel="sms", sent_only=True))
    day_count = len(recent_alerts(hours=24, channel="sms", sent_only=True))
    if hour_count >= int(cfg.get("sms_max_per_hour") or 8):
        return False, "", "rate_limited_hour"
    if day_count >= int(cfg.get("sms_max_per_day") or 20):
        return False, "", "rate_limited_day"
    if drop:
        alert_type = "PRICE_DROP"
    elif str(classification).upper() == "HOT" and (upgrade or last_class in {"BUY", "WATCH", "RISK", "PASS"}):
        alert_type = "THRESHOLD_HOT"
    elif str(classification).upper() == "HOT":
        alert_type = "THRESHOLD_HOT"
    else:
        alert_type = "INSTANT"
    _LAST_POSITIVE[_memory_key(int(listing_id))] = (str(classification).upper(), amount)
    return True, alert_type, ""


def format_sms(listing: dict[str, Any], valuation: dict[str, Any] | None = None) -> str:
    valuation = valuation or {}
    title = str(listing.get("title") or "Marketplace deal")[:80]
    classification = str(valuation.get("classification") or listing.get("classification") or "BUY")
    ask = listing.get("asking_price")
    profit = valuation.get("expected_profit")
    roi = valuation.get("roi_pct", valuation.get("roi"))
    location = listing.get("location_text") or ""
    url = listing.get("listing_url") or ""
    lines = [
        f"Market Radar {classification}: {title}",
        f"Ask ${float(ask or 0):.0f} | Profit ${float(profit or 0):.0f} | ROI {float(roi or 0):.0f}%",
    ]
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
    except Exception as exc:
        logger.info("MARKETPLACE_SMS_FAILED error=%s", type(exc).__name__)
        return {"ok": False, "error": "twilio_request_failed"}
    if response.status_code >= 400:
        logger.info("MARKETPLACE_SMS_HTTP http=%s", response.status_code)
        return {"ok": False, "error": f"twilio_http_{response.status_code}"}
    return {"ok": True, "sid": (response.json() or {}).get("sid", "")}


def maybe_alert(
    listing: dict[str, Any],
    valuation: dict[str, Any],
    previous_class: str = "",
    previous_price: Any = None,
) -> dict[str, Any]:
    listing_id = int(listing.get("id") or 0)
    classification = str(valuation.get("classification") or "")
    price = listing.get("asking_price")
    send, alert_type, reason = should_send_sms(
        listing_id,
        classification=classification,
        price=price,
        previous_class=previous_class,
        previous_price=previous_price,
    )
    if not send:
        record_alert(
            listing_id,
            alert_type or "SKIP",
            price=price,
            profit=valuation.get("expected_profit"),
            classification=classification,
            skip_reason=reason,
            sent=False,
        )
        return {"sent": False, "reason": reason, "alert_type": alert_type}
    result = send_sms(format_sms(listing, valuation))
    record_alert(
        listing_id,
        alert_type,
        price=price,
        profit=valuation.get("expected_profit"),
        classification=classification,
        skip_reason="" if result.get("ok") else str(result.get("error") or "send_failed"),
        sent=bool(result.get("ok")),
    )
    return {"sent": bool(result.get("ok")), "reason": "" if result.get("ok") else result.get("error"), "alert_type": alert_type}


def format_digest(rows: list[dict[str, Any]] | None = None) -> str:
    rows = rows or []
    if not rows:
        return "Market Radar digest: no HOT/BUY Facebook Marketplace deals in this window."
    lines = [f"Market Radar digest: {len(rows)} deal(s)"]
    for row in rows[:8]:
        lines.append(
            f"{row.get('classification') or ''} {row.get('title') or ''} ${float(row.get('asking_price') or 0):.0f} profit ${float(row.get('expected_profit') or 0):.0f}"
        )
        if row.get("listing_url"):
            lines.append(str(row["listing_url"]))
    return "\n".join(lines)[:1500]
