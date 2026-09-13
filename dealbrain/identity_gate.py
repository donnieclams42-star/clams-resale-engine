"""Shared strict identity gate for Facebook and eBay actionable classification."""
from __future__ import annotations

from typing import Any

from marketplace.identity import (
    ACTIONABLE_IDENTITY,
    IDENTITY_ACCESSORY_ONLY,
    IDENTITY_AMBIGUOUS,
    IDENTITY_BOX_ONLY,
    IDENTITY_BUNDLE_UNRESOLVED,
    IDENTITY_CONTRADICTORY,
    IDENTITY_EXACT_CONFIRMED,
    IDENTITY_EXACT_STRONG,
    IDENTITY_FALSE_MATCH,
    IDENTITY_FAMILY_ONLY,
    IDENTITY_PARTS_ONLY,
    IDENTITY_UNKNOWN,
    category_identity_conflict,
    identity_is_exact,
    normalize_identity_confidence,
    resolved_identity_query,
)

FEED_ACTIONABLE = "ACTIONABLE"
FEED_NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
FEED_REPAIR = "REPAIR"
FEED_MARKET_RESEARCH = "MARKET_RESEARCH"
FEED_FALSE_MATCH = "FALSE_MATCH"
FEED_REJECTED = "REJECTED"

VERIFY_IDENTITY_ALERT = "VERIFY_IDENTITY"

BLOCKING_IDENTITY = {
    IDENTITY_ACCESSORY_ONLY,
    IDENTITY_PARTS_ONLY,
    IDENTITY_BOX_ONLY,
    IDENTITY_BUNDLE_UNRESOLVED,
    IDENTITY_FALSE_MATCH,
    IDENTITY_CONTRADICTORY,
}


def identity_blocks_actionable(identity: dict[str, Any] | None = None, **kwargs: Any) -> tuple[bool, str]:
    identity = dict(identity or {})
    identity.update({k: v for k, v in kwargs.items() if v is not None})
    ident = normalize_identity_confidence(identity.get("identity_confidence") or identity.get("ident") or "")
    kind = str(identity.get("item_kind") or "").lower()
    if ident in BLOCKING_IDENTITY:
        return True, ident.lower()
    if kind in {"accessory", "controller", "empty_box", "parts", "box"}:
        return True, f"{kind}_kind"
    if identity.get("accessory_mismatch"):
        return True, "accessory_mismatch"
    if identity.get("identity_contradiction") or identity.get("variant_conflict"):
        return True, "identity_conflict"
    if identity.get("for_product"):
        return True, "for_product"
    if identity.get("category_conflict"):
        return True, "category_identity_conflict"
    return False, ""


def actionable_identity_ok(identity: dict[str, Any] | None = None, **kwargs: Any) -> tuple[bool, str]:
    blocked, reason = identity_blocks_actionable(identity, **kwargs)
    if blocked:
        return False, reason
    ident = normalize_identity_confidence((identity or {}).get("identity_confidence") or kwargs.get("identity_confidence") or "")
    if not identity_is_exact(ident):
        return False, "identity_not_exact"
    if ident not in ACTIONABLE_IDENTITY and ident not in {IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG, "CONFIRMED", "STRONG"}:
        return False, "identity_not_exact"
    return True, "ok"


def needs_verification(identity: dict[str, Any] | None = None, **kwargs: Any) -> bool:
    identity = dict(identity or {})
    ident = normalize_identity_confidence(identity.get("identity_confidence") or kwargs.get("identity_confidence") or "")
    if ident in {IDENTITY_FAMILY_ONLY, IDENTITY_AMBIGUOUS, IDENTITY_UNKNOWN, "PROBABLE", "FAMILY_ONLY"}:
        return True
    if identity.get("variant_unproven") or identity.get("category_conflict"):
        return True
    ok, _reason = actionable_identity_ok(identity, **kwargs)
    return not ok and ident not in BLOCKING_IDENTITY


def feed_lane_for(
    *,
    classification: str = "",
    identity: dict[str, Any] | None = None,
    repair: bool = False,
    repair_alert_ok: bool = False,
    geo_lane: str = "",
    false_match: bool = False,
) -> str:
    ident = normalize_identity_confidence((identity or {}).get("identity_confidence") or "")
    if false_match or ident == IDENTITY_FALSE_MATCH:
        return FEED_FALSE_MATCH
    blocked, _reason = identity_blocks_actionable(identity)
    if blocked:
        return FEED_REJECTED
    if repair_alert_ok or (repair and ident in ACTIONABLE_IDENTITY | {"CONFIRMED", "STRONG", IDENTITY_EXACT_CONFIRMED, IDENTITY_EXACT_STRONG}):
        return FEED_REPAIR
    if str(geo_lane or "").upper() == "MARKET_RESEARCH":
        return FEED_MARKET_RESEARCH
    klass = str(classification or "").upper()
    ok, _reason = actionable_identity_ok(identity)
    if klass in {"HOT", "MONSTER", "STRONG"} and ok:
        return FEED_ACTIONABLE
    if needs_verification(identity) or klass in {"WATCH", "RISK"}:
        return FEED_NEEDS_VERIFICATION
    if not ok:
        return FEED_NEEDS_VERIFICATION
    return FEED_ACTIONABLE if klass in {"HOT", "MONSTER", "STRONG"} else FEED_NEEDS_VERIFICATION


def apply_actionable_class_gate(
    classification: str,
    identity: dict[str, Any] | None = None,
    *,
    expected_profit: float = 0.0,
    huge_profit: float = 100.0,
) -> dict[str, Any]:
    klass = str(classification or "").upper()
    ok, reason = actionable_identity_ok(identity)
    blocked, block_reason = identity_blocks_actionable(identity)
    ident = normalize_identity_confidence((identity or {}).get("identity_confidence") or "")
    result = {
        "classification": klass,
        "identity_ok": ok,
        "gate_reason": reason if not ok else "ok",
        "verify_identity_alert": False,
        "feed_lane": FEED_ACTIONABLE,
    }
    if blocked:
        result["classification"] = "PASS" if ident in {IDENTITY_ACCESSORY_ONLY, IDENTITY_PARTS_ONLY, IDENTITY_BOX_ONLY, IDENTITY_FALSE_MATCH} else "WATCH"
        result["feed_lane"] = FEED_FALSE_MATCH if ident == IDENTITY_FALSE_MATCH else FEED_REJECTED
        result["gate_reason"] = block_reason
        return result
    if klass in {"HOT", "MONSTER", "STRONG"} and not ok:
        if float(expected_profit or 0) >= float(huge_profit or 100):
            result["classification"] = "WATCH"
            result["verify_identity_alert"] = True
            result["feed_lane"] = FEED_NEEDS_VERIFICATION
            result["gate_reason"] = reason
            return result
        result["classification"] = "WATCH" if ident in {IDENTITY_FAMILY_ONLY, IDENTITY_AMBIGUOUS, "PROBABLE"} else "PASS"
        result["feed_lane"] = FEED_NEEDS_VERIFICATION
        result["gate_reason"] = reason
        return result
    result["feed_lane"] = feed_lane_for(classification=result["classification"], identity=identity)
    return result


def discord_alert_kind(
    *,
    classification: str,
    identity: dict[str, Any] | None = None,
    expected_profit: float = 0.0,
) -> tuple[str, str]:
    """Return (alert_type, skip_reason). Empty skip_reason means allowed."""
    klass = str(classification or "").upper()
    gate = apply_actionable_class_gate(klass, identity, expected_profit=expected_profit)
    if gate.get("verify_identity_alert"):
        return VERIFY_IDENTITY_ALERT, ""
    ok, reason = actionable_identity_ok(identity)
    if klass in {"HOT", "MONSTER", "STRONG"} and not ok:
        return "", reason or "identity_not_exact"
    return "", ""


def comps_query(identity: dict[str, Any] | None, title: str = "") -> str:
    return resolved_identity_query(identity or {}, title=title)


def listing_category_conflict(listing: dict[str, Any] | None, identity: dict[str, Any] | None) -> bool:
    listing = listing or {}
    return category_identity_conflict(
        str(listing.get("category") or listing.get("fb_category") or ""),
        identity or {},
    )
