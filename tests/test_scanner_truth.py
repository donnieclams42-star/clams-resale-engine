from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dealbrain.alerts import format_discord_deal, should_send_discord
from dealbrain.budget import facebook_run_priority_lanes, qualifies_for_budget_boost
from dealbrain.classify import CLASS_HOT, CLASS_PASS, CLASS_WATCH, classify_deal
from dealbrain.comps import extract_model_query
from dealbrain.identity_gate import (
    FEED_ACTIONABLE,
    FEED_NEEDS_VERIFICATION,
    FEED_REJECTED,
    VERIFY_IDENTITY_ALERT,
    actionable_identity_ok,
    apply_actionable_class_gate,
    discord_alert_kind,
)
from dealbrain.spend import leftover_research_gate
from dj_deal_project.utils.model_parser import detect_category
from marketplace.identity import (
    IDENTITY_ACCESSORY_ONLY,
    IDENTITY_EXACT_CONFIRMED,
    IDENTITY_FALSE_MATCH,
    IDENTITY_FAMILY_ONLY,
    IDENTITY_PARTS_ONLY,
    category_identity_conflict,
    identify_product,
    resolved_identity_query,
)
from marketplace.image_identity import should_analyze_image
from marketplace.ledger import (
    CAP_OK,
    CAP_REACHED,
    LANE_GENERIC,
    LANE_PRECISION,
    LANE_REMOTE_RESEARCH,
    LANE_REPAIR,
    LANE_TREASURE,
    cap_reason_label,
    cap_state_from_meta,
    lane_counts,
    lane_for_target,
    lane_starvation_status,
    latest_scheduler_decision,
    list_run_history,
    market_performance,
    normalize_lane,
    peek_next_planned_run,
    persist_run_ledger,
    query_performance,
    record_scheduler_decision,
    resolve_cost,
    spend_by_lane,
)
from marketplace.models import ScanTarget
from marketplace.planner import planner_tick
from marketplace.store import create_scan_run, enable_phase2_expansion, finish_run, seed_defaults, set_db_path


def _target(**overrides) -> ScanTarget:
    data = dict(
        id="precision-phl-iphone",
        name="Philadelphia · iphone 15 pro",
        enabled=True,
        provider="mock",
        query="iphone 15 pro",
        product_family="iphone-15-pro",
        query_type="EXACT_MODEL",
        market_id="philadelphia",
        location="Philadelphia, PA",
        cadence_tier="PRECISION",
        result_limit=12,
    )
    data.update(overrides)
    return ScanTarget(**data)


class ScannerTruthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        set_db_path(os.path.join(self.tmp.name, "marketplace_scanner.db"))
        seed_defaults("rigelbytes")

    def tearDown(self):
        self.tmp.cleanup()

    def _record_run(self, target: ScanTarget, *, cost: float = 0.016, raw: int = 12, unique: int = 9, dups: int = 3, stage1: int = 3, extra: dict | None = None):
        run_id = create_scan_run(target, stage="discovery", provider="mock")
        payload = {
            "deep_count": 2,
            "identity_verified_count": 1,
            "needs_verification_count": 1,
            "actionable_count": 1,
            "discord_alert_count": 1,
            "cost_usd": cost,
            "cost_kind": "estimated" if cost == 0.016 else "actual",
            "success": True,
            "hot": 1,
            "monster": 0,
        }
        payload.update(extra or {})
        finish_run(
            run_id,
            status="SUCCEEDED",
            raw_row_count=raw,
            unique_count=unique,
            candidate_count=stage1,
            duplicate_count=dups,
            usage_usd=cost,
            extra=payload,
        )
        persist_run_ledger(run_id, {
            "raw_row_count": raw,
            "unique_count": unique,
            "candidate_count": stage1,
            "duplicate_count": dups,
            "usage_usd": cost,
            "status": "SUCCEEDED",
        })
        return run_id

    def test_lane_enum_has_no_unknown_for_production(self):
        self.assertEqual(normalize_lane("PRECISION", "EXACT_MODEL"), LANE_PRECISION)
        self.assertEqual(normalize_lane("TREASURE", "BUNDLE"), LANE_TREASURE)
        self.assertEqual(normalize_lane("REPAIR", "REPAIR"), LANE_REPAIR)
        self.assertEqual(normalize_lane("GENERIC", "GENERIC"), LANE_GENERIC)
        self.assertEqual(normalize_lane("RESEARCH", "RESEARCH", research=True), LANE_REMOTE_RESEARCH)
        self.assertEqual(lane_for_target(_target(cadence_tier="REPAIR", query_type="REPAIR")), LANE_REPAIR)
        with self.assertRaises(ValueError):
            normalize_lane("WEIRD", "WEIRD")

    def test_run_ledger_and_spend_by_lane(self):
        self._record_run(_target())
        self._record_run(_target(id="repair-1", cadence_tier="REPAIR", query_type="REPAIR", query="cracked iphone", market_id="philadelphia"), cost=0.016, raw=12, unique=9, stage1=3)
        self._record_run(_target(id="generic-1", cadence_tier="GENERIC", query_type="GENERIC", query="electronics", market_id="trenton"))
        self._record_run(_target(id="treasure-1", cadence_tier="TREASURE", query_type="BUNDLE", query="nintendo lot", market_id="south-jersey"))
        self._record_run(_target(id="remote-1", cadence_tier="RESEARCH", query_type="RESEARCH", query="remote", market_id="research-nyc"), extra={"cost_kind": "estimated"})
        counts = lane_counts(today_only=True)
        self.assertEqual(counts[LANE_PRECISION], 1)
        self.assertEqual(counts[LANE_REPAIR], 1)
        self.assertEqual(counts[LANE_GENERIC], 1)
        self.assertEqual(counts[LANE_TREASURE], 1)
        self.assertEqual(counts[LANE_REMOTE_RESEARCH], 1)
        self.assertEqual(counts["total"], 5)
        spend = spend_by_lane(today_only=True)
        self.assertAlmostEqual(spend["total"], 0.08, places=3)
        self.assertAlmostEqual(spend[LANE_REPAIR]["usd"], 0.016, places=3)
        history = list_run_history(hours=24)
        self.assertTrue(history)
        self.assertIn(history[0]["lane"], {LANE_PRECISION, LANE_REPAIR, LANE_GENERIC, LANE_TREASURE, LANE_REMOTE_RESEARCH})
        self.assertEqual(resolve_cost(None)[1], "estimated")
        self.assertEqual(resolve_cost(0.021)[1], "actual")

    def test_market_and_query_stats_come_from_runs(self):
        self._record_run(_target(query="cracked iphone", cadence_tier="REPAIR", query_type="REPAIR"), extra={"hot": 2, "monster": 1, "actionable_count": 1})
        self._record_run(_target(id="q2", query="random electronics", cadence_tier="GENERIC", query_type="GENERIC", market_id="newark"), extra={"hot": 0, "actionable_count": 0, "identity_verified_count": 0})
        markets = {row["market_id"]: row for row in market_performance(today_only=True)}
        self.assertGreaterEqual(markets["philadelphia"]["runs"], 1)
        self.assertEqual(markets["philadelphia"]["raw"], 12)
        stats = query_performance()
        top = stats["top_yielding"][0]["query"]
        self.assertEqual(top, "cracked iphone")
        lowest = [row["query"] for row in stats["lowest_yielding"]]
        self.assertIn("random electronics", lowest)

    def test_daily_and_run_caps_stop_paid_launches_but_keep_scheduler_healthy(self):
        from marketplace.config import MarketplaceConfig
        cfg = MarketplaceConfig(
            apify_token="",
            webhook_secret="x",
            primary_provider="mock",
            rigel_actor="x",
            k1ra_actor="x",
            discovery_hot_task_id="",
            discovery_normal_task_id="",
            detail_task_id="",
            fallback_task_id="",
            scanner_enabled=True,
            scheduler_enabled=True,
            provider_rigel_enabled=True,
            provider_k1ra_enabled=True,
            allow_fallback=False,
            public_base_url="https://market-radar.fly.dev",
            max_items_discovery=8,
            max_items_canary=8,
            stage2_max_per_run=0,
            circuit_breaker_failures=3,
            circuit_retry_seconds=60,
            recovery_stale_seconds=1,
            recovery_interval_seconds=1,
            planner_interval_seconds=1,
            jitter_seconds=0,
            seen_duplicate_hours=6,
            default_currency="USD",
            default_country="US",
        )
        with patch("dealbrain.spend.can_start_facebook_run", return_value=(False, "apify_daily_cap", {"spent": 0.50, "cap": 0.50, "runs": 12, "run_cap": 30})):
            out = asyncio.run(planner_tick(cfg))
        self.assertTrue(out.get("skipped"))
        self.assertTrue(out.get("scheduler_healthy"))
        self.assertEqual(out.get("cap_state"), CAP_REACHED)
        decision = latest_scheduler_decision()
        self.assertEqual(decision.get("reason_selected"), "daily cap reached")
        self.assertFalse(decision.get("launched"))
        with patch("dealbrain.spend.can_start_facebook_run", return_value=(False, "facebook_daily_run_cap", {"spent": 0.10, "cap": 0.50, "runs": 30, "run_cap": 30})):
            runs = asyncio.run(planner_tick(cfg))
        self.assertEqual(runs.get("reason"), "facebook_daily_run_cap")
        self.assertTrue(runs.get("scheduler_healthy"))
        self.assertEqual(cap_state_from_meta({"spent": 0.10, "cap": 0.50, "runs": 2, "run_cap": 30}, ok=True), CAP_OK)

    def test_repair_generic_receive_slots_and_remote_is_leftover_only(self):
        lanes = facebook_run_priority_lanes(protect_core=False, runs_today=3)
        self.assertIn("CORE_REPAIR", lanes)
        treasure = facebook_run_priority_lanes(protect_core=False, runs_today=5)
        self.assertIn("LOCAL_TREASURE", treasure)
        ok, reason = leftover_research_gate(runs_today=10, research_runs_today=0, remaining_usd=0.20, local_allotment=30)
        self.assertFalse(ok)
        self.assertEqual(reason, "local_allotment_reserved")
        ok2, reason2 = leftover_research_gate(runs_today=30, research_runs_today=0, remaining_usd=0.005, local_allotment=30)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "no_leftover_budget")
        self.assertEqual(cap_reason_label("no_leftover_budget"), "remote blocked by low remaining budget")

    def test_lane_starvation_status(self):
        enable_phase2_expansion("rigelbytes", enable_repair=True, enable_generic=True, enable_remote=True)
        status = lane_starvation_status()
        self.assertIn(status[LANE_REPAIR]["status"], {"STARVED", "NOT YET ELIGIBLE", "LIVE"})
        self.assertIn(status[LANE_GENERIC]["status"], {"STARVED", "NOT YET ELIGIBLE", "LIVE"})
        self.assertEqual(status[LANE_REMOTE_RESEARCH]["status"], "NOT YET ELIGIBLE")
        self.assertIn("leftover", status[LANE_REMOTE_RESEARCH]["reason"])
        self._record_run(_target(id="repair-now", cadence_tier="REPAIR", query_type="REPAIR", query="cracked iphone"))
        after = lane_starvation_status()
        self.assertEqual(after[LANE_REPAIR]["runs_today"], 1)
        self.assertFalse(after[LANE_REPAIR]["starved"])

    def test_facebook_strict_identity_and_false_positive(self):
        amp = identify_product("Bluetooth Voice Amplifier / two-mic system")
        self.assertEqual(amp["identity_confidence"], IDENTITY_FALSE_MATCH)
        self.assertNotEqual(detect_category("Bluetooth Voice Amplifier / two-mic system"), "phone")
        klass = classify_deal(
            expected_profit=180,
            roi_pct=80,
            confidence="HIGH",
            identity_confidence=amp["identity_confidence"],
            has_sold_comps=True,
            age_hours=1,
        )
        self.assertEqual(klass, CLASS_PASS)
        self.assertEqual(identify_product("case for iPhone 15 Pro")["identity_confidence"], IDENTITY_ACCESSORY_ONLY)
        self.assertEqual(identify_product("screen for Switch OLED")["identity_confidence"], IDENTITY_ACCESSORY_ONLY)
        self.assertIn(identify_product("water block for RTX 4080")["identity_confidence"], {IDENTITY_ACCESSORY_ONLY, IDENTITY_PARTS_ONLY})
        self.assertEqual(identify_product("charger for MacBook Pro")["identity_confidence"], IDENTITY_ACCESSORY_ONLY)
        self.assertEqual(identify_product("controller for PS5")["identity_confidence"], IDENTITY_ACCESSORY_ONLY)
        self.assertEqual(identify_product("iPhone 15 Pro logic board")["identity_confidence"], IDENTITY_PARTS_ONLY)
        self.assertEqual(identify_product("Nintendo Switch empty box")["identity_confidence"], "BOX_ONLY")
        self.assertEqual(identify_product("MacBook")["identity_confidence"], IDENTITY_FAMILY_ONLY)
        self.assertEqual(identify_product("Nintendo Switch OLED")["identity_confidence"], IDENTITY_EXACT_CONFIRMED)

    def test_ebay_strict_identity_and_resolved_comps(self):
        ebay_title = "Case for iPhone 15 Pro Max 256"
        ident = identify_product(ebay_title)
        self.assertEqual(ident["identity_confidence"], IDENTITY_ACCESSORY_ONLY)
        ok, reason = actionable_identity_ok(ident)
        self.assertFalse(ok)
        self.assertEqual(extract_model_query(ebay_title, ident), "")
        confirmed = identify_product("iPhone 15 Pro 256GB unlocked")
        self.assertEqual(confirmed["identity_confidence"], IDENTITY_EXACT_CONFIRMED)
        self.assertEqual(extract_model_query("iPhone 15 Pro 256GB unlocked cheap", confirmed), "iPhone 15 Pro 256GB")
        self.assertEqual(resolved_identity_query({"identity_confidence": "UNKNOWN", "candidate_model": "iPhone 15 Pro"}), "")
        self.assertEqual(extract_model_query("random seller title", {"identity_confidence": "UNKNOWN", "discovery_query": "iphone 15 pro"}), "")

    def test_category_conflict_variant_and_hot_gate(self):
        self.assertTrue(category_identity_conflict("Cell Phones", {"candidate_product_family": ""}))
        self.assertFalse(category_identity_conflict("Cell Phones", {"candidate_product_family": "iphone-15-pro"}))
        family = identify_product("MacBook")
        self.assertEqual(family["identity_confidence"], IDENTITY_FAMILY_ONLY)
        hot = classify_deal(
            expected_profit=100,
            roi_pct=55,
            confidence="HIGH",
            identity_confidence=family["identity_confidence"],
            has_sold_comps=True,
            age_hours=1,
        )
        self.assertNotEqual(hot, CLASS_HOT)
        exact = classify_deal(
            expected_profit=100,
            roi_pct=55,
            confidence="HIGH",
            identity_confidence="EXACT_CONFIRMED",
            has_sold_comps=True,
            age_hours=1,
        )
        self.assertEqual(exact, CLASS_HOT)
        gate = apply_actionable_class_gate("HOT", {"identity_confidence": "AMBIGUOUS"}, expected_profit=250)
        self.assertTrue(gate["verify_identity_alert"])
        self.assertEqual(gate["feed_lane"], FEED_NEEDS_VERIFICATION)
        rejected = apply_actionable_class_gate("HOT", {"identity_confidence": IDENTITY_ACCESSORY_ONLY})
        self.assertEqual(rejected["feed_lane"], FEED_REJECTED)
        ok_gate = apply_actionable_class_gate("HOT", {"identity_confidence": "EXACT_STRONG"})
        self.assertEqual(ok_gate["feed_lane"], FEED_ACTIONABLE)

    def test_budget_boost_and_discord_identity_gates(self):
        ok, reason = qualifies_for_budget_boost({}, {"classification": "HOT", "expected_profit": 180, "identity_confidence": "AMBIGUOUS"})
        self.assertFalse(ok)
        ok2, reason2 = qualifies_for_budget_boost({}, {"classification": "WATCH", "expected_profit": 400, "identity_confidence": "EXACT_CONFIRMED"})
        self.assertFalse(ok2)
        ok3, reason3 = qualifies_for_budget_boost({}, {"classification": "HOT", "expected_profit": 180, "identity_confidence": "EXACT_CONFIRMED", "item_kind": "accessory"})
        self.assertFalse(ok3)
        ok4, _reason4 = qualifies_for_budget_boost({}, {"classification": "HOT", "expected_profit": 180, "identity_confidence": "EXACT_CONFIRMED"})
        self.assertTrue(ok4)
        listing = {
            "id": "verify-1",
            "source": "facebook_marketplace",
            "canonical_url": "https://www.facebook.com/marketplace/item/1/",
            "title": "Bluetooth Voice Amplifier",
        }
        send, alert, skip = should_send_discord(
            listing,
            {
                "classification": CLASS_WATCH,
                "expected_profit": 250,
                "identity_confidence": "AMBIGUOUS",
                "verify_identity_alert": True,
                "feed_lane": "NEEDS_VERIFICATION",
            },
        )
        self.assertTrue(send)
        self.assertEqual(alert, "VERIFY_IDENTITY")
        self.assertEqual(skip, "")
        kind, _ = discord_alert_kind(classification="HOT", identity={"identity_confidence": "AMBIGUOUS"}, expected_profit=250)
        self.assertEqual(kind, VERIFY_IDENTITY_ALERT)
        body = format_discord_deal({**listing, "alert_type": "VERIFY_IDENTITY", "classification": "WATCH", "expected_profit": 250, "asking_price": 40})
        self.assertIn("VERIFY IDENTITY", body)
        self.assertNotIn("HOT DEAL", body)
        blocked = should_send_discord(listing, {"classification": "HOT", "expected_profit": 180, "identity_confidence": "FAMILY_ONLY"})
        self.assertFalse(blocked[0])

    def test_ledger_persisted_at_run_start(self):
        run_id = create_scan_run(_target(), stage="discovery", provider="mock")
        history = {row["run_id"]: row for row in list_run_history(hours=24)}
        self.assertIn(run_id, history)
        self.assertEqual(history[run_id]["lane"], LANE_PRECISION)
        self.assertEqual(history[run_id]["query"], "iphone 15 pro")
        self.assertEqual(history[run_id]["market_id"], "philadelphia")

    def test_next_planned_and_hot_image_gate(self):
        enable_phase2_expansion("rigelbytes", enable_repair=True, enable_generic=True, enable_remote=True)
        peeked = peek_next_planned_run()
        self.assertIn(peeked.get("lane") or "", {"", LANE_PRECISION, LANE_REPAIR, LANE_TREASURE, LANE_GENERIC, LANE_REMOTE_RESEARCH, "PRECISION", "REPAIR", "TREASURE", "GENERIC"})
        self.assertIn("reason", peeked)
        listing = {"title": "iPhone 15 Pro 256GB unlocked", "thumbnail_url": "https://example.com/a.jpg", "asking_price": 220}
        ident = identify_product(listing["title"])
        gate = should_analyze_image(listing, ident, would_hot=True)
        self.assertTrue(gate["should_analyze_image"])
        self.assertIn("hot_or_monster_candidate", gate["reasons"])
        toaster = {"title": "toaster", "asking_price": 12}
        self.assertFalse(should_analyze_image(toaster, identify_product("toaster"), potential_value=12)["should_analyze_image"])

    def test_category_cannot_override_false_match_into_hot(self):
        from dealbrain.pipeline import analyze_listing
        amp = identify_product("Bluetooth Voice Amplifier / two-mic system")
        self.assertEqual(amp["identity_confidence"], IDENTITY_FALSE_MATCH)
        self.assertTrue(category_identity_conflict("Cell Phones", amp))
        verdict = analyze_listing(
            {
                "title": "Bluetooth Voice Amplifier / two-mic system",
                "category": "Cell Phones",
                "source": "facebook_marketplace",
                "asking_price": 35,
                "canonical_url": "https://www.facebook.com/marketplace/item/9/",
            },
            comps_lookup=lambda _query: [],
        )
        self.assertEqual(verdict.get("identity_confidence"), IDENTITY_FALSE_MATCH)
        self.assertNotEqual(str(verdict.get("classification") or "").upper(), "HOT")
        self.assertNotEqual(str(verdict.get("feed_lane") or "").upper(), "ACTIONABLE")


if __name__ == "__main__":
    unittest.main()
