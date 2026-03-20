import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

try:
    from dj_deal_project.config import CRAIGSLIST_REGIONS, HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
    from dj_deal_project.keywords.keyword_engine import get_keywords_for_cycle
    from dj_deal_project.utils.logger import log_event
    from dj_deal_project.utils.model_parser import is_deal_candidate
except Exception:
    from config import CRAIGSLIST_REGIONS, HTTP_TIMEOUT, MAX_PRICE, MIN_PRICE, USER_AGENT
    from keywords.keyword_engine import get_keywords_for_cycle
    from utils.logger import log_event
    from utils.model_parser import is_deal_candidate

HEADERS = {"User-Agent": USER_AGENT}


def extract_price(text: str):
    match = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", text or '')
    if not match:
        return None
    try:
        return float(match.group(1).replace(',', ''))
    except Exception:
        return None


def scan_craigslist() -> list[dict]:
    deals = []
    seen_links = set()
    keywords = get_keywords_for_cycle('craigslist')[:6]
    for region in CRAIGSLIST_REGIONS:
        for keyword in keywords:
            log_event(f"CRAIGSLIST_SCAN region={region} keyword={keyword}")
            url = (
                f"https://{region}.craigslist.org/search/sss"
                f"?format=rss&sort=date&query={quote_plus(keyword)}&max_price={MAX_PRICE}"
            )
            try:
                response = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
                response.raise_for_status()
                root = ET.fromstring(response.text)
            except Exception as e:
                log_event(f"CRAIGSLIST_SCAN_ERROR region={region} keyword={keyword} error={e}")
                continue
            channel = root.find('channel')
            if channel is None:
                continue
            for item in channel.findall('item'):
                title = (item.findtext('title') or '').strip().lower()
                link = (item.findtext('link') or '').strip()
                if not link or link in seen_links:
                    continue
                description = (item.findtext('description') or '').strip().lower()
                combined = f"{title} {description}".strip()
                price = extract_price(combined)
                if price is None or price < MIN_PRICE or price > MAX_PRICE:
                    continue
                if not is_deal_candidate(combined):
                    continue
                seen_links.add(link)
                deals.append({
                    'title': title,
                    'price': round(float(price), 2),
                    'link': link,
                    'url': link,
                    'market': f'Craigslist-{region}',
                    'source': 'Craigslist',
                    'search_keyword': keyword,
                })
    log_event(f"CRAIGSLIST_SCAN_RESULT deals={len(deals)}")
    return deals


def run_craigslist_scan():
    return scan_craigslist()
