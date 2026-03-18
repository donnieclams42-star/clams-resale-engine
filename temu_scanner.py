
import json
import os
import random
import time

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "temu_cache.json")
CACHE_SECONDS = 86400

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16 Mobile Safari/605.1",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
]

URL = "https://www.temu.com"


def _read_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - float(data.get("timestamp", 0) or 0) < CACHE_SECONDS:
            items = data.get("items", [])
            if isinstance(items, list) and items:
                return items
    except Exception:
        return None
    return None


def _write_cache(items):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp_path = f"{CACHE_FILE}.tmp"
    payload = {
        "timestamp": time.time(),
        "items": items,
    }
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp_path, CACHE_FILE)


def human_delay():
    time.sleep(random.uniform(2.0, 4.5))


def _clean_title(text: str) -> str:
    text = " ".join((text or "").split()).strip()
    return text


def _is_valid_title(text: str) -> bool:
    lowered = (text or "").lower()
    if len(text) < 20 or len(text) > 120:
        return False
    if any(x in lowered for x in ["free", "%", "download", "app", "login", "sign in"]):
        return False
    return True


def fetch_temu_items():
    cached = _read_cache()
    if cached:
        return cached

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    items = []

    try:
        response = requests.get(URL, headers=headers, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        seen_titles = set()
        for tag in soup.find_all("a"):
            text = _clean_title(tag.get_text())
            if not _is_valid_title(text):
                continue

            key = text.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)

            items.append(
                {
                    "title": text,
                    "price": 0.0,
                    "asking_price": 0.0,
                    "source": "temu",
                    "category": "temu-flip",
                    "category_label": "Temu Candidate",
                    "trend": "WATCH",
                    "confidence": "LOW",
                }
            )

            if len(items) >= 20:
                break

        human_delay()

    except Exception as e:
        print("Temu error:", e)
        fallback = _read_cache()
        if fallback:
            return fallback
        return []

    if items:
        _write_cache(items)
    return items
