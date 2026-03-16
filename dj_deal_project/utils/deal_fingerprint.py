import hashlib
import re


def normalize(text):

    text = (text or "").lower()

    text = re.sub(r'[^a-z0-9 ]', '', text)

    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def generate_fingerprint(deal):

    title = normalize(deal.get("title", ""))

    link = normalize(deal.get("link", ""))

    try:
        price = float(deal.get("price", 0))
    except:
        price = 0

    # bucket price slightly so small changes don't create new alerts
    price_bucket = int(price / 10)

    if link:
        raw = f"{link}_{price_bucket}"
    else:
        raw = f"{title}_{price_bucket}"

    return hashlib.md5(raw.encode()).hexdigest()