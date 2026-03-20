
# (same imports as before)
import json, re, time, random
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
from keywords.keyword_engine import get_keywords_for_cycle
from utils.logger import log_event
from utils.model_parser import is_deal_candidate, normalize_text
from market_cache import is_cache_valid, get_cached_results, update_cache

USER_AGENTS = [USER_AGENT]

def build_headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

def human_delay():
    time.sleep(random.randint(4,10))

def extract_price(text):
    import re
    m = re.search(r"\$\s*([\d,]+)", text or "")
    return float(m.group(1).replace(",","")) if m else None

def _clean_link(h):
    if h.startswith("http"): return h
    return f"https://www.mercari.com{h}"

def _candidate_ok(t,p):
    if not t or p is None: return False
    if p < MIN_PRICE or p > MAX_PRICE: return False
    return is_deal_candidate(normalize_text(t))

def scan_mercari():
    if is_cache_valid():
        log_event("[MERCARI CACHE HIT]")
        return get_cached_results("Mercari")

    deals, seen = [], set()
    session = requests.Session()
    keywords = get_keywords_for_cycle("mercari")[:2]

    for keyword in keywords:
        try:
            r = session.get(f"https://www.mercari.com/search/?keyword={quote_plus(keyword)}", headers=build_headers(), timeout=HTTP_TIMEOUT)
            if r.status_code == 403:
                log_event("[MERCARI BLOCK]")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
        except:
            continue

        for a in soup.find_all("a", href=True):
            if "/item/" not in a.get("href"): continue
            text = " ".join(a.stripped_strings)
            price = extract_price(text)
            title = normalize_text(text)
            if not _candidate_ok(title, price): continue
            link = _clean_link(a.get("href"))
            if link in seen: continue
            seen.add(link)
            deals.append({"title":title,"price":price,"link":link,"url":link,"source":"Mercari"})
        human_delay()

    update_cache(deals)
    return deals
