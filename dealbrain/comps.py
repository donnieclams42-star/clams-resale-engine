from __future__ import annotations

import re
import statistics
from typing import Any, Callable

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from dealbrain.config import env_str

STOPWORDS = {
    "the", "and", "with", "for", "from", "a", "an", "to", "of", "in", "on",
    "used", "good", "great", "excellent", "condition", "local", "pickup",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {word for word in words if word not in STOPWORDS and len(word) > 1}


def extract_model_query(title: str, listing: dict[str, Any] | None = None) -> str:
    listing = listing or {}
    try:
        from marketplace.identity import resolved_identity_query, identity_is_exact
        resolved = resolved_identity_query(listing, title=title)
        if resolved:
            return resolved
        if not identity_is_exact(str(listing.get("identity_confidence") or "")):
            return ""
    except Exception:
        resolved = ""
    model = str(listing.get("candidate_model") or "").strip()
    if model:
        return model
    return ""


def match_quality(listing_title: str, comp_title: str) -> str:
    left = _tokens(listing_title)
    right = _tokens(comp_title)
    if not left or not right:
        return "weak"
    overlap = left & right
    if not overlap:
        return "weak"
    ratio = len(overlap) / max(1, min(len(left), len(right)))
    if overlap == left or overlap == right or ratio >= 0.8:
        return "exact"
    if ratio >= 0.5:
        return "strong"
    if ratio >= 0.3:
        return "partial"
    return "weak"


def _trim(values: list[float], pct: float = 0.10) -> list[float]:
    ordered = sorted(values)
    if len(ordered) < 4:
        return ordered
    cut = max(1, int(len(ordered) * pct))
    if cut * 2 >= len(ordered):
        return ordered
    return ordered[cut:-cut]


SOLD_COMP_SOURCE_EBAY = "ebay_sold"
SOLD_COMP_SOURCE_UNAVAILABLE = "SOLD_COMP_SOURCE_UNAVAILABLE"


def _quantile(sample: list[float], pct: float) -> float:
    if not sample:
        return 0.0
    ordered = sorted(sample)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return float(ordered[lo] * (1 - frac) + ordered[hi] * frac)


def summarize_comps(comps: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = [row for row in (comps or []) if _f(row.get("price"), 0) > 0]
    prices = [_f(row.get("price")) for row in rows]
    sold_count = len(prices)
    if not prices:
        return {
            "sold_count": 0,
            "sold_median": 0.0,
            "sold_average": 0.0,
            "sold_low": 0.0,
            "sold_high": 0.0,
            "sold_q1": 0.0,
            "sold_q3": 0.0,
            "conservative_resale": 0.0,
            "comp_confidence": "NONE",
            "spread_ratio": 0.0,
        }
    trimmed = _trim(prices)
    sample = trimmed or prices
    median = float(statistics.median(sample))
    average = float(statistics.mean(sample))
    low = float(min(sample))
    high = float(max(sample))
    q1 = _quantile(sample, 0.25) if sold_count >= 4 else median
    q3 = _quantile(sample, 0.75) if sold_count >= 4 else median
    conservative = q1 if sold_count >= 4 and q1 > 0 else median
    spread = (high - low) / median if median else 1.0
    if sold_count >= 8 and spread <= 0.45:
        confidence = "HIGH"
    elif sold_count >= 4 and spread <= 0.8:
        confidence = "MEDIUM"
    elif sold_count >= 1:
        confidence = "LOW"
    else:
        confidence = "NONE"
    return {
        "sold_count": sold_count,
        "sold_median": round(median, 2),
        "sold_average": round(average, 2),
        "sold_low": round(low, 2),
        "sold_high": round(high, 2),
        "sold_q1": round(q1, 2),
        "sold_q3": round(q3, 2),
        "conservative_resale": round(conservative, 2),
        "comp_confidence": confidence,
        "spread_ratio": round(spread, 3),
    }


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        return str(value.get("__value__") or value.get("value") or value.get("title") or "")
    return str(value or "")


def _finding_sold_comps(query: str) -> dict[str, Any]:
    app_id = env_str("EBAY_CLIENT_ID") or env_str("EBAY_APP_ID")
    if not app_id or not query or requests is None:
        return {"ok": False, "comps": [], "http_status": 0, "error": "missing_app_id_or_client", "ack": ""}
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "true",
        "keywords": query,
        "paginationInput.entriesPerPage": "20",
        "sortOrder": "EndTimeSoonest",
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "LocatedIn",
        "itemFilter(1).value": "US",
    }
    try:
        response = requests.get(
            "https://svcs.ebay.com/services/search/FindingService/v1",
            params=params,
            timeout=20,
        )
        http_status = int(getattr(response, "status_code", 0) or 0)
        if http_status >= 400:
            return {"ok": False, "comps": [], "http_status": http_status, "error": f"http_{http_status}", "ack": ""}
        payload = response.json()
    except Exception:
        return {"ok": False, "comps": [], "http_status": 0, "error": "request_failed", "ack": ""}
    root = payload.get("findCompletedItemsResponse") or []
    if isinstance(root, dict):
        root = [root]
    if not root:
        return {"ok": False, "comps": [], "http_status": http_status, "error": "empty_response", "ack": ""}
    block = root[0] if isinstance(root[0], dict) else {}
    ack = _first_text(block.get("ack")).strip()
    if ack.lower() in {"failure", "partialfailure"}:
        return {"ok": False, "comps": [], "http_status": http_status, "error": "finding_ack_failure", "ack": ack}
    result = (block.get("searchResult") or [{}])[0]
    items = result.get("item") or []
    comps = []
    from marketplace.normalize import utc_now
    retrieved = utc_now()
    for item in items:
        title = _first_text(item.get("title"))
        url = _first_text(item.get("viewItemURL"))
        item_id = _first_text(item.get("itemId"))
        selling = item.get("sellingStatus") or [{}]
        if isinstance(selling, list):
            selling = selling[0] if selling else {}
        current = selling.get("currentPrice") or [{}]
        if isinstance(current, list):
            current = current[0] if current else {}
        price = _f(current.get("__value__") or current.get("value"))
        selling_state = _first_text(selling.get("sellingState")).lower()
        listing_info = item.get("listingInfo") or [{}]
        if isinstance(listing_info, list):
            listing_info = listing_info[0] if listing_info else {}
        end_time = _first_text(listing_info.get("endTime"))
        shipping_info = item.get("shippingInfo") or [{}]
        if isinstance(shipping_info, list):
            shipping_info = shipping_info[0] if shipping_info else {}
        ship_cost = shipping_info.get("shippingServiceCost") or [{}]
        if isinstance(ship_cost, list):
            ship_cost = ship_cost[0] if ship_cost else {}
        shipping = ship_cost.get("__value__") or ship_cost.get("value")
        condition = item.get("condition") or [{}]
        if isinstance(condition, list):
            condition = condition[0] if condition else {}
        condition_name = _first_text(condition.get("conditionDisplayName") or condition.get("conditionDisplayName"))
        if price > 0 and (not selling_state or "sold" in selling_state or "ended" in selling_state or "completed" in selling_state):
            comps.append({
                "source": SOLD_COMP_SOURCE_EBAY,
                "source_comp_id": item_id,
                "canonical_product": query,
                "title": str(title or ""),
                "price": price,
                "shipping": None if shipping in (None, "") else _f(shipping),
                "condition": condition_name,
                "variant": "",
                "sold_at": str(end_time or ""),
                "url": str(url or ""),
                "retrieved_at": retrieved,
                "include_decision": "include",
                "selling_state": selling_state,
                "match_quality": match_quality(query, str(title or "")),
            })
    return {"ok": True, "comps": comps, "http_status": http_status, "error": "", "ack": ack, "retrieved_at": retrieved}


def fetch_sold_comps(query: str) -> dict[str, Any]:
    query = str(query or "").strip()
    result = _finding_sold_comps(query)
    comps = list(result.get("comps") or [])
    if result.get("ok") and comps:
        return {
            "comps": comps,
            "source": SOLD_COMP_SOURCE_EBAY,
            "sold_comp_state": SOLD_COMP_SOURCE_EBAY,
            "http_status": result.get("http_status"),
            "ack": result.get("ack") or "",
            "error": "",
        }
    return {
        "comps": [],
        "source": SOLD_COMP_SOURCE_UNAVAILABLE,
        "sold_comp_state": SOLD_COMP_SOURCE_UNAVAILABLE,
        "http_status": result.get("http_status") or 0,
        "ack": result.get("ack") or "",
        "error": result.get("error") or "no_completed_records",
    }


def resolve_comps(query: str, comps_lookup: Callable[..., Any] | None = None) -> dict[str, Any]:
    if comps_lookup is not None:
        raw = comps_lookup(query)
        if isinstance(raw, dict):
            comps = list(raw.get("comps") or [])
            source = str(raw.get("source") or "")
        elif isinstance(raw, list):
            comps = raw
            source = ""
        else:
            comps = []
            source = ""
        sold_like = [row for row in comps if str(row.get("source") or "") in {"", SOLD_COMP_SOURCE_EBAY}]
        if source in {"", SOLD_COMP_SOURCE_EBAY} and sold_like:
            return {"comps": sold_like, "source": SOLD_COMP_SOURCE_EBAY, "sold_comp_state": SOLD_COMP_SOURCE_EBAY}
        return {"comps": [], "source": SOLD_COMP_SOURCE_UNAVAILABLE, "sold_comp_state": SOLD_COMP_SOURCE_UNAVAILABLE}
    return fetch_sold_comps(query)


def usable_sold_comps(listing_title: str, comps: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], int, bool]:
    usable = []
    rejected = 0
    for comp in comps or []:
        source = str(comp.get("source") or "")
        if source and source != SOLD_COMP_SOURCE_EBAY:
            rejected += 1
            continue
        quality = match_quality(listing_title, str(comp.get("title") or ""))
        if quality == "weak":
            rejected += 1
            continue
        row = dict(comp)
        row["match_quality"] = quality
        row["source"] = SOLD_COMP_SOURCE_EBAY
        row["include_decision"] = "include"
        usable.append(row)
    return usable, rejected, bool(usable)
