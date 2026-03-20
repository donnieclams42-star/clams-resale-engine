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

USER_AGENTS = [
    USER_AGENT,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
]


def build_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.mercari.com/",
    }


def human_delay():
    time.sleep(random.uniform(1.0, 2.5))


def extract_price(text):
    m = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def _clean_link(h):
    if not h:
        return ""
    return h if h.startswith("http") else f"https://www.mercari.com{h}"


def _candidate_ok(title, price):
    if not title or price is None:
        return False
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    return is_deal_candidate(normalize_text(title))


def _parse_json_state(html):
    deals = []
    patterns = [
        r'"items":\s*(\[[^;]+?\])\s*,\s*"pageState"',
        r'window\.__PRELOADED_STATE__\s*=\s*({.*?})\s*;</script>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.DOTALL):
            chunk = match.group(1)
            try:
                data = json.loads(chunk)
            except Exception:
                continue
            items = data if isinstance(data, list) else []
            for item in items:
                title = str(item.get('name') or item.get('title') or '').strip()
                price = item.get('price') or item.get('displayPrice') or item.get('priceText')
                try:
                    price = float(str(price).replace('$', '').replace(',', ''))
                except Exception:
                    price = None
                link = _clean_link(item.get('url') or item.get('path') or '')
                if title and link:
                    deals.append((title, price, link))
            if deals:
                return deals
    return deals


def scan_mercari():
    cached = get_cached_results("Mercari") if is_cache_valid() else []
    if cached:
        log_event("[MERCARI CACHE HIT]")
        return cached

    deals = []
    seen = set()
    session = requests.Session()
    keywords = get_keywords_for_cycle("mercari")[:8]
    blocked_count = 0

    for keyword in keywords:
        log_event(f"SCAN mercari keyword={keyword}")
        try:
            r = session.get(
                f"https://www.mercari.com/search/?keyword={quote_plus(keyword)}",
                headers=build_headers(),
                timeout=HTTP_TIMEOUT,
            )
            if r.status_code == 403:
                blocked_count += 1
                log_event(f"ERROR mercari_scan keyword={keyword} error=403 block")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log_event(f"ERROR mercari_scan keyword={keyword} error={e}")
            continue

        rows = _parse_json_state(r.text)
        if not rows:
            for a in soup.find_all("a", href=True):
                href = a.get("href") or ""
                if "/item/" not in href:
                    continue
                rows.append((" ".join(a.stripped_strings), extract_price(" ".join(a.stripped_strings)), _clean_link(href)))

        for raw_title, price, link in rows:
            title = normalize_text(raw_title)
            if not _candidate_ok(title, price) or link in seen:
                continue
            seen.add(link)
            deals.append({
                "title": raw_title.strip(),
                "price": round(float(price), 2),
                "link": link,
                "url": link,
                "market": "Mercari",
                "source": "Mercari",
                "search_keyword": keyword,
            })
        human_delay()

    if deals:
        update_cache(deals)
    log_event(f"MERCARI_SCAN_RESULT deals={len(deals)} blocked={blocked_count}")
    return deals


def run_mercari_scan():
    return scan_mercari()
