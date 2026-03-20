
import json
import re
import time
import random
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
from keywords.keyword_engine import get_keywords_for_cycle
from utils.logger import log_event
from utils.model_parser import is_deal_candidate, normalize_text

# --- ROTATING USER AGENTS ---
USER_AGENTS = [
    USER_AGENT,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile Safari/604.1",
]

def build_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

def human_delay():
    t = random.randint(3, 12)
    log_event(f"[MERCARI] sleep {t}s")
    time.sleep(t)

def extract_price(text):
    match = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text or "")
    return float(match.group(1).replace(",", "")) if match else None

def _clean_link(href):
    if not href: return ""
    if href.startswith("http"): return href
    return f"https://www.mercari.com{href}"

def _candidate_ok(title, price):
    if not title or price is None: return False
    if price < MIN_PRICE or price > MAX_PRICE: return False
    return is_deal_candidate(normalize_text(title))

def scan_mercari():
    deals = []
    seen = set()
    keywords = get_keywords_for_cycle("mercari")

    session = requests.Session()

    fail_count = 0

    for keyword in keywords:
        url = f"https://www.mercari.com/search/?keyword={quote_plus(keyword)}"
        log_event(f"SCAN mercari keyword={keyword}")

        try:
            response = session.get(url, headers=build_headers(), timeout=HTTP_TIMEOUT)

            if response.status_code == 403:
                fail_count += 1
                log_event(f"[MERCARI BLOCK] keyword={keyword}")
                time.sleep(10 * fail_count)
                if fail_count >= 3:
                    log_event("[MERCARI COOLDOWN]")
                    break
                continue

            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

        except Exception as e:
            log_event(f"ERROR mercari_scan keyword={keyword} error={e}")
            continue

        items = soup.find_all("a", href=True)

        for a in items:
            href = a.get("href")
            if "/item/" not in href:
                continue

            text = " ".join(a.stripped_strings)
            price = extract_price(text)
            title = normalize_text(text)

            if not _candidate_ok(title, price):
                continue

            link = _clean_link(href)

            if link in seen:
                continue

            seen.add(link)

            deals.append({
                "title": title,
                "price": price,
                "link": link,
                "url": link,
                "market": "Mercari",
                "source": "Mercari",
                "search_keyword": keyword,
            })

        human_delay()

    log_event(f"MERCARI_SCAN_RESULT deals={len(deals)}")
    return deals
