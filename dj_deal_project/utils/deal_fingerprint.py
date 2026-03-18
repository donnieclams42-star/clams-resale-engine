import hashlib
import re
from urllib.parse import urlsplit, urlunsplit


def normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_link(link: str) -> str:
    link = (link or "").strip().lower()
    if not link:
        return ""
    try:
        parts = urlsplit(link)
        clean_path = re.sub(r"/+$$", "", parts.path or "")
        return urlunsplit((parts.scheme, parts.netloc, clean_path, "", ""))
    except Exception:
        return link.split("?")[0].rstrip("/")


def extract_item_token(link: str) -> str:
    norm = normalize_link(link)
    if not norm:
        return ""
    patterns = [
        r"/itm/(\d+)",
        r"/item/(?:m)?(\d+)",
        r"/listings?/detail/(\d+)",
        r"/detail/(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, norm)
        if m:
            return m.group(1)
    return ""


def generate_fingerprint(deal):
    title = normalize(deal.get("title", ""))
    link = normalize_link(deal.get("link") or deal.get("url") or "")
    source = normalize(deal.get("source") or deal.get("market") or "")
    keyword = normalize(deal.get("search_keyword") or "")
    image = normalize_link(deal.get("image") or deal.get("image_url") or "")
    seller = normalize(deal.get("seller") or "")
    token = extract_item_token(link)

    try:
        price = float(deal.get("price", 0))
    except Exception:
        price = 0

    price_bucket = int(round(price / 5.0))
    title_core = " ".join(title.split()[:10])

    if token:
        raw = f"{source}_{token}_{price_bucket}"
    elif link:
        raw = f"{source}_{link}_{price_bucket}_{seller}"
    else:
        raw = f"{source}_{title_core}_{price_bucket}_{keyword}_{seller}_{image}"

    return hashlib.md5(raw.encode()).hexdigest()
