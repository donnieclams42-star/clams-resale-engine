import re
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT, USER_AGENT, MAX_PRICE, MIN_PRICE
from keywords.keyword_engine import get_keywords_for_cycle
from utils.logger import log_event
from utils.model_parser import is_deal_candidate


HEADERS = {
    "User-Agent": USER_AGENT
}


def extract_price(text):

    match = re.search(r"\$([\d,]+)", text)

    if not match:
        return None

    try:
        return float(match.group(1).replace(",", ""))
    except:
        return None


def scan_facebook():

    deals = []

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

            href = a.get("href","")

            if "/marketplace/item/" not in href:
                continue

            text = " ".join(a.stripped_strings).lower()

            price = extract_price(text)

            if price is None:
                continue

            if price < MIN_PRICE or price > MAX_PRICE:
                continue

            if not is_deal_candidate(text):
                continue

            link = href if href.startswith("http") else f"https://www.facebook.com{href}"

            deals.append({

                "title": text,
                "price": price,
                "link": link,
                "market": "Facebook",
                "search_keyword": keyword

            })

    log_event(f"FACEBOOK_SCAN_RESULT deals={len(deals)}")

    return deals