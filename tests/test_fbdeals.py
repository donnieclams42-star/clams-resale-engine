from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fbdeals.alerts import material_price_drop, should_send_sms
from fbdeals.classify import classify_deal
from fbdeals.config import (
    apify_configured,
    twilio_auth_credentials,
    twilio_auth_mode,
    twilio_configured,
    twilio_message_data,
    twilio_sender_mode,
)
from fbdeals.normalize import canonical_listing_url, detect_price_event, normalize_listing
from fbdeals.pipeline import ingest_raw_items, run_watch_scan
from fbdeals.providers.apify import ProviderError
from fbdeals.screen import fast_screen, is_placeholder_price
from fbdeals.store import deal_feed, fetchall, init_db, listing_by_external, record_alert, set_db_path, upsert_watch
from fbdeals.valuation import analyze_deal, summarize_comps


def _sample_raw(**overrides):
    item = {
        "listingId": "958550220194623",
        "url": "https://www.facebook.com/marketplace/item/958550220194623/?ref=search",
        "title": "PS5 Disc Edition",
        "price": "$175",
        "priceAmount": 175.0,
        "currency": "$",
        "imageUrl": "https://example.com/ps5.jpg",
        "imageUrls": ["https://example.com/ps5.jpg"],
        "location": "Atlantic City, NJ",
        "description": "Must go today, pickup today, OBO",
        "condition": "Used - Good",
        "deliveryTypes": ["IN_PERSON"],
        "isSold": False,
        "isPending": False,
        "isLive": True,
        "creationTime": "2026-09-10T09:00:00+00:00",
    }
    item.update(overrides)
    return item


def _sold_comps(prices):
    return [
        {
            "title": "Sony PS5 Disc Edition Console",
            "price": p,
            "url": f"https://ebay.test/{i}",
            "sold_at": "2026-09-01",
            "condition": "Used",
            "match_quality": "exact",
            "source": "ebay_sold",
        }
        for i, p in enumerate(prices)
    ]


class FbDealsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        set_db_path(self.tmp.name)
        init_db()
        self.watch_id = upsert_watch({
            "name": "PS5",
            "query": "PS5",
            "location": "Atlantic City, New Jersey",
            "min_expected_profit": 40,
            "min_roi_pct": 25,
        })
        self.watch = {
            "id": self.watch_id,
            "name": "PS5",
            "query": "PS5",
            "min_expected_profit": 40,
            "min_roi_pct": 25,
            "excluded_terms": "",
            "required_terms": "",
        }

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_normalize_listing_and_facebook_url(self):
        listing = normalize_listing(_sample_raw())
        self.assertEqual(listing["external_listing_id"], "958550220194623")
        self.assertEqual(listing["listing_url"], "https://www.facebook.com/marketplace/item/958550220194623/")
        self.assertEqual(listing["asking_price"], 175.0)
        self.assertIn("facebook.com/marketplace/item/", canonical_listing_url(listing["listing_url"]))

    def test_dedupe_same_listing_id(self):
        comps = lambda q: {"comps": _sold_comps([300, 310, 290, 320, 305, 315, 295, 308, 312, 298, 301, 307])}
        ingest_raw_items([_sample_raw()], watch=self.watch, comps_lookup=comps, send_alerts=False)
        ingest_raw_items([_sample_raw()], watch=self.watch, comps_lookup=comps, send_alerts=False)
        rows = fetchall("SELECT * FROM marketplace_listings")
        self.assertEqual(len(rows), 1)

    def test_price_drop_detection(self):
        self.assertEqual(detect_price_event(None, 175, False), "NEW_LISTING")
        self.assertEqual(detect_price_event(175, 175, True), "ALREADY_SEEN")
        self.assertEqual(detect_price_event(175, 125, True), "PRICE_DROP")
        self.assertEqual(detect_price_event(125, 140, True), "PRICE_INCREASE")
        ingest_raw_items([_sample_raw(priceAmount=175)], watch=self.watch, comps_lookup=lambda q: {"comps": []}, send_alerts=False)
        ingest_raw_items([_sample_raw(priceAmount=125, price="$125")], watch=self.watch, comps_lookup=lambda q: {"comps": []}, send_alerts=False)
        listing = listing_by_external("facebook_marketplace", "958550220194623")
        self.assertEqual(listing["last_event"], "PRICE_DROP")
        self.assertEqual(listing["asking_price"], 125)

    def test_profit_roi_max_buy(self):
        listing = normalize_listing(_sample_raw(priceAmount=80, price="$80"))
        valuation = analyze_deal(
            listing,
            _sold_comps([180, 175, 190, 170, 185, 200, 160, 188, 172, 179, 181, 177]),
            watch=self.watch,
            event_type="NEW_LISTING",
            screen={"placeholder_price": False},
        )
        self.assertGreater(valuation["expected_resale"], 160)
        self.assertGreater(valuation["expected_profit"], 40)
        self.assertGreater(valuation["roi_pct"], 40)
        self.assertGreater(valuation["max_buy_price"], 0)
        self.assertLess(valuation["max_buy_price"], valuation["expected_resale"])
        self.assertIn(valuation["classification"], {"BUY", "HOT"})

    def test_buy_pass_thresholds(self):
        self.assertEqual(classify_deal(expected_profit=90, roi_pct=81, confidence="HIGH", age_hours=0.3), "HOT")
        self.assertEqual(classify_deal(expected_profit=50, roi_pct=30, confidence="MEDIUM", age_hours=12), "BUY")
        self.assertEqual(classify_deal(expected_profit=50, roi_pct=30, confidence="LOW", age_hours=12), "RISK")
        self.assertEqual(classify_deal(expected_profit=25, roi_pct=15, confidence="MEDIUM"), "WATCH")
        self.assertEqual(classify_deal(expected_profit=5, roi_pct=4, confidence="HIGH"), "PASS")

    def test_comp_confidence(self):
        high = summarize_comps(_sold_comps([100, 102, 98, 101, 99, 103, 97, 104, 96, 105, 100, 101]))
        self.assertEqual(high["comp_confidence"], "HIGH")
        self.assertGreaterEqual(high["sold_count"], 10)
        low = summarize_comps(_sold_comps([100, 250]))
        self.assertEqual(low["comp_confidence"], "LOW")
        none = summarize_comps([])
        self.assertEqual(none["comp_confidence"], "NONE")

    def test_sms_dedupe_and_price_drop_realert(self):
        ingest_raw_items(
            [_sample_raw(priceAmount=80, price="$80")],
            watch=self.watch,
            comps_lookup=lambda q: {"comps": _sold_comps([220, 210, 230, 215, 225, 218, 222, 219, 221, 217, 216, 224])},
            send_alerts=False,
        )
        listing_id = int(listing_by_external("facebook_marketplace", "958550220194623")["id"])
        send, alert_type, reason = should_send_sms(listing_id, classification="BUY", price=80)
        self.assertTrue(send)
        record_alert(listing_id, "INSTANT", 80, 65, "BUY")
        send, alert_type, reason = should_send_sms(listing_id, classification="BUY", price=80)
        self.assertFalse(send)
        self.assertEqual(reason, "duplicate_unchanged")
        self.assertTrue(material_price_drop(80, 50))
        send, alert_type, reason = should_send_sms(listing_id, classification="HOT", price=50)
        self.assertTrue(send)
        self.assertIn(alert_type, {"PRICE_DROP", "THRESHOLD_HOT"})

    def test_hot_threshold_transition(self):
        ingest_raw_items([_sample_raw(priceAmount=80, price="$80")], watch=self.watch, comps_lookup=lambda q: {"comps": []}, send_alerts=False)
        listing_id = int(listing_by_external("facebook_marketplace", "958550220194623")["id"])
        record_alert(listing_id, "INSTANT", 80, 50, "BUY")
        send, alert_type, reason = should_send_sms(listing_id, classification="HOT", price=80)
        self.assertTrue(send)
        self.assertEqual(alert_type, "THRESHOLD_HOT")

    def test_provider_failure_handling(self):
        class Boom:
            name = "apify_facebook_marketplace"
            def search(self, watch, enrich=False):
                raise ProviderError("actor_failed", "Actor failed")
        result = run_watch_scan(self.watch, Boom(), send_alerts=False)
        self.assertEqual(result["code"], "actor_failed")
        runs = fetchall("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1")
        self.assertEqual(runs[0]["error_code"], "actor_failed")
        self.assertEqual(runs[0]["status"], "error")

    def test_placeholder_and_fast_screen(self):
        listing = normalize_listing(_sample_raw(priceAmount=1, price="$1", title="PS5 Disc Edition"))
        self.assertTrue(is_placeholder_price(listing))
        rejected = fast_screen(normalize_listing(_sample_raw(title="WTB PS5 looking for")), self.watch)
        self.assertTrue(rejected["reject"])

    def test_below_threshold_does_not_qualify_sms(self):
        ingest_raw_items(
            [_sample_raw(priceAmount=400, price="$400", title="Random HDMI cable")],
            watch=self.watch,
            comps_lookup=lambda q: {"comps": _sold_comps([12, 11, 13])},
            send_alerts=False,
        )
        listing_id = int(listing_by_external("facebook_marketplace", "958550220194623")["id"])
        send, _alert, reason = should_send_sms(listing_id, classification="PASS", price=400)
        self.assertFalse(send)
        self.assertEqual(reason, "below_threshold")

    def test_facebook_link_survives_feed(self):
        ingest_raw_items([_sample_raw()], watch=self.watch, comps_lookup=lambda q: {"comps": _sold_comps([300] * 8)}, send_alerts=False)
        feed = deal_feed({}, limit=10)
        self.assertTrue(feed)
        self.assertTrue(feed[0]["listing_url"].startswith("https://www.facebook.com/marketplace/item/"))

    def test_twilio_prefers_api_key_and_messaging_service(self):
        saved = {
            key: os.environ.get(key)
            for key in (
                "TWILIO_ACCOUNT_SID",
                "TWILIO_AUTH_TOKEN",
                "TWILIO_API_KEY_SID",
                "TWILIO_API_KEY_SECRET",
                "TWILIO_MESSAGING_SERVICE_SID",
                "TWILIO_FROM_NUMBER",
                "TWILIO_PHONE_NUMBER",
                "MARKET_RADAR_ALERT_TO_NUMBER",
            )
        }
        try:
            os.environ["TWILIO_ACCOUNT_SID"] = "ACaccount"
            os.environ["TWILIO_API_KEY_SID"] = "SKkey"
            os.environ["TWILIO_API_KEY_SECRET"] = "api-secret"
            os.environ["TWILIO_AUTH_TOKEN"] = "legacy-token"
            os.environ["TWILIO_MESSAGING_SERVICE_SID"] = "MGservice"
            os.environ["TWILIO_FROM_NUMBER"] = "+15551111111"
            os.environ["MARKET_RADAR_ALERT_TO_NUMBER"] = "+15552222222"
            self.assertEqual(twilio_auth_mode(), "api_key")
            self.assertEqual(twilio_auth_credentials(), ("SKkey", "api-secret"))
            self.assertEqual(twilio_sender_mode(), "messaging_service")
            self.assertTrue(twilio_configured())
            data = twilio_message_data("hello")
            self.assertEqual(data["MessagingServiceSid"], "MGservice")
            self.assertNotIn("From", data)
            self.assertEqual(data["To"], "+15552222222")
            os.environ.pop("TWILIO_API_KEY_SID")
            os.environ.pop("TWILIO_API_KEY_SECRET")
            os.environ.pop("TWILIO_MESSAGING_SERVICE_SID")
            self.assertEqual(twilio_auth_mode(), "auth_token")
            self.assertEqual(twilio_auth_credentials(), ("ACaccount", "legacy-token"))
            self.assertEqual(twilio_sender_mode(), "from_number")
            data = twilio_message_data("hello")
            self.assertEqual(data["From"], "+15551111111")
            os.environ.pop("TWILIO_FROM_NUMBER")
            os.environ["TWILIO_PHONE_NUMBER"] = "+15553333333"
            self.assertEqual(twilio_message_data("hello")["From"], "+15553333333")
            os.environ.pop("MARKET_RADAR_ALERT_TO_NUMBER")
            self.assertFalse(twilio_configured())
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_apify_token_alias(self):
        saved_api = os.environ.get("APIFY_API_TOKEN")
        saved_alias = os.environ.get("APIFY_TOKEN")
        saved_actor = os.environ.get("APIFY_FB_MARKETPLACE_ACTOR")
        try:
            os.environ.pop("APIFY_API_TOKEN", None)
            os.environ["APIFY_TOKEN"] = "alias-token"
            os.environ["APIFY_FB_MARKETPLACE_ACTOR"] = "rigelbytes/facebook-marketplace"
            self.assertTrue(apify_configured())
        finally:
            for key, value in (("APIFY_API_TOKEN", saved_api), ("APIFY_TOKEN", saved_alias), ("APIFY_FB_MARKETPLACE_ACTOR", saved_actor)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
