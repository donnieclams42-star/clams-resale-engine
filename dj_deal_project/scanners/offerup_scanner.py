import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
from keywords.keyword_engine import get_keywords_for_cycle
from utils.logger import log_event
from utils.model_parser import is_deal_candidate

HEADERS = {
    "User-Agent": USER_AGENT,
}


def extract_price(text: str) -> float | None:
    match = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", text)
    if not match:
        return None

    try:
        return float(match.group(1).replace(",", ""))
    except Exception:
        return None


def scan_offerup() -> list[dict]:
    deals = []

    keywords = get_keywords_for_cycle("offerup")

    for keyword in keywords:
        log_event(f"SCAN offerup keyword={keyword}")
        url = f"https://offerup.com/search/?q={quote_plus(keyword)}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            log_event(f"ERROR offerup_scan keyword={keyword} error={e}")
            continue

        listing_links = soup.find_all("a", href=True)

        for a_tag in listing_links:
            href = a_tag.get("href", "")
            text = " ".join(a_tag.stripped_strings).lower()
            if not href or not text:
                continue

            price = extract_price(text)
            if price is None:
                continue

            if price < MIN_PRICE or price > MAX_PRICE:
                continue

            if not is_deal_candidate(text):
                continue

            link = href if href.startswith("http") else f"https://offerup.com{href}"

            deals.append(
                {
                    "title": text,
                    "price": price,
                    "link": link,
                    "market": "OfferUp",
                    "search_keyword": keyword,
                }
            )

    log_event(f"OFFERUP_SCAN_RESULT deals={len(deals)}")
    return deals