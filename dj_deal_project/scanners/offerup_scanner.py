import json
import re
import time
import random
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

try:
    from dj_deal_project.config import HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
    from dj_deal_project.keywords.keyword_engine import get_keywords_for_cycle
    from dj_deal_project.utils.logger import log_event
    from dj_deal_project.utils.model_parser import is_deal_candidate, normalize_text
    from dj_deal_project.market_cache import is_cache_valid, get_cached_results, update_cache
except Exception:
    from config import HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
    from keywords.keyword_engine import get_keywords_for_cycle
    from utils.logger import log_event
    from utils.model_parser import is_deal_candidate, normalize_text
    from market_cache import is_cache_valid, get_cached_results, update_cache


def build_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://offerup.com/",
    }


def human_delay():
    time.sleep(random.uniform(1.0, 2.0))


def extract_price(text):
    m = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def _clean_link(h):
    if not h:
        return ""
    return h if h.startswith("http") else f"https://offerup.com{h}"


def _candidate_ok(title, price):
    if not title or price is None:
        return False
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    return is_deal_candidate(normalize_text(title))


def scan_offerup():
    cached = get_cached_results("OfferUp") if is_cache_valid() else []
    if cached:
        log_event("[OFFERUP CACHE HIT]")
        return cached

    deals = []
    seen = set()
    session = requests.Session()

    for keyword in get_keywords_for_cycle("offerup")[:6]:
        log_event(f"SCAN offerup keyword={keyword}")
        try:
            r = session.get(f"https://offerup.com/search/?q={quote_plus(keyword)}", headers=build_headers(), timeout=HTTP_TIMEOUT)
            if r.status_code == 403:
                log_event(f"ERROR offerup_scan keyword={keyword} error=403 block")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log_event(f"ERROR offerup_scan keyword={keyword} error={e}")
            continue

        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            if "/item/detail/" not in href and "/item/" not in href:
                continue
            text = " ".join(a.stripped_strings)
            price = extract_price(text)
            title = text.strip()
            link = _clean_link(href)
            if not _candidate_ok(title, price) or link in seen:
                continue
            seen.add(link)
            deals.append({
                "title": title,
                "price": round(float(price), 2),
                "link": link,
                "url": link,
                "market": "OfferUp",
                "source": "OfferUp",
                "search_keyword": keyword,
            })
        human_delay()

    if deals:
        update_cache(deals)
    log_event(f"OFFERUP_SCAN_RESULT deals={len(deals)}")
    return deals


def run_offerup_scan():
    return scan_offerup()
