from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from marketplace.normalize import utc_now
from marketplace.store import connect, listing_by_id as mp_listing_by_id, _json_list, _row


def save_verdict(listing_id: str, listing: dict[str, Any], verdict: dict[str, Any]) -> None:
    now = utc_now()
    payload = {
        "listing_id": listing_id,
        "source": listing.get("source") or verdict.get("source") or "",
        "classification": verdict.get("classification") or "",
        "expected_profit": verdict.get("expected_profit"),
        "roi_pct": verdict.get("roi_pct"),
        "landed_cost": verdict.get("landed_cost"),
        "net_resale": verdict.get("net_resale") or verdict.get("expected_net"),
        "expected_resale": verdict.get("expected_resale"),
        "fees": verdict.get("fees"),
        "shipping": verdict.get("shipping"),
        "max_buy_price": verdict.get("max_buy_price"),
        "inbound_shipping": verdict.get("inbound_shipping"),
        "discount_pct": verdict.get("discount_pct"),
        "sold_comp_state": verdict.get("sold_comp_state") or verdict.get("comp_source") or "",
        "verification_required": 1 if verdict.get("verification_required") else 0,
        "risk": verdict.get("risk") or "",
        "liquidity": verdict.get("liquidity") or "",
        "confidence": verdict.get("comp_confidence") or verdict.get("confidence") or "",
        "comp_source": verdict.get("comp_source") or "",
        "sold_count": int(verdict.get("sold_count") or 0),
        "valuation_grade": verdict.get("valuation_grade") or "",
        "verified_exit_basis": verdict.get("verified_exit_basis") or "",
        "fast_cash": verdict.get("fast_cash"),
        "exit_floor": verdict.get("exit_floor"),
        "market_expectation": verdict.get("market_expectation"),
        "provider_badges_json": json.dumps(verdict.get("provider_badges") or []),
        "why_json": json.dumps(verdict.get("why_this_value") or []),
        "best_expected_exit": verdict.get("best_expected_exit") or "",
        "source_to_exit": verdict.get("source_to_exit") or "",
        "profit_velocity": verdict.get("profit_velocity"),
        "reasons_json": json.dumps(verdict.get("reasons") or []),
        "signals_json": json.dumps(verdict.get("signals") or []),
        "identity_confidence": verdict.get("identity_confidence") or "",
        "candidate_model": verdict.get("candidate_model") or "",
        "candidate_product_family": verdict.get("candidate_product_family") or "",
        "analyzed_at": now,
        "conservative_active_exit": verdict.get("conservative_active_exit"),
        "margin_of_safety_dollars": verdict.get("margin_of_safety_dollars"),
        "margin_of_safety_percent": verdict.get("margin_of_safety_percent"),
        "break_even_resale": verdict.get("break_even_resale") or verdict.get("break_even_price"),
        "valuation_error_cushion_dollars": verdict.get("valuation_error_cushion_dollars"),
        "valuation_error_cushion_percent": verdict.get("valuation_error_cushion_percent"),
        "clean_comparable_count": int(verdict.get("clean_comparable_count") or verdict.get("clean_sample_count") or 0),
        "raw_comparable_count": int(verdict.get("raw_comparable_count") or 0),
        "excluded_comparable_count": int(verdict.get("excluded_comparable_count") or 0),
        "market_stability": verdict.get("market_stability") or "",
        "market_sample_confidence": verdict.get("market_sample_confidence") or verdict.get("confidence") or "",
        "valuation_basis": verdict.get("valuation_basis") or verdict.get("verified_exit_basis") or "",
        "why_this_deal": verdict.get("why_this_deal") or "",
        "first_profit_priority": verdict.get("first_profit_priority"),
        "active_p25": verdict.get("active_p25"),
        "active_haircut": verdict.get("active_haircut"),
        "expected_net": verdict.get("expected_net") or verdict.get("net_resale"),
    }
    columns = ",".join(payload.keys())
    placeholders = ",".join(f":{key}" for key in payload)
    updates = ",".join(f"{key}=excluded.{key}" for key in payload if key != "listing_id")
    with connect() as conn:
        conn.execute(
            f"""INSERT INTO deal_verdicts ({columns}) VALUES ({placeholders})
            ON CONFLICT(listing_id) DO UPDATE SET {updates}""",
            payload,
        )


def save_comps(listing_id: str, comps: list[dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM deal_comps WHERE listing_id = ?", (listing_id,))
        for comp in comps[:20]:
            conn.execute(
                """INSERT INTO deal_comps (listing_id, title, price, url, sold_at, source, match_quality, shipping, condition, source_comp_id, variant, retrieved_at, include_decision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    listing_id,
                    str(comp.get("title") or "")[:240],
                    comp.get("price"),
                    str(comp.get("url") or ""),
                    str(comp.get("sold_at") or ""),
                    str(comp.get("source") or ""),
                    str(comp.get("match_quality") or ""),
                    comp.get("shipping"),
                    str(comp.get("condition") or ""),
                    str(comp.get("source_comp_id") or ""),
                    str(comp.get("variant") or ""),
                    str(comp.get("retrieved_at") or ""),
                    str(comp.get("include_decision") or "include"),
                ),
            )


def latest_verdict(listing_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = _row(conn.execute("SELECT * FROM deal_verdicts WHERE listing_id = ?", (listing_id,)).fetchone())
    if row:
        row["reasons"] = _json_list(row.get("reasons_json"))
        row["signals"] = _json_list(row.get("signals_json"))
        row["provider_badges"] = _json_list(row.get("provider_badges_json"))
        row["why_this_value"] = _json_list(row.get("why_json"))
    return row


def comps_for(listing_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return [_row(row) for row in conn.execute("SELECT * FROM deal_comps WHERE listing_id = ?", (listing_id,))]


def list_deal_feed(filters: dict[str, Any] | None = None, limit: int = 60) -> list[dict[str, Any]]:
    filters = filters or {}
    sql = """SELECT l.*, v.classification, v.expected_profit, v.roi_pct, v.landed_cost, v.net_resale,
             v.expected_resale, v.fees, v.shipping, v.max_buy_price, v.risk, v.liquidity, v.confidence,
             v.comp_source, v.sold_count, v.reasons_json, v.signals_json, v.analyzed_at AS verdict_at,
             v.valuation_grade, v.verified_exit_basis, v.fast_cash, v.exit_floor, v.market_expectation,
             v.provider_badges_json, v.why_json, v.best_expected_exit, v.source_to_exit, v.profit_velocity,
             v.discount_pct, v.conservative_active_exit, v.margin_of_safety_dollars, v.margin_of_safety_percent,
             v.break_even_resale, v.valuation_error_cushion_dollars, v.valuation_error_cushion_percent,
             v.clean_comparable_count, v.raw_comparable_count, v.excluded_comparable_count,
             v.market_stability, v.market_sample_confidence, v.valuation_basis, v.why_this_deal,
             v.first_profit_priority, v.active_p25, v.active_haircut, v.expected_net, v.inbound_shipping,
             v.identity_confidence, v.candidate_model, v.candidate_product_family
             FROM marketplace_listings l
             LEFT JOIN deal_verdicts v ON v.listing_id = l.id
             WHERE 1=1"""
    args: list[Any] = []
    if filters.get("classification"):
        sql += " AND v.classification = ?"
        args.append(str(filters["classification"]).upper())
    if filters.get("source"):
        sql += " AND l.source = ?"
        args.append(filters["source"])
    if filters.get("family"):
        sql += " AND COALESCE(v.candidate_product_family, l.candidate_product_family) = ?"
        args.append(filters["family"])
    if filters.get("market"):
        sql += " AND l.market_id = ?"
        args.append(filters["market"])
    if filters.get("min_profit"):
        try:
            sql += " AND COALESCE(v.expected_profit,0) >= ?"
            args.append(float(filters["min_profit"]))
        except Exception:
            pass
    mode = str(filters.get("mode") or "first_profit").lower()
    if not filters.get("classification") and mode in {"first_profit", "money", ""}:
        include_watch = str(filters.get("include_watch") or "").lower() in {"1", "true", "yes"}
        include_risk = str(filters.get("include_risk") or "").lower() in {"1", "true", "yes"}
        allowed = ["MONSTER", "HOT", "STRONG"]
        if include_watch:
            allowed.append("WATCH")
        if include_risk:
            allowed.append("RISK")
        placeholders = ",".join("?" for _ in allowed)
        sql += f" AND v.classification IN ({placeholders})"
        args.extend(allowed)
        try:
            from dealbrain.config import get_config
            sql += " AND COALESCE(v.expected_profit,0) >= ?"
            args.append(float(get_config().first_profit_min_profit))
        except Exception:
            sql += " AND COALESCE(v.expected_profit,0) >= 50"
    sort = str(filters.get("sort") or "best").lower()
    if sort == "newest":
        sql += " ORDER BY l.last_seen_at DESC"
    elif sort == "profit":
        sql += " ORDER BY COALESCE(v.expected_profit, -99999) DESC"
    elif sort == "roi":
        sql += " ORDER BY COALESCE(v.roi_pct, -99999) DESC"
    elif sort == "price":
        sql += " ORDER BY CASE WHEN l.asking_price IS NULL THEN 1 ELSE 0 END, l.asking_price ASC"
    elif sort == "price_drop":
        sql += " ORDER BY CASE l.lifecycle_status WHEN 'PRICE_DROP' THEN 0 ELSE 1 END, l.last_seen_at DESC"
    elif sort == "discount":
        sql += " ORDER BY COALESCE(v.discount_pct, -99999) DESC"
    elif sort == "confidence":
        sql += """ ORDER BY CASE v.confidence
            WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,
            COALESCE(v.expected_profit,0) DESC"""
    else:
        sql += """ ORDER BY COALESCE(v.first_profit_priority, -99999) DESC, CASE v.classification
            WHEN 'MONSTER' THEN 0 WHEN 'HOT' THEN 1 WHEN 'STRONG' THEN 2
            WHEN 'WATCH' THEN 3 WHEN 'RISK' THEN 4 ELSE 5 END,
            COALESCE(v.expected_profit,0) DESC, l.last_seen_at DESC"""
    sql += " LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = [_row(row) for row in conn.execute(sql, args)]
    for row in rows:
        row["stage1_reasons"] = _json_list(row.get("stage1_reasons"))
        row["reasons"] = _json_list(row.get("reasons_json"))
        row["signals"] = _json_list(row.get("signals_json"))
        row["listing_url"] = row.get("canonical_url") or ""
        row["primary_image"] = row.get("thumbnail_url") or ""
        row["facebook_url"] = row.get("canonical_url") if str(row.get("source") or "").startswith("facebook") else ""
        row["provider_badges"] = _json_list(row.get("provider_badges_json"))
        row["why_this_value"] = _json_list(row.get("why_json"))
    return rows


def deal_counts() -> dict[str, Any]:
    with connect() as conn:
        def _count(klass: str) -> int:
            return int(conn.execute("SELECT COUNT(*) FROM deal_verdicts WHERE classification = ?", (klass,)).fetchone()[0])
        counts = {
            "monster": _count("MONSTER"),
            "hot": _count("HOT"),
            "strong": _count("STRONG"),
            "watch": _count("WATCH"),
        }
        last = _row(conn.execute("SELECT * FROM ebay_sniper_runs ORDER BY started_at DESC LIMIT 1").fetchone())
    counts["last_ebay_run"] = last
    return counts


def listing_detail(listing_id: str) -> dict[str, Any]:
    listing = mp_listing_by_id(listing_id)
    if not listing:
        return {}
    verdict = latest_verdict(listing_id)
    deal = {**listing, **verdict}
    deal["reasons"] = verdict.get("reasons") or _json_list(listing.get("stage1_reasons"))
    deal["valuation_explanation"] = next((r for r in deal["reasons"] if str(r).startswith("VALUATION EVIDENCE:")), "")
    deal["listing_url"] = listing.get("canonical_url") or ""
    deal["primary_image"] = listing.get("thumbnail_url") or ""
    deal["comps"] = comps_for(listing_id)
    deal["evidence_rows"] = evidence_for(listing_id)
    from marketplace.store import price_events
    deal["history"] = price_events(listing_id)
    own = own_sales_for(str(deal.get("canonical_product_id") or deal.get("candidate_model") or listing_id))
    deal["own_sales"] = own
    if own:
        latest = own[0]
        predicted = deal.get("conservative_active_exit") or deal.get("conservative_resale") or latest.get("predicted_resale")
        actual = latest.get("sale_price")
        deal["predicted_vs_actual"] = {
            "predicted_resale": predicted,
            "actual_resale": actual,
            "predicted_profit": deal.get("expected_profit"),
            "actual_profit": latest.get("profit"),
            "prediction_error": None if predicted in (None, "") or actual in (None, "") else round(float(actual) - float(predicted), 2),
            "predicted_roi": deal.get("roi_pct"),
            "actual_roi": None,
            "days_held": latest.get("days_held"),
        }
        try:
            if latest.get("profit") not in (None, "") and latest.get("purchase_price"):
                buy = float(latest.get("purchase_price") or 0) + float(latest.get("purchase_shipping") or 0)
                if buy:
                    deal["predicted_vs_actual"]["actual_roi"] = round((float(latest.get("profit")) / buy) * 100.0, 1)
        except Exception:
            pass
    return deal


deal_detail = listing_detail


def record_alert(
    listing_id: str,
    alert_type: str,
    *,
    classification: str = "",
    price: Any = None,
    profit: Any = None,
    sent: bool = False,
    skip_reason: str = "",
    channel: str = "sms",
) -> None:
    payload = json.dumps({"classification": classification, "price": price, "profit": profit}, default=str)
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO marketplace_alert_events
            (id, listing_id, alert_type, payload_json, created_at, sent_at, channel, skip_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                __import__("uuid").uuid4().hex,
                listing_id,
                alert_type,
                payload,
                now,
                now if sent else "",
                channel,
                skip_reason,
            ),
        )


def alerts_for(listing_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = [_row(row) for row in conn.execute(
            "SELECT * FROM marketplace_alert_events WHERE listing_id = ? ORDER BY created_at DESC",
            (listing_id,),
        )]
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        row["classification"] = payload.get("classification") or ""
        row["price"] = payload.get("price")
        row["sent"] = 1 if row.get("sent_at") and not row.get("skip_reason") else 0
    return rows


def recent_alerts(hours: int = 1, sent_only: bool = False) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(microsecond=0).isoformat()
    sql = "SELECT * FROM marketplace_alert_events WHERE created_at >= ?"
    if sent_only:
        sql += " AND sent_at != '' AND (skip_reason IS NULL OR skip_reason = '')"
    with connect() as conn:
        return [_row(row) for row in conn.execute(sql, (cutoff,))]


def save_sniper_run(**fields: Any) -> str:
    run_id = str(fields.get("id") or __import__("uuid").uuid4().hex)
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO ebay_sniper_runs
            (id, query, status, started_at, finished_at, raw_row_count, unique_count, candidate_count, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                fields.get("query") or "",
                fields.get("status") or "RUNNING",
                fields.get("started_at") or now,
                fields.get("finished_at") or "",
                int(fields.get("raw_row_count") or 0),
                int(fields.get("unique_count") or 0),
                int(fields.get("candidate_count") or 0),
                fields.get("error_message") or "",
            ),
        )
    return run_id


def finish_sniper_run(run_id: str, **fields: Any) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE ebay_sniper_runs SET status=?, finished_at=?, raw_row_count=?, unique_count=?, candidate_count=?, error_message=?
            WHERE id=?""",
            (
                fields.get("status") or "SUCCEEDED",
                utc_now(),
                int(fields.get("raw_row_count") or 0),
                int(fields.get("unique_count") or 0),
                int(fields.get("candidate_count") or 0),
                fields.get("error_message") or "",
                run_id,
            ),
        )


def save_evidence(listing_id: str, rows: list[dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM valuation_evidence WHERE listing_id = ?", (listing_id,))
        for row in rows[:30]:
            conn.execute(
                """INSERT INTO valuation_evidence
                (listing_id, provider, evidence_type, grade, value, currency, sample_count, is_realized_sale, is_active_ask, payload_json, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    listing_id,
                    str(row.get("provider") or ""),
                    str(row.get("evidence_type") or ""),
                    str(row.get("grade") or ""),
                    row.get("value"),
                    str(row.get("currency") or "USD"),
                    int(row.get("sample_count") or 0),
                    1 if row.get("is_realized_sale") else 0,
                    1 if row.get("is_active_ask") else 0,
                    json.dumps(row, default=str),
                    str(row.get("retrieved_at") or utc_now()),
                ),
            )


def evidence_for(listing_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = [_row(r) for r in conn.execute(
            "SELECT * FROM valuation_evidence WHERE listing_id = ? ORDER BY id",
            (listing_id,),
        )]
    out = []
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except Exception:
            payload = {}
        out.append({**payload, **row})
    return out


def own_sales_for(canonical_product_id: str) -> list[dict[str, Any]]:
    if not canonical_product_id:
        return []
    with connect() as conn:
        return [_row(r) for r in conn.execute(
            """SELECT * FROM valuation_own_sales
            WHERE canonical_product_id = ? OR exact_model = ?
            ORDER BY created_at DESC""",
            (canonical_product_id, canonical_product_id),
        )]


def save_own_sale(fields: dict[str, Any]) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO valuation_own_sales
            (listing_id, canonical_product_id, exact_model, variant, condition, purchase_price, purchase_shipping,
             purchase_fees, repair, sale_platform, sale_price, sale_shipping, sale_fees, net_proceeds, profit,
             days_held, location, purchased_at, sold_at, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(fields.get("listing_id") or ""),
                str(fields.get("canonical_product_id") or ""),
                str(fields.get("exact_model") or ""),
                str(fields.get("variant") or ""),
                str(fields.get("condition") or ""),
                fields.get("purchase_price"),
                fields.get("purchase_shipping"),
                fields.get("purchase_fees"),
                fields.get("repair"),
                str(fields.get("sale_platform") or ""),
                fields.get("sale_price"),
                fields.get("sale_shipping"),
                fields.get("sale_fees"),
                fields.get("net_proceeds"),
                fields.get("profit"),
                fields.get("days_held"),
                str(fields.get("location") or ""),
                str(fields.get("purchased_at") or ""),
                str(fields.get("sold_at") or ""),
                str(fields.get("notes") or ""),
                now,
            ),
        )
        if fields.get("sale_price") not in (None, ""):
            try:
                family = str(fields.get("canonical_product_id") or fields.get("exact_model") or "unknown")
                predicted = fields.get("predicted_resale")
                actual = fields.get("sale_price")
                error = None
                if predicted not in (None, "") and actual not in (None, ""):
                    error = round(float(actual) - float(predicted), 2)
                conn.execute(
                    """INSERT INTO valuation_family_stats
                    (family, sales, actual_profit, predicted_resale, actual_resale, prediction_error, days_to_sell, updated_at)
                    VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(family) DO UPDATE SET
                    sales = sales + 1,
                    actual_profit = COALESCE(actual_profit,0) + excluded.actual_profit,
                    predicted_resale = excluded.predicted_resale,
                    actual_resale = excluded.actual_resale,
                    prediction_error = excluded.prediction_error,
                    days_to_sell = excluded.days_to_sell,
                    updated_at = excluded.updated_at""",
                    (
                        family,
                        float(fields.get("profit") or 0),
                        predicted,
                        actual,
                        error,
                        fields.get("days_held"),
                        now,
                    ),
                )
            except Exception:
                pass


def manual_refs_for(key: str) -> list[dict[str, Any]]:
    if not key:
        return []
    like = f"%{key}%"
    with connect() as conn:
        return [_row(r) for r in conn.execute(
            """SELECT * FROM valuation_manual_refs
            WHERE canonical_product_id = ? OR query LIKE ?
            ORDER BY created_at DESC""",
            (key, like),
        )]


def save_manual_ref(fields: dict[str, Any]) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO valuation_manual_refs
            (query, canonical_product_id, date_range, average_sold_price, sold_low, sold_high, average_shipping,
             sell_through, sample_count, research_at, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(fields.get("query") or ""),
                str(fields.get("canonical_product_id") or fields.get("query") or ""),
                str(fields.get("date_range") or ""),
                fields.get("average_sold_price"),
                fields.get("sold_low"),
                fields.get("sold_high"),
                fields.get("average_shipping"),
                fields.get("sell_through"),
                int(fields.get("sample_count") or 0),
                str(fields.get("research_at") or now),
                str(fields.get("notes") or ""),
                now,
            ),
        )


def save_dry_run_alert(listing_id: str, classification: str, payload: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO valuation_alert_dry_run (listing_id, classification, payload, created_at) VALUES (?, ?, ?, ?)",
            (listing_id, classification, payload, utc_now()),
        )


def list_dry_run_alerts(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        return [_row(r) for r in conn.execute(
            "SELECT * FROM valuation_alert_dry_run ORDER BY id DESC LIMIT ?",
            (limit,),
        )]


def record_query_stats(source: str, query: str, category: str, **counts: Any) -> None:
    now = utc_now()
    with connect() as conn:
        existing = _row(conn.execute(
            "SELECT * FROM valuation_query_stats WHERE source = ? AND query = ?",
            (source, query),
        ).fetchone())
        if not existing:
            conn.execute(
                """INSERT INTO valuation_query_stats
                (source, query, category, runs, raw_rows, unique_rows, candidates, deep, monster, hot, strong,
                 purchases, actual_profit, provider_cost, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source, query, category,
                    int(counts.get("raw_rows") or 0),
                    int(counts.get("unique_rows") or 0),
                    int(counts.get("candidates") or 0),
                    int(counts.get("deep") or 0),
                    int(counts.get("monster") or 0),
                    int(counts.get("hot") or 0),
                    int(counts.get("strong") or 0),
                    int(counts.get("purchases") or 0),
                    float(counts.get("actual_profit") or 0),
                    float(counts.get("provider_cost") or 0),
                    now,
                ),
            )
            return
        conn.execute(
            """UPDATE valuation_query_stats SET
            runs = runs + 1,
            raw_rows = raw_rows + ?, unique_rows = unique_rows + ?, candidates = candidates + ?,
            deep = deep + ?, monster = monster + ?, hot = hot + ?, strong = strong + ?,
            purchases = purchases + ?, actual_profit = actual_profit + ?, provider_cost = provider_cost + ?,
            updated_at = ?
            WHERE source = ? AND query = ?""",
            (
                int(counts.get("raw_rows") or 0),
                int(counts.get("unique_rows") or 0),
                int(counts.get("candidates") or 0),
                int(counts.get("deep") or 0),
                int(counts.get("monster") or 0),
                int(counts.get("hot") or 0),
                int(counts.get("strong") or 0),
                int(counts.get("purchases") or 0),
                float(counts.get("actual_profit") or 0),
                float(counts.get("provider_cost") or 0),
                now, source, query,
            ),
        )


def list_query_stats(source: str = "", limit: int = 80) -> list[dict[str, Any]]:
    sql = "SELECT * FROM valuation_query_stats"
    args: list[Any] = []
    if source:
        sql += " WHERE source = ?"
        args.append(source)
    sql += " ORDER BY runs DESC, provider_cost DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [_row(row) for row in conn.execute(sql, args)]
