import json
import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
from keywords.keyword_engine import get_keywords_for_cycle
from utils.logger import log_event
from utils.model_parser import is_deal_candidate, normalize_text

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def extract_price(text: str) -> float | None:
    match = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except Exception:
        return None


def _safe_price(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def _clean_link(href: str) -> str:
    href = str(href or "").strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://offerup.com{href}"
    return f"https://offerup.com/{href.lstrip('/')}"


def _candidate_ok(title: str, price: float | None) -> bool:
    if not title or price is None:
        return False
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    return is_deal_candidate(normalize_text(title))


def _collect_from_anchors(soup: BeautifulSoup, keyword: str) -> list[dict]:
    results = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if not href or ("/item/" not in href and "/detail/" not in href and "/listings/" not in href):
            continue
        text = " ".join(a_tag.stripped_strings).strip()
        price = extract_price(text)
        title = normalize_text(text)
        if not _candidate_ok(title, price):
            continue
        link = _clean_link(href)
        results.append({
            "title": title,
            "price": price,
            "link": link,
            "url": link,
            "market": "OfferUp",
            "source": "OfferUp",
            "search_keyword": keyword,
        })
    return results


def _collect_from_json_scripts(soup: BeautifulSoup, keyword: str) -> list[dict]:
    results = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text(" ", strip=False) or ""
        if not text or "offerup" not in text.lower():
            continue

        if 'application/ld+json' in str(script.get('type') or ''):
            try:
                payload = json.loads(text)
            except Exception:
                payload = None
            items = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = normalize_text(item.get('name') or '')
                url = _clean_link(item.get('url') or '')
                price = _safe_price(((item.get('offers') or {}).get('price') if isinstance(item.get('offers'), dict) else None))
                if not _candidate_ok(title, price) or not url:
                    continue
                results.append({
                    "title": title,
                    "price": price,
                    "link": url,
                    "url": url,
                    "market": "OfferUp",
                    "source": "OfferUp",
                    "search_keyword": keyword,
                })

        for match in re.finditer(r'"title"\s*:\s*"([^"]{5,180})".*?"price"\s*:\s*"?([\d.]+)"?.*?"(?:url|webUrl|canonicalPath)"\s*:\s*"([^"]+)"', text, re.I | re.S):
            title = normalize_text(match.group(1))
            price = _safe_price(match.group(2))
            url = _clean_link(match.group(3))
            if not _candidate_ok(title, price) or not url:
                continue
            results.append({
                "title": title,
                "price": price,
                "link": url,
                "url": url,
                "market": "OfferUp",
                "source": "OfferUp",
                "search_keyword": keyword,
            })
    return results


def scan_offerup() -> list[dict]:
    deals = []
    seen = set()
    keywords = get_keywords_for_cycle("offerup")

    for keyword in keywords:
        log_event(f"SCAN offerup keyword={keyword}")
        url = f"https://offerup.com/search/?q={quote_plus(keyword)}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            log_event(f"ERROR offerup_scan keyword={keyword} error={e}")
            continue

        parsed = _collect_from_anchors(soup, keyword)
        if not parsed:
            parsed = _collect_from_json_scripts(soup, keyword)

        kept = 0
        for deal in parsed:
            link = str(deal.get("link") or "").strip().lower()
            if not link or link in seen:
                continue
            seen.add(link)
            deals.append(deal)
            kept += 1
        log_event(f"OFFERUP_KEYWORD_RESULT keyword={keyword} deals={kept}")

    log_event(f"OFFERUP_SCAN_RESULT deals={len(deals)}")
    return deals
