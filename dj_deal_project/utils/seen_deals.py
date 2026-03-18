import json
import os
import re
import time
from .deal_fingerprint import generate_fingerprint, normalize_link

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
SEEN_FILE = os.path.join(CACHE_DIR, "seen_deals.json")
MAX_MEMORY = 5000
EXPIRY_SECONDS = 2700  # 45 minutes

os.makedirs(CACHE_DIR, exist_ok=True)


def _normalize_title_key(title: str) -> str:
    title = (title or "").lower().strip()
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    title = re.sub(r"\s+", " ", title)
    return " ".join(title.split()[:12]).strip()


def load_seen() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {"links": {}, "fingerprints": {}, "titles": {}}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"links": {}, "fingerprints": {}, "titles": {}}
    return {
        "links": dict(data.get("links", {})),
        "fingerprints": dict(data.get("fingerprints", {})),
        "titles": dict(data.get("titles", {})),
    }


def _prune(seen: dict) -> dict:
    now = time.time()
    for key in ["links", "fingerprints", "titles"]:
        fresh = {}
        for item, ts in dict(seen.get(key, {})).items():
            try:
                item_ts = float(ts)
            except Exception:
                continue
            if now - item_ts <= EXPIRY_SECONDS:
                fresh[item] = item_ts
        if len(fresh) > MAX_MEMORY:
            fresh = dict(sorted(fresh.items(), key=lambda kv: kv[1])[-MAX_MEMORY:])
        seen[key] = fresh
    return seen


def save_seen(seen: dict) -> None:
    seen = _prune(seen)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def clear_seen_cache() -> None:
    payload = {"links": {}, "fingerprints": {}, "titles": {}}
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def filter_new(deals: list[dict]) -> list[dict]:
    seen = load_seen()
    seen = _prune(seen)
    fresh: list[dict] = []
    now = time.time()
    cycle_links = set()
    cycle_fingerprints = set()
    cycle_title_keys = set()

    for deal in deals:
        link = normalize_link(str(deal.get("link") or deal.get("url") or "").strip())
        fingerprint = generate_fingerprint(deal)
        title = str(deal.get("title") or "")
        source = str(deal.get("source") or deal.get("market") or "").strip().lower()
        try:
            price = round(float(deal.get("price") or 0), 2)
        except Exception:
            price = 0.0
        title_key = f"{source}|{_normalize_title_key(title)}|{int(round(price / 10.0))}"

        if link and (link in seen["links"] or link in cycle_links):
            continue
        if fingerprint in seen["fingerprints"] or fingerprint in cycle_fingerprints:
            continue
        if title_key in seen["titles"] or title_key in cycle_title_keys:
            continue

        if link:
            seen["links"][link] = now
            cycle_links.add(link)
        seen["fingerprints"][fingerprint] = now
        seen["titles"][title_key] = now
        cycle_fingerprints.add(fingerprint)
        cycle_title_keys.add(title_key)
        fresh.append(deal)

    save_seen(seen)
    return fresh
