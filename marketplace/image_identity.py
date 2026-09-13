from __future__ import annotations

from typing import Any

from marketplace.identity import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_CONFIRMED,
    IDENTITY_CONTRADICTORY,
    IDENTITY_FAMILY_ONLY,
    IDENTITY_PROBABLE,
    IDENTITY_STRONG,
    IDENTITY_UNKNOWN,
    identify_product,
)

VARIANT_PAIRS = (
    ("Nintendo Switch OLED", "Nintendo Switch Lite"),
    ("Nintendo Switch OLED", "Nintendo Switch"),
    ("Nintendo Switch 2", "Nintendo Switch OLED"),
    ("iPhone 15 Pro Max", "iPhone 15 Pro"),
    ("iPhone 14 Pro Max", "iPhone 14 Pro"),
    ("iPhone 13 Pro Max", "iPhone 13 Pro"),
    ("PlayStation 5 Pro", "PlayStation 5"),
    ("PlayStation 5 Slim", "PlayStation 5"),
    ("Xbox Series X", "Xbox Series S"),
    ("Steam Deck OLED", "Steam Deck LCD"),
    ("ROG Ally X", "ROG Ally"),
    ("RTX 4090", "RTX 4080"),
    ("RTX 4080 SUPER", "RTX 4080"),
    ("RTX 4070 Ti SUPER", "RTX 4070"),
    ("Galaxy S24 Ultra", "Galaxy S24"),
    ("MacBook Air M2", "MacBook Air M1"),
    ("MacBook Air M3", "MacBook Air M2"),
)

LOWER_VARIANT = {
    "Nintendo Switch OLED": "Nintendo Switch",
    "Nintendo Switch 2": "Nintendo Switch OLED",
    "iPhone 15 Pro Max": "iPhone 15 Pro",
    "iPhone 14 Pro Max": "iPhone 14 Pro",
    "iPhone 13 Pro Max": "iPhone 13 Pro",
    "PlayStation 5 Pro": "PlayStation 5",
    "Xbox Series X": "Xbox Series S",
    "Steam Deck OLED": "Steam Deck LCD",
    "ROG Ally X": "ROG Ally",
    "RTX 4090": "RTX 4080",
    "Galaxy S24 Ultra": "Galaxy S24",
}


def image_evidence_text(listing: dict[str, Any] | None) -> str:
    listing = listing or {}
    parts = [
        listing.get("image_text"),
        listing.get("ocr_text"),
        listing.get("image_alt"),
        listing.get("image_caption"),
        listing.get("photo_text"),
        listing.get("image_hints"),
    ]
    hints = listing.get("image_identity") or {}
    if isinstance(hints, dict):
        parts.extend([hints.get("text"), hints.get("model"), hints.get("ocr")])
    return " ".join(str(part or "") for part in parts).strip()


def should_analyze_image(
    listing: dict[str, Any] | None,
    identity: dict[str, Any] | None = None,
    *,
    potential_value: float = 0.0,
    value_floor: float = 200.0,
    would_hot: bool = False,
) -> dict[str, Any]:
    listing = listing or {}
    identity = identity or {}
    title = str(listing.get("title") or "")
    ident = str(identity.get("identity_confidence") or "").upper()
    family = str(identity.get("candidate_product_family") or "")
    generic = ident in {IDENTITY_FAMILY_ONLY, IDENTITY_AMBIGUOUS, IDENTITY_UNKNOWN, ""}
    blob = f"{title} {listing.get('description') or ''}".lower()
    variant_matters = any(token in blob for token in ("switch", "iphone", "pro max", "oled", "ps5", "rtx", "ally", "steam deck"))
    repair_matters = any(token in blob for token in ("broken", "cracked", "repair", "parts", "untested"))
    bundle = any(token in blob for token in ("lot", "bundle", "gaming pc", "gaming computer", "electronics"))
    asking = 0.0
    try:
        asking = float(listing.get("asking_price") or 0)
    except Exception:
        asking = 0.0
    potential = float(potential_value or asking or 0)
    expensive = potential >= float(value_floor or 0)
    extreme_price = asking > 0 and asking <= max(25.0, float(value_floor or 200) * 0.15) and (generic or variant_matters or repair_matters)
    repair_high_value = repair_matters and expensive
    variant_conflict = bool(identity.get("variant_unproven") or identity.get("identity_contradiction") or ident in {IDENTITY_CONTRADICTORY, "CONTRADICTORY"})
    generic_high_value = generic and expensive
    has_image = bool(listing.get("thumbnail_url") or listing.get("image_url") or image_evidence_text(listing))
    gated = bool(has_image and (extreme_price or repair_high_value or variant_conflict or generic_high_value or would_hot))
    reasons = []
    if would_hot:
        reasons.append("hot_or_monster_candidate")
    if generic:
        reasons.append("generic_or_weak_title")
    if variant_matters:
        reasons.append("variant_matters")
    if repair_matters:
        reasons.append("repair_type_matters")
    if bundle:
        reasons.append("bundle_may_hide_value")
    if extreme_price:
        reasons.append("extreme_price_anomaly")
    if variant_conflict:
        reasons.append("material_variant_conflict")
    if generic_high_value:
        reasons.append("generic_high_value")
    if not expensive and not extreme_price:
        reasons.append("below_value_gate")
    if not has_image:
        reasons.append("no_image_evidence")
    return {
        "should_analyze_image": gated,
        "gated": True,
        "reasons": reasons,
        "family": family,
        "note": "Do not image-analyze every listing. Only HOT/MONSTER, extreme-price, high-value repair, variant conflict, or generic high-value cases.",
    }


def _lower_defensible(model: str) -> str:
    return LOWER_VARIANT.get(str(model or "").strip(), str(model or "").strip())


def fuse_identity(text_identity: dict[str, Any], image_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    text_identity = dict(text_identity or {})
    image_identity = dict(image_identity or {})
    text_model = str(text_identity.get("candidate_model") or "").strip()
    image_model = str(image_identity.get("candidate_model") or "").strip()
    text_conf = str(text_identity.get("identity_confidence") or IDENTITY_UNKNOWN).upper()
    image_conf = str(image_identity.get("identity_confidence") or IDENTITY_UNKNOWN).upper()
    fused = dict(text_identity)
    fused["text_identity"] = text_identity
    fused["image_identity"] = image_identity
    fused["image_gated"] = True
    if not image_model:
        fused["evidence_source"] = "text"
        return fused
    if text_model and image_model and text_model.lower() == image_model.lower():
        fused["identity_confidence"] = IDENTITY_CONFIRMED if IDENTITY_CONFIRMED in {text_conf, image_conf} else IDENTITY_STRONG
        fused["evidence_source"] = "text+image"
        fused.setdefault("reasons", []).append("text and image agree")
        return fused
    if text_model and image_model and text_model.lower() != image_model.lower():
        pair = {text_model, image_model}
        conflict = any(set(item) == pair for item in VARIANT_PAIRS)
        if conflict or (text_identity.get("candidate_product_family") and image_identity.get("candidate_product_family") and text_identity.get("candidate_product_family") != image_identity.get("candidate_product_family")):
            lower = _lower_defensible(text_model) if text_model in LOWER_VARIANT else _lower_defensible(image_model)
            if lower and lower.lower() in {text_model.lower(), image_model.lower(), _lower_defensible(text_model).lower(), _lower_defensible(image_model).lower()}:
                fused["candidate_model"] = lower if lower in {text_model, image_model} else _lower_defensible(text_model) or _lower_defensible(image_model)
                fused["identity_confidence"] = IDENTITY_CONTRADICTORY
                fused["reasons"] = list(fused.get("reasons") or []) + ["variant conflict; value lower defensible variant"]
                fused["evidence_source"] = "conflict_lower_variant"
                fused["identity_contradiction"] = True
                return fused
            fused["identity_confidence"] = IDENTITY_CONTRADICTORY
            fused["identity_contradiction"] = True
            fused["reasons"] = list(fused.get("reasons") or []) + ["text/image model conflict"]
            fused["evidence_source"] = "conflict"
            return fused
    if image_model and (not text_model or text_conf in {IDENTITY_FAMILY_ONLY, IDENTITY_AMBIGUOUS, IDENTITY_UNKNOWN}):
        fused.update({k: v for k, v in image_identity.items() if v})
        fused["identity_confidence"] = IDENTITY_STRONG if image_conf in {IDENTITY_CONFIRMED, IDENTITY_STRONG} else IDENTITY_PROBABLE
        fused["evidence_source"] = "image"
        fused.setdefault("reasons", []).append("image evidence resolved generic title")
        return fused
    fused["evidence_source"] = "text"
    return fused


def resolve_identity(listing: dict[str, Any] | None, *, query: str = "", potential_value: float = 0.0, value_floor: float = 200.0, would_hot: bool = False) -> dict[str, Any]:
    listing = listing or {}
    title = str(listing.get("title") or "")
    text_ident = identify_product(title, query or str(listing.get("discovery_query") or ""))
    gate = should_analyze_image(listing, text_ident, potential_value=potential_value, value_floor=value_floor, would_hot=would_hot)
    image_text = image_evidence_text(listing)
    image_ident = identify_product(image_text, query) if (gate.get("should_analyze_image") and image_text) else {}
    fused = fuse_identity(text_ident, image_ident)
    fused["image_analysis"] = gate
    fused["image_analyzed"] = bool(image_ident)
    return fused
