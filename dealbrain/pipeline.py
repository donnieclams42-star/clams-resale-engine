from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
import logging
import re

from dealbrain.anomaly import cheap_anomaly_screen
from dealbrain.classify import class_emoji, classify_deal
from dealbrain.comps import SOLD_COMP_SOURCE_EBAY, SOLD_COMP_SOURCE_UNAVAILABLE
from dealbrain.config import DealBrainConfig, get_config
from dealbrain.economics import score_economics
from dealbrain.first_profit import (
    EVIDENCE_LABEL,
    PHONE_CHECKLIST,
    VALUATION_BADGE,
    VALUATION_BASIS,
    VALUATION_BASIS_LABEL,
    active_haircut_for,
    authenticity_warning,
    class_purchase_thresholds,
    conservative_active_exit,
    first_profit_priority,
    phone_warning,
    sample_confidence,
    why_this_deal,
)
from dealbrain.risk import assess_liquidity, assess_risk
from dealbrain.signals import listing_signals
from dealbrain.valuation.consensus import PHONE_FAMILIES
from dealbrain.valuation.evidence import REASON_DOWNGRADED
from dealbrain.valuation.router import value_listing
from marketplace.identity import identify_product
from marketplace.image_identity import resolve_identity

logger = logging.getLogger("market_radar.dealbrain")

HOLD_DAYS = {"HIGH": 3.0, "FAST": 3.0, "MEDIUM": 14.0, "NORMAL": 14.0, "LOW": 90.0, "SLOW": 90.0}

EXIT_BY_CATEGORY = {
    "PHONES": "Swappa / eBay",
    "TABLETS": "eBay",
    "MACBOOKS": "eBay",
    "GPUS": "eBay",
    "CURRENT GAMING": "eBay / PriceCharting category",
    "RETRO GAMING": "PriceCharting-based resale / eBay",
    "CAMERAS": "specialist dealer / eBay",
    "MUSICAL": "Reverb",
    "COLLECTIBLES": "eBay / specialist",
    "TOOLS": "local Marketplace / eBay",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _valuation_explanation(valued: dict[str, Any], reasons: list[str]) -> str:
    basis = str(valued.get("verified_exit_basis") or "")
    parts: list[str] = []
    if basis in {"CONSERVATIVE_ACTIVE_EXIT", "ACTIVE_MARKET_ONLY"}:
        parts.append("VALUATION BASIS: Conservative Active Market")
        parts.append("EVIDENCE: Active exact-match inventory")
        parts.append("ACTIVE-MARKET DERIVED — not sold verified")
    else:
        parts.append(f"VALUATION EVIDENCE: {valued.get('valuation_grade') or 'UNKNOWN'}")
        parts.append("eBay completed-items not required; asking prices were not sold")
    pc = next((row for row in (valued.get("why_this_value") or []) if row.get("provider") == "pricecharting"), None)
    active = next((row for row in (valued.get("why_this_value") or []) if row.get("provider") == "ebay_active" or row.get("is_active_ask")), None)
    if active:
        parts.append(
            f"eBay active: p25 ${float(active.get('p25') or active.get('value') or 0):.0f} median ${float(active.get('p50') or active.get('value') or 0):.0f} (not sold)"
        )
        if valued.get("active_haircut"):
            parts.append(f"Safety haircut: {round(float(valued.get('active_haircut') or 0) * 100)}%")
        parts.append(f"Conservative active exit: ${float(valued.get('conservative_active_exit') or valued.get('conservative_resale') or 0):.0f}")
    elif pc:
        parts.append(f"PriceCharting (on hold / optional): ${float(pc.get('value') or 0):.0f}")
        parts.append(f"Conservative value: ${float(valued.get('conservative_resale') or 0):.0f}")
    else:
        parts.append(f"Conservative value: ${float(valued.get('conservative_resale') or 0):.0f}")
    extra = [r for r in reasons if r][:2]
    if extra:
        parts.append("Reason: " + "; ".join(extra))
    return " · ".join(parts)


def _age_hours(listing: dict[str, Any]) -> float | None:
    for key in ("listing_created_at", "first_seen_at", "observed_at"):
        raw = str(listing.get(key) or "").strip()
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            hours = (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0
            return round(max(0.0, hours), 3)
        except Exception:
            continue
    return None


def analyze_listing(
    listing: dict[str, Any],
    *,
    comps_lookup: Callable[..., Any] | None = None,
    market_median: float = 0.0,
    config: DealBrainConfig | None = None,
) -> dict[str, Any]:
    cfg = config or get_config()
    title = str(listing.get("title") or "")
    identity = resolve_identity(
        listing,
        query=str(listing.get("discovery_query") or ""),
        potential_value=_f(listing.get("asking_price")),
        value_floor=_f(getattr(cfg, "high_value_floor", 200) or 200),
    )
    try:
        from dealbrain.identity_gate import listing_category_conflict
        from marketplace.identity import IDENTITY_ACCESSORY_ONLY, IDENTITY_BOX_ONLY, IDENTITY_FALSE_MATCH, IDENTITY_PARTS_ONLY
        if listing_category_conflict(listing, identity):
            identity["category_conflict"] = True
            identity.setdefault("reasons", []).append("category/identity conflict")
            current = str(identity.get("identity_confidence") or "").upper()
            if current not in {IDENTITY_FALSE_MATCH, IDENTITY_ACCESSORY_ONLY, IDENTITY_PARTS_ONLY, IDENTITY_BOX_ONLY, "FALSE_MATCH", "ACCESSORY_ONLY", "PARTS_ONLY", "BOX_ONLY"}:
                identity["identity_confidence"] = "AMBIGUOUS"
    except Exception:
        pass
    family = identity.get("candidate_product_family") or listing.get("candidate_product_family") or ""
    model = identity.get("candidate_model") or listing.get("candidate_model") or ""
    ident = identity.get("identity_confidence") or listing.get("identity_confidence") or ""
    valued = value_listing(
        listing,
        identity,
        comps_lookup=comps_lookup,
        market_median=market_median,
        config=cfg,
    )
    from dealbrain.valuation.pricecharting.authenticity import authenticity_status
    auth = authenticity_status(title)
    if re.search(r"\b(lot|bundle|nintendo stuff|old games|box of games)\b", title, re.I):
        from dealbrain.valuation.pricecharting.bundles import value_bundle
        bundle = value_bundle(title, str(listing.get("description") or ""))
        if float(bundle.get("conservative_resale") or 0) > 0:
            valued["conservative_resale"] = bundle["conservative_resale"]
            valued["market_expectation"] = max(float(valued.get("market_expectation") or 0), bundle["conservative_resale"])
            valued["bundle"] = bundle
            valued.setdefault("reason_codes", []).append("BUNDLE_COMPONENT_VALUATION")
    asking = _f(listing.get("asking_price"))
    signals = listing_signals(listing)
    repair = bool(signals.get("repair_opportunity"))
    category = str(valued.get("category") or "")
    active_rows = [row for row in (valued.get("why_this_value") or []) if row.get("is_active_ask") or row.get("provider") == "ebay_active"]
    clean_n = int(valued.get("clean_sample_count") or 0)
    if not clean_n and active_rows:
        clean_n = max(int(row.get("sample_count") or 0) for row in active_rows)
    raw_n = 0
    excluded_n = 0
    if active_rows:
        meta = (valued.get("evidence") or [{}])[0]
        if isinstance(meta, dict):
            raw_meta = meta.get("raw_metadata") or {}
            raw_n = int(raw_meta.get("raw_comparable_count") or 0)
            excluded_n = int(raw_meta.get("excluded_comparable_count") or 0)
    p25 = _f(valued.get("active_p25"))
    if p25 <= 0 and active_rows:
        p25 = _f(active_rows[0].get("p25") or active_rows[0].get("value"))
    haircut = active_haircut_for(family=str(family), category=category, repair=repair, config=cfg)
    basis = str(valued.get("verified_exit_basis") or "")
    if basis in {VALUATION_BASIS, "ACTIVE_MARKET_ONLY", ""} and p25 > 0:
        exit_val = conservative_active_exit(p25, haircut)
        valued["conservative_resale"] = exit_val
        valued["conservative_active_exit"] = exit_val
        valued["active_p25"] = p25
        valued["active_haircut"] = haircut
        valued["verified_exit_basis"] = VALUATION_BASIS
        basis = VALUATION_BASIS
    elif p25 > 0 and not valued.get("conservative_active_exit"):
        valued["conservative_active_exit"] = conservative_active_exit(p25, haircut)
        valued["active_p25"] = p25
        valued["active_haircut"] = haircut
    from dataclasses import replace
    econ_cfg = cfg
    if getattr(cfg, "first_profit_mode", True) and not _f(getattr(cfg, "return_reserve_rate", 0)):
        econ_cfg = replace(cfg, return_reserve_rate=_f(getattr(cfg, "first_profit_return_reserve_rate", 0.02)))
    active_median = _f(valued.get("market_expectation") or market_median or p25)
    screen = cheap_anomaly_screen(listing, market_median=active_median, config=cfg)
    inbound = listing.get("inbound_shipping")
    if inbound in (None, ""):
        inbound = listing.get("shipping_cost")
    local_pickup = bool(signals.get("local_pickup") or listing.get("local_pickup"))
    shipping_unknown = (not local_pickup) and inbound in (None, "") and str(listing.get("source") or "") == "ebay"
    liquidity_hint = "HIGH" if clean_n >= 12 or int(valued.get("sold_count") or 0) >= 8 else "MEDIUM" if clean_n >= 5 else "UNKNOWN"
    hold = HOLD_DAYS.get(liquidity_hint or "UNKNOWN")
    repair_reserve = 40.0 if repair else 0.0
    economics = score_economics(
        asking=asking,
        conservative_resale=_f(valued.get("conservative_resale")),
        market_expectation=_f(valued.get("market_expectation")),
        fast_cash=_f(valued.get("fast_cash")),
        exit_floor=_f(valued.get("exit_floor")),
        local_pickup=local_pickup,
        inbound_shipping=None if inbound in (None, "") else _f(inbound),
        best_offer=bool(signals.get("best_offer") or listing.get("best_offer")),
        expected_hold_days=hold,
        shipping_unknown=shipping_unknown,
        unknown_inbound_reserve=_f(getattr(cfg, "first_profit_unknown_inbound_reserve", 12)),
        repair_reserve=repair_reserve,
        config=econ_cfg,
    )
    placeholder = bool(listing.get("price_is_placeholder") or asking in {0.0, 1.0})
    age = _age_hours(listing)
    device_risk = bool(signals.get("device_risk") or signals.get("auction_only") or signals.get("deposit"))
    has_sold = bool(valued.get("has_sold_comps"))
    grade = str(valued.get("valuation_grade") or "")
    b_sources = len({row.get("provider") for row in (valued.get("why_this_value") or []) if str(row.get("grade") or "") == "B"})
    market_conf = sample_confidence(clean_n, cfg)
    from dealbrain.first_profit import market_stability as _stab
    stability = str(valued.get("market_stability") or "")
    if not stability and active_rows:
        stability = _stab(_f(active_rows[0].get("p25")), _f(active_rows[0].get("p50")), _f(active_rows[0].get("p75")))
    confidence = market_conf if clean_n else (
        "HIGH" if grade == "A" and int(valued.get("sold_count") or 0) >= 8 else "MEDIUM" if grade in {"A", "B"} else "LOW" if grade == "C" else "NONE"
    )
    from dealbrain.market_clean import reject_reason
    mismatch = reject_reason(title, target_kind=str(identity.get("item_kind") or "unit"), target_model=str(model), target_storage=str(identity.get("storage") or ""), target_family=str(family))
    accessory_mismatch = str(identity.get("item_kind") or "") in {
        "accessory", "controller", "empty_box", "game", "lens",
    } or mismatch in {
        "parts_only", "empty_box", "manual_only", "case_only", "charger_only",
        "screen_protector", "replacement_component", "controller_when_console",
        "game_when_console", "wanted_ad", "repair_service", "deposit", "replica",
        "accessory",
    }
    listing_url = str(listing.get("canonical_url") or listing.get("listing_url") or "")
    available = str(listing.get("availability_status") or "live").lower() not in {"sold", "ended", "removed", "unavailable"}
    active_derived = (not has_sold) and basis == VALUATION_BASIS and p25 > 0
    classification = classify_deal(
        expected_profit=economics["expected_profit"],
        roi_pct=economics["roi_pct"],
        confidence=confidence,
        identity_confidence=str(ident),
        age_hours=age,
        placeholder=placeholder,
        repair=repair,
        has_sold_comps=has_sold,
        device_risk=device_risk,
        extreme_anomaly=bool(screen.get("extreme_anomaly")),
        valuation_grade=grade,
        verified_exit_basis=basis,
        discount_pct=_f(economics.get("discount_pct")),
        floor_profit=_f(economics.get("floor_profit")),
        independent_b_sources=b_sources,
        phone=family in PHONE_FAMILIES,
        authenticity_risk=bool(auth.get("material")) or bool(authenticity_warning(title, str(family))),
        high_risk=bool(auth.get("material")) or repair,
        active_derived=active_derived,
        clean_sample_count=clean_n,
        market_stability=stability,
        listing_available=available,
        direct_link=bool(listing_url) and "ebay.com/sch" not in listing_url,
        accessory_mismatch=accessory_mismatch,
        config=cfg,
    )
    raw_class = classification
    risk = assess_risk(
        identity_confidence=str(ident),
        comp_confidence=confidence,
        sold_count=max(int(valued.get("sold_count") or 0), clean_n),
        placeholder=placeholder,
        repair=repair,
        has_sold_comps=has_sold or grade in {"A", "B"} or (active_derived and clean_n >= 8),
        spread_ratio=0.0,
        device_risk=device_risk,
        phone=family in PHONE_FAMILIES,
    )
    if authenticity_warning(title, str(family)) and risk == "LOW":
        risk = "MEDIUM"
    liquidity = assess_liquidity(
        sold_count=int(valued.get("sold_count") or 0),
        has_sold_comps=has_sold or bool(valued.get("conservative_resale")),
        age_hours=age,
        listing_volume=max(clean_n, sum(int(row.get("sample_count") or 0) for row in (valued.get("why_this_value") or []))),
    )
    reasons: list[str] = list(screen.get("anomaly_reasons") or [])
    reasons.extend(valued.get("reason_codes") or [])
    explanation = _valuation_explanation(valued, reasons)
    reasons.insert(0, explanation)
    if has_sold:
        reasons.append("usable realized-sale evidence")
    else:
        reasons.append("eBay completed-items not required; active asking prices were not treated as sold comps")
        reasons.append("VALUATION BASIS: Conservative Active Market")
        reasons.append("EVIDENCE: Active exact-match inventory")
    if grade in {"C", "D", "UNKNOWN"} and raw_class in {"STRONG", "WATCH", "RISK"} and not active_derived:
        reasons.append(REASON_DOWNGRADED)
        reasons.append(f"valuation evidence {grade or 'UNKNOWN'} cannot auto-verify HOT/MONSTER")
    if ident not in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"} and raw_class in {"HOT", "MONSTER"}:
        classification = "STRONG"
        raw_class = classification
        reasons.append("identity not strong enough for HOT/MONSTER")
    if raw_class in {"HOT", "MONSTER"} and str(listing.get("source") or "").startswith("facebook") and not identity.get("image_analyzed"):
        try:
            from marketplace.image_identity import image_evidence_text, identify_product, should_analyze_image, fuse_identity
            gate = should_analyze_image(
                listing,
                identity,
                potential_value=economics["expected_profit"] + _f(asking),
                value_floor=_f(getattr(cfg, "high_value_floor", 200) or 200),
                would_hot=True,
            )
            image_text = image_evidence_text(listing)
            if gate.get("should_analyze_image") and image_text:
                identity = fuse_identity(identity, identify_product(image_text, str(listing.get("discovery_query") or "")))
                identity["image_analysis"] = gate
                identity["image_analyzed"] = True
                ident = identity.get("identity_confidence") or ident
                family = identity.get("candidate_product_family") or family
                model = identity.get("candidate_model") or model
                reasons.append("gated image identity check on HOT/MONSTER candidate")
                if ident not in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"}:
                    classification = "WATCH"
                    raw_class = classification
                    reasons.append("image identity did not confirm HOT/MONSTER")
        except Exception:
            pass
    try:
        from dealbrain.identity_gate import apply_actionable_class_gate
        gate = apply_actionable_class_gate(
            classification,
            {**identity, "identity_confidence": ident, "accessory_mismatch": accessory_mismatch},
            expected_profit=economics["expected_profit"],
        )
        if gate.get("classification") and gate["classification"] != classification:
            reasons.append(f"strict identity gate: {gate.get('gate_reason')}")
            classification = gate["classification"]
            raw_class = classification
        payload_feed_lane = gate.get("feed_lane") or ""
        verify_identity_alert = bool(gate.get("verify_identity_alert"))
    except Exception:
        payload_feed_lane = ""
        verify_identity_alert = False
    if signals.get("phrases"):
        reasons.append("signals: " + ", ".join(signals["phrases"][:6]))
    if family:
        reasons.append(f"identity {ident or 'UNKNOWN'}: {model or family}")
    phone_verification = family in PHONE_FAMILIES
    warn_phone = phone_warning(str(family))
    if warn_phone:
        reasons.append(warn_phone)
    warn_auth = authenticity_warning(title, str(family))
    if warn_auth:
        reasons.append(warn_auth)
    if repair:
        reasons.append("REPAIR RISK")
    if auth.get("material"):
        reasons.append(str(auth.get("status") or "AUTHENTICITY_UNKNOWN"))
    if valued.get("bundle"):
        reasons.append("bundle conservative value uses confirmed components minus reserves")
    if screen.get("extreme_anomaly"):
        reasons.append("EXTREME_PRICE_ANOMALY — too cheap is not an automatic rejection; verify identity/condition/scam")
    best_exit = EXIT_BY_CATEGORY.get(category, "eBay")
    if best_exit.startswith("eBay / PriceCharting"):
        best_exit = "eBay"
    source = str(listing.get("source") or "")
    arbitrage = ""
    if source.startswith("facebook"):
        arbitrage = "Facebook → eBay"
    elif source == "ebay":
        arbitrage = "eBay → eBay (active-market anomaly)"
    payload = {
        **economics,
        "classification": classification,
        "class_emoji": class_emoji(classification),
        "confidence": confidence,
        "deal_confidence": confidence,
        "comp_confidence": confidence,
        "market_sample_confidence": market_conf,
        "market_stability": stability or "LOW",
        "risk": risk,
        "liquidity": liquidity,
        "sold_count": int(valued.get("sold_count") or 0),
        "sold_median": _f(valued.get("sold_median")),
        "sold_average": _f(valued.get("market_expectation")),
        "sold_low": _f(valued.get("fast_cash")),
        "sold_high": _f(valued.get("market_expectation")),
        "sold_q1": _f(valued.get("conservative_resale")),
        "sold_q3": _f(valued.get("market_expectation")),
        "comp_source": SOLD_COMP_SOURCE_EBAY if has_sold else SOLD_COMP_SOURCE_UNAVAILABLE,
        "sold_comp_state": SOLD_COMP_SOURCE_EBAY if has_sold else SOLD_COMP_SOURCE_UNAVAILABLE,
        "has_sold_comps": has_sold,
        "safe_to_buy": False,
        "verification_required": phone_verification or device_risk or repair,
        "phone_checklist": list(PHONE_CHECKLIST) if phone_verification else [],
        "reasons": reasons,
        "signals": signals.get("phrases") or [],
        "signals_json": signals,
        "placeholder_price": 1 if placeholder else 0,
        "age_hours": age,
        "model_query": valued.get("model_query") or "",
        "usable_comps": valued.get("usable_comps") or [],
        "candidate_product_family": family,
        "candidate_model": model,
        "canonical_product_id": identity.get("canonical_product_id") or "",
        "storage": identity.get("storage") or "",
        "identity_confidence": ident,
        "identity_state": ident,
        "feed_lane": payload_feed_lane,
        "verify_identity_alert": verify_identity_alert,
        "system_resolved_identity": identity.get("system_resolved_identity") or model,
        "anomaly_status": screen.get("anomaly_status"),
        "needs_deep": screen.get("needs_deep"),
        "extreme_anomaly": bool(screen.get("extreme_anomaly")),
        "active_market_baseline": active_median,
        "listing_url": listing_url,
        "source": listing.get("source") or "",
        "valuation_grade": grade or "UNKNOWN",
        "verified_exit_basis": basis or "NONE",
        "valuation_basis": VALUATION_BASIS if active_derived else basis,
        "valuation_basis_label": VALUATION_BASIS_LABEL if active_derived else (basis or "NONE"),
        "valuation_evidence_label": EVIDENCE_LABEL if active_derived else "",
        "valuation_badge": VALUATION_BADGE if active_derived else "",
        "conservative_active_exit": _f(valued.get("conservative_active_exit") or (valued.get("conservative_resale") if active_derived else 0)),
        "active_p25": p25,
        "active_haircut": haircut,
        "clean_comparable_count": clean_n,
        "raw_comparable_count": raw_n,
        "excluded_comparable_count": excluded_n,
        "clean_sample_count": clean_n,
        "valuation_reason_codes": valued.get("reason_codes") or [],
        "provider_badges": valued.get("provider_badges") or [],
        "why_this_value": valued.get("why_this_value") or [],
        "valuation_explanation": explanation,
        "evidence": valued.get("evidence") or [],
        "best_expected_exit": best_exit,
        "source_to_exit": arbitrage,
        "value_of_information_priority": valued.get("value_of_information_priority") or "LOW",
        "voi_score": valued.get("voi_score"),
        "scale_level": getattr(cfg, "scale_level", 0),
        "authenticity": auth.get("status") or "",
        "provider_spread": valued.get("provider_spread"),
        "bundle": valued.get("bundle") or {},
        "open_label": "OPEN FACEBOOK LISTING" if source.startswith("facebook") else "OPEN EBAY LISTING" if source == "ebay" else "OPEN LISTING",
        "class_thresholds": class_purchase_thresholds(
            _f(valued.get("conservative_active_exit") or valued.get("conservative_resale")),
            local_pickup=local_pickup,
            inbound_shipping=None if inbound in (None, "") else _f(inbound),
            extra_costs=repair_reserve,
            config=econ_cfg,
        ),
    }
    payload["first_profit_priority"] = first_profit_priority(payload)
    payload["why_this_deal"] = why_this_deal(payload)
    try:
        payload.update(_market_repair_overlay(listing, payload, identity, cfg, economics, valued, signals, repair, family, model, ident, p25))
    except Exception:
        payload.setdefault("opportunity_types", ["STANDARD_ARBITRAGE"] if payload.get("expected_profit") else [])
        payload.setdefault("deal_lane", "ACTIONABLE")
    return payload


def _market_repair_overlay(
    listing: dict[str, Any],
    payload: dict[str, Any],
    identity: dict[str, Any],
    cfg: DealBrainConfig,
    economics: dict[str, Any],
    valued: dict[str, Any],
    signals: dict[str, Any],
    repair: bool,
    family: str,
    model: str,
    ident: str,
    p25: float,
) -> dict[str, Any]:
    from dealbrain.market_map import LOCAL_MARKET_IDS, listing_market_context, observation_from_listing
    from dealbrain.opportunity import likely_exit_market, opportunity_types
    from dealbrain.repair_hunter import (
        classify_damage,
        repair_economics,
        worth_repair_analysis,
        lookup_repair_cost,
    )

    local_ids = LOCAL_MARKET_IDS
    market_ctx = listing_market_context(
        {**listing, **payload, "candidate_product_family": family, "candidate_model": model},
        national_p25=p25,
        sell_exit=_f(payload.get("conservative_active_exit") or payload.get("conservative_resale")),
        config=cfg,
    )
    damage = classify_damage({**listing, "candidate_product_family": family, "candidate_model": model})
    repair_info: dict[str, Any] = dict(damage)
    potential = max(_f(payload.get("conservative_active_exit")), _f(p25), _f(listing.get("asking_price")))
    floor = _f(getattr(cfg, "high_value_floor", 200) or 200)
    repair_floor = _f(getattr(cfg, "repair_high_value_floor", 250) or 250)
    if repair or damage.get("repair_type") not in {"", "UNKNOWN"} and str(damage.get("repair_type") or "") != "UNKNOWN":
        if worth_repair_analysis(family=family, potential_value=potential, asking=_f(listing.get("asking_price")), floor=floor, repair_floor=repair_floor):
            def _store_cost(**kwargs):
                try:
                    from marketplace.store import lookup_repair_cost_row
                    return lookup_repair_cost_row(**kwargs)
                except Exception:
                    return {}
            cost_row = lookup_repair_cost(family=family, model=model, repair_type=str(damage.get("repair_type") or ""), store_lookup=_store_cost)
            repair_info.update(
                repair_economics(
                    {**listing, "candidate_product_family": family, "candidate_model": model, "identity_confidence": ident},
                    working_conservative_exit=_f(payload.get("conservative_active_exit") or payload.get("conservative_resale")),
                    damage=damage,
                    cost_row=cost_row,
                    inbound_shipping=listing.get("inbound_shipping") if listing.get("inbound_shipping") not in (None, "") else None,
                    local_pickup=bool(signals.get("local_pickup") or listing.get("local_pickup")),
                    target_profit=_f(getattr(cfg, "repair_target_profit", 175) or 175),
                    config=cfg,
                )
            )
        else:
            repair_info["skipped"] = "below_repair_value_floor"
    bundle = bool(valued.get("bundle") or "lot" in str(listing.get("title") or "").lower())
    extreme = bool(payload.get("extreme_anomaly"))
    market_spread = _f((market_ctx.get("cross_market") or {}).get("cross_market_expected_profit"))
    market_tag = bool(market_ctx.get("metro_id")) and str(market_ctx.get("metro_id") or "") not in local_ids and market_spread > 0
    standard = (not repair_info.get("repair_alert_ok")) and _f(payload.get("expected_profit")) >= _f(getattr(cfg, "first_profit_min_profit", 50) or 50)
    tags = opportunity_types(
        standard=standard or bool(payload.get("classification") in {"HOT", "MONSTER", "STRONG"}),
        market=market_tag,
        repair=bool(repair_info.get("repair_alert_ok") or (repair and repair_info.get("preferred_repair"))),
        bundle=bundle,
        extreme=extreme,
    )
    exit_info = likely_exit_market(source=str(listing.get("source") or ""), actionable=bool(market_ctx.get("actionable")))
    obs = observation_from_listing({**listing, **payload}, identity)
    if obs:
        try:
            from marketplace.store import save_price_observation
            save_price_observation(obs)
        except Exception:
            pass
    overlay = {
        "opportunity_types": tags,
        "opportunity_types_json": tags,
        "deal_lane": payload.get("feed_lane") or market_ctx.get("deal_lane") or "ACTIONABLE",
        "actionable": bool(market_ctx.get("actionable")),
        "metro_id": market_ctx.get("metro_id") or listing.get("market_id") or "",
        "market_state": market_ctx.get("state") or "",
        "acquisition_type": market_ctx.get("acquisition_type") or "",
        "distance_miles": market_ctx.get("distance_miles"),
        "estimated_travel_cost": market_ctx.get("estimated_travel_cost"),
        "travel_known": market_ctx.get("travel_known"),
        "cross_market": market_ctx.get("cross_market") or {},
        "cross_market_expected_profit": market_spread,
        "repair_type": repair_info.get("repair_type") or "",
        "damage_isolated": repair_info.get("damage_isolated"),
        "max_repair_buy": repair_info.get("max_repair_buy"),
        "repair_expected_profit": repair_info.get("repair_expected_profit"),
        "repair_roi": repair_info.get("repair_roi"),
        "estimated_repair": repair_info.get("estimated_repair"),
        "repair_risk_reserve": repair_info.get("repair_risk_reserve"),
        "repair_warnings": repair_info.get("repair_warnings") or [],
        "repair_alert_ok": bool(repair_info.get("repair_alert_ok")),
        "working_conservative_exit": repair_info.get("working_conservative_exit"),
        "WORKING_CONSERVATIVE_EXIT": repair_info.get("WORKING_CONSERVATIVE_EXIT") or repair_info.get("working_conservative_exit"),
        "REPAIR_PARTS_RESERVE": repair_info.get("REPAIR_PARTS_RESERVE") or repair_info.get("parts_estimate"),
        "REPAIR_LABOR_RESERVE": repair_info.get("REPAIR_LABOR_RESERVE") or repair_info.get("labor_estimate"),
        "REPAIR_RISK_RESERVE": repair_info.get("REPAIR_RISK_RESERVE") or repair_info.get("repair_risk_reserve"),
        "TOTAL_REPAIR_COST": repair_info.get("TOTAL_REPAIR_COST") or repair_info.get("total_repair_cost"),
        "REPAIRED_NET_EXIT": repair_info.get("REPAIRED_NET_EXIT") or repair_info.get("repaired_net_exit"),
        "REPAIR_EXPECTED_PROFIT": repair_info.get("REPAIR_EXPECTED_PROFIT") or repair_info.get("repair_expected_profit"),
        "REPAIR_ROI": repair_info.get("REPAIR_ROI") or repair_info.get("repair_roi"),
        "MAX_REPAIR_BUY": repair_info.get("MAX_REPAIR_BUY") or repair_info.get("max_repair_buy"),
        "cost_known": repair_info.get("cost_known"),
        "cost_status": repair_info.get("cost_status") or "",
        "phone_checklist": repair_info.get("phone_checklist") or payload.get("phone_checklist") or [],
        "image_analysis": identity.get("image_analysis") or {},
        "image_analyzed": bool(identity.get("image_analyzed")),
        "identity_contradiction": bool(identity.get("identity_contradiction")),
        "likely_exit": exit_info,
        "source_to_exit": exit_info.get("source_to_exit") or payload.get("source_to_exit"),
    }
    overlay["deal_lane"] = payload.get("feed_lane") or overlay.get("deal_lane")
    if overlay.get("repair_alert_ok"):
        overlay["deal_lane"] = "REPAIR"
    if str(market_ctx.get("deal_lane") or "") == "MARKET_RESEARCH" and overlay.get("deal_lane") not in {"FALSE_MATCH", "REJECTED", "NEEDS_VERIFICATION"}:
        overlay["deal_lane"] = "MARKET_RESEARCH"
    if overlay["repair_warnings"]:
        payload_reasons = list(payload.get("reasons") or [])
        payload_reasons.extend(overlay["repair_warnings"][:4])
        overlay["reasons"] = payload_reasons
    return overlay


def analyze_and_store(
    listing: dict[str, Any],
    *,
    comps_lookup: Callable[..., Any] | None = None,
    market_median: float = 0.0,
    send_alerts: bool = True,
    previous_class: str = "",
    previous_price: Any = None,
    config: DealBrainConfig | None = None,
) -> dict[str, Any]:
    from dealbrain.alerts import maybe_alert
    from dealbrain.store import save_comps, save_evidence, save_verdict

    listing_id = str(listing.get("id") or "")
    previous_profit = None
    previous_risk = ""
    if listing_id:
        try:
            from dealbrain.store import latest_verdict
            prior = latest_verdict(listing_id) or {}
            if not previous_class:
                previous_class = str(prior.get("classification") or "")
            if previous_price in (None, "") and prior.get("asking_price") not in (None, ""):
                previous_price = prior.get("asking_price")
            previous_profit = prior.get("expected_profit")
            previous_risk = str(prior.get("risk") or "")
        except Exception:
            prior = {}
    verdict = analyze_listing(listing, comps_lookup=comps_lookup, market_median=market_median, config=config)
    if listing_id:
        save_verdict(listing_id, listing, verdict)
        save_comps(listing_id, verdict.get("usable_comps") or [])
        save_evidence(listing_id, verdict.get("evidence") or [])
        if send_alerts:
            try:
                maybe_alert(
                    listing,
                    verdict,
                    previous_class=previous_class,
                    previous_price=previous_price,
                    previous_profit=previous_profit,
                    previous_risk=previous_risk,
                )
            except Exception:
                logger.info("DEALBRAIN_ALERT_ISOLATED listing_id=%s", listing_id)
        try:
            from dealbrain.budget import maybe_apply_opportunity_boost
            maybe_apply_opportunity_boost(listing, verdict)
        except Exception:
            logger.info("BUDGET_LADDER_SKIPPED listing_id=%s", listing_id)
    return verdict


def recheck_actionable_inventory(*, send_alerts: bool = False, limit: int = 400) -> dict[str, Any]:
    """Re-run current inventory through strict identity. Does not delete history or spend provider quota."""
    from dealbrain.identity_gate import apply_actionable_class_gate
    from dealbrain.store import list_deal_feed, save_verdict
    from marketplace.identity import (
        IDENTITY_ACCESSORY_ONLY,
        IDENTITY_BOX_ONLY,
        IDENTITY_FALSE_MATCH,
        IDENTITY_PARTS_ONLY,
        identify_product,
        identity_is_exact,
    )
    from marketplace.store import listing_by_id

    before = list_deal_feed({"mode": "all"}, limit=limit)
    old_actionable = [row for row in before if str(row.get("classification") or "").upper() in {"HOT", "MONSTER", "STRONG"}]
    counts = {
        "old_actionable": len(old_actionable),
        "old_hot": sum(1 for row in old_actionable if str(row.get("classification") or "").upper() == "HOT"),
        "old_monster": sum(1 for row in old_actionable if str(row.get("classification") or "").upper() == "MONSTER"),
        "checked": 0,
        "new_actionable": 0,
        "new_hot": 0,
        "new_monster": 0,
        "exact_confirmed": 0,
        "exact_strong": 0,
        "needs_verification": 0,
        "accessory_rejects": 0,
        "parts_rejects": 0,
        "box_rejects": 0,
        "variant_conflicts": 0,
        "false_matches": 0,
    }
    for row in before:
        listing_id = str(row.get("id") or "")
        identity = identify_product(str(row.get("title") or ""), str(row.get("discovery_query") or ""))
        gate = apply_actionable_class_gate(
            str(row.get("classification") or ""),
            identity,
            expected_profit=float(row.get("expected_profit") or 0),
        )
        klass = str(gate.get("classification") or row.get("classification") or "").upper()
        ident = str(identity.get("identity_confidence") or "")
        counts["checked"] += 1
        if ident in {"EXACT_CONFIRMED", "CONFIRMED"}:
            counts["exact_confirmed"] += 1
        if ident in {"EXACT_STRONG", "STRONG"}:
            counts["exact_strong"] += 1
        if ident in {IDENTITY_ACCESSORY_ONLY, "ACCESSORY_ONLY"} or identity.get("item_kind") == "accessory":
            counts["accessory_rejects"] += 1
        if ident in {IDENTITY_PARTS_ONLY, "PARTS_ONLY"}:
            counts["parts_rejects"] += 1
        if ident in {IDENTITY_BOX_ONLY, "BOX_ONLY"}:
            counts["box_rejects"] += 1
        if ident == "CONTRADICTORY" or identity.get("variant_unproven"):
            counts["variant_conflicts"] += 1
        if ident in {IDENTITY_FALSE_MATCH, "FALSE_MATCH"}:
            counts["false_matches"] += 1
        if str(gate.get("feed_lane") or "") == "NEEDS_VERIFICATION":
            counts["needs_verification"] += 1
        if klass in {"HOT", "MONSTER", "STRONG"} and identity_is_exact(ident):
            counts["new_actionable"] += 1
        if klass == "HOT" and identity_is_exact(ident):
            counts["new_hot"] += 1
        if klass == "MONSTER" and identity_is_exact(ident):
            counts["new_monster"] += 1
        if listing_id:
            updated = dict(row)
            updated.update({
                "classification": klass,
                "identity_confidence": ident,
                "identity_state": ident,
                "candidate_model": identity.get("candidate_model") or row.get("candidate_model"),
                "candidate_product_family": identity.get("candidate_product_family") or row.get("candidate_product_family"),
                "feed_lane": gate.get("feed_lane") or row.get("feed_lane") or row.get("deal_lane"),
                "deal_lane": gate.get("feed_lane") or row.get("deal_lane"),
                "previous_classification": row.get("classification"),
            })
            try:
                listing = listing_by_id(listing_id) or row
                save_verdict(listing_id, listing, updated)
            except Exception:
                pass
    return counts
