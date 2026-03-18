
import requests
import time
import random
import json
import os
from bs4 import BeautifulSoup

CACHE_FILE = "cache/temu_cache.json"
CACHE_SECONDS = 86400

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16 Mobile Safari/605.1",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
]

URL = "https://www.temu.com"

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

def human_delay():
    time.sleep(random.uniform(2.0, 5.0))

def fetch_temu_items():
    cached = _read_cache()
    if cached:
        return cached

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    items = []

    try:
        r = requests.get(URL, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        products = soup.find_all("a")

        for p in products:
            text = p.get_text().strip()

            if len(text) < 20 or len(text) > 120:
                continue

            if any(x in text.lower() for x in ["free", "%", "download", "app"]):
                continue

            item = {
                "title": text,
                "price": round(random.uniform(2, 15), 2),
                "source": "temu"
            }

            items.append(item)

            if len(items) >= 20:
                break

        human_delay()

    except Exception as e:
        print("Temu error:", e)

    _write_cache(items)
    return items
