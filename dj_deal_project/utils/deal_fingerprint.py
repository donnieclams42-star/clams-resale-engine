
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
        clean_path = re.sub(r"/+$", "", parts.path or "")
        return urlunsplit((parts.scheme, parts.netloc, clean_path, "", ""))
    except Exception:
        return link.split("?")[0].rstrip("/")


def generate_fingerprint(deal):
    title = normalize(deal.get("title", ""))
    link = normalize_link(deal.get("link") or deal.get("url") or "")
    source = normalize(deal.get("source") or deal.get("market") or "")

    try:
        price = float(deal.get("price", 0))
    except Exception:
        price = 0

    price_bucket = int(price / 10)

    if link:
        raw = f"{source}_{link}_{price_bucket}"
    else:
        raw = f"{source}_{title}_{price_bucket}"

    return hashlib.md5(raw.encode()).hexdigest()
