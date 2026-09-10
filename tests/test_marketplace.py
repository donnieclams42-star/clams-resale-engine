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

from marketplace.fingerprints import classify_lifecycle, hard_key, soft_fingerprint
from marketplace.identity import identify_product
from marketplace.ingest import ingest_dataset, mark_provider_failure
from marketplace.models import ScanTarget
from marketplace.normalize import canonical_facebook_url, extract_listing_id, listing_id_from_url, normalize_provider_item, parse_currency, parse_price
from marketplace.planner import can_start_target, start_canary_runs
from marketplace.providers.mock import MockMarketplaceProvider
from marketplace.providers.k1ra import K1raMarketplaceProvider
from marketplace.providers.rigelbytes import RigelBytesMarketplaceProvider
from marketplace.webhook_auth import event_id, token_from_request_values, verify_webhook_secret
from marketplace.stage1 import evaluate_stage1
from marketplace.store import (
    active_run_for_target,
    create_scan_run,
    get_run,
    listing_by_hard,
    list_feed,
    mark_run_started,
    record_target_failure,
    remember_webhook,
    seed_defaults,
    set_db_path,
    upsert_listing,
)
from marketplace.config import MarketplaceConfig


def _cfg(**overrides) -> MarketplaceConfig:
    base = dict(
        apify_token="",
        webhook_secret="test-secret",
        primary_provider="mock",
        rigel_actor="rigelbytes/facebook-marketplace",
        k1ra_actor="k1ra/facebook-marketplace-scraper",
        discovery_hot_task_id="",
        discovery_normal_task_id="",
        detail_task_id="",
        fallback_task_id="",
        scanner_enabled=True,
        scheduler_enabled=False,
        provider_rigel_enabled=True,
        provider_k1ra_enabled=True,
        allow_fallback=False,
        public_base_url="https://market-radar.fly.dev",
        max_items_discovery=8,
        max_items_canary=8,
        stage2_max_per_run=3,
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
    base.update(overrides)
    return MarketplaceConfig(**base)


def _raw(**overrides):
    item = {
        "listingId": "958550220194623",
        "url": "https://www.facebook.com/marketplace/item/958550220194623/?fbclid=abc&utm_source=x",
        "title": "iPhone 15 Pro 256GB unlocked",
        "price": "$325",
        "priceAmount": 325.0,
        "currency": "USD",
        "imageUrl": "https://example.com/phone.jpg",
        "location": "Philadelphia, PA",
        "category": "Electronics",
        "isSold": False,
        "isPending": False,
        "isLive": True,
        "creationTime": "2026-09-10T09:00:00+00:00",
        "searchQuery": "iphone 15 pro",
    }
    item.update(overrides)
    return item


def _target(**overrides) -> ScanTarget:
    data = dict(
        id="canary-phl-iphone-15-pro",
        name="Philadelphia · iphone 15 pro",
        enabled=True,
        provider="mock",
        query="iphone 15 pro",
        product_family="iphone-15-pro",
        query_type="EXACT_MODEL",
        market_id="philadelphia",
        location="Philadelphia, PA",
        radius_miles=35,
        radius_km=56,
        maximum_price=700,
        is_canary=True,
    )
    data.update(overrides)
    return ScanTarget(**data)


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        set_db_path(os.path.join(self.tmp.name, "marketplace_scanner.db"))
        seed_defaults("rigelbytes")

    def tearDown(self):
        self.tmp.cleanup()

    def test_canonical_url_strips_tracking(self):
        url = canonical_facebook_url("https://www.facebook.com/marketplace/item/958550220194623/?fbclid=abc&utm_source=x")
        self.assertEqual(url, "https://www.facebook.com/marketplace/item/958550220194623/")

    def test_listing_id_extraction(self):
        self.assertEqual(listing_id_from_url("https://www.facebook.com/marketplace/item/958550220194623/?ref=share"), "958550220194623")
        self.assertEqual(extract_listing_id({"id": "not-a-listing", "url": "https://www.facebook.com/marketplace/item/111222333444/"}), "111222333444")

    def test_price_and_currency(self):
        amount, placeholder = parse_price("$1,200")
        self.assertEqual(amount, 1200.0)
        self.assertFalse(placeholder)
        amount, placeholder = parse_price("free")
        self.assertEqual(amount, 0.0)
        self.assertTrue(placeholder)
        amount, placeholder = parse_price({"amount": 1, "currency": "USD", "formatted": "$1"})
        self.assertTrue(placeholder)
        self.assertEqual(parse_currency("€"), "EUR")
        self.assertEqual(parse_currency("USD"), "USD")

    def test_unknown_provider_fields(self):
        listing = normalize_provider_item({"weirdField": True, "title": "iPhone 15 Pro", "listingId": "123456789012", "url": "https://www.facebook.com/marketplace/item/123456789012/"})
        self.assertIsNotNone(listing)
        self.assertEqual(listing["source_listing_id"], "123456789012")
        self.assertIn("weirdField", listing["raw_payload"])

    def test_malformed_record_skipped(self):
        self.assertIsNone(normalize_provider_item({"title": "no id or url"}))

    def test_hard_and_soft_dedupe(self):
        listing = normalize_provider_item(_raw())
        saved, life, is_new = upsert_listing(listing, "run-1")
        self.assertEqual(life, "NEW")
        self.assertTrue(is_new)
        saved2, life2, is_new2 = upsert_listing(listing, "run-2")
        self.assertFalse(is_new2)
        self.assertEqual(life2, "SEEN")
        self.assertEqual(saved["id"], saved2["id"])
        self.assertEqual(hard_key("facebook_marketplace", "958550220194623"), "facebook_marketplace:958550220194623")
        self.assertEqual(
            soft_fingerprint(title="iphone 15 pro", price=325, location="Philadelphia, PA"),
            soft_fingerprint(title="iPhone 15 Pro", price=325, location="Philadelphia, PA"),
        )

    def test_repeat_observation_and_price_events(self):
        listing = normalize_provider_item(_raw())
        upsert_listing(listing, "run-1")
        drop = normalize_provider_item(_raw(priceAmount=250, price="$250"))
        saved, life, _ = upsert_listing(drop, "run-2")
        self.assertEqual(life, "PRICE_DROP")
        bump = normalize_provider_item(_raw(priceAmount=400, price="$400"))
        saved, life, _ = upsert_listing(bump, "run-3")
        self.assertEqual(life, "PRICE_INCREASE")
        row = listing_by_hard("facebook_marketplace", "958550220194623")
        self.assertEqual(row["lifecycle_status"], "PRICE_INCREASE")
        self.assertTrue(row["first_seen_at"])

    def test_placeholder_price(self):
        listing = normalize_provider_item(_raw(price="OBO", priceAmount=1))
        self.assertTrue(listing["price_is_placeholder"])

    def test_stage1_reject_and_candidate(self):
        wanted = evaluate_stage1({"title": "Wanted iPhone 15 Pro", "asking_price": 200, "lifecycle_status": "NEW"}, _target().to_dict())
        self.assertEqual(wanted["stage1_status"], "REJECT")
        rental = evaluate_stage1({"title": "iPhone 15 Pro rent weekly", "asking_price": 40, "lifecycle_status": "NEW"}, _target().to_dict())
        self.assertEqual(rental["stage1_status"], "REJECT")
        case_only = evaluate_stage1({"title": "iPhone 15 Pro case only", "asking_price": 10, "lifecycle_status": "NEW"}, _target().to_dict())
        self.assertEqual(case_only["stage1_status"], "REJECT")
        ceiling = evaluate_stage1({"title": "iPhone 15 Pro Max unlocked", "asking_price": 1200, "lifecycle_status": "NEW"}, _target(maximum_price=700).to_dict())
        self.assertEqual(ceiling["stage1_status"], "REJECT")
        seen = evaluate_stage1({"title": "iPhone 15 Pro", "asking_price": 300, "lifecycle_status": "SEEN"}, _target().to_dict())
        self.assertEqual(seen["stage1_status"], "REJECT")
        hot = evaluate_stage1({"title": "iPhone 15 Pro 256 factory unlocked", "asking_price": 325, "lifecycle_status": "NEW"}, _target().to_dict())
        self.assertEqual(hot["stage1_status"], "CANDIDATE")
        parts = evaluate_stage1({"title": "iPhone 15 Pro for parts untested", "asking_price": 90, "lifecycle_status": "NEW"}, _target().to_dict())
        self.assertNotEqual(parts["stage1_status"], "REJECT")
        placeholder = evaluate_stage1({"title": "iPhone 15 Pro Max", "asking_price": 1, "price_is_placeholder": True, "lifecycle_status": "NEW"}, _target().to_dict())
        self.assertEqual(placeholder["stage1_status"], "CANDIDATE")

    def test_identity_regressions(self):
        self.assertEqual(identify_product("iPhone 15 128GB")["candidate_model"], "iPhone 15")
        self.assertEqual(identify_product("iPhone 15 Pro 256")["candidate_model"], "iPhone 15 Pro")
        self.assertEqual(identify_product("iPhone 15 Pro Max 256")["candidate_model"], "iPhone 15 Pro Max")
        self.assertNotEqual(identify_product("iPhone 15")["candidate_model"], identify_product("iPhone 15 Pro")["candidate_model"])
        self.assertEqual(identify_product("RTX 4070 12GB")["candidate_model"], "RTX 4070")
        self.assertEqual(identify_product("GeForce RTX 4070 SUPER")["candidate_model"], "RTX 4070 SUPER")
        self.assertEqual(identify_product("RTX 4070 Ti Founders")["candidate_model"], "RTX 4070 Ti")
        self.assertNotEqual(identify_product("RTX 4070")["candidate_model"], identify_product("RTX 4070 SUPER")["candidate_model"])
        self.assertEqual(identify_product("Nintendo Switch OLED white")["candidate_model"], "Nintendo Switch OLED")
        self.assertEqual(identify_product("Nintendo Switch Lite")["candidate_model"], "Nintendo Switch Lite")
        self.assertEqual(identify_product("Nintendo Switch console")["identity_confidence"], "FAMILY_ONLY")
        self.assertEqual(identify_product("NES Classic Edition")["candidate_model"], "NES Classic Edition")
        self.assertEqual(identify_product("Original NES console")["candidate_model"], "NES")
        self.assertEqual(identify_product("MacBook Pro 2019 Intel i7")["candidate_model"], "MacBook Intel")
        self.assertEqual(identify_product("MacBook Air M1")["candidate_model"], "MacBook Air M1")
        self.assertEqual(identify_product("MacBook Air M2 2022")["candidate_model"], "MacBook Air M2")
        self.assertEqual(identify_product("MacBook Pro M3")["candidate_model"], "MacBook Pro M3")

    def test_scan_lock(self):
        target = _target()
        run_id = create_scan_run(target, stage="discovery", provider="mock")
        mark_run_started(run_id, apify_run_id="apify-1", status="RUNNING")
        ok, reason = can_start_target(target)
        self.assertFalse(ok)
        self.assertEqual(reason, "run_locked")
        self.assertTrue(active_run_for_target(target.id))

    def test_circuit_breaker(self):
        from marketplace.store import list_targets
        row = list_targets(canary_only=True)[0]
        target_id = row["id"]
        result = {}
        for _ in range(3):
            result = record_target_failure(target_id, breaker=3, retry_seconds=60)
        self.assertTrue(result["paused"])
        self.assertEqual(result["consecutive_failures"], 3)

    def test_webhook_idempotency(self):
        first = remember_webhook("ACTOR.RUN.SUCCEEDED:abc", "ACTOR.RUN.SUCCEEDED", "abc", {"eventType": "ACTOR.RUN.SUCCEEDED"})
        second = remember_webhook("ACTOR.RUN.SUCCEEDED:abc", "ACTOR.RUN.SUCCEEDED", "abc", {"eventType": "ACTOR.RUN.SUCCEEDED"})
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(event_id({"eventType": "ACTOR.RUN.SUCCEEDED"}, "ACTOR.RUN.SUCCEEDED", "abc"), "ACTOR.RUN.SUCCEEDED:abc")

    def test_webhook_secret_required(self):
        token = token_from_request_values("test-secret", "", "")
        self.assertTrue(verify_webhook_secret(token, "test-secret"))
        self.assertFalse(verify_webhook_secret("", "test-secret"))
        self.assertFalse(verify_webhook_secret("test-secret", ""))
        self.assertFalse(verify_webhook_secret("wrong", "test-secret"))

    def test_failed_and_zero_result_runs(self):
        target = _target()
        run_id = create_scan_run(target, stage="discovery", provider="mock")
        mark_provider_failure(run_id, error_code="provider_error", error_message="Marketplace provider error", config=_cfg())
        run = get_run(run_id)
        self.assertEqual(run["status"], "FAILED")
        self.assertEqual(run["error_message"], "Marketplace provider error")

        provider = MockMarketplaceProvider(items=[])
        run_id = create_scan_run(target, stage="discovery", provider="mock")
        started = asyncio.run(provider.start_discovery_run(target))
        mark_run_started(run_id, apify_run_id=started.run_id, dataset_id=started.dataset_id, status="RUNNING")
        summary = asyncio.run(ingest_dataset(run_id=run_id, provider=provider, dataset_id=started.dataset_id, apify_run_id=started.run_id, config=_cfg()))
        self.assertEqual(summary["raw_rows"], 0)
        self.assertEqual(summary["status"], "completed_zero")

    def test_detail_fetch_dedupe_and_ingest(self):
        provider = MockMarketplaceProvider([_raw(), _raw()])
        target = _target()
        run_id = create_scan_run(target, stage="discovery", provider="mock")
        started = asyncio.run(provider.start_discovery_run(target))
        mark_run_started(run_id, apify_run_id=started.run_id, dataset_id=started.dataset_id, status="RUNNING")
        summary = asyncio.run(ingest_dataset(run_id=run_id, provider=provider, dataset_id=started.dataset_id, apify_run_id=started.run_id, config=_cfg(stage2_max_per_run=0)))
        self.assertEqual(summary["unique_rows"], 1)
        self.assertGreaterEqual(summary["candidates"], 1)
        again = asyncio.run(ingest_dataset(run_id=run_id, provider=provider, dataset_id=started.dataset_id, apify_run_id=started.run_id, config=_cfg()))
        self.assertTrue(again.get("duplicate_ingest"))
        feed = list_feed({"stage1": "CANDIDATE"})
        self.assertTrue(all(item["canonical_url"].startswith("https://www.facebook.com/marketplace/item/") for item in feed))

    def test_provider_input_mapping(self):
        rigel = RigelBytesMarketplaceProvider(_cfg())
        payload = rigel.build_discovery_input(_target(provider="rigelbytes"))
        self.assertEqual(payload["searchQueries"], ["iphone 15 pro"])
        self.assertEqual(payload["location"], "Philadelphia, PA")
        self.assertFalse(payload["scrapeListingDetails"])
        k1ra = K1raMarketplaceProvider(_cfg())
        payload = k1ra.build_discovery_input(_target(provider="k1ra"))
        self.assertEqual(payload["searchQueries"], ["iphone 15 pro"])
        self.assertFalse(payload["includeDetails"])
        detail = rigel.build_detail_input([])
        self.assertEqual(detail["startUrls"], [])

    def test_missing_config_state(self):
        cfg = _cfg(apify_token="", primary_provider="rigelbytes")
        self.assertFalse(cfg.apify_configured)
        from marketplace.status import scanner_status
        with patch("marketplace.status.get_config", return_value=cfg):
            status = scanner_status()
            self.assertEqual(status["operational"], "NOT CONFIGURED")
            self.assertEqual(status["message"], "Marketplace Scanner not configured")

    def test_scheduler_enable_flag_stays_off(self):
        saved_enable = os.environ.get("MARKETPLACE_ENABLE_SCHEDULER")
        saved_scanner = os.environ.get("MARKETPLACE_SCANNER_SCHEDULER")
        try:
            os.environ["MARKETPLACE_ENABLE_SCHEDULER"] = "0"
            os.environ["MARKETPLACE_SCANNER_SCHEDULER"] = "1"
            from marketplace.config import get_config
            self.assertFalse(get_config().scheduler_enabled)
            os.environ.pop("MARKETPLACE_ENABLE_SCHEDULER")
            os.environ["MARKETPLACE_SCANNER_SCHEDULER"] = "0"
            self.assertFalse(get_config().scheduler_enabled)
        finally:
            for key, value in (("MARKETPLACE_ENABLE_SCHEDULER", saved_enable), ("MARKETPLACE_SCANNER_SCHEDULER", saved_scanner)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_single_canary_filters_query_and_market(self):
        cfg = _cfg(primary_provider="mock", allow_fallback=True, stage2_max_per_run=2)
        with patch("marketplace.planner.get_provider", return_value=MockMarketplaceProvider()):
            result = asyncio.run(start_canary_runs(
                cfg,
                comparison=True,
                query="iphone 15 pro",
                market_id="philadelphia",
                max_items=5,
                max_starts=1,
                stage2_max=2,
                allow_fallback=False,
            ))
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["started"][0]["query"], "iphone 15 pro")
        self.assertEqual(result["started"][0]["market_id"], "philadelphia")
        self.assertEqual(len(result["started"]), 1)


if __name__ == "__main__":
    unittest.main()
