
import requests
import time
import json
import os
import re
from bs4 import BeautifulSoup

CACHE_FILE = "cache/temu_cache.json"
CACHE_SECONDS = 86400

def _read_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) < CACHE_SECONDS:
            return data.get("items", [])
    except:
        return None
    return None

def _write_cache(items):
    os.makedirs("cache", exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "items": items
        }, f)

def clean_title(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def fetch_temu_items():
    cached = _read_cache()
    if cached:
        return cached

    url = "https://www.temu.com"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        items = set()

        for tag in soup.find_all(["a", "span"]):
            text = tag.get_text().strip()

            if len(text) < 10 or len(text) > 80:
                continue

            cleaned = clean_title(text)

            if any(x in cleaned for x in ["free shipping", "download", "app", "sale", "%"]):
                continue

            items.add(cleaned)

            if len(items) >= 40:
                break

        items = list(items)
        _write_cache(items)
        return items

    except Exception as e:
        print("Temu fetch failed:", e)
        return []
