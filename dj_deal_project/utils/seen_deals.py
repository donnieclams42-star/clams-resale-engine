import json
import os

from utils.deal_fingerprint import generate_fingerprint

SEEN_FILE = "seen_deals.json"
MAX_MEMORY = 5000


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

    data = {
        "links": links,
        "fingerprints": fingerprints,
    }

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def filter_new(deals: list[dict]) -> list[dict]:
    seen = load_seen()
    fresh: list[dict] = []

    for deal in deals:
        link = str(deal.get("link", "")).strip()
        fingerprint = generate_fingerprint(deal)

        if link and link in seen["links"]:
            continue

        if fingerprint in seen["fingerprints"]:
            continue

        if link:
            seen["links"].add(link)
        seen["fingerprints"].add(fingerprint)

        fresh.append(deal)

    save_seen(seen)
    return fresh