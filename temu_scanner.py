import requests
import time
import random
import json
import os
import re
from bs4 import BeautifulSoup

CACHE_FILE = "cache/temu_cache.json"
CACHE_SECONDS = 86400

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16 Mobile Safari/605.1",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
]

URLS = [
    "https://www.temu.com",
    "https://www.temu.com/electronics.html",
    "https://www.temu.com/cell-phones-accessories.html",
]

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

def human_delay():
    time.sleep(random.uniform(2.0, 5.0))

def fetch_temu_items():
    cached = _read_cache()
    if cached:
        return cached

    urls = URLS[:]
    random.shuffle(urls)

    items = set()
    max_pages = random.randint(2, 3)

    for i, url in enumerate(urls):
        if i >= max_pages:
            break

        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            for tag in soup.find_all(["a", "span"]):
                text = tag.get_text().strip()

                if len(text) < 12 or len(text) > 80:
                    continue

                cleaned = clean_title(text)

                if any(x in cleaned for x in ["free", "sale", "download", "app", "%"]):
                    continue

                items.add(cleaned)

                if len(items) >= 40:
                    break

            human_delay()

        except Exception as e:
            print("Temu scan error:", e)
            continue

    items = list(items)
    _write_cache(items)

    return items
