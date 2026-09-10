from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from ..config import apify_configured, env_str, settings

logger = logging.getLogger("market_radar.marketplace")
APIFY_BASE = "https://api.apify.com/v2"


class ProviderError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class ApifyMarketplaceProvider:
    name = "apify_facebook_marketplace"

    def configured(self) -> bool:
        return apify_configured()

    def actor_id(self) -> str:
        actor = settings().get("apify_actor") or env_str("APIFY_FB_MARKETPLACE_ACTOR", "datascrapers/facebook-marketplace")
        return str(actor).strip().replace("/", "~")

    def task_id(self) -> str:
        return str(settings().get("apify_task_id") or env_str("APIFY_FB_TASK_ID") or "").strip()

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "configured": self.configured(),
            "actor_id": self.actor_id(),
            "task_id": self.task_id(),
        }

    def _token(self) -> str:
        return env_str("APIFY_API_TOKEN") or env_str("APIFY_TOKEN")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def build_input(self, watch: dict[str, Any], enrich: bool = False) -> dict[str, Any]:
        cfg = settings()
        query = str(watch.get("query") or watch.get("name") or "").strip()
        location = str(watch.get("location") or cfg.get("default_location") or "Atlantic City, New Jersey")
        radius = int(watch.get("radius_km") or cfg.get("default_radius_km") or 80)
        max_items = int(watch.get("max_items") or cfg.get("max_items_per_watch") or 12)
        min_price = watch.get("min_price") or 0
        max_price = watch.get("max_price") or 0
        try:
            min_price = float(min_price or 0)
        except Exception:
            min_price = 0.0
        try:
            max_price = float(max_price or 0)
        except Exception:
            max_price = 0.0
        start_query = urlencode({"query": query})
        start_url = f"https://www.facebook.com/marketplace/search/?{start_query}"
        payload: dict[str, Any] = {
            "searchQueries": [query] if query else [],
            "search": query,
            "query": query,
            "location": location,
            "locationQuery": location,
            "city": location,
            "radius": radius,
            "radiusKm": radius,
            "maxItems": max_items,
            "maxPosts": max_items,
            "itemLimit": max_items,
            "scrapeListingDetails": bool(enrich),
            "proxy": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
            },
            "startUrls": [{"url": start_url}],
        }
        if min_price > 0:
            payload["minPrice"] = min_price
            payload["minimumPrice"] = min_price
        if max_price > 0:
            payload["maxPrice"] = max_price
            payload["maximumPrice"] = max_price
        if watch.get("category"):
            payload["category"] = watch.get("category")
        if watch.get("condition") and str(watch.get("condition")).lower() not in {"", "any"}:
            payload["condition"] = watch.get("condition")
        age_days = watch.get("max_listing_age_days")
        if age_days not in (None, "", 0, "0"):
            payload["maxListingAgeDays"] = int(float(age_days))
            payload["itemAge"] = int(float(age_days))
        return payload

    def search(self, watch: dict[str, Any], enrich: bool = False, wait_secs: int = 180) -> dict[str, Any]:
        if not self.configured() or not self._token():
            raise ProviderError("apify_not_configured", "Apify token or Facebook Marketplace actor/task is missing")
        run_input = self.build_input(watch, enrich=enrich)
        task = self.task_id()
        if task:
            url = f"{APIFY_BASE}/actor-tasks/{quote(task, safe='')}/runs"
        else:
            url = f"{APIFY_BASE}/acts/{quote(self.actor_id(), safe='~')}/runs"
        wait = max(5, int(wait_secs or 180))
        logger.info(
            "MARKETPLACE_APIFY_RUN_START actor=%s task=%s wait=%s",
            self.actor_id(),
            "set" if task else "",
            wait,
        )
        if requests is None:
            raise ProviderError("apify_request_failed", "HTTP client unavailable")
        try:
            response = requests.post(
                url,
                headers=self._headers(),
                params={"waitForFinish": wait},
                json=run_input,
                timeout=wait + 30,
            )
        except Exception as exc:
            logger.info("MARKETPLACE_APIFY_REQUEST_FAILED error=%s", type(exc).__name__)
            raise ProviderError("apify_request_failed", "Apify request failed") from exc
        if response.status_code >= 400:
            logger.info("MARKETPLACE_APIFY_HTTP http=%s", response.status_code)
            raise ProviderError("apify_request_failed", f"Apify HTTP {response.status_code}")
        body = response.json() if response.content else {}
        data = body.get("data") or body or {}
        status = str(data.get("status") or "")
        run_id = str(data.get("id") or "")
        dataset_id = str(data.get("defaultDatasetId") or "")
        if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            logger.info("MARKETPLACE_APIFY_ACTOR_FAILED status=%s run_id=%s", status, run_id)
            raise ProviderError("actor_failed", f"Actor ended with status {status}")
        if status in {"READY", "RUNNING"} or not dataset_id:
            logger.info("MARKETPLACE_APIFY_TIMEOUT status=%s run_id=%s", status, run_id)
            raise ProviderError("actor_timeout", "Actor did not finish before wait limit")
        fetched = self.fetch_dataset(dataset_id)
        items = fetched.get("items") or []
        logger.info("MARKETPLACE_APIFY_RUN_DONE run_id=%s items=%s", run_id, len(items))
        return {"items": items, "run_id": run_id, "dataset_id": dataset_id, "status": status}

    def fetch_dataset(self, dataset_id: str) -> dict[str, Any]:
        if not dataset_id:
            raise ProviderError("dataset_unavailable", "No dataset id")
        if not self._token():
            raise ProviderError("apify_not_configured", "Apify token missing")
        if requests is None:
            raise ProviderError("dataset_unavailable", "HTTP client unavailable")
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 250
        try:
            while True:
                response = requests.get(
                    f"{APIFY_BASE}/datasets/{quote(dataset_id, safe='')}/items",
                    headers=self._headers(),
                    params={"clean": "true", "format": "json", "limit": limit, "offset": offset},
                    timeout=45,
                )
                if response.status_code >= 400:
                    logger.info("MARKETPLACE_DATASET_HTTP http=%s", response.status_code)
                    raise ProviderError("dataset_unavailable", f"Dataset HTTP {response.status_code}")
                chunk = response.json()
                if not isinstance(chunk, list) or not chunk:
                    break
                items.extend([row for row in chunk if isinstance(row, dict)])
                if len(chunk) < limit:
                    break
                offset += len(chunk)
        except ProviderError:
            raise
        except Exception as exc:
            logger.info("MARKETPLACE_DATASET_FAILED error=%s", type(exc).__name__)
            raise ProviderError("dataset_unavailable", "Could not read Apify dataset") from exc
        return {"items": items, "dataset_id": dataset_id}

    def __repr__(self) -> str:
        return f"ApifyMarketplaceProvider(actor={self.actor_id()!r})"
