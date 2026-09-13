from __future__ import annotations

import re
from typing import Any

from dealbrain.economics import _f, net_resale, roi_pct, score_economics
from dealbrain.first_profit import PHONE_CHECKLIST, is_phone
from marketplace.normalize import utc_now

SCREEN_ONLY = "SCREEN_ONLY_LIKELY"
BATTERY_ONLY = "BATTERY_ONLY_LIKELY"
COSMETIC_ONLY = "COSMETIC_ONLY"
CHARGING_PORT = "CHARGING_PORT"
PORT_CHARGING = CHARGING_PORT
CAMERA_MODULE = "CAMERA_MODULE"
CAMERA = CAMERA_MODULE
CONTROLLER_JOYSTICK = "CONTROLLER / JOYSTICK"
JOYSTICK = CONTROLLER_JOYSTICK
BACK_GLASS = "BACK_GLASS"
UNKNOWN_ELECTRICAL = "UNKNOWN_ELECTRICAL"
NO_POWER = "NO_POWER"
WATER_DAMAGE = "WATER_DAMAGE"
MOTHERBOARD = "MOTHERBOARD / LOGIC_BOARD"
ACCOUNT_LOCK = "ACCOUNT_LOCK"
PARTS_ONLY = "PARTS_ONLY"
UNKNOWN = "UNKNOWN"

PREFERRED_REPAIR_TYPES = {SCREEN_ONLY, BATTERY_ONLY, COSMETIC_ONLY}
SECONDARY_REPAIR_TYPES = {CHARGING_PORT, CONTROLLER_JOYSTICK, CAMERA_MODULE, BACK_GLASS}
DEPRIORITIZED_REPAIR_TYPES = {NO_POWER, WATER_DAMAGE, MOTHERBOARD, UNKNOWN_ELECTRICAL, ACCOUNT_LOCK}

HIGH_VALUE_FAMILIES = {
    "iphone-15-pro-max", "iphone-15-pro", "iphone-16-pro", "iphone-14-pro", "iphone-13-pro",
    "galaxy-s24-ultra", "galaxy-s-family", "pixel-pro", "macbook-air-m1", "macbook-air-m2-m3",
    "macbook-pro-silicon", "ipad-silicon", "steam-deck", "switch-oled", "ps5", "rtx-4070",
    "rtx-4080-4090", "rog-ally", "camera-drone",
}

REPAIR_QUERIES = [
    {"query": "cracked iphone", "query_type": "REPAIR", "product_family": "iphone-15-16-base", "priority": 32},
    {"query": "iphone cracked screen", "query_type": "REPAIR", "product_family": "iphone-15-pro", "priority": 30},
    {"query": "iphone broken screen", "query_type": "REPAIR", "product_family": "iphone-15-pro", "priority": 30},
    {"query": "iphone needs screen", "query_type": "REPAIR", "product_family": "iphone-15-pro", "priority": 31},
    {"query": "broken iphone", "query_type": "REPAIR", "product_family": "iphone-15-16-base", "priority": 34},
    {"query": "iphone for repair", "query_type": "REPAIR", "product_family": "iphone-15-16-base", "priority": 34},
    {"query": "cracked samsung", "query_type": "REPAIR", "product_family": "galaxy-s-family", "priority": 34},
    {"query": "galaxy cracked screen", "query_type": "REPAIR", "product_family": "galaxy-s-family", "priority": 32},
    {"query": "broken galaxy", "query_type": "REPAIR", "product_family": "galaxy-s-family", "priority": 36},
    {"query": "samsung needs screen", "query_type": "REPAIR", "product_family": "galaxy-s-family", "priority": 34},
    {"query": "ipad cracked", "query_type": "REPAIR", "product_family": "ipad-silicon", "priority": 36},
    {"query": "ipad broken screen", "query_type": "REPAIR", "product_family": "ipad-silicon", "priority": 34},
    {"query": "macbook cracked screen", "query_type": "REPAIR", "product_family": "macbook-air-m2-m3", "priority": 32},
    {"query": "broken macbook", "query_type": "REPAIR", "product_family": "macbook-air-m1", "priority": 36},
    {"query": "steam deck broken", "query_type": "REPAIR", "product_family": "steam-deck", "priority": 34},
    {"query": "steam deck screen", "query_type": "REPAIR", "product_family": "steam-deck", "priority": 34},
    {"query": "switch broken", "query_type": "REPAIR", "product_family": "switch-oled", "priority": 34},
    {"query": "switch screen", "query_type": "REPAIR", "product_family": "switch-oled", "priority": 34},
    {"query": "ps5 broken", "query_type": "REPAIR", "product_family": "ps5", "priority": 38},
    {"query": "xbox broken", "query_type": "REPAIR", "product_family": "xbox-series", "priority": 40},
    {"query": "gaming laptop broken", "query_type": "REPAIR", "product_family": "gaming-pc", "priority": 40},
    {"query": "camera broken", "query_type": "REPAIR", "product_family": "camera-drone", "priority": 42},
    {"query": "camera for repair", "query_type": "REPAIR", "product_family": "camera-drone", "priority": 42},
]

GENERIC_HIGH_VALUE_QUERIES = [
    {"query": "old iphone", "query_type": "GENERIC", "product_family": "iphone-15-16-base", "priority": 44},
    {"query": "apple phone", "query_type": "GENERIC", "product_family": "iphone-15-16-base", "priority": 46},
    {"query": "old samsung", "query_type": "GENERIC", "product_family": "galaxy-s-family", "priority": 48},
    {"query": "broken phone", "query_type": "REPAIR", "product_family": "iphone-15-16-base", "priority": 42},
    {"query": "cracked phone", "query_type": "REPAIR", "product_family": "iphone-15-16-base", "priority": 40},
    {"query": "phone lot", "query_type": "BUNDLE", "product_family": "iphone-15-16-base", "priority": 42},
    {"query": "apple laptop", "query_type": "GENERIC", "product_family": "macbook-air-m2-m3", "priority": 44},
    {"query": "old macbook", "query_type": "GENERIC", "product_family": "macbook-air-m1", "priority": 44},
    {"query": "broken laptop", "query_type": "REPAIR", "product_family": "macbook-air-m1", "priority": 46},
    {"query": "gaming laptop", "query_type": "GENERIC", "product_family": "gaming-pc", "priority": 44},
    {"query": "gaming pc", "query_type": "GENERIC", "product_family": "gaming-pc", "priority": 40},
    {"query": "gaming computer", "query_type": "GENERIC", "product_family": "gaming-pc", "priority": 42},
    {"query": "computer parts", "query_type": "GENERIC", "product_family": "rtx-4070", "priority": 48},
    {"query": "graphics card", "query_type": "GENERIC", "product_family": "rtx-4070", "priority": 40},
    {"query": "gpu", "query_type": "GENERIC", "product_family": "rtx-4070", "priority": 40},
    {"query": "old camera", "query_type": "GENERIC", "product_family": "camera-drone", "priority": 48},
    {"query": "camera stuff", "query_type": "GENERIC", "product_family": "camera-drone", "priority": 50},
    {"query": "camera lens", "query_type": "GENERIC", "product_family": "camera-drone", "priority": 46},
    {"query": "camera bundle", "query_type": "BUNDLE", "product_family": "camera-drone", "priority": 44},
    {"query": "game system", "query_type": "GENERIC", "product_family": "ps5", "priority": 46},
    {"query": "old consoles", "query_type": "GENERIC", "product_family": "retro-nintendo", "priority": 46},
    {"query": "console lot", "query_type": "BUNDLE", "product_family": "ps5", "priority": 44},
    {"query": "gaming stuff", "query_type": "GENERIC", "product_family": "electronics-generic", "priority": 50},
    {"query": "electronics lot", "query_type": "BUNDLE", "product_family": "electronics-generic", "priority": 44},
    {"query": "electronics must go", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 48},
    {"query": "moving electronics", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 48},
    {"query": "garage electronics", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 50},
    {"query": "box of electronics", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 46},
]
TREASURE_ELECTRONICS_QUERIES = GENERIC_HIGH_VALUE_QUERIES

SEED_REPAIR_COSTS: list[dict[str, Any]] = [
    {"product_family": "iphone-13-pro", "exact_model": "iPhone 13 Pro", "repair_type": SCREEN_ONLY, "parts_estimate": 80, "labor_estimate": 80, "donald_diy": 1, "outside_repair_cost": 180, "risk_reserve": 75, "source_note": "admin seed; approximate street parts/labor, not a quote"},
    {"product_family": "iphone-13-pro", "exact_model": "iPhone 13 Pro Max", "repair_type": SCREEN_ONLY, "parts_estimate": 90, "labor_estimate": 80, "donald_diy": 1, "outside_repair_cost": 200, "risk_reserve": 80, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-14-pro", "exact_model": "iPhone 14 Pro", "repair_type": SCREEN_ONLY, "parts_estimate": 100, "labor_estimate": 90, "donald_diy": 1, "outside_repair_cost": 220, "risk_reserve": 90, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-14-pro", "exact_model": "iPhone 14 Pro Max", "repair_type": SCREEN_ONLY, "parts_estimate": 110, "labor_estimate": 90, "donald_diy": 1, "outside_repair_cost": 240, "risk_reserve": 95, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-15-pro", "exact_model": "iPhone 15 Pro", "repair_type": SCREEN_ONLY, "parts_estimate": 120, "labor_estimate": 100, "donald_diy": 1, "outside_repair_cost": 260, "risk_reserve": 100, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-15-pro-max", "exact_model": "iPhone 15 Pro Max", "repair_type": SCREEN_ONLY, "parts_estimate": 130, "labor_estimate": 100, "donald_diy": 1, "outside_repair_cost": 280, "risk_reserve": 110, "source_note": "admin seed; approximate"},
    {"product_family": "galaxy-s-family", "exact_model": "Galaxy S23 Ultra", "repair_type": SCREEN_ONLY, "parts_estimate": 120, "labor_estimate": 100, "donald_diy": 0, "outside_repair_cost": 260, "risk_reserve": 110, "source_note": "admin seed; approximate"},
    {"product_family": "galaxy-s24-ultra", "exact_model": "Galaxy S24 Ultra", "repair_type": SCREEN_ONLY, "parts_estimate": 140, "labor_estimate": 110, "donald_diy": 0, "outside_repair_cost": 300, "risk_reserve": 120, "source_note": "admin seed; approximate"},
    {"product_family": "macbook-air-m1", "exact_model": "MacBook Air M1", "repair_type": SCREEN_ONLY, "parts_estimate": 180, "labor_estimate": 150, "donald_diy": 0, "outside_repair_cost": 380, "risk_reserve": 150, "source_note": "admin seed; approximate"},
    {"product_family": "macbook-air-m2-m3", "exact_model": "MacBook Air M2", "repair_type": SCREEN_ONLY, "parts_estimate": 200, "labor_estimate": 160, "donald_diy": 0, "outside_repair_cost": 420, "risk_reserve": 160, "source_note": "admin seed; approximate"},
    {"product_family": "ipad-silicon", "exact_model": "iPad Pro", "repair_type": SCREEN_ONLY, "parts_estimate": 180, "labor_estimate": 150, "donald_diy": 0, "outside_repair_cost": 380, "risk_reserve": 150, "source_note": "admin seed; approximate"},
    {"product_family": "switch-oled", "exact_model": "Nintendo Switch OLED", "repair_type": SCREEN_ONLY, "parts_estimate": 50, "labor_estimate": 60, "donald_diy": 1, "outside_repair_cost": 130, "risk_reserve": 40, "source_note": "admin seed; approximate"},
    {"product_family": "steam-deck", "exact_model": "Steam Deck OLED", "repair_type": SCREEN_ONLY, "parts_estimate": 120, "labor_estimate": 80, "donald_diy": 1, "outside_repair_cost": 220, "risk_reserve": 90, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-15-pro", "exact_model": "iPhone 15 Pro", "repair_type": BATTERY_ONLY, "parts_estimate": 40, "labor_estimate": 40, "donald_diy": 1, "outside_repair_cost": 99, "risk_reserve": 40, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-15-pro-max", "exact_model": "iPhone 15 Pro Max", "repair_type": BATTERY_ONLY, "parts_estimate": 45, "labor_estimate": 40, "donald_diy": 1, "outside_repair_cost": 110, "risk_reserve": 45, "source_note": "admin seed; approximate"},
    {"product_family": "iphone-14-pro", "exact_model": "iPhone 14 Pro Max", "repair_type": BATTERY_ONLY, "parts_estimate": 40, "labor_estimate": 40, "donald_diy": 1, "outside_repair_cost": 99, "risk_reserve": 40, "source_note": "admin seed; approximate"},
    {"product_family": "macbook-air-m1", "exact_model": "MacBook Air M1", "repair_type": BATTERY_ONLY, "parts_estimate": 80, "labor_estimate": 80, "donald_diy": 0, "outside_repair_cost": 180, "risk_reserve": 70, "source_note": "admin seed; approximate"},
    {"product_family": "steam-deck", "exact_model": "Steam Deck OLED", "repair_type": JOYSTICK, "parts_estimate": 25, "labor_estimate": 30, "donald_diy": 1, "outside_repair_cost": 70, "risk_reserve": 25, "source_note": "admin seed; approximate"},
    {"product_family": "electronics-generic", "exact_model": "", "repair_type": UNKNOWN, "parts_estimate": None, "labor_estimate": None, "donald_diy": 0, "outside_repair_cost": None, "risk_reserve": 150, "confidence": "LOW", "cost_known": False, "cost_status": "UNKNOWN", "source_note": "unknown repair cost is UNKNOWN, never $0"},
]

_SCREEN = re.compile(
    r"\b(cracked\s+screen|broken\s+screen|screen\s+(?:cracked|broken|out)|needs?\s+screen|glass\s+cracked|lcd\s+cracked|"
    r"cracked\s+(?:iphone|galaxy|pixel|ipad|macbook|switch)|(?:iphone|galaxy|pixel|ipad)\s+cracked)\b"
)
_WORKS = re.compile(r"\b(works|working|powers?\s+on|turns?\s+on|phone\s+works|fully\s+functional except|everything works except)\b")
_BATTERY = re.compile(r"\b(battery\s+(?:swollen|swell|health|needs? replacing|only)|needs?\s+battery|bad\s+battery)\b")
_COSMETIC = re.compile(r"\b(cosmetic|scuff|scratch|dent|wear|hairline)\b")
_PORT = re.compile(r"\b(charging\s+port|charge\s+port|usb[\s-]?c\s+port|lightning\s+port|won't charge|wont charge)\b")
_CAMERA = re.compile(r"\b(camera\s+(?:broken|blurry|not working|module)|rear camera|front camera)\b")
_JOY = re.compile(r"\b(joy[\s-]?con|joystick|stick\s+drift|drift|controller)\b")
_BACK_GLASS = re.compile(r"\b(back\s+glass|rear\s+glass|cracked\s+back)\b")
_NO_POWER = re.compile(r"\b(no power|won't turn on|wont turn on|does not turn on|dead|no boot)\b")
_WATER = re.compile(r"\b(water(?:\s+damage)?|liquid(?:\s+damage)?|wet|dropped in (?:pool|toilet|sink))\b")
_BOARD = re.compile(r"\b(motherboard|logic board|board issue|no backlight)\b")
_LOCK = re.compile(r"\b(icloud|activation lock|mdm|fmip|find my|account lock|icloud locked)\b")
_PARTS = re.compile(r"\b(parts only|for parts|parting out|board only)\b")
_BROKEN = re.compile(r"\b(broken|cracked|for repair|needs repair|as is|untested|not working)\b")
_IMEI = re.compile(r"\b(imei|blacklist|financed|financing|esn)\b")


def _blob(listing: dict[str, Any]) -> str:
    return f"{listing.get('title') or ''} {listing.get('description') or ''} {listing.get('normalized_title') or ''}".lower()


def classify_damage(listing: dict[str, Any] | None) -> dict[str, Any]:
    listing = listing or {}
    blob = _blob(listing)
    isolated = False
    repair_type = UNKNOWN
    warnings: list[str] = []
    if _PARTS.search(blob):
        repair_type = PARTS_ONLY
    elif _LOCK.search(blob):
        repair_type = ACCOUNT_LOCK
        warnings.append("ACTIVATION LOCK / iCloud / account lock — do not buy as a working repair")
    elif _WATER.search(blob):
        repair_type = WATER_DAMAGE
        warnings.append("WATER DAMAGE — heavily deprioritize")
    elif _NO_POWER.search(blob):
        repair_type = NO_POWER
        warnings.append("NO POWER — likely more than a cheap repair")
    elif _BOARD.search(blob):
        repair_type = MOTHERBOARD
        warnings.append("BOARD / logic-board language — nightmare repair")
    elif _BACK_GLASS.search(blob) and not re.search(r"\b(screen|lcd|display)\b", blob):
        repair_type = BACK_GLASS
        isolated = True
    elif _SCREEN.search(blob) and _WORKS.search(blob) and not (_WATER.search(blob) or _NO_POWER.search(blob) or _BOARD.search(blob) or _LOCK.search(blob)):
        repair_type = SCREEN_ONLY
        isolated = True
    elif _SCREEN.search(blob) and not (_WATER.search(blob) or _NO_POWER.search(blob) or _BOARD.search(blob) or _LOCK.search(blob)):
        repair_type = SCREEN_ONLY
        isolated = False
        warnings.append("Cracked screen does NOT prove the screen is the only problem")
    elif _BATTERY.search(blob) and not (_WATER.search(blob) or _NO_POWER.search(blob) or _SCREEN.search(blob)):
        repair_type = BATTERY_ONLY
        isolated = True
    elif _PORT.search(blob):
        repair_type = CHARGING_PORT
    elif _CAMERA.search(blob):
        repair_type = CAMERA_MODULE
    elif _JOY.search(blob):
        repair_type = CONTROLLER_JOYSTICK
        isolated = True
    elif _COSMETIC.search(blob) and _WORKS.search(blob):
        repair_type = COSMETIC_ONLY
        isolated = True
    elif _BROKEN.search(blob):
        repair_type = UNKNOWN_ELECTRICAL if re.search(r"\b(not working|doesn't work|untested|as is)\b", blob) else UNKNOWN
    preferred = repair_type in PREFERRED_REPAIR_TYPES and isolated
    secondary = repair_type in SECONDARY_REPAIR_TYPES
    deprioritized = repair_type in DEPRIORITIZED_REPAIR_TYPES or (repair_type == SCREEN_ONLY and not isolated)
    if is_phone(str(listing.get("candidate_product_family") or "")) or "iphone" in blob or "galaxy" in blob:
        warnings.extend([
            "PHONE VERIFICATION REQUIRED — never auto-HOT",
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
        ])
        if _IMEI.search(blob):
            warnings.append("IMEI / financing language present — treat as hard block until verified")
        if _LOCK.search(blob):
            warnings.append("ACTIVATION LOCK warning")
    return {
        "repair_type": repair_type,
        "damage_isolated": isolated,
        "preferred_repair": preferred,
        "secondary_repair": secondary,
        "deprioritized_repair": deprioritized or repair_type in DEPRIORITIZED_REPAIR_TYPES,
        "repair_warnings": warnings,
        "phone_checklist": list(PHONE_CHECKLIST) if is_phone(str(listing.get("candidate_product_family") or "")) or "iphone" in blob else [],
        "screen_only_confident": repair_type == SCREEN_ONLY and isolated,
        "note": "Listing language is a hint. Manual verification is required before buying.",
    }


def repair_cost_id(family: str, model: str, repair_type: str) -> str:
    return "|".join(part for part in (str(family or "").strip(), str(model or "").strip(), str(repair_type or "").strip()) if part) or "unknown"


def lookup_repair_cost(
    *,
    family: str = "",
    model: str = "",
    repair_type: str = "",
    store_lookup=None,
) -> dict[str, Any]:
    if callable(store_lookup):
        found = store_lookup(family=family, model=model, repair_type=repair_type) or {}
        if found:
            return found
    ranked: list[dict[str, Any]] = []
    for row in SEED_REPAIR_COSTS:
        if repair_type and str(row.get("repair_type") or "") != str(repair_type):
            continue
        score = 0
        if model and str(row.get("exact_model") or "").lower() == str(model).lower():
            score += 4
        if family and str(row.get("product_family") or "") == family:
            score += 2
        if str(row.get("repair_type") or "") == repair_type:
            score += 3
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked and ranked[0][0] >= 5:
        chosen = dict(ranked[0][1])
        chosen["matched"] = True
        parts = chosen.get("parts_estimate")
        labor = chosen.get("labor_estimate")
        chosen["cost_known"] = parts not in (None, "") and labor not in (None, "")
        chosen["cost_status"] = "KNOWN" if chosen["cost_known"] else "UNKNOWN"
        chosen["confidence"] = chosen.get("confidence") or "MEDIUM"
        return chosen
    fallback = dict(SEED_REPAIR_COSTS[-1])
    fallback["matched"] = False
    fallback["repair_type"] = repair_type or UNKNOWN
    fallback["product_family"] = family
    fallback["exact_model"] = model
    fallback["parts_estimate"] = None
    fallback["labor_estimate"] = None
    fallback["cost_known"] = False
    fallback["cost_status"] = "UNKNOWN"
    fallback["confidence"] = "LOW"
    fallback["source_note"] = "no exact cost row; repair cost UNKNOWN, not $0"
    return fallback


def unknown_damage_reserve(base_reserve: float, *, isolated: bool, repair_type: str, asking: float = 0.0) -> float:
    base = max(_f(base_reserve), 40.0)
    if repair_type in DEPRIORITIZED_REPAIR_TYPES:
        return round(max(base * 3.0, 200.0), 2)
    if not isolated:
        return round(max(base * 2.0, 100.0), 2)
    return round(base, 2)


def max_repair_buy(
    *,
    working_net: float,
    parts: float,
    labor: float,
    risk_reserve: float,
    target_profit: float,
) -> float:
    return round(_f(working_net) - _f(parts) - _f(labor) - _f(risk_reserve) - _f(target_profit), 2)


def repair_economics(
    listing: dict[str, Any],
    *,
    working_conservative_exit: float,
    damage: dict[str, Any] | None = None,
    cost_row: dict[str, Any] | None = None,
    inbound_shipping: float | None = None,
    local_pickup: bool = False,
    tax: float = 0.0,
    target_profit: float = 175.0,
    config=None,
) -> dict[str, Any]:
    damage = damage or classify_damage(listing)
    family = str(listing.get("candidate_product_family") or "")
    model = str(listing.get("candidate_model") or "")
    cost_row = cost_row or lookup_repair_cost(family=family, model=model, repair_type=str(damage.get("repair_type") or ""))
    parts_raw = cost_row.get("parts_estimate")
    labor_raw = cost_row.get("labor_estimate")
    cost_known = bool(cost_row.get("cost_known", parts_raw not in (None, "") and labor_raw not in (None, "")))
    if str(cost_row.get("cost_status") or "").upper() == "UNKNOWN":
        cost_known = False
    parts = _f(parts_raw) if cost_known else None
    labor = _f(labor_raw) if cost_known else None
    risk = unknown_damage_reserve(
        _f(cost_row.get("risk_reserve")),
        isolated=bool(damage.get("damage_isolated")),
        repair_type=str(damage.get("repair_type") or ""),
        asking=_f(listing.get("asking_price")),
    )
    asking = _f(listing.get("asking_price"))
    working_net = net_resale(_f(working_conservative_exit), local_pickup=local_pickup, config=config)
    if not cost_known:
        return {
            **damage,
            "working_conservative_exit": round(_f(working_conservative_exit), 2),
            "working_conservative_net": working_net,
            "WORKING_CONSERVATIVE_EXIT": round(_f(working_conservative_exit), 2),
            "parts_estimate": None,
            "labor_estimate": None,
            "REPAIR_PARTS_RESERVE": None,
            "REPAIR_LABOR_RESERVE": None,
            "repair_risk_reserve": risk,
            "REPAIR_RISK_RESERVE": risk,
            "estimated_repair": None,
            "total_repair_cost": None,
            "TOTAL_REPAIR_COST": None,
            "repaired_net_exit": None,
            "REPAIRED_NET_EXIT": None,
            "repair_expected_profit": None,
            "REPAIR_EXPECTED_PROFIT": None,
            "repair_roi": None,
            "REPAIR_ROI": None,
            "max_repair_buy": None,
            "MAX_REPAIR_BUY": None,
            "cost_known": False,
            "cost_status": "UNKNOWN",
            "repair_alert_ok": False,
            "below_max_buy": False,
            "repair_cost_source": cost_row.get("source_note") or "UNKNOWN",
            "note": "repair cost UNKNOWN — not $0",
        }
    repair_total = round(_f(parts) + _f(labor), 2)
    extra = round(repair_total + risk + _f(tax), 2)
    econ = score_economics(
        asking=asking,
        conservative_resale=_f(working_conservative_exit),
        local_pickup=local_pickup,
        inbound_shipping=inbound_shipping,
        extra_costs=extra,
        buyer_tax=_f(tax),
        repair_reserve=0.0,
        config=config,
    )
    max_buy = max_repair_buy(
        working_net=working_net,
        parts=_f(parts),
        labor=_f(labor),
        risk_reserve=risk,
        target_profit=target_profit,
    )
    profit = econ["expected_profit"]
    repaired_net = round(working_net - repair_total - risk, 2)
    roi = roi_pct(profit, econ["landed_cost"])
    easy_repair = bool(damage.get("preferred_repair") or damage.get("secondary_repair"))
    return {
        **econ,
        **damage,
        "working_conservative_exit": round(_f(working_conservative_exit), 2),
        "working_conservative_net": working_net,
        "WORKING_CONSERVATIVE_EXIT": round(_f(working_conservative_exit), 2),
        "parts_estimate": parts,
        "labor_estimate": labor,
        "REPAIR_PARTS_RESERVE": parts,
        "REPAIR_LABOR_RESERVE": labor,
        "estimated_repair": repair_total,
        "total_repair_cost": round(repair_total + risk, 2),
        "TOTAL_REPAIR_COST": round(repair_total + risk, 2),
        "repair_risk_reserve": risk,
        "REPAIR_RISK_RESERVE": risk,
        "repaired_net_exit": repaired_net,
        "REPAIRED_NET_EXIT": repaired_net,
        "repair_expected_profit": profit,
        "REPAIR_EXPECTED_PROFIT": profit,
        "repair_roi": roi,
        "REPAIR_ROI": roi,
        "max_repair_buy": max_buy,
        "MAX_REPAIR_BUY": max_buy,
        "target_profit": round(_f(target_profit), 2),
        "repair_cost_source": cost_row.get("source_note") or "",
        "repair_diy": bool(cost_row.get("donald_diy")),
        "outside_repair_cost": _f(cost_row.get("outside_repair_cost")),
        "cost_known": True,
        "cost_status": "KNOWN",
        "below_max_buy": asking > 0 and asking <= max_buy,
        "repair_alert_ok": (
            easy_repair
            and not bool(damage.get("deprioritized_repair"))
            and profit >= 50
            and asking <= max_buy
            and str(listing.get("identity_confidence") or "").upper() in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"}
        ),
    }


def potential_value_gate(
    *,
    asking: float = 0.0,
    potential_value: float = 0.0,
    floor: float = 200.0,
    identity: str = "",
    junk: bool = False,
    treasure: bool = False,
) -> dict[str, Any]:
    if junk and str(identity or "").upper() not in {"CONFIRMED", "STRONG", "FAMILY_ONLY"}:
        return {"pass": False, "reason": "junk_electronics"}
    value = max(_f(asking), _f(potential_value))
    if str(identity or "").upper() in {"CONFIRMED", "STRONG", "FAMILY_ONLY"}:
        return {"pass": True, "reason": "identifiable_product", "value": value, "floor": floor}
    if treasure and value >= 80:
        return {"pass": True, "reason": "treasure_evidence", "value": value, "floor": floor}
    if value >= floor:
        return {"pass": True, "reason": "high_value_floor", "value": value, "floor": floor}
    return {"pass": False, "reason": "below_high_value_floor", "value": value, "floor": floor}


def worth_repair_analysis(*, family: str = "", potential_value: float = 0.0, asking: float = 0.0, floor: float = 200.0, repair_floor: float = 250.0) -> bool:
    if str(family or "") in HIGH_VALUE_FAMILIES:
        return True
    value = max(_f(potential_value), _f(asking))
    if value >= repair_floor:
        return True
    if value >= floor and str(family or "").startswith(("iphone", "macbook", "ipad", "steam", "rtx", "galaxy")):
        return True
    if 0 < value < 80:
        return False
    return False
