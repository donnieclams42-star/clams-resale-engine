import json
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "temu_cache.json")
CACHE_SECONDS = int(os.getenv("TEMU_CACHE_SECONDS", "86400") or 86400)
TEMU_URL = os.getenv("TEMU_SOURCE_URL", "https://www.temu.com/")
REQUEST_TIMEOUT = int(os.getenv("TEMU_REQUEST_TIMEOUT", "20") or 20)
MAX_ITEMS = int(os.getenv("TEMU_MAX_ITEMS", "24") or 24)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Mobile Safari/537.36",
]

PRICE_RE = re.compile(r"\$(\d{1,4}(?:\.\d{1,2})?)")
BAD_TITLE_TERMS = {
    "download",
    "app",
    "coupon",
    "free shipping on orders",
    "sign in",
    "join now",
    "privacy policy",
}


def _read_cache(allow_stale: bool = False):
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        timestamp = float(data.get("timestamp", 0) or 0)
        items = data.get("items") or []
        if not isinstance(items, list):
            return None
        if allow_stale or (time.time() - timestamp < CACHE_SECONDS):
            return items
    except Exception:
        return None
    return None



def _write_cache(items):
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {"timestamp": time.time(), "items": items}
    tmp_file = f"{CACHE_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, CACHE_FILE)



def _normalize_title(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    text = text.replace("\u200b", "")
    return text.strip(" -|\t\n\r")



def _extract_price(text: str):
    if not text:
        return None
    match = PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        value = float(match.group(1))
    except Exception:
        return None
    if value <= 0 or value > 1000:
        return None
    return round(value, 2)



def _collect_anchor_candidates(soup: BeautifulSoup):
    items = []
    seen = set()
    anchors = soup.find_all("a", href=True)

    for tag in anchors:
        href = (tag.get("href") or "").strip()
        title = _normalize_title(tag.get("title") or tag.get_text(" ", strip=True) or "")
        lower_title = title.lower()

        if not href or not title:
            continue
        if len(title) < 12 or len(title) > 180:
            continue
        if any(term in lower_title for term in BAD_TITLE_TERMS):
            continue
        if not any(ch.isalpha() for ch in title):
            continue

        container_text = _normalize_title(tag.parent.get_text(" ", strip=True) if tag.parent else title)
        combined_text = f"{title} {container_text}".strip()
        price = _extract_price(combined_text)
        if price is None:
            continue

        full_url = urljoin(TEMU_URL, href)
        key = (title.lower(), price)
        if key in seen:
            continue
        seen.add(key)

        items.append(
            {
                "title": title,
                "price": price,
                "url": full_url,
                "source": "temu",
            }
        )

        if len(items) >= MAX_ITEMS:
            break

    return items



def fetch_temu_items(force_refresh: bool = False):
    if not force_refresh:
        cached = _read_cache()
        if cached:
            return cached

    headers = {
        "User-Agent": USER_AGENTS[int(time.time()) % len(USER_AGENTS)],
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    items = []
    try:
        response = requests.get(TEMU_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = _collect_anchor_candidates(soup)
    except Exception as e:
        print("Temu error:", e)

    if items:
        _write_cache(items)
        return items

    cached = _read_cache()
    if cached:
        return cached

    stale_cached = _read_cache(allow_stale=True)
    if stale_cached:
        return stale_cached
    return []
