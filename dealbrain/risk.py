from __future__ import annotations

from typing import Any


def assess_risk(
    *,
    identity_confidence: str,
    comp_confidence: str,
    sold_count: int,
    placeholder: bool,
    repair: bool,
    has_sold_comps: bool,
    spread_ratio: float = 0.0,
    device_risk: bool = False,
    phone: bool = False,
) -> str:
    ident = str(identity_confidence or "").upper()
    conf = str(comp_confidence or "NONE").upper()
    if ident == "CONTRADICTORY" or placeholder or device_risk:
        return "HIGH"
    if repair or not has_sold_comps or conf in {"NONE", "LOW"} or ident in {"UNKNOWN", "AMBIGUOUS", "FAMILY_ONLY"}:
        return "HIGH" if repair or conf == "NONE" else "MEDIUM"
    if phone:
        return "MEDIUM"
    if sold_count < 4 or spread_ratio >= 0.8:
        return "MEDIUM"
    if ident in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"} and conf == "HIGH":
        return "LOW"
    return "MEDIUM"


def assess_liquidity(*, sold_count: int, has_sold_comps: bool, age_hours: float | None = None, listing_volume: int = 0) -> str:
    volume = max(int(sold_count or 0), int(listing_volume or 0))
    if not has_sold_comps and volume <= 0:
        return "UNKNOWN"
    if volume >= 8:
        return "HIGH"
    if volume >= 4:
        return "MEDIUM"
    if volume >= 1:
        return "LOW"
    return "UNKNOWN"
