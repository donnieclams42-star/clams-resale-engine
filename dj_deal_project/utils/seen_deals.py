import json
import os

from utils.deal_fingerprint import generate_fingerprint, normalize_link

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
SEEN_FILE = os.path.join(CACHE_DIR, "seen_deals.json")
MAX_MEMORY = 5000

os.makedirs(CACHE_DIR, exist_ok=True)


def load_seen() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {"links": set(), "fingerprints": set()}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"links": set(), "fingerprints": set()}
    return {
        "links": set(data.get("links", [])),
        "fingerprints": set(data.get("fingerprints", [])),
    }


def save_seen(seen: dict) -> None:
    links = list(seen["links"])[-MAX_MEMORY:]
    fingerprints = list(seen["fingerprints"])[-MAX_MEMORY:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"links": links, "fingerprints": fingerprints}, f, indent=2)


def filter_new(deals: list[dict]) -> list[dict]:
    seen = load_seen()
    fresh: list[dict] = []
    cycle_links = set()
    cycle_fingerprints = set()
    cycle_title_keys = set()

    for deal in deals:
        link = normalize_link(str(deal.get("link") or deal.get("url") or "").strip())
        fingerprint = generate_fingerprint(deal)
        title = str(deal.get("title") or "").strip().lower()
        source = str(deal.get("source") or deal.get("market") or "").strip().lower()
        try:
            price = round(float(deal.get("price") or 0), 2)
        except Exception:
            price = 0.0
        title_key = (source, " ".join(title.split()[:12]), round(price / 5.0) * 5)

        if (link and (link in seen["links"] or link in cycle_links)):
            continue
        if fingerprint in seen["fingerprints"] or fingerprint in cycle_fingerprints:
            continue
        if title_key in cycle_title_keys:
            continue

        if link:
            seen["links"].add(link)
            cycle_links.add(link)
        seen["fingerprints"].add(fingerprint)
        cycle_fingerprints.add(fingerprint)
        cycle_title_keys.add(title_key)
        fresh.append(deal)

    save_seen(seen)
    return fresh
