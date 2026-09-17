from __future__ import annotations

import re
from typing import Any

from marketplace.normalize import normalize_title_text

try:
    from dj_deal_project.utils.model_parser import normalize_text as _legacy_normalize
except Exception:  # pragma: no cover
    def _legacy_normalize(text: str) -> str:
        return normalize_title_text(text)


IDENTITY_EXACT_CONFIRMED = "EXACT_CONFIRMED"
IDENTITY_EXACT_STRONG = "EXACT_STRONG"
IDENTITY_PROBABLE = "PROBABLE"
IDENTITY_FAMILY_ONLY = "FAMILY_ONLY"
IDENTITY_AMBIGUOUS = "AMBIGUOUS"
IDENTITY_CONTRADICTORY = "CONTRADICTORY"
IDENTITY_ACCESSORY_ONLY = "ACCESSORY_ONLY"
IDENTITY_PARTS_ONLY = "PARTS_ONLY"
IDENTITY_BOX_ONLY = "BOX_ONLY"
IDENTITY_BUNDLE_UNRESOLVED = "BUNDLE_UNRESOLVED"
IDENTITY_FALSE_MATCH = "FALSE_MATCH"
IDENTITY_UNKNOWN = "UNKNOWN"
# Backward-compatible aliases. New code should use EXACT_*.
IDENTITY_CONFIRMED = IDENTITY_EXACT_CONFIRMED
IDENTITY_STRONG = IDENTITY_EXACT_STRONG

ACTIONABLE_IDENTITY = {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG, "CONFIRMED", "STRONG"}
PHONE_FAMILIES = {
    "iphone-15-pro-max", "iphone-15-pro", "iphone-16-pro", "iphone-14-pro",
    "iphone-13-pro", "iphone-15-16-base", "galaxy-s24-ultra", "galaxy-s-family", "pixel-pro",
}
AUDIO_NOT_PHONE_RE = re.compile(
    r"\b(amplifier|voice\s*amp|karaoke|pa\s*system|bullhorn|megaphone|microphone|mic\s*system|"
    r"headset|headphones?|earbuds?|speaker|soundbar|two[\s-]*mic)\b"
)
_FOR_PRODUCT_HEAD_RE = re.compile(
    r"\b(case|cover|skin|pouch|bag|grip|shell|housing|bumper|protector|tempered\s*glass|"
    r"screen\s*protector|screen|replacement\s*screen|charger|cable|cord|adapter|dock|"
    r"controller|joy[\s-]*cons?|water\s*block|replacement\s*fan|cooler|bracket|stand|"
    r"holder|mount|logic\s*board|motherboard|board|fan|parts?)\b.{0,24}\bfor\b"
)
_FOR_NAMED_PRODUCT_RE = re.compile(
    r"\bfor\s+(?:the\s+)?(iphone|ipad|macbook|switch|ps5|playstation|xbox|steam\s*deck|"
    r"galaxy|pixel|rtx|ro g\s*ally|nintendo)\b"
)
_PARTS_RE = re.compile(
    r"\b(parts?\s*only|for\s*parts|parting\s*out|logic\s*board|motherboard|replacement\s*screen|"
    r"replacement\s*fan|gpu\s*fan|graphics\s*card\s*fan|cooler\s*fan|fan\s*only|water\s*block|"
    r"housing\s*only|shell\s*only|board\s*only|digitizer|lcd\s*only|screen\s*assembly)\b"
)
# Multi-fan cooler marketing on a complete GPU (e.g. "Triple Fan") must not look like a bare fan part.
_MULTI_FAN_COOLER_RE = re.compile(
    # Only cooler-count marketing (triple/dual/2-fan/3 fan). Do NOT match model numbers like "4070 fan".
    r"\b(?:triple|dual|twin|single|rgb|[1-4])\s*[\s-]*fans?\b"
)
_BOX_RE = re.compile(r"\b(empty\s*box|box\s*only|box\s*only\s*no\s*console|retail\s*box\s*only)\b")
_BUNDLE_RE = re.compile(r"\b(lot|bundle|mixed|assorted|various)\b")
_CONTROLLER_ONLY_RE = re.compile(r"\b(controller|joy[\s-]*cons?|dualsense|dualshock)s?\s*(only)?\b")
_PREMIUM_VARIANT_TOKENS = {
    "Nintendo Switch OLED": ("oled",),
    "Nintendo Switch 2": ("switch 2", "switch2"),
    "iPhone 15 Pro Max": ("pro max", "promax"),
    "iPhone 14 Pro Max": ("pro max", "promax"),
    "iPhone 13 Pro Max": ("pro max", "promax"),
    "PlayStation 5 Pro": ("ps5 pro", "playstation 5 pro"),
    "Steam Deck OLED": ("oled",),
    "ROG Ally X": ("ally x",),
    "RTX 4070 Ti SUPER": ("ti super",),
    "RTX 4070 SUPER": ("super",),
    "RTX 4070 Ti": ("ti",),
    "RTX 4080 SUPER": ("super",),
    "Galaxy S24 Ultra": ("ultra",),
}


def normalize_identity_confidence(value: str) -> str:
    ident = str(value or "").strip().upper()
    if ident in {"CONFIRMED", "EXACT_CONFIRMED"}:
        return IDENTITY_EXACT_CONFIRMED
    if ident in {"STRONG", "EXACT_STRONG"}:
        return IDENTITY_EXACT_STRONG
    return ident or IDENTITY_UNKNOWN


def identity_is_exact(value: str) -> bool:
    return normalize_identity_confidence(value) in {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG}


def resolved_identity_query(identity: dict[str, Any] | None, title: str = "") -> str:
    identity = identity or {}
    model = str(identity.get("candidate_model") or "").strip()
    canonical = str(identity.get("canonical_product_id") or "").strip()
    if identity_is_exact(str(identity.get("identity_confidence") or "")) and (model or canonical):
        storage = str(identity.get("storage") or "").strip()
        if model and storage and storage not in model:
            return f"{model} {storage}".strip()
        return model or canonical.split("|")[0]
    family = str(identity.get("candidate_product_family") or "").strip()
    ident = normalize_identity_confidence(str(identity.get("identity_confidence") or ""))
    if ident in {IDENTITY_ACCESSORY_ONLY, IDENTITY_PARTS_ONLY, IDENTITY_BOX_ONLY, IDENTITY_FALSE_MATCH}:
        return ""
    if ident == IDENTITY_FAMILY_ONLY and family:
        return ""
    return ""


def category_identity_conflict(category: str, identity: dict[str, Any] | None) -> bool:
    identity = identity or {}
    cat = str(category or "").strip().lower()
    family = str(identity.get("candidate_product_family") or "").lower()
    if not cat:
        return False
    phoneish = any(token in cat for token in ("phone", "iphone", "mobile", "cell"))
    if phoneish and "headphone" not in cat and "microphone" not in cat:
        if family and family not in PHONE_FAMILIES and "iphone" not in family and "galaxy" not in family and "pixel" not in family:
            return True
        if not family:
            return True
    return False

# Longest / most specific first. Never collapse materially different models.
_MODEL_RULES: list[dict[str, Any]] = [
    {"family": "iphone-15-pro-max", "model": "iPhone 15 Pro Max", "patterns": [r"\biphone\s*15\s*pro\s*max\b", r"\b15\s*promax\b", r"\b15pm\b"]},
    {"family": "iphone-15-pro", "model": "iPhone 15 Pro", "patterns": [r"\biphone\s*15\s*pro\b(?!\s*max)", r"\b15\s*pro\b(?!\s*max)"]},
    {"family": "iphone-16-pro", "model": "iPhone 16 Pro Max", "patterns": [r"\biphone\s*16\s*pro\s*max\b"]},
    {"family": "iphone-16-pro", "model": "iPhone 16 Pro", "patterns": [r"\biphone\s*16\s*pro\b(?!\s*max)"]},
    {"family": "iphone-14-pro", "model": "iPhone 14 Pro Max", "patterns": [r"\biphone\s*14\s*pro\s*max\b"]},
    {"family": "iphone-14-pro", "model": "iPhone 14 Pro", "patterns": [r"\biphone\s*14\s*pro\b(?!\s*max)"]},
    {"family": "iphone-13-pro", "model": "iPhone 13 Pro Max", "patterns": [r"\biphone\s*13\s*pro\s*max\b"]},
    {"family": "iphone-13-pro", "model": "iPhone 13 Pro", "patterns": [r"\biphone\s*13\s*pro\b(?!\s*max)"]},
    {"family": "iphone-15-16-base", "model": "iPhone 16", "patterns": [r"\biphone\s*16\b(?!\s*pro)"]},
    {"family": "iphone-15-16-base", "model": "iPhone 15", "patterns": [r"\biphone\s*15\b(?!\s*pro)"]},
    {"family": "galaxy-s24-ultra", "model": "Galaxy S24 Ultra", "patterns": [r"\b(?:samsung\s+)?(?:galaxy\s*)?s24\s*ultra\b"]},
    {"family": "galaxy-s-family", "model": "Galaxy S25 Ultra", "patterns": [r"\b(?:samsung\s+)?(?:galaxy\s*)?s25\s*ultra\b"]},
    {"family": "galaxy-s-family", "model": "Galaxy S23 Ultra", "patterns": [r"\b(?:samsung\s+)?(?:galaxy\s*)?s23\s*ultra\b"]},
    {"family": "galaxy-s-family", "model": "Galaxy S25", "patterns": [r"\b(?:samsung\s+)?(?:galaxy\s*)?s25\b(?!\s*ultra)"]},
    {"family": "galaxy-s-family", "model": "Galaxy S24", "patterns": [r"\b(?:samsung\s+)?(?:galaxy\s*)?s24\b(?!\s*ultra)"]},
    {"family": "pixel-pro", "model": "Pixel 9 Pro", "patterns": [r"\bpixel\s*9\s*pro\b"]},
    {"family": "pixel-pro", "model": "Pixel 8 Pro", "patterns": [r"\bpixel\s*8\s*pro\b"]},
    {"family": "macbook-air-m1", "model": "MacBook Air M1", "patterns": [r"\bmacbook\s*air\s*m1\b", r"\bmba\s*m1\b"]},
    {"family": "macbook-air-m2-m3", "model": "MacBook Air M3", "patterns": [r"\bmacbook\s*air\s*m3\b", r"\bmba\s*m3\b"]},
    {"family": "macbook-air-m2-m3", "model": "MacBook Air M2", "patterns": [r"\bmacbook\s*air\s*m2\b", r"\bmba\s*m2\b"]},
    {"family": "macbook-pro-silicon", "model": "MacBook Pro M3", "patterns": [r"\bmacbook\s*pro\s*m3\b"]},
    {"family": "macbook-pro-silicon", "model": "MacBook Pro M2", "patterns": [r"\bmacbook\s*pro\s*m2\b"]},
    {"family": "macbook-pro-silicon", "model": "MacBook Pro M1", "patterns": [r"\bmacbook\s*pro\s*m1\b"]},
    {"family": "ipad-silicon", "model": "iPad Pro M4", "patterns": [r"\bipad\s*pro\s*m4\b"]},
    {"family": "ipad-silicon", "model": "iPad Pro M2", "patterns": [r"\bipad\s*pro\s*m2\b"]},
    {"family": "ipad-silicon", "model": "iPad Air M2", "patterns": [r"\bipad\s*air\s*m2\b"]},
    {"family": "apple-watch", "model": "Apple Watch Ultra", "patterns": [r"\bapple\s*watch\s*ultra\b", r"\bwatch\s*ultra\b"]},
    {"family": "switch-2", "model": "Nintendo Switch 2", "patterns": [r"\bswitch\s*2\b", r"\bnintendo\s*switch\s*2\b"]},
    {"family": "switch-oled", "model": "Nintendo Switch OLED", "patterns": [r"\bswitch\s*oled\b", r"\boled\s*switch\b", r"\bnintendo\s*switch\s*oled\b"]},
    {"family": "switch-lite", "model": "Nintendo Switch Lite", "patterns": [r"\bswitch\s*lite\b", r"\bnintendo\s*switch\s*lite\b"]},
    {"family": "switch-base", "model": "Nintendo Switch", "patterns": [r"\bnintendo\s*switch\b(?!\s*(?:oled|lite|2))"]},
    {"family": "steam-deck", "model": "Steam Deck OLED", "patterns": [r"\bsteam\s*deck\s*oled\b"]},
    {"family": "steam-deck", "model": "Steam Deck LCD", "patterns": [r"\bsteam\s*deck\s*lcd\b", r"\bsteam\s*deck\b"]},
    {"family": "rog-ally", "model": "ROG Ally X", "patterns": [r"\brog\s*ally\s*x\b"]},
    {"family": "rog-ally", "model": "ROG Ally", "patterns": [r"\brog\s*ally\b(?!\s*x)"]},
    {"family": "ps5", "model": "PlayStation 5 Pro", "patterns": [r"\bps5\s*pro\b", r"\bplaystation\s*5\s*pro\b"]},
    {"family": "ps5", "model": "PlayStation 5 Slim", "patterns": [r"\bps5\s*slim\b", r"\bplaystation\s*5\s*slim\b"]},
    {"family": "ps5", "model": "PlayStation 5", "patterns": [r"\bps5\b(?!\s*(?:pro|slim))", r"\bplaystation\s*5\b(?!\s*(?:pro|slim))", r"\bplay\s*station\s*5\b"]},
    {"family": "xbox-series", "model": "Xbox Series X", "patterns": [r"\bxbox\s*series\s*x\b"]},
    {"family": "xbox-series", "model": "Xbox Series S", "patterns": [r"\bxbox\s*series\s*s\b"]},
    {"family": "rtx-4070", "model": "RTX 4070 Ti SUPER", "patterns": [r"\brtx\s*4070\s*ti\s*super\b"]},
    {"family": "rtx-4070", "model": "RTX 4070 SUPER", "patterns": [r"\brtx\s*4070\s*super\b(?!\s*ti)"]},
    {"family": "rtx-4070", "model": "RTX 4070 Ti", "patterns": [r"\brtx\s*4070\s*ti\b(?!\s*super)"]},
    {"family": "rtx-4070", "model": "RTX 4070", "patterns": [r"\brtx\s*4070\b(?!\s*(?:ti|super))"]},
    {"family": "rtx-4080-4090", "model": "RTX 4090", "patterns": [r"\brtx\s*4090\b"]},
    {"family": "rtx-4080-4090", "model": "RTX 4080 SUPER", "patterns": [r"\brtx\s*4080\s*super\b"]},
    {"family": "rtx-4080-4090", "model": "RTX 4080", "patterns": [r"\brtx\s*4080\b(?!\s*super)"]},
    {"family": "retro-nintendo", "model": "NES Classic Edition", "patterns": [r"\bnes\s*classic(?:\s*edition)?\b", r"\bnintendo\s*classic\s*mini\b"]},
    {"family": "retro-nintendo", "model": "New Nintendo 3DS XL", "patterns": [r"\bnew\s*(?:nintendo\s*)?3ds\s*xl\b"]},
    {"family": "retro-nintendo", "model": "Nintendo 3DS XL", "patterns": [r"\b(?:nintendo\s*)?3ds\s*xl\b"]},
    {"family": "retro-nintendo", "model": "GameCube Controller", "patterns": [r"\bgame\s*cube\s*controller\b", r"\bgamecube\s*controller\b"]},
    {"family": "retro-nintendo", "model": "GameCube", "patterns": [r"\bgame\s*cube\b", r"\bgamecube\b"]},
    {"family": "retro-nintendo", "model": "Nintendo 64", "patterns": [r"\bn64\b", r"\bnintendo\s*64\b"]},
    {"family": "retro-nintendo", "model": "GBA SP AGS-101", "patterns": [r"\bags[\s-]*101\b", r"\bgba\s*sp\s*101\b"]},
    {"family": "retro-nintendo", "model": "GBA SP AGS-001", "patterns": [r"\bags[\s-]*001\b", r"\bgba\s*sp\s*001\b"]},
    {"family": "retro-nintendo", "model": "GBA SP", "patterns": [r"\bgba\s*sp\b", r"\bgame\s*boy\s*advance\s*sp\b"]},
    {"family": "retro-nintendo", "model": "Nintendo 3DS", "patterns": [r"\b3ds\b", r"\bnintendo\s*3ds\b"]},
]

_FAMILY_ONLY_RULES: list[tuple[str, str]] = [
    ("iphone-15-16-base", r"\biphone\b|\bapple\s*phone\b"),
    ("macbook-pro-silicon", r"\bmacbook\s*pro\b"),
    ("macbook-air-m2-m3", r"\bmacbook\s*air\b"),
    ("macbook-intel", r"\bmacbook\b"),
    ("switch-family", r"\bnintendo\s*switch\b"),
    ("gaming-pc", r"\bgaming\s*(?:pc|computer|desktop)\b|\brtx\s*40\d0\b"),
    ("electronics-generic", r"\belectronics\b|\bconsole\b|\blaptop\b"),
    ("camera-drone", r"\bcamera\b|\bdrone\b|\bdji\b|\bcanon\b|\bsony\s*a7\b"),
    ("retro-nintendo", r"\bnintendo\b|\bn64\b|\bgamecube\b"),
]


def _norm(text: str) -> str:
    raw = _legacy_normalize(text) if text else ""
    cleaned = re.sub(r"\s+", " ", str(raw or text or "").lower())
    cleaned = re.sub(r"[^a-z0-9+ ]+", " ", cleaned)
    return f" {cleaned.strip()} "


_ACCESSORY_RE = re.compile(
    r"\b(case|cover|skin|pouch|bag|grip|shell|bumper|protector|tempered\s*glass|screen\s*film|"
    r"screen\s*protector|charger|cable|cord|adapter|dock\s*only|stand|holder|mount|stylus|"
    r"sticker|decal|silicone|carrying|travel\s*bag|microsd|micro\s*sd|sd\s*card|memory\s*card|"
    r"game\s*card|amiibo|water\s*block|cooler|bracket|housing|fan)\b"
)
_UNIT_RE = re.compile(
    r"\b(console|handheld|complete|with\s+dock|w\/?\s*dock|bundle|in\s*box|cib|body\s*only)\b"
)


def _variant_aspects(title: str) -> dict[str, Any]:
    text = _norm(title)
    storage = ""
    match = re.search(r"\b(64|128|256|512|1024|1)\s*(gb|tb)\b", text)
    card_storage = bool(re.search(r"\b(microsd|micro\s*sd|sd\s*card|memory\s*card|game\s*card)\b", text))
    phone_or_laptop = bool(re.search(r"\b(iphone|galaxy|pixel|macbook|ipad)\b", text))
    if match and (phone_or_laptop or not card_storage):
        unit = "TB" if match.group(2).lower() == "tb" else "GB"
        storage = f"{match.group(1)}{unit}"
    carrier = ""
    if "unlocked" in text:
        carrier = "unlocked"
    else:
        m2 = re.search(r"\b(verizon|at&t|att|tmobile|t-mobile|sprint)\b", text)
        if m2:
            carrier = m2.group(1).replace(" ", "")
    return {"storage": storage, "carrier": carrier, "variant": storage}


def _item_kind(title: str, model: str, family: str) -> str:
    text = _norm(title)
    if _BOX_RE.search(text):
        return "empty_box"
    if _PARTS_RE.search(text) and not re.search(r"\b(console|handheld|complete|working|unlocked)\b", text):
        return "parts"
    if _FOR_PRODUCT_HEAD_RE.search(text) or (_FOR_NAMED_PRODUCT_RE.search(text) and _ACCESSORY_RE.search(text)):
        return "accessory"
    if _CONTROLLER_ONLY_RE.search(text) and not re.search(r"\b(console|handheld|bundle|oled|lite|ps5|switch|gamecube|n64)\b", text):
        return "controller"
    accessory = bool(_ACCESSORY_RE.search(text))
    unitish = bool(_UNIT_RE.search(text))
    included_extra = bool(re.search(r"\b(with|plus|w\/|and)\b.{0,24}\b(case|cover|charger|dock|game)\b", text))
    if accessory and not unitish and not included_extra:
        return "accessory"
    if re.search(r"\b(case|cover|charger|cable|screen protector) only\b", text):
        return "accessory"
    if family in {"retro-nintendo"} and re.search(r"\b(game|cartridge|disc)s?\b", text) and not re.search(r"\bconsole\b", text):
        return "game"
    if family in {"camera-drone"}:
        if re.search(r"\blens\b", text) and not re.search(r"\b(body|kit)\b", text):
            return "lens"
        if re.search(r"\bkit\b", text):
            return "kit"
        if re.search(r"\bbody\b", text):
            return "body"
    if "controller" in model.lower():
        return "controller"
    if family in {"ps5", "switch-oled", "switch-lite", "switch-2", "switch-base", "xbox-series", "steam-deck"}:
        return "console"
    return "unit"


def _role_from_title(title: str) -> dict[str, Any]:
    text = _norm(title)
    if _BOX_RE.search(text):
        return {"identity_confidence": IDENTITY_BOX_ONLY, "item_kind": "empty_box", "reasons": ["box only"]}
    if _PARTS_RE.search(text) and not re.search(r"\b(console|handheld|complete|working phone|unlocked)\b", text):
        return {"identity_confidence": IDENTITY_PARTS_ONLY, "item_kind": "parts", "reasons": ["parts only / replacement component"]}
    if _FOR_PRODUCT_HEAD_RE.search(text):
        return {"identity_confidence": IDENTITY_ACCESSORY_ONLY, "item_kind": "accessory", "for_product": True, "reasons": ["for-product accessory/part, not the named main product"]}
    # Bare fan / GPU fan / cooler fan without multi-fan cooler marketing → PARTS_ONLY before model EXACT.
    if (
        re.search(r"\bfan\b", text)
        and not _MULTI_FAN_COOLER_RE.search(text)
        and not re.search(r"\b(console|handheld|complete|working phone|unlocked)\b", text)
    ):
        return {"identity_confidence": IDENTITY_PARTS_ONLY, "item_kind": "parts", "reasons": ["parts only / replacement component"]}
    if _ACCESSORY_RE.search(text) and _FOR_NAMED_PRODUCT_RE.search(text) and not _UNIT_RE.search(text):
        return {"identity_confidence": IDENTITY_ACCESSORY_ONLY, "item_kind": "accessory", "for_product": True, "reasons": ["accessory for a named product"]}
    if _ACCESSORY_RE.search(text) and not _UNIT_RE.search(text) and not re.search(r"\b(with|plus|w\/|and)\b.{0,24}\b(case|cover|charger|dock|game)\b", text):
        if re.search(r"\b(case|cover|protector|charger|dock|controller|shell|housing|water\s*block|cooler|bracket|motherboard|logic\s*board|fan)\b", text):
            # Do not treat multi-fan cooler marketing on a complete GPU as an accessory/part.
            if re.search(r"\bfan\b", text) and _MULTI_FAN_COOLER_RE.search(text):
                pass
            else:
                return {"identity_confidence": IDENTITY_ACCESSORY_ONLY, "item_kind": "accessory", "reasons": ["accessory/part language without a complete unit"]}
    if AUDIO_NOT_PHONE_RE.search(text) and not re.search(r"\b(iphone\s*\d|galaxy\s*s\d|pixel\s*\d|switch|ps5|playstation|xbox|macbook|steam\s*deck|rtx)\b", text):
        return {"identity_confidence": IDENTITY_FALSE_MATCH, "item_kind": "accessory", "reasons": ["audio/accessory language is not a phone or named console"]}
    if _BUNDLE_RE.search(text) and not re.search(r"\b(console|iphone|macbook|ps5|switch oled|steam deck)\b", text):
        return {"identity_confidence": IDENTITY_BUNDLE_UNRESOLVED, "item_kind": "bundle", "reasons": ["bundle/lot without resolved unit identity"]}
    return {}


def _unproven_premium_variant(model: str, title_n: str) -> bool:
    tokens = _PREMIUM_VARIANT_TOKENS.get(str(model or ""), ())
    if not tokens:
        return False
    return not any(token in title_n for token in tokens)


def identify_product(title: str, query: str = "") -> dict[str, Any]:
    role = _role_from_title(title)
    result = _identify_product_core(title, query)
    if role:
        result["identity_confidence"] = role["identity_confidence"]
        result["item_kind"] = role.get("item_kind") or result.get("item_kind") or "accessory"
        result["for_product"] = bool(role.get("for_product"))
        result["reasons"] = list(role.get("reasons") or []) + list(result.get("reasons") or [])
        if role["identity_confidence"] in {IDENTITY_ACCESSORY_ONLY, IDENTITY_PARTS_ONLY, IDENTITY_BOX_ONLY, IDENTITY_FALSE_MATCH}:
            result["candidate_model"] = ""
            result["candidate_product_family"] = ""
    result.update(_variant_aspects(title))
    if "item_kind" not in result:
        result["item_kind"] = _item_kind(title, str(result.get("candidate_model") or ""), str(result.get("candidate_product_family") or ""))
    model = str(result.get("candidate_model") or "").strip()
    family = str(result.get("candidate_product_family") or "").strip()
    storage = str(result.get("storage") or "").strip()
    result["canonical_product_id"] = "|".join(part for part in (model or family, storage) if part)
    result["identity_confidence"] = normalize_identity_confidence(str(result.get("identity_confidence") or ""))
    result["system_resolved_identity"] = model or family
    return result


def _identify_product_core(title: str, query: str = "") -> dict[str, Any]:
    title_n = _norm(title)
    query_n = _norm(query)
    if not title_n.strip():
        return {
            "candidate_product_family": "",
            "candidate_model": "",
            "identity_confidence": IDENTITY_UNKNOWN,
            "reasons": ["empty title"],
        }

    matches: list[dict[str, Any]] = []
    for rule in _MODEL_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, title_n):
                matches.append(rule)
                break

    unique_models = []
    seen = set()
    for item in matches:
        key = (item["family"], item["model"])
        if key in seen:
            continue
        seen.add(key)
        unique_models.append(item)

    if len(unique_models) > 1:
        families = {item["family"] for item in unique_models}
        kinds = {item["family"].split("-")[0] for item in unique_models}
        if len(families) > 1 and len(kinds) > 1:
            return {
                "candidate_product_family": "",
                "candidate_model": "",
                "identity_confidence": IDENTITY_CONTRADICTORY,
                "reasons": [f"conflicting models: {', '.join(item['model'] for item in unique_models[:4])}"],
            }
        # Prefer the first (most specific) match rather than collapsing.
        chosen = unique_models[0]
        return {
            "candidate_product_family": chosen["family"],
            "candidate_model": chosen["model"],
            "identity_confidence": IDENTITY_AMBIGUOUS if len(families) > 1 else IDENTITY_STRONG,
            "reasons": ["multiple model matches; kept most specific"],
        }

    if unique_models:
        chosen = unique_models[0]
        confidence = IDENTITY_EXACT_CONFIRMED
        if chosen["family"] in {"ps5", "xbox-series"} and "slim" not in title_n and "digital" not in title_n and "pro" not in title_n:
            confidence = IDENTITY_EXACT_STRONG
        if chosen["model"] == "Nintendo Switch OLED" and "oled" in title_n:
            confidence = IDENTITY_EXACT_CONFIRMED
        # Base Nintendo Switch without OLED/Lite/2 must stay FAMILY_ONLY (never EXACT).
        if chosen["model"] == "Nintendo Switch" or chosen["family"] == "switch-base":
            if not re.search(r"\b(oled|lite|switch\s*2)\b", title_n):
                return {
                    "candidate_product_family": "switch-family",
                    "candidate_model": "Nintendo Switch",
                    "identity_confidence": IDENTITY_FAMILY_ONLY,
                    "reasons": ["Switch family without OLED/Lite/2 variant"],
                }
        if _unproven_premium_variant(chosen["model"], title_n):
            return {
                "candidate_product_family": chosen["family"],
                "candidate_model": "",
                "identity_confidence": IDENTITY_FAMILY_ONLY,
                "variant_unproven": True,
                "reasons": [f"{chosen['model']} not proven; using lower defensible family"],
            }
        if chosen["model"] == "iPhone 15" and "pro" in title_n:
            return {
                "candidate_product_family": "iphone-15-pro",
                "candidate_model": "",
                "identity_confidence": IDENTITY_AMBIGUOUS,
                "reasons": ["iPhone 15 family present but Pro/Max variant unclear"],
            }
        return {
            "candidate_product_family": chosen["family"],
            "candidate_model": chosen["model"],
            "identity_confidence": confidence,
            "reasons": [f"matched {chosen['model']}"],
        }

    if re.search(r"\bnintendo\s*switch\b", title_n) and not re.search(r"\b(oled|lite|switch\s*2)\b", title_n):
        return {
            "candidate_product_family": "switch-family",
            "candidate_model": "Nintendo Switch",
            "identity_confidence": IDENTITY_FAMILY_ONLY,
            "reasons": ["Switch family without OLED/Lite/2 variant"],
        }
    if re.search(r"\bswitch\b", title_n) and not re.search(r"\bnintendo\b|\boled\b|\blite\b", title_n):
        return {
            "candidate_product_family": "",
            "candidate_model": "",
            "identity_confidence": IDENTITY_AMBIGUOUS,
            "reasons": ["bare 'switch' is too ambiguous"],
        }
    if re.search(r"\bnes\b", title_n) and "classic" not in title_n:
        return {
            "candidate_product_family": "retro-nintendo",
            "candidate_model": "NES",
            "identity_confidence": IDENTITY_STRONG,
            "reasons": ["NES without Classic Edition"],
        }
    if re.search(r"\bmacbook\b", title_n):
        if re.search(r"\b(m1|m2|m3|m4)\b", title_n):
            chip = re.search(r"\b(m[1-4])\b", title_n).group(1).upper()
            family = "macbook-air-m1" if chip == "M1" else "macbook-pro-silicon" if "pro" in title_n else "macbook-air-m2-m3"
            return {
                "candidate_product_family": family,
                "candidate_model": "",
                "identity_confidence": IDENTITY_FAMILY_ONLY,
                "reasons": [f"Apple silicon {chip} without exact model lock"],
            }
        if re.search(r"\b(intel|i5|i7|i9|core)\b", title_n):
            return {
                "candidate_product_family": "macbook-intel",
                "candidate_model": "MacBook Intel",
                "identity_confidence": IDENTITY_EXACT_STRONG,
                "reasons": ["Intel MacBook is not Apple silicon"],
            }
        return {
            "candidate_product_family": "macbook-intel" if "air" not in title_n and "pro" not in title_n else "macbook-air-m2-m3",
            "candidate_model": "",
            "identity_confidence": IDENTITY_FAMILY_ONLY,
            "reasons": ["MacBook family only"],
        }

    for family, pattern in _FAMILY_ONLY_RULES:
        if re.search(pattern, title_n):
            return {
                "candidate_product_family": family,
                "candidate_model": "",
                "identity_confidence": IDENTITY_FAMILY_ONLY,
                "reasons": ["family language only"],
            }

    if query_n.strip() and re.search(r"\b(iphone|macbook|switch|ps5|rtx|pixel|galaxy)\b", query_n):
        return {
            "candidate_product_family": "",
            "candidate_model": "",
            "identity_confidence": IDENTITY_UNKNOWN,
            "reasons": ["query family present but title did not confirm a model"],
        }

    return {
        "candidate_product_family": "",
        "candidate_model": "",
        "identity_confidence": IDENTITY_UNKNOWN,
        "reasons": ["no confident product identity"],
    }
