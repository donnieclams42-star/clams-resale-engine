import re
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from dj_deal_project.config import HTTP_TIMEOUT, USER_AGENT, MAX_PRICE, MIN_PRICE
from dj_deal_project.keywords.keyword_engine import get_keywords_for_cycle
from dj_deal_project.utils.logger import log_event
from dj_deal_project.utils.model_parser import is_deal_candidate, normalize_text


HEADERS = {
    "User-Agent": USER_AGENT
}


LOOSE_SIGNAL_WORDS = [
    "cracked",
    "broken",
    "no power",
    "not working",
    "for parts",
    "parts only",
    "untested",
    "as is",
    "locked",
    "icloud",
    "bundle",
    "lot",
    "garage sale",
    "estate sale",
    "moving sale",
    "must sell",
    "need gone",
    "make offer",
    "pickup today",
]


def extract_price(text):
    matches = re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text or "")
    if not matches:
        return None

    prices = []
    for raw in matches:
        try:
            prices.append(float(raw.replace(",", "")))
        except Exception:
            continue

    if not prices:
        return None

    return min(prices)


def _text_has_loose_signal(text: str, keyword: str = "") -> bool:
    text = normalize_text(text)
    keyword = normalize_text(keyword)
    if any(word in text for word in LOOSE_SIGNAL_WORDS):
        return True
    if any(word in keyword for word in LOOSE_SIGNAL_WORDS):
        return True
    return False


def _collect_candidate_text(anchor) -> str:
    pieces = []

    anchor_text = " ".join(anchor.stripped_strings)
    if anchor_text:
        pieces.append(anchor_text)

    parent = getattr(anchor, "parent", None)
    if parent is not None:
        parent_text = " ".join(parent.stripped_strings)
        if parent_text:
            pieces.append(parent_text)

    return normalize_text(" ".join(pieces))


def scan_facebook():
    deals = []
    seen_links = set()

    keywords = get_keywords_for_cycle("facebook")

    for keyword in keywords:
        log_event(f"SCAN facebook keyword={keyword}")
        url = f"https://www.facebook.com/marketplace/search/?query={quote_plus(keyword)}"

        try:
            r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log_event(f"FACEBOOK_SCAN_ERROR keyword={keyword} error={e}")
            continue

        links = soup.find_all("a", href=True)

        for a in links:
            href = a.get("href", "")
            if "/marketplace/item/" not in href:
                continue

            link = href if href.startswith("http") else f"https://www.facebook.com{href}"
            if link in seen_links:
                continue

            text = _collect_candidate_text(a)
            if not text:
                continue

            price = extract_price(text)
            # LOOSENED FILTER (SAFE)
            if price is None:
                # allow no-price listings if strong signal
                if not _text_has_loose_signal(text, keyword):
                    continue
            else:
                # widen price bounds instead of strict cut
                if price < (MIN_PRICE * 0.5) or price > (MAX_PRICE * 1.5):
                    continue

            # loosen candidate requirement
            if not is_deal_candidate(text) and not _text_has_loose_signal(text, keyword):
                # allow weak matches occasionally
                if "lot" not in text and "bundle" not in text:
                    continue

            seen_links.add(link)
            deals.append({
                "title": text,
                "price": price,
                "link": link,
                "url": link,
                "market": "Facebook",
                "source": "Facebook",
                "search_keyword": keyword,
                "candidate_strength": "loose" if _text_has_loose_signal(text, keyword) else "standard",
            })

    log_event(f"FACEBOOK_SCAN_RESULT deals={len(deals)}")
    return deals
