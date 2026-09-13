from __future__ import annotations

from typing import Any, Callable

from dealbrain.comps import SOLD_COMP_SOURCE_EBAY, extract_model_query
from dealbrain.valuation.consensus import PHONE_FAMILIES, conservative_from_evidence
from dealbrain.valuation.evidence import (
    ACTIVE_EXACT_MATCH,
    ACTIVE_MARKET_DISTRIBUTION,
    GRADE_C,
    GRADE_D,
    GRADE_UNKNOWN,
    ValuationEvidence,
    evidence_from_sold_rows,
    now_iso,
)
from dealbrain.valuation.provider import ProviderRegistry
from dealbrain.valuation.providers import default_providers
from dealbrain.valuation.scale import category_from_family
from dealbrain.valuation.voi import value_of_information

_REGISTRY: ProviderRegistry | None = None
_IDENTITY_BATCH: dict[str, list[ValuationEvidence]] = {}


def get_registry(providers=None) -> ProviderRegistry:
    global _REGISTRY
    if providers is not None:
        _REGISTRY = ProviderRegistry(providers)
        return _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ProviderRegistry(default_providers())
    return _REGISTRY


def reset_registry() -> None:
    global _REGISTRY, _IDENTITY_BATCH
    _REGISTRY = None
    _IDENTITY_BATCH = {}


def _lookup_evidence(query: str, comps_lookup: Callable[..., Any], identity: dict[str, Any]) -> list[ValuationEvidence]:
    raw = comps_lookup(query)
    if isinstance(raw, dict):
        comps = list(raw.get("comps") or [])
        source = str(raw.get("source") or "")
    elif isinstance(raw, list):
        comps = raw
        source = ""
    else:
        return []
    sold_like = [row for row in comps if str(row.get("source") or "") in {"", SOLD_COMP_SOURCE_EBAY}]
    if source in {"", SOLD_COMP_SOURCE_EBAY} and sold_like:
        evidence = evidence_from_sold_rows(sold_like, query=query, identity=identity)
        return [evidence] if evidence else []
    active = [row for row in comps if "active" in str(row.get("source") or "").lower()]
    if active:
        from dealbrain.market_clean import filter_comparables
        from dealbrain.valuation.stats import distribution
        from marketplace.identity import identify_product
        filtered = filter_comparables(active, identity=identity, identify=identify_product)
        stats = distribution(filtered["prices"], filtered["shipping"])
        if stats["count"] <= 0:
            return []
        return [ValuationEvidence(
            provider="ebay_active",
            evidence_type=ACTIVE_EXACT_MATCH if stats["count"] >= 8 else ACTIVE_MARKET_DISTRIBUTION,
            canonical_product_id=str(identity.get("canonical_product_id") or query),
            exact_model=str(identity.get("candidate_model") or query),
            value=stats["p25"] or stats["median"],
            p10=stats["p10"],
            p25=stats["p25"],
            p50=stats["p50"],
            p75=stats["p75"],
            sample_count=stats["count"],
            retrieved_at=now_iso(),
            is_active_ask=True,
            is_realized_sale=False,
            eligible_for_conservative_value=False,
            grade=GRADE_C if stats["count"] >= 5 else GRADE_D,
            notes="injected active asking prices; never sold comps",
            raw_metadata=stats,
        )]
    return []


def value_listing(
    listing: dict[str, Any],
    identity: dict[str, Any],
    *,
    comps_lookup: Callable[..., Any] | None = None,
    market_median: float = 0.0,
    config=None,
    registry: ProviderRegistry | None = None,
    extra_evidence: list[ValuationEvidence] | None = None,
) -> dict[str, Any]:
    query = extract_model_query(
        str(listing.get("title") or ""),
        {**listing, **(identity or {}), "candidate_model": identity.get("candidate_model")},
    )
    ident = dict(identity or {})
    ident.setdefault("query", query)
    ident.setdefault("title", listing.get("title") or "")
    ident.setdefault("identity_confidence", identity.get("identity_confidence") or "")
    ident.setdefault("canonical_product_id", identity.get("canonical_product_id") or "")
    family = str(ident.get("candidate_product_family") or "")
    category = category_from_family(family) or str(ident.get("category") or "")
    ident["category"] = category
    from marketplace.identity import identity_is_exact
    if not query and not identity_is_exact(str(ident.get("identity_confidence") or "")):
        consensus = conservative_from_evidence([], category)
        return {
            **consensus,
            "category": category,
            "model_query": "",
            "reason_codes": ["comps_require_resolved_identity", "active asking prices were not treated as sold comps"],
            "why_this_value": [],
            "provider_badges": [],
            "clean_sample_count": 0,
        }
    batch_key = str(ident.get("canonical_product_id") or ident.get("candidate_model") or query)
    collected: list[ValuationEvidence] = list(extra_evidence or [])
    if comps_lookup is not None:
        collected.extend(_lookup_evidence(query, comps_lookup, ident))
    if batch_key and batch_key in _IDENTITY_BATCH and comps_lookup is None:
        collected.extend(_IDENTITY_BATCH[batch_key])
    else:
        skip_live = comps_lookup is not None
        context = {
            "category": category,
            "listing": listing,
            "limit": 20,
        }
        live_rows = (registry or get_registry()).quote_all(ident, condition=str(listing.get("condition") or ""), context=context, skip_live=skip_live)
        collected.extend(live_rows)
        if batch_key and comps_lookup is None:
            _IDENTITY_BATCH[batch_key] = list(live_rows)
    if market_median and not any(row.is_active_ask for row in collected):
        collected.append(ValuationEvidence(
            provider="ebay_active",
            evidence_type=ACTIVE_MARKET_DISTRIBUTION,
            canonical_product_id=batch_key,
            exact_model=str(ident.get("candidate_model") or query),
            value=float(market_median),
            p50=float(market_median),
            p25=round(float(market_median) * 0.9, 2),
            sample_count=1,
            retrieved_at=now_iso(),
            is_active_ask=True,
            eligible_for_conservative_value=False,
            grade=GRADE_C,
            notes="active market median baseline; not sold comps",
        ))
    consensus = conservative_from_evidence(collected, category)
    voi = value_of_information(listing, ident, consensus)
    has_sold = any(row.is_realized_sale and row.evidence_type != ACTIVE_MARKET_DISTRIBUTION for row in collected)
    sold_rows = [row for row in collected if row.is_realized_sale]
    return {
        **consensus,
        **voi,
        "has_sold_comps": has_sold,
        "sold_count": sum(int(row.sold_count or row.sample_count or 0) for row in sold_rows),
        "sold_median": consensus.get("conservative_resale") if has_sold else 0.0,
        "model_query": query,
        "category": category,
        "phone": family in PHONE_FAMILIES,
        "valuation_grade": consensus.get("valuation_grade") or GRADE_UNKNOWN,
        "provider_badges": sorted({row.provider for row in collected if row.provider}),
        "why_this_value": [
            {
                "provider": row.provider,
                "evidence_type": row.evidence_type,
                "grade": row.grade,
                "value": row.value,
                "p25": row.p25,
                "p50": row.p50,
                "sample_count": row.sample_count,
                "is_realized_sale": row.is_realized_sale,
                "is_active_ask": row.is_active_ask,
                "notes": row.notes,
            }
            for row in collected
        ],
        "evidence": [row.to_dict() for row in collected],
        "usable_comps": [
            {
                "title": row.exact_model,
                "price": row.value,
                "url": row.url,
                "source": "ebay_sold" if row.is_realized_sale and row.provider.startswith("ebay") else row.provider,
                "match_quality": "exact" if row.identity_confidence in {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"} else "strong",
            }
            for row in collected if row.is_realized_sale
        ],
    }
