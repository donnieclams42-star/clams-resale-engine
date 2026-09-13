"""Per-run Facebook scanner ledger, lane accounting, and scheduler evidence.

Discovery cadence stays unchanged. This module records what actually ran.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from marketplace.catalog import (
    ESTIMATED_APIFY_USD_PER_RUN,
    FIRST_PROFIT_LEVEL1_MARKETS,
    LEVEL1_MAX_RUNS_PER_DAY,
)
from marketplace.normalize import utc_now

LANE_PRECISION = "PRECISION"
LANE_TREASURE = "TREASURE"
LANE_REPAIR = "REPAIR"
LANE_GENERIC = "GENERIC"
LANE_REMOTE_RESEARCH = "REMOTE_RESEARCH"

PRODUCTION_LANES = (
    LANE_PRECISION,
    LANE_TREASURE,
    LANE_REPAIR,
    LANE_GENERIC,
    LANE_REMOTE_RESEARCH,
)

CADENCE_TO_LANE = {
    "PRECISION": LANE_PRECISION,
    "TREASURE": LANE_TREASURE,
    "REPAIR": LANE_REPAIR,
    "GENERIC": LANE_GENERIC,
    "RESEARCH": LANE_REMOTE_RESEARCH,
    "REMOTE_RESEARCH": LANE_REMOTE_RESEARCH,
}

QUERY_TYPE_TO_LANE = {
    "EXACT_MODEL": LANE_PRECISION,
    "ABBREVIATION": LANE_PRECISION,
    "MISSPELLING": LANE_PRECISION,
    "BUNDLE": LANE_TREASURE,
    "URGENCY": LANE_TREASURE,
    "HOUSEHOLD_LANGUAGE": LANE_TREASURE,
    "PLACEHOLDER": LANE_TREASURE,
    "REPAIR": LANE_REPAIR,
    "GENERIC": LANE_GENERIC,
    "RESEARCH": LANE_REMOTE_RESEARCH,
}

CAP_OK = "CAP_OK"
CAP_NEAR_LIMIT = "CAP_NEAR_LIMIT"
CAP_REACHED = "CAP_REACHED"

LOCAL_MARKET_IDS = tuple(row["id"] for row in FIRST_PROFIT_LEVEL1_MARKETS)
LOCAL_MARKET_NAMES = {row["id"]: row["name"] for row in FIRST_PROFIT_LEVEL1_MARKETS}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(microsecond=0).isoformat()


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def normalize_lane(cadence_tier: str = "", query_type: str = "", *, research: bool = False) -> str:
    cadence = str(cadence_tier or "").strip().upper()
    qtype = str(query_type or "").strip().upper()
    if research or cadence in {"RESEARCH", "REMOTE_RESEARCH"}:
        return LANE_REMOTE_RESEARCH
    if cadence in CADENCE_TO_LANE:
        return CADENCE_TO_LANE[cadence]
    if qtype in QUERY_TYPE_TO_LANE:
        return QUERY_TYPE_TO_LANE[qtype]
    if qtype in {"EXACT_MODEL", "ABBREVIATION", "MISSPELLING"}:
        return LANE_PRECISION
    raise ValueError(f"no production lane for cadence={cadence_tier!r} query_type={query_type!r}")


def lane_for_target(target: Any) -> str:
    if isinstance(target, dict):
        cadence = str(target.get("cadence_tier") or "")
        qtype = str(target.get("query_type") or "")
        research = cadence.upper() == "RESEARCH" or str(target.get("id") or "").startswith("research:")
        return normalize_lane(cadence, qtype, research=research)
    cadence = str(getattr(target, "cadence_tier", "") or "")
    qtype = str(getattr(target, "query_type", "") or "")
    ident = str(getattr(target, "id", "") or "")
    return normalize_lane(cadence, qtype, research=cadence.upper() == "RESEARCH" or ident.startswith("research:"))


def cap_state_from_meta(meta: dict[str, Any] | None, *, ok: bool, reason: str = "") -> str:
    meta = meta or {}
    spent = float(meta.get("spent") or 0)
    cap = float(meta.get("cap") or 0)
    runs = int(meta.get("runs") or 0)
    run_cap = int(meta.get("run_cap") or LEVEL1_MAX_RUNS_PER_DAY or 30)
    remaining = float(meta.get("remaining") if meta.get("remaining") is not None else (cap - spent))
    blocked = (not ok) and str(reason or "") in {"apify_daily_cap", "facebook_daily_run_cap"}
    if blocked or (cap > 0 and spent + 1e-9 >= cap) or (run_cap > 0 and runs >= run_cap):
        return CAP_REACHED
    near_spend = cap > 0 and remaining <= max(0.05, cap * 0.20)
    near_runs = run_cap > 0 and runs >= max(1, int(run_cap * 0.80))
    if near_spend or near_runs:
        return CAP_NEAR_LIMIT
    return CAP_OK


def seed_run_extra(target: Any, *, stage: str = "discovery", result_limit: int = 0) -> dict[str, Any]:
    if isinstance(target, dict):
        market_id = str(target.get("market_id") or "")
        query = str(target.get("query") or "")
        provider = str(target.get("provider") or "")
        limit = int(result_limit or target.get("result_limit") or 0)
    else:
        market_id = str(getattr(target, "market_id", "") or "")
        query = str(getattr(target, "query", "") or "")
        provider = str(getattr(target, "provider", "") or "")
        limit = int(result_limit or getattr(target, "result_limit", 0) or 0)
    lane = lane_for_target(target) if str(stage or "discovery") != "detail" else ""
    return {
        "lane": lane,
        "market_id": market_id,
        "query": query,
        "provider": provider,
        "result_limit": limit,
        "cost_kind": "",
        "cost_usd": 0.0,
        "deep_count": 0,
        "identity_verified_count": 0,
        "needs_verification_count": 0,
        "actionable_count": 0,
        "discord_alert_count": 0,
        "success": None,
        "failure_reason": "",
        "duration_ms": 0,
    }


def cap_reason_label(reason: str) -> str:
    return {
        "apify_daily_cap": "daily cap reached",
        "facebook_daily_run_cap": "daily run cap reached",
        "market_stagger": "stagger wait",
        "local_allotment_reserved": "remote blocked by leftover-only rule",
        "no_leftover_budget": "remote blocked by low remaining budget",
        "leftover_research_cap": "remote leftover cap reached",
        "protect_core_regions": "precision protected",
        "no_due_targets": "cadence not due",
    }.get(str(reason or ""), str(reason or ""))


def lane_due_reason(lane: str) -> str:
    return {
        LANE_PRECISION: "precision due",
        LANE_REPAIR: "repair due",
        LANE_TREASURE: "treasure due",
        LANE_GENERIC: "generic due",
        LANE_REMOTE_RESEARCH: "remote leftover-only due",
    }.get(str(lane or "").upper(), f"{str(lane or 'lane').lower()} due")


def save_identity_recheck(report: dict[str, Any]) -> None:
    from marketplace.store import connect

    payload = dict(report or {})
    payload["saved_at"] = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO marketplace_kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("identity_recheck_latest", json.dumps(payload, default=str)),
        )


def load_identity_recheck() -> dict[str, Any]:
    from marketplace.store import connect

    with connect() as conn:
        row = conn.execute("SELECT value FROM marketplace_kv WHERE key = ?", ("identity_recheck_latest",)).fetchone()
    if not row:
        return {}
    return _json_obj(row[0] if not hasattr(row, "keys") else row["value"])


def backfill_run_ledger_from_scan_runs(limit: int = 500) -> int:
    """Copy existing discovery scan_runs into the ledger. Does not launch scans."""
    from marketplace.store import connect

    filled = 0
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.id, r.usage_usd, r.status, r.error_message, r.raw_row_count, r.unique_count,
                      r.candidate_count, r.duplicate_count, r.stage,
                      t.cadence_tier, t.query_type, t.market_id, t.query, t.provider, t.result_limit, t.id
               FROM marketplace_scan_runs r
               LEFT JOIN marketplace_scan_targets t ON t.id = r.target_id
               LEFT JOIN marketplace_run_ledger l ON l.run_id = r.id
               WHERE l.run_id IS NULL AND COALESCE(r.stage, 'discovery') != 'detail'
               ORDER BY r.started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    for row in rows:
        target = {
            "id": row[15] or "",
            "cadence_tier": row[9] or "",
            "query_type": row[10] or "",
            "market_id": row[11] or "",
            "query": row[12] or "",
            "provider": row[13] or "",
            "result_limit": row[14] or 0,
        }
        try:
            lane = lane_for_target(target)
        except Exception:
            lane = LANE_PRECISION if str(row[10] or "").upper() in {"EXACT_MODEL", "ABBREVIATION", "MISSPELLING", ""} else ""
        usage = row[1]
        cost_usd, cost_kind = resolve_cost(usage)
        persist_run_ledger(row[0], {
            "usage_usd": cost_usd,
            "status": row[2],
            "error_message": row[3] or "",
            "raw_row_count": row[4] or 0,
            "unique_count": row[5] or 0,
            "candidate_count": row[6] or 0,
            "duplicate_count": row[7] or 0,
            "lane": lane,
            "market_id": target["market_id"],
            "query": target["query"],
            "cost_usd": cost_usd,
            "cost_kind": "actual" if float(usage or 0) > 0 else cost_kind,
            "success": str(row[2] or "") in {"SUCCEEDED", "completed", "completed_zero"},
        })
        filled += 1
    return filled


def persist_run_ledger(run_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    from marketplace.store import connect, get_run

    run = get_run(run_id) or {}
    extra = _json_obj(run.get("extra_json"))
    extra.update({key: value for key, value in fields.items() if value is not None})
    started = str(run.get("started_at") or "")
    finished = str(fields.get("finished_at") or run.get("finished_at") or utc_now())
    duration_ms = extra.get("duration_ms") or 0
    if started and finished and not duration_ms:
        try:
            start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            duration_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))
            extra["duration_ms"] = duration_ms
        except Exception:
            duration_ms = 0
    payload = {
        "run_id": run_id,
        "started_at": started,
        "finished_at": finished,
        "lane": extra.get("lane") or fields.get("lane") or "",
        "market_id": extra.get("market_id") or fields.get("market_id") or "",
        "query": extra.get("query") or fields.get("query") or "",
        "provider": extra.get("provider") or run.get("provider") or "",
        "result_limit": int(extra.get("result_limit") or fields.get("result_limit") or 0),
        "raw_count": int(fields.get("raw_row_count") if fields.get("raw_row_count") is not None else run.get("raw_row_count") or 0),
        "unique_count": int(fields.get("unique_count") if fields.get("unique_count") is not None else run.get("unique_count") or 0),
        "duplicate_count": int(fields.get("duplicate_count") if fields.get("duplicate_count") is not None else run.get("duplicate_count") or 0),
        "stage1_count": int(fields.get("candidate_count") if fields.get("candidate_count") is not None else run.get("candidate_count") or 0),
        "deep_count": int(extra.get("deep_count") or 0),
        "identity_verified_count": int(extra.get("identity_verified_count") or 0),
        "needs_verification_count": int(extra.get("needs_verification_count") or 0),
        "actionable_count": int(extra.get("actionable_count") or 0),
        "discord_alert_count": int(extra.get("discord_alert_count") or 0),
        "cost_usd": float(extra.get("cost_usd") or fields.get("usage_usd") or 0),
        "cost_kind": extra.get("cost_kind") or "",
        "success": 1 if (
            extra.get("success") is True
            or (
                extra.get("success") is None
                and str(fields.get("status") or run.get("status") or "") in {"SUCCEEDED", "completed", "completed_zero"}
            )
        ) else 0,
        "failure_reason": extra.get("failure_reason") or fields.get("error_message") or "",
        "duration_ms": int(duration_ms or 0),
        "extra_json": json.dumps(extra, default=str),
        "stage": str(run.get("stage") or "discovery"),
        "status": str(fields.get("status") or run.get("status") or ""),
    }
    with connect() as conn:
        conn.execute(
            """INSERT INTO marketplace_run_ledger(
                run_id, started_at, finished_at, lane, market_id, query, provider, result_limit,
                raw_count, unique_count, duplicate_count, stage1_count, deep_count,
                identity_verified_count, needs_verification_count, actionable_count, discord_alert_count,
                cost_usd, cost_kind, success, failure_reason, duration_ms, extra_json, stage, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET
                finished_at=excluded.finished_at, lane=excluded.lane, market_id=excluded.market_id,
                query=excluded.query, provider=excluded.provider, result_limit=excluded.result_limit,
                raw_count=excluded.raw_count, unique_count=excluded.unique_count, duplicate_count=excluded.duplicate_count,
                stage1_count=excluded.stage1_count, deep_count=excluded.deep_count,
                identity_verified_count=excluded.identity_verified_count,
                needs_verification_count=excluded.needs_verification_count,
                actionable_count=excluded.actionable_count, discord_alert_count=excluded.discord_alert_count,
                cost_usd=excluded.cost_usd, cost_kind=excluded.cost_kind, success=excluded.success,
                failure_reason=excluded.failure_reason, duration_ms=excluded.duration_ms,
                extra_json=excluded.extra_json, stage=excluded.stage, status=excluded.status
            """,
            (
                payload["run_id"], payload["started_at"], payload["finished_at"], payload["lane"],
                payload["market_id"], payload["query"], payload["provider"], payload["result_limit"],
                payload["raw_count"], payload["unique_count"], payload["duplicate_count"], payload["stage1_count"],
                payload["deep_count"], payload["identity_verified_count"], payload["needs_verification_count"],
                payload["actionable_count"], payload["discord_alert_count"], payload["cost_usd"],
                payload["cost_kind"], payload["success"], payload["failure_reason"], payload["duration_ms"],
                payload["extra_json"], payload["stage"], payload["status"],
            ),
        )
        conn.execute(
            "UPDATE marketplace_scan_runs SET extra_json = ?, lane = ?, market_id = ?, query = ? WHERE id = ?",
            (payload["extra_json"], payload["lane"], payload["market_id"], payload["query"], run_id),
        )
    return payload


def record_scheduler_decision(
    *,
    selected_lane: str = "",
    selected_market: str = "",
    selected_query: str = "",
    reason_selected: str = "",
    skipped: list[dict[str, Any]] | None = None,
    cap_state: str = CAP_OK,
    launched: bool = False,
    extra: dict[str, Any] | None = None,
) -> str:
    from marketplace.store import connect

    decision_id = uuid.uuid4().hex
    with connect() as conn:
        conn.execute(
            """INSERT INTO marketplace_scheduler_decisions(
                id, created_at, selected_lane, selected_market, selected_query,
                reason_selected, skipped_json, cap_state, launched, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision_id,
                utc_now(),
                selected_lane,
                selected_market,
                selected_query,
                reason_selected,
                json.dumps(skipped or [], default=str),
                cap_state,
                1 if launched else 0,
                json.dumps(extra or {}, default=str),
            ),
        )
    return decision_id


def _discovery_filter_sql() -> str:
    return "AND COALESCE(stage, 'discovery') != 'detail'"


def lane_counts(*, since: str = "", today_only: bool = False) -> dict[str, int]:
    from marketplace.store import connect

    counts = {lane: 0 for lane in PRODUCTION_LANES}
    counts["total"] = 0
    day = _today()
    with connect() as conn:
        sql = f"""SELECT lane, COUNT(*) AS n FROM marketplace_run_ledger
                  WHERE COALESCE(stage,'discovery') != 'detail' """
        args: list[Any] = []
        if today_only:
            sql += " AND started_at LIKE ?"
            args.append(f"{day}%")
        elif since:
            sql += " AND started_at >= ?"
            args.append(since)
        sql += " GROUP BY lane"
        for row in conn.execute(sql, args):
            lane = str(row[0] or "")
            n = int(row[1] or 0)
            if lane in counts:
                counts[lane] = n
            counts["total"] += n
    return counts


def spend_by_lane(*, today_only: bool = True) -> dict[str, Any]:
    from marketplace.store import connect

    day = _today()
    out = {lane: {"usd": 0.0, "actual_usd": 0.0, "estimated_usd": 0.0, "runs": 0} for lane in PRODUCTION_LANES}
    total = 0.0
    with connect() as conn:
        sql = """SELECT lane, COALESCE(SUM(cost_usd),0), COUNT(*),
                        COALESCE(SUM(CASE WHEN cost_kind='actual' THEN cost_usd ELSE 0 END),0),
                        COALESCE(SUM(CASE WHEN cost_kind='estimated' THEN cost_usd ELSE 0 END),0)
                 FROM marketplace_run_ledger
                 WHERE COALESCE(stage,'discovery') != 'detail'"""
        args: list[Any] = []
        if today_only:
            sql += " AND started_at LIKE ?"
            args.append(f"{day}%")
        sql += " GROUP BY lane"
        for row in conn.execute(sql, args):
            lane = str(row[0] or "")
            usd = float(row[1] or 0)
            if lane in out:
                out[lane] = {
                    "usd": round(usd, 4),
                    "runs": int(row[2] or 0),
                    "actual_usd": round(float(row[3] or 0), 4),
                    "estimated_usd": round(float(row[4] or 0), 4),
                }
            total += usd
    out["total"] = round(total, 4)
    return out


def list_run_history(*, hours: int = 24, limit: int = 80) -> list[dict[str, Any]]:
    from marketplace.store import connect

    cutoff = _hours_ago(hours)
    with connect() as conn:
        rows = conn.execute(
            """SELECT run_id, started_at, finished_at, lane, market_id, query, provider,
                      result_limit, raw_count, unique_count, duplicate_count, stage1_count,
                      deep_count, identity_verified_count, needs_verification_count,
                      actionable_count, discord_alert_count, cost_usd, cost_kind, success,
                      failure_reason, duration_ms, status, extra_json
               FROM marketplace_run_ledger
               WHERE COALESCE(stage,'discovery') != 'detail' AND started_at >= ?
               ORDER BY started_at DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    history = []
    for row in rows:
        keys = [
            "run_id", "started_at", "finished_at", "lane", "market_id", "query", "provider",
            "result_limit", "raw_count", "unique_count", "duplicate_count", "stage1_count",
            "deep_count", "identity_verified_count", "needs_verification_count",
            "actionable_count", "discord_alert_count", "cost_usd", "cost_kind", "success",
            "failure_reason", "duration_ms", "status", "extra_json",
        ]
        item = {keys[i]: row[i] for i in range(len(keys))}
        item["success"] = bool(item.get("success"))
        item["market_name"] = LOCAL_MARKET_NAMES.get(str(item.get("market_id") or ""), item.get("market_id") or "")
        extra = _json_obj(item.pop("extra_json", {}))
        item["cost_label"] = "estimated" if str(item.get("cost_kind") or "") == "estimated" else "actual"
        item.update({k: v for k, v in extra.items() if k not in item})
        history.append(item)
    return history


def market_performance(*, today_only: bool = True) -> list[dict[str, Any]]:
    from marketplace.store import connect

    day = _today()
    with connect() as conn:
        sql = """SELECT market_id,
                        COUNT(*) AS runs,
                        COALESCE(SUM(cost_usd),0) AS spend,
                        COALESCE(SUM(raw_count),0) AS raw,
                        COALESCE(SUM(unique_count),0) AS unique_n,
                        COALESCE(SUM(duplicate_count),0) AS dups,
                        COALESCE(SUM(stage1_count),0) AS stage1,
                        COALESCE(SUM(identity_verified_count),0) AS verified,
                        COALESCE(SUM(actionable_count),0) AS actionable
                 FROM marketplace_run_ledger
                 WHERE COALESCE(stage,'discovery') != 'detail'"""
        args: list[Any] = []
        if today_only:
            sql += " AND started_at LIKE ?"
            args.append(f"{day}%")
        sql += " GROUP BY market_id"
        rows = conn.execute(sql, args).fetchall()
    by_id = {str(row[0] or ""): row for row in rows}
    out = []
    for market_id in LOCAL_MARKET_IDS:
        row = by_id.get(market_id)
        raw = int(row[3] or 0) if row else 0
        dups = int(row[5] or 0) if row else 0
        out.append({
            "market_id": market_id,
            "market_name": LOCAL_MARKET_NAMES.get(market_id, market_id),
            "runs": int(row[1] or 0) if row else 0,
            "spend": round(float(row[2] or 0), 4) if row else 0.0,
            "raw": raw,
            "unique": int(row[4] or 0) if row else 0,
            "duplicate_pct": round((dups / raw) * 100.0, 1) if raw else 0.0,
            "stage1": int(row[6] or 0) if row else 0,
            "verified": int(row[7] or 0) if row else 0,
            "actionable": int(row[8] or 0) if row else 0,
        })
    return out


def query_performance(*, limit: int = 80) -> dict[str, Any]:
    from marketplace.store import connect

    with connect() as conn:
        rows = conn.execute(
            """SELECT query,
                      COUNT(*) AS runs,
                      COALESCE(SUM(cost_usd),0) AS spend,
                      COALESCE(SUM(unique_count),0) AS unique_n,
                      COALESCE(SUM(stage1_count),0) AS stage1,
                      COALESCE(SUM(identity_verified_count),0) AS verified,
                      COALESCE(SUM(actionable_count),0) AS actionable,
                      COALESCE(SUM(CAST(json_extract(extra_json,'$.hot') AS INTEGER)),0) AS hot,
                      COALESCE(SUM(CAST(json_extract(extra_json,'$.monster') AS INTEGER)),0) AS monster,
                      COALESCE(SUM(CAST(json_extract(extra_json,'$.realized') AS INTEGER)),0) AS realized
               FROM marketplace_run_ledger
               WHERE COALESCE(stage,'discovery') != 'detail' AND COALESCE(query,'') != ''
               GROUP BY query
               ORDER BY actionable DESC, verified DESC, stage1 DESC, runs DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    items = []
    for row in rows:
        items.append({
            "query": row[0],
            "runs": int(row[1] or 0),
            "spend": round(float(row[2] or 0), 4),
            "unique": int(row[3] or 0),
            "stage1": int(row[4] or 0),
            "verified": int(row[5] or 0),
            "actionable": int(row[6] or 0),
            "hot": int(row[7] or 0),
            "monster": int(row[8] or 0),
            "realized": int(row[9] or 0),
            "yield_score": int(row[6] or 0) * 10 + int(row[5] or 0) * 3 + int(row[4] or 0),
        })
    yielding = [row for row in items if row["runs"] > 0]
    top = sorted(yielding, key=lambda r: (r["actionable"], r["verified"], r["stage1"]), reverse=True)[:8]
    bottom = sorted(yielding, key=lambda r: (r["actionable"], r["verified"], r["stage1"], -r["runs"]))[:8]
    return {"queries": items, "top_yielding": top, "lowest_yielding": bottom}


def lane_starvation_status() -> dict[str, Any]:
    from marketplace.store import connect

    now = utc_now()
    day = _today()
    cutoff = _hours_ago(24)
    with connect() as conn:
        targets = conn.execute(
            """SELECT cadence_tier, COUNT(*) AS n,
                      MIN(CASE WHEN enabled=1 AND next_due_at NOT NULL AND next_due_at != '' THEN next_due_at END) AS next_due,
                      SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) AS enabled_n
               FROM marketplace_scan_targets
               GROUP BY cadence_tier"""
        ).fetchall()
        last_rows = conn.execute(
            """SELECT lane, MAX(started_at), COUNT(*) FROM marketplace_run_ledger
               WHERE COALESCE(stage,'discovery') != 'detail' AND started_at >= ?
               GROUP BY lane""",
            (cutoff,),
        ).fetchall()
        today_rows = conn.execute(
            """SELECT lane, COUNT(*) FROM marketplace_run_ledger
               WHERE COALESCE(stage,'discovery') != 'detail' AND started_at LIKE ?
               GROUP BY lane""",
            (f"{day}%",),
        ).fetchall()
    last_by = {str(row[0] or ""): str(row[1] or "") for row in last_rows}
    last24_by = {str(row[0] or ""): int(row[2] or 0) for row in last_rows}
    today_by = {str(row[0] or ""): int(row[1] or 0) for row in today_rows}
    cadence_enabled = {}
    cadence_next = {}
    for row in targets:
        lane = CADENCE_TO_LANE.get(str(row[0] or "").upper(), "")
        if not lane:
            continue
        cadence_enabled[lane] = int(row[3] or 0)
        cadence_next[lane] = str(row[2] or "")
    out: dict[str, Any] = {}
    for lane in PRODUCTION_LANES:
        enabled = int(cadence_enabled.get(lane) or 0)
        runs_today = int(today_by.get(lane) or 0)
        runs_24h = int(last24_by.get(lane) or 0)
        last_run = last_by.get(lane) or ""
        next_due = cadence_next.get(lane) or ""
        status = "LIVE"
        reason = ""
        if enabled <= 0:
            status = "NOT CONFIGURED"
            reason = "no enabled targets"
        elif runs_today == 0 and runs_24h == 0:
            if lane == LANE_REMOTE_RESEARCH:
                status = "NOT YET ELIGIBLE"
                reason = "leftover-only after local allotment"
            elif next_due and next_due > now:
                status = "NOT YET ELIGIBLE"
                reason = f"cadence not due until {next_due}"
            else:
                status = "STARVED"
                reason = "configured targets due but 0 runs recorded"
        elif runs_today == 0:
            if next_due and next_due > now:
                status = "NOT YET ELIGIBLE"
                reason = f"cadence not due until {next_due}"
            else:
                status = "LIVE"
                reason = "ran in last 24h"
        out[lane] = {
            "lane": lane,
            "enabled_targets": enabled,
            "runs_today": runs_today,
            "runs_last_24h": runs_24h,
            "last_run_at": last_run,
            "next_eligible_at": next_due,
            "status": status,
            "reason": reason,
            "starved": status == "STARVED",
        }
    return out


def peek_next_planned_run(*, protect_core: bool = False) -> dict[str, Any]:
    """Next due paid run from live targets. Does not launch a scan."""
    from marketplace.planner import _next_staggered_target

    skipped: list[dict[str, Any]] = []
    try:
        row = _next_staggered_target(protect_core=protect_core, skipped=skipped)
    except Exception:
        row = {}
    if row:
        try:
            lane = lane_for_target(row)
        except Exception:
            lane = str(row.get("cadence_tier") or "")
        return {
            "lane": lane,
            "market": str(row.get("market_id") or ""),
            "query": str(row.get("query") or ""),
            "time": str(row.get("next_due_at") or ""),
            "reason": lane_due_reason(lane),
            "skipped": skipped,
        }
    reason = ""
    if skipped:
        reason = str(skipped[0].get("reason") or "cadence not due")
    return {
        "lane": "",
        "market": "",
        "query": "",
        "time": "",
        "reason": reason or "cadence not due",
        "skipped": skipped,
    }


def latest_scheduler_decision() -> dict[str, Any]:
    from marketplace.store import connect

    with connect() as conn:
        row = conn.execute(
            """SELECT id, created_at, selected_lane, selected_market, selected_query,
                      reason_selected, skipped_json, cap_state, launched, extra_json
               FROM marketplace_scheduler_decisions
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
    if not row:
        return {}
    return {
        "id": row[0],
        "created_at": row[1],
        "selected_lane": row[2],
        "selected_market": row[3],
        "selected_query": row[4],
        "reason_selected": row[5],
        "skipped": json.loads(row[6] or "[]"),
        "cap_state": row[7],
        "launched": bool(row[8]),
        "extra": _json_obj(row[9]),
    }


def resolve_cost(usage_usd: float | None) -> tuple[float, str]:
    try:
        amount = float(usage_usd) if usage_usd not in (None, "") else 0.0
    except Exception:
        amount = 0.0
    if amount > 0:
        return round(amount, 4), "actual"
    return round(float(ESTIMATED_APIFY_USD_PER_RUN), 4), "estimated"


def scanner_truth_snapshot() -> dict[str, Any]:
    from dealbrain.spend import can_start_facebook_run, spend_snapshot
    from marketplace.catalog import ESTIMATED_APIFY_USD_PER_RUN as per_run
    from marketplace.config import get_config
    from marketplace.workers import runtime_flags

    cfg = get_config()
    flags = runtime_flags()
    spend = spend_snapshot()
    ok, reason, meta = True, "ok", {}
    try:
        ok, reason, meta = can_start_facebook_run(per_run)
    except Exception:
        ok, reason, meta = True, "ok", {}
    state = cap_state_from_meta(meta, ok=ok, reason=reason)
    lanes_today = lane_counts(today_only=True)
    spend_lanes = spend_by_lane(today_only=True)
    starvation = lane_starvation_status()
    decision = latest_scheduler_decision()
    cap = float(spend.get("apify_daily_cap_usd") or spend.get("current_cap_usd") or 0.50)
    spent = float(spend.get("apify_spend_today") or spend.get("facebook_spend_today") or 0)
    run_cap = int(spend.get("facebook_run_cap") or LEVEL1_MAX_RUNS_PER_DAY or 30)
    runs = int(spend.get("facebook_runs_today") or lanes_today.get("total") or 0)
    remaining = round(max(0.0, cap - spent), 4)
    next_run = {
        "lane": decision.get("selected_lane") or "",
        "market": decision.get("selected_market") or "",
        "query": decision.get("selected_query") or "",
        "time": decision.get("created_at") or "",
        "reason": decision.get("reason_selected") or "",
    }
    if not decision.get("launched"):
        next_run["note"] = decision.get("reason_selected") or "waiting for next due target"
    if state != CAP_REACHED:
        peeked = peek_next_planned_run(protect_core=bool((meta or {}).get("protect_core_regions")))
        if peeked.get("lane") or peeked.get("query") or peeked.get("reason"):
            next_run = peeked
    else:
        next_run = {
            "lane": "",
            "market": "",
            "query": "",
            "time": "",
            "reason": cap_reason_label(reason) or "daily cap reached",
        }
    return {
        "scheduler_on": bool(cfg.scheduler_enabled) and bool(cfg.scanner_enabled),
        "scheduler_healthy": True,
        "worker_error": flags.get("last_error") or "",
        "budget_tier": spend.get("current_tier") or "BASE_0.50",
        "budget_tier_label": "$0.50" if "0.50" in str(spend.get("current_tier") or "BASE_0.50") else ("$1" if "1.00" in str(spend.get("current_tier") or "") else "$2"),
        "spend_today": round(spent, 4),
        "daily_cap": cap,
        "remaining_budget": remaining,
        "runs_today": runs,
        "run_cap": run_cap,
        "runs_remaining": max(0, run_cap - runs),
        "cap_state": state,
        "cap_reason": reason if state == CAP_REACHED else "ok",
        "lane_runs_today": {
            "precision": lanes_today.get(LANE_PRECISION, 0),
            "treasure": lanes_today.get(LANE_TREASURE, 0),
            "repair": lanes_today.get(LANE_REPAIR, 0),
            "generic": lanes_today.get(LANE_GENERIC, 0),
            "remote": lanes_today.get(LANE_REMOTE_RESEARCH, 0),
            "total": lanes_today.get("total", 0),
        },
        "spend_by_lane": {
            "precision": spend_lanes.get(LANE_PRECISION, {}).get("usd", 0) if isinstance(spend_lanes.get(LANE_PRECISION), dict) else 0,
            "treasure": spend_lanes.get(LANE_TREASURE, {}).get("usd", 0) if isinstance(spend_lanes.get(LANE_TREASURE), dict) else 0,
            "repair": spend_lanes.get(LANE_REPAIR, {}).get("usd", 0) if isinstance(spend_lanes.get(LANE_REPAIR), dict) else 0,
            "generic": spend_lanes.get(LANE_GENERIC, {}).get("usd", 0) if isinstance(spend_lanes.get(LANE_GENERIC), dict) else 0,
            "remote": spend_lanes.get(LANE_REMOTE_RESEARCH, {}).get("usd", 0) if isinstance(spend_lanes.get(LANE_REMOTE_RESEARCH), dict) else 0,
            "total": spend_lanes.get("total", 0),
            "detail": spend_lanes,
        },
        "starvation": starvation,
        "next_planned_run": next_run,
        "history_24h": list_run_history(hours=24, limit=60),
        "market_performance": market_performance(today_only=True),
        "query_performance": query_performance(),
        "last_decision": decision,
        "estimated_usd_per_run": per_run,
        "identity_recheck": load_identity_recheck(),
    }
