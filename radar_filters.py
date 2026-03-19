import re
from typing import Tuple, Dict, Any

BAD_TERMS = [
    " for ", "compatible", "replacement", "replace", "part", "parts", "fan", "shell", "housing",
    "case", "cover", "folio", "protector", "grip", "mount", "stand", "bracket", "holder",
    "bundle", "lot", "kit", "pack",
    "book", "guide", "manual", "for dummies",
    "repair", "service", "mail-in", "unlock",
    "game only", "disc only", "digital code", "download code", "empty box", "box only", "accessory only",
]

QUESTIONABLE_DAMAGE_TERMS = [
    "untested", "as-is", "as is", "parts only", "broken", "cracked", "not working",
]

DEVICE_TERMS = [
    "iphone", "ipad", "ps5", "ps4", "xbox", "graphics card", "gpu", "laptop", "tablet", "macbook", "switch"
]

ALLOWED_HINTS = [
    "iphone", "android", "phone", "console", "playstation", "xbox", "nintendo", "switch",
    "laptop", "tablet", "ipad", "tool", "drill", "saw", "appliance", "milwaukee", "dewalt"
]

CONSOLE_GAME_MISMATCHES = [
    ("ps5", ["game", "disc", "digital", "dlc", "steelbook"]),
    ("ps4", ["game", "disc", "digital", "dlc", "steelbook"]),
    ("xbox", ["game", "disc", "digital", "dlc", "steelbook"]),
    ("switch", ["game", "cartridge", "case only", "empty case"]),
]


def _norm(text: str) -> str:
    return f" {(text or '').lower().strip()} "


def radar_precheck(deal: Dict[str, Any]) -> Tuple[bool, str]:
    title = str(deal.get("title") or "")
    keyword = str(deal.get("search_keyword") or "")
    text = _norm(f"{title} {keyword}")

    if any(term in text for term in BAD_TERMS):
        return False, "blocked accessory/part/service term"

    for device, mismatch_terms in CONSOLE_GAME_MISMATCHES:
        if device in text and any(term in text for term in mismatch_terms):
            return False, "console/game mismatch"

    # protect against device keyword hijacks like "for iphone", "gpu bracket", etc.
    if any(dev in text for dev in DEVICE_TERMS):
        accessory_context = [
            " for ", "compatible", "case", "cover", "folio", "protector", "grip", "mount",
            "stand", "bracket", "holder", "fan", "part", "parts", "replacement", "kit", "bundle",
            "manual", "book", "guide", "attachment", "dock", "controller only", "charger only"
        ]
        if any(term in text for term in accessory_context):
            return False, "device accessory/part mismatch"

    # require at least one useful category hint, otherwise skip noisy generic posts
    if not any(hint in text for hint in ALLOWED_HINTS):
        return False, "no allowed category hint"

    return True, "ok"


def radar_postcheck(result: Dict[str, Any]) -> Tuple[bool, str]:
    price = float(result.get("price") or 0)
    value = float(result.get("market_value") or result.get("resale") or 0)
    profit = float(result.get("profit") or 0)
    sold_count = int(result.get("sold_count") or 0)
    sell_through_pct = int(result.get("sell_through_pct") or result.get("sell_through") or 0)

    title = str(result.get("title") or "")
    keyword = str(result.get("search_keyword") or "")
    text = _norm(f"{title} {keyword}")

    if any(term in text for term in QUESTIONABLE_DAMAGE_TERMS):
        return False, "damaged/untested listing"

    if price <= 0:
        return False, "invalid price"

    if value <= 0:
        return False, "invalid value"

    # hard sanity cap to stop fake spikes
    if value > price * 2.5:
        return False, "value spike"

    if profit < 10:
        return False, "low profit"

    if sold_count < 3:
        return False, "not enough sold comps"

    if sell_through_pct and sell_through_pct < 35:
        return False, "sell-through too weak"

    return True, "ok"
