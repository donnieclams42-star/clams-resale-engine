from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dealbrain.classify import CLASS_HOT, CLASS_MONSTER, CLASS_PASS, CLASS_RISK, CLASS_STRONG, CLASS_WATCH, classify_deal
from dealbrain.config import DealBrainConfig, get_config
from dealbrain.economics import landed_cost, score_economics
from dealbrain.first_profit import (
    VALUATION_BASIS,
    active_haircut_for,
    break_even_resale,
    class_purchase_thresholds,
    conservative_active_exit,
    first_profit_priority,
    in_first_profit_feed,
    margin_of_safety,
    market_stability,
    sample_confidence,
    valuation_error_cushion,
)
from dealbrain.market_clean import filter_comparables, reject_reason
from dealbrain.pipeline import analyze_listing
from dealbrain.spend import can_spend_apify, record_apify_spend
from dealbrain.store import listing_detail, save_own_sale, save_verdict
from dealbrain.valuation.stats import distribution
from marketplace.identity import identify_product
from marketplace.store import set_db_path, upsert_listing


def _cfg(**overrides) -> DealBrainConfig:
    base = get_config()
    data = dict(base.__dict__)
    data.update(overrides)
    return DealBrainConfig(**data)


def _active_listing(title="Nintendo Switch OLED", ask=65.0, source="facebook_marketplace", **extra):
    row = {
        "id": extra.pop("id", "fp1"),
        "title": title,
        "asking_price": ask,
        "source": source,
        "canonical_url": extra.pop("canonical_url", "https://www.facebook.com/marketplace/item/111/"),
        "local_pickup": extra.pop("local_pickup", True),
        "first_seen_at": "2026-09-10T12:00:00+00:00",
        "availability_status": "live",
    }
    row.update(extra)
    return row


def _active_prices(n=24, p25=218.0):
    # Tight market around p25=218, median ~250
    base = [190, 200, 210, 218, 220, 225, 230, 235, 240, 245, 250, 252, 255, 258, 260, 262, 265, 268, 270, 272, 275, 278, 280, 285]
    return [{"title": "Nintendo Switch OLED 64GB", "price": p, "source": "ebay_active"} for p in base[:n]]


class FirstProfitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        set_db_path(os.path.join(self.tmp.name, "marketplace_scanner.db"))
        self.cfg = _cfg(local_pickup_shipping=0, shipping_estimate=12, ebay_fee_rate=0.1325, ebay_fee_fixed=0.40, return_reserve_rate=0.02)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_identity(self):
        self.assertEqual(identify_product("iPhone 15 128GB unlocked")["candidate_model"], "iPhone 15")
        self.assertEqual(identify_product("iPhone 15 Pro 256GB")["candidate_model"], "iPhone 15 Pro")
        self.assertEqual(identify_product("iPhone 15 Pro Max 512GB")["candidate_model"], "iPhone 15 Pro Max")
        self.assertEqual(identify_product("MacBook Air M1")["candidate_model"], "MacBook Air M1")
        self.assertEqual(identify_product("MacBook Air M2")["candidate_model"], "MacBook Air M2")
        self.assertEqual(identify_product("MacBook Air M3")["candidate_model"], "MacBook Air M3")
        self.assertEqual(identify_product("RTX 4070")["candidate_model"], "RTX 4070")
        self.assertEqual(identify_product("RTX 4070 Super")["candidate_model"], "RTX 4070 SUPER")
        self.assertEqual(identify_product("RTX 4070 Ti")["candidate_model"], "RTX 4070 Ti")
        self.assertEqual(identify_product("RTX 4070 Ti Super")["candidate_model"], "RTX 4070 Ti SUPER")
        self.assertEqual(identify_product("Nintendo Switch OLED")["candidate_model"], "Nintendo Switch OLED")
        self.assertEqual(identify_product("OLED switch")["candidate_model"], "Nintendo Switch OLED")
        self.assertEqual(identify_product("Nintendo Switch OLED")["item_kind"], "console")
        self.assertEqual(identify_product("Nintendo Switch OLED carrying case")["item_kind"], "accessory")
        self.assertEqual(identify_product("256GB microSD Nintendo Switch OLED")["item_kind"], "accessory")
        self.assertFalse(identify_product("Nintendo Switch OLED with dock and 256GB microSD")["storage"])
        self.assertEqual(identify_product("Nintendo Switch Lite")["candidate_model"], "Nintendo Switch Lite")
        self.assertEqual(identify_product("Nintendo Switch 2")["candidate_model"], "Nintendo Switch 2")
        self.assertEqual(identify_product("PS5 Pro")["candidate_model"], "PlayStation 5 Pro")
        self.assertEqual(identify_product("PS5 Slim")["candidate_model"], "PlayStation 5 Slim")
        self.assertEqual(identify_product("New Nintendo 3DS XL")["candidate_model"], "New Nintendo 3DS XL")
        self.assertEqual(identify_product("Nintendo 3DS XL")["candidate_model"], "Nintendo 3DS XL")

    def test_wrong_model_and_variant(self):
        ident = identify_product("iPhone 15 Pro 256GB")
        other = identify_product("iPhone 15 Pro Max 256GB")
        self.assertNotEqual(ident["candidate_model"], other["candidate_model"])
        self.assertEqual(reject_reason("iPhone 15 Pro 512GB", target_model="iPhone 15 Pro", target_storage="256GB"), "wrong_storage")
        self.assertIn(reject_reason("Nintendo Switch Lite", target_model="Nintendo Switch OLED", target_family="switch-oled"), {"wrong_generation", "wrong_variant"})

    def test_clean_sample_filtering_and_counts(self):
        items = [
            {"title": "Nintendo Switch OLED", "price": 220},
            {"title": "Nintendo Switch OLED", "price": 230},
            {"title": "Nintendo Switch OLED empty box", "price": 40},
            {"title": "Switch OLED case only", "price": 12},
            {"title": "Nintendo Switch OLED carrying case", "price": 18},
            {"title": "256GB microSD Nintendo Switch OLED", "price": 9.49},
            {"title": "Switch OLED charger only", "price": 8},
            {"title": "Switch OLED for parts", "price": 25},
            {"title": "Switch OLED controller only", "price": 30},
            {"title": "Nintendo Switch OLED screen protector", "price": 7},
            {"title": "Nintendo Switch OLED", "price": 240},
            {"title": "Wanted Switch OLED", "price": 50},
        ]
        ident = identify_product("Nintendo Switch OLED")
        filtered = filter_comparables(items, identity=ident, identify=identify_product)
        self.assertGreaterEqual(filtered["raw_comparable_count"], 9)
        self.assertGreaterEqual(filtered["excluded_comparable_count"], 8)
        self.assertGreaterEqual(filtered["clean_comparable_count"], 3)
        self.assertGreaterEqual(min(filtered["prices"]), 70)
        self.assertTrue(any(row["reason"] in {"empty_box", "junk_title"} for row in filtered["excluded"]))
        self.assertTrue(any(row["reason"] in {"accessory", "accessory_when_console", "implausible_comp_price", "screen_protector"} for row in filtered["excluded"]))

    def test_false_positive_accessories_not_hot(self):
        for title in [
            "Nintendo Switch OLED empty box",
            "Switch OLED case only",
            "Nintendo Switch OLED carrying case",
            "256GB microSD for Nintendo Switch OLED",
            "Switch OLED charger only",
            "GameCube controller only",
            "PS5 for parts not working",
            "iPhone 15 Pro broken repair service",
            "Pokemon Emerald reproduction",
            "Switch OLED $1 deposit",
            "Wanted Nintendo Switch OLED",
        ]:
            reason = reject_reason(title, target_model="Nintendo Switch OLED", target_family="switch-oled", target_kind="console")
            self.assertTrue(reason, msg=title)

    def test_distribution_percentiles_and_outliers(self):
        stats = distribution([270, 300, 340, 350, 355, 360, 365, 370, 5000], [0, 10, 12, 0, 8, 0, 0, 15, 0])
        self.assertLessEqual(stats["p10"], 310)
        self.assertGreaterEqual(stats["p25"], 270)
        self.assertGreaterEqual(stats["median"], 340)
        self.assertLess(stats["p75"], 5000)
        self.assertLess(stats["maximum_non_outlier"], 5000)
        self.assertGreaterEqual(stats["clean_comparable_count"], 8)

    def test_p25_haircut_and_category_override(self):
        self.assertEqual(conservative_active_exit(300, 0.15), 255.0)
        self.assertAlmostEqual(active_haircut_for(family="switch-oled"), 0.15)
        self.assertAlmostEqual(active_haircut_for(family="iphone-15-pro"), 0.20)
        self.assertGreaterEqual(active_haircut_for(repair=True), 0.25)

    def test_sample_confidence_and_stability(self):
        self.assertEqual(sample_confidence(16), "HIGH")
        self.assertEqual(sample_confidence(10), "MEDIUM")
        self.assertEqual(sample_confidence(6), "LOW")
        self.assertEqual(sample_confidence(3), "INSUFFICIENT")
        self.assertEqual(market_stability(300, 340, 365), "HIGH")
        self.assertEqual(market_stability(100, 200, 400), "LOW")

    def test_landed_cost_shipping_and_condition_rule(self):
        self.assertEqual(landed_cost(500, inbound_shipping=0, local_pickup=True), 500)
        self.assertEqual(landed_cost(500, inbound_shipping=15), 515)
        unknown = landed_cost(500, inbound_shipping=None, shipping_unknown=True, unknown_inbound_reserve=12)
        self.assertEqual(unknown, 512)
        pickup = score_economics(asking=500, conservative_resale=800, local_pickup=True, config=self.cfg)
        self.assertEqual(pickup["landed_cost"], 500)
        free = score_economics(asking=95, conservative_resale=246.5, inbound_shipping=0, local_pickup=False, config=self.cfg)
        self.assertEqual(free["inbound_shipping"], 0)

    def test_fees_profit_mos_breakeven_cushion(self):
        math = score_economics(asking=65, conservative_resale=185, local_pickup=True, inbound_shipping=0, extra_costs=7, config=self.cfg)
        self.assertGreater(math["expected_net"], 0)
        self.assertEqual(math["expected_profit"], round(math["expected_net"] - math["landed_cost"], 2))
        mos = margin_of_safety(185, math["landed_cost"])
        self.assertGreater(mos["percent"], 50)
        even = break_even_resale(math["landed_cost"], local_pickup=True, config=self.cfg)
        cushion = valuation_error_cushion(185, even)
        self.assertGreater(cushion["dollars"], 50)
        self.assertEqual(math["break_even_resale"], even)

    def test_hot_monster_active_derived(self):
        hot = classify_deal(
            expected_profit=82, roi_pct=114, confidence="HIGH", identity_confidence="CONFIRMED",
            has_sold_comps=False, valuation_grade="C", verified_exit_basis=VALUATION_BASIS,
            discount_pct=65, age_hours=1, active_derived=True, clean_sample_count=24,
            market_stability="HIGH", direct_link=True, config=self.cfg,
        )
        self.assertEqual(hot, CLASS_HOT)
        monster = classify_deal(
            expected_profit=170, roi_pct=70, confidence="HIGH", identity_confidence="CONFIRMED",
            has_sold_comps=False, valuation_grade="C", verified_exit_basis=VALUATION_BASIS,
            discount_pct=62, age_hours=1, active_derived=True, clean_sample_count=12,
            market_stability="HIGH", direct_link=True, config=self.cfg,
        )
        self.assertEqual(monster, CLASS_MONSTER)

    def test_strong_and_low_sample_and_unstable_downgrade(self):
        low = classify_deal(
            expected_profit=90, roi_pct=80, confidence="MEDIUM", identity_confidence="CONFIRMED",
            has_sold_comps=False, valuation_grade="C", verified_exit_basis=VALUATION_BASIS,
            discount_pct=55, active_derived=True, clean_sample_count=6,
            market_stability="HIGH", direct_link=True, config=self.cfg,
        )
        self.assertEqual(low, CLASS_STRONG)
        unstable = classify_deal(
            expected_profit=90, roi_pct=80, confidence="HIGH", identity_confidence="CONFIRMED",
            has_sold_comps=False, valuation_grade="C", verified_exit_basis=VALUATION_BASIS,
            discount_pct=55, active_derived=True, clean_sample_count=12,
            market_stability="LOW", direct_link=True, config=self.cfg,
        )
        self.assertNotEqual(unstable, CLASS_HOT)

    def test_phone_repair_counterfeit_risk(self):
        phone = classify_deal(
            expected_profit=90, roi_pct=80, confidence="HIGH", identity_confidence="CONFIRMED",
            has_sold_comps=False, phone=True, active_derived=True, clean_sample_count=12,
            market_stability="HIGH", discount_pct=55, direct_link=True, config=self.cfg,
        )
        self.assertIn(phone, {CLASS_HOT, CLASS_STRONG, CLASS_RISK})
        repair = classify_deal(
            expected_profit=200, roi_pct=90, confidence="HIGH", identity_confidence="CONFIRMED",
            has_sold_comps=False, repair=True, active_derived=True, clean_sample_count=12,
            market_stability="HIGH", discount_pct=70, direct_link=True, config=self.cfg,
        )
        self.assertEqual(repair, CLASS_RISK)
        auth = classify_deal(
            expected_profit=200, roi_pct=90, confidence="HIGH", identity_confidence="CONFIRMED",
            has_sold_comps=False, authenticity_risk=True, active_derived=True, clean_sample_count=12,
            market_stability="HIGH", discount_pct=70, direct_link=True, config=self.cfg,
        )
        self.assertEqual(auth, CLASS_RISK)

    def test_bundle_weighting_tiny_profit_and_ranking(self):
        from dealbrain.valuation.consensus import bundle_conservative_value
        bundle = bundle_conservative_value([
            {"status": "CONFIRMED", "value": 100},
            {"status": "PROBABLE", "value": 100},
            {"status": "POSSIBLE", "value": 100},
            {"status": "UNKNOWN", "value": 400},
        ])
        self.assertAlmostEqual(bundle["confirmed"], 100)
        self.assertAlmostEqual(bundle["probable"], 75)
        self.assertEqual(bundle["unknown_components"], 1)
        tiny = {"classification": CLASS_STRONG, "expected_profit": 11, "roi_pct": 220}
        big = {"classification": CLASS_HOT, "expected_profit": 170, "roi_pct": 70, "identity_confidence": "CONFIRMED", "market_sample_confidence": "HIGH", "risk": "MEDIUM"}
        self.assertFalse(in_first_profit_feed(tiny, config=self.cfg))
        self.assertGreater(first_profit_priority(big), first_profit_priority(tiny))

    def test_analyze_switch_oled_fixture(self):
        listing = _active_listing()
        comps = {"comps": _active_prices(), "source": "ebay_active"}
        verdict = analyze_listing(listing, comps_lookup=lambda q: comps, config=self.cfg)
        self.assertFalse(verdict["has_sold_comps"])
        self.assertIn("not sold verified", (verdict.get("valuation_explanation") or "").lower())
        self.assertIn("conservative active market", (verdict.get("valuation_explanation") or "").lower())
        self.assertEqual(verdict["valuation_basis"], VALUATION_BASIS)
        self.assertGreater(verdict["clean_comparable_count"], 8)
        self.assertAlmostEqual(verdict["active_haircut"], 0.15)
        self.assertLess(verdict["conservative_active_exit"], verdict["active_p25"])
        self.assertIn(verdict["classification"], {CLASS_HOT, CLASS_MONSTER, CLASS_STRONG})
        self.assertTrue(verdict["listing_url"].startswith("https://www.facebook.com/marketplace/item/"))
        self.assertGreater(verdict["class_thresholds"]["hot_below"], 0)
        self.assertIn("WHY THIS IS", verdict["why_this_deal"])

    def test_ebay_anomaly_and_extreme_price_not_rejected(self):
        listing = _active_listing(title="Nintendo Switch OLED", ask=95, source="ebay", local_pickup=False, inbound_shipping=0, canonical_url="https://www.ebay.com/itm/123456789012")
        comps = {"comps": _active_prices(), "source": "ebay_active"}
        verdict = analyze_listing(listing, comps_lookup=lambda q: comps, config=self.cfg)
        self.assertTrue(verdict["extreme_anomaly"] or verdict["expected_profit"] > 50)
        self.assertNotEqual(verdict["classification"], CLASS_PASS)

    def test_price_drop_upgrade_dedupe_bought_sold(self):
        listing = _active_listing(id="drop1", ask=140)
        comps = {"comps": _active_prices(), "source": "ebay_active"}
        first = analyze_listing(listing, comps_lookup=lambda q: comps, config=self.cfg)
        save_verdict("drop1", listing, first)
        listing["asking_price"] = 60
        listing["lifecycle_status"] = "PRICE_DROP"
        second = analyze_listing(listing, comps_lookup=lambda q: comps, config=self.cfg)
        save_verdict("drop1", listing, second)
        self.assertGreaterEqual(
            {"WATCH": 1, "STRONG": 2, "HOT": 3, "MONSTER": 4}.get(second["classification"], 0),
            {"WATCH": 1, "STRONG": 2, "HOT": 3, "MONSTER": 4}.get(first["classification"], 0),
        )
        upsert_listing({**listing, "source": "facebook_marketplace", "source_listing_id": "111"}, "run-a")
        upsert_listing({**listing, "source": "facebook_marketplace", "source_listing_id": "111", "asking_price": 60}, "run-b")
        save_own_sale({
            "listing_id": "drop1",
            "canonical_product_id": "Nintendo Switch OLED",
            "exact_model": "Nintendo Switch OLED",
            "purchase_price": 65,
            "purchase_shipping": 0,
            "sale_price": 180,
            "sale_fees": 20,
            "sale_shipping": 12,
            "net_proceeds": 148,
            "profit": 83,
            "predicted_resale": 185,
            "sold_at": "2026-09-10T00:00:00+00:00",
        })
        from dealbrain.store import own_sales_for
        self.assertTrue(own_sales_for("Nintendo Switch OLED"))

    def test_spend_cap_and_admin_defaults(self):
        cfg = _cfg(first_profit_apify_daily_cap_usd=0.25, level1_max_provider_dollars_per_day=3.0)
        self.assertEqual(cfg.apify_daily_cap_usd(), 0.25)
        with patch("dealbrain.spend.get_config", return_value=cfg):
            record_apify_spend(0.30)
            ok, reason, spent = can_spend_apify(0.05)
            self.assertFalse(ok)
            self.assertEqual(reason, "apify_daily_cap")
            self.assertGreaterEqual(spent, 0.25)

    def test_identity_not_strong_cannot_be_monster(self):
        klass = classify_deal(
            expected_profit=200, roi_pct=90, confidence="HIGH", identity_confidence="FAMILY_ONLY",
            has_sold_comps=False, active_derived=True, clean_sample_count=20,
            market_stability="HIGH", discount_pct=70, direct_link=True, config=self.cfg,
        )
        self.assertNotIn(klass, {CLASS_HOT, CLASS_MONSTER})


if __name__ == "__main__":
    unittest.main()
