from __future__ import annotations

from typing import Any

from dealbrain.config import DealBrainConfig, get_config

CLASS_MONSTER = "MONSTER"
CLASS_HOT = "HOT"
CLASS_STRONG = "STRONG"
CLASS_WATCH = "WATCH"
CLASS_RISK = "RISK"
CLASS_PASS = "PASS"

CLASS_RANK = {
    CLASS_PASS: 0,
    CLASS_WATCH: 1,
    CLASS_RISK: 2,
    CLASS_STRONG: 3,
    CLASS_HOT: 4,
    CLASS_MONSTER: 5,
}

ALERT_CLASSES = {CLASS_MONSTER, CLASS_HOT}

STRONG_BASIS = {
    "REALIZED_SALES",
    "SPECIALIST_PRICE_GUIDE",
    "BUYBACK_FLOOR",
    "MULTI_SOURCE_CONSENSUS",
}


def verified_exit_ok(
    *,
    has_sold_comps: bool = False,
    valuation_grade: str = "",
    verified_exit_basis: str = "",
    independent_b_sources: int = 0,
    identity_confidence: str = "",
) -> bool:
    grade = str(valuation_grade or "").upper()
    basis = str(verified_exit_basis or "").upper()
    ident = str(identity_confidence or "").upper()
    if has_sold_comps or grade == "A":
        return True
    if grade == "B" and basis == "BUYBACK_FLOOR":
        return True
    if grade == "B" and basis in STRONG_BASIS and ident in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"} and independent_b_sources >= 2:
        return True
    return False


def classify_deal(
    *,
    expected_profit: float,
    roi_pct: float,
    confidence: str,
    identity_confidence: str = "",
    age_hours: float | None = None,
    placeholder: bool = False,
    repair: bool = False,
    has_sold_comps: bool = False,
    device_risk: bool = False,
    extreme_anomaly: bool = False,
    valuation_grade: str = "",
    verified_exit_basis: str = "",
    discount_pct: float = 0.0,
    floor_profit: float = 0.0,
    independent_b_sources: int = 0,
    phone: bool = False,
    high_risk: bool = False,
    authenticity_risk: bool = False,
    active_derived: bool = False,
    clean_sample_count: int = 0,
    market_stability: str = "",
    listing_available: bool = True,
    direct_link: bool = True,
    accessory_mismatch: bool = False,
    config: DealBrainConfig | None = None,
) -> str:
    cfg = config or get_config()
    conf = str(confidence or "NONE").upper()
    ident = str(identity_confidence or "").upper()
    profit = float(expected_profit or 0)
    roi = float(roi_pct or 0)
    grade = str(valuation_grade or "").upper()
    discount = float(discount_pct or 0)
    if placeholder and conf in {"NONE", "LOW"}:
        return CLASS_RISK
    if repair and profit > 0 and conf in {"NONE", "LOW"}:
        return CLASS_RISK
    if ident == "CONTRADICTORY":
        return CLASS_RISK
    if accessory_mismatch:
        return CLASS_PASS
    if not listing_available:
        return CLASS_PASS
    if device_risk:
        return CLASS_RISK

    strong_exit = verified_exit_ok(
        has_sold_comps=has_sold_comps,
        valuation_grade=grade,
        verified_exit_basis=verified_exit_basis,
        independent_b_sources=independent_b_sources,
        identity_confidence=ident,
    )
    risk_mult = 1.0 if (getattr(cfg, "first_profit_mode", True) and active_derived) else (1.25 if (phone or high_risk) else 1.0)
    monster_profit = cfg.monster_profit * risk_mult
    hot_profit = cfg.hot_profit * risk_mult
    discount_monster_ok = discount <= 0 or discount >= cfg.monster_discount_pct
    discount_hot_ok = discount <= 0 or discount >= cfg.hot_discount_pct
    ident_ok = ident in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"}
    blocking = ident in {
        "ACCESSORY_ONLY", "PARTS_ONLY", "BOX_ONLY", "BUNDLE_UNRESOLVED",
        "FALSE_MATCH", "CONTRADICTORY",
    }
    if blocking:
        return CLASS_PASS
    sample_ok_hot = conf in {"HIGH", "MEDIUM"} or (active_derived and int(clean_sample_count or 0) >= int(getattr(cfg, "first_profit_hot_clean_comps", 8) or 8))
    sample_ok_monster = conf == "HIGH" or (active_derived and int(clean_sample_count or 0) >= int(getattr(cfg, "first_profit_monster_clean_comps", 10) or 10))
    would_monster = (
        profit >= monster_profit
        and roi >= cfg.monster_roi_pct
        and ident_ok
        and sample_ok_monster
        and discount_monster_ok
    )
    would_hot = (
        profit >= hot_profit
        and roi >= cfg.hot_roi_pct
        and ident_ok
        and sample_ok_hot
        and discount_hot_ok
        and (active_derived or age_hours is None or float(age_hours) <= cfg.hot_max_age_hours)
    )
    floor_ok = float(floor_profit or 0) >= hot_profit and str(verified_exit_basis or "").upper() == "BUYBACK_FLOOR"

    from dealbrain.first_profit import first_profit_class_ok

    active_monster = (
        bool(getattr(cfg, "first_profit_mode", True))
        and active_derived
        and would_monster
        and first_profit_class_ok(
            klass=CLASS_MONSTER,
            identity_confidence=ident,
            clean_sample_count=clean_sample_count,
            market_stability=market_stability,
            expected_profit=profit,
            roi_pct=roi,
            discount_pct=discount,
            risk="MEDIUM" if (phone or high_risk or authenticity_risk) else "LOW",
            listing_available=listing_available,
            direct_link=direct_link,
            accessory_mismatch=accessory_mismatch,
            identity_contradiction=ident == "CONTRADICTORY",
            config=cfg,
        )
    )
    active_hot = (
        bool(getattr(cfg, "first_profit_mode", True))
        and active_derived
        and would_hot
        and first_profit_class_ok(
            klass=CLASS_HOT,
            identity_confidence=ident,
            clean_sample_count=clean_sample_count,
            market_stability=market_stability,
            expected_profit=profit,
            roi_pct=roi,
            discount_pct=discount,
            risk="MEDIUM" if (phone or high_risk or authenticity_risk) else "LOW",
            listing_available=listing_available,
            direct_link=direct_link,
            accessory_mismatch=accessory_mismatch,
            identity_contradiction=ident == "CONTRADICTORY",
            config=cfg,
        )
    )
    if repair and (would_monster or would_hot or active_monster or active_hot):
        return CLASS_RISK
    if would_monster and strong_exit:
        if authenticity_risk:
            return CLASS_RISK
        return CLASS_MONSTER
    if active_monster:
        if authenticity_risk:
            return CLASS_RISK
        return CLASS_MONSTER
    if would_hot and strong_exit:
        if authenticity_risk:
            return CLASS_STRONG
        return CLASS_HOT
    if active_hot:
        if authenticity_risk:
            return CLASS_RISK
        return CLASS_HOT
    if floor_ok and ident_ok and strong_exit:
        return CLASS_HOT if profit >= hot_profit else CLASS_STRONG
    if would_monster or would_hot:
        if grade in {"C", "D", "UNKNOWN", ""}:
            return CLASS_STRONG if ident_ok and profit >= cfg.strong_profit else CLASS_RISK
        return CLASS_STRONG
    if not strong_exit:
        if extreme_anomaly and ident in {"CONFIRMED", "STRONG", "FAMILY_ONLY"}:
            return CLASS_WATCH
        if profit >= cfg.strong_profit and roi >= cfg.strong_roi_pct and ident_ok and conf != "NONE":
            return CLASS_WATCH if grade in {"", "UNKNOWN", "D"} else CLASS_STRONG
        if profit >= cfg.watch_profit or roi >= cfg.watch_roi_pct:
            return CLASS_WATCH
        return CLASS_PASS
    if profit >= cfg.strong_profit and roi >= cfg.strong_roi_pct:
        if not ident_ok:
            return CLASS_WATCH
        if conf in {"NONE"}:
            return CLASS_RISK
        if conf == "LOW":
            return CLASS_WATCH
        return CLASS_STRONG
    if profit >= cfg.watch_profit or roi >= cfg.watch_roi_pct:
        return CLASS_WATCH
    return CLASS_PASS


def class_emoji(classification: str) -> str:
    return {
        CLASS_MONSTER: "💥",
        CLASS_HOT: "🔥",
        CLASS_STRONG: "💪",
        CLASS_WATCH: "👀",
        CLASS_RISK: "⚠️",
        CLASS_PASS: "⛔",
    }.get(str(classification or "").upper(), "👀")
