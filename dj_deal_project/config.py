import os

try:
    from dj_deal_project.keywords.search_terms import SEARCH_TERMS
except Exception:
    try:
        from keywords.search_terms import SEARCH_TERMS
    except Exception:
        SEARCH_TERMS = []


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        item = str(value or '').strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


LOG_FILE = os.getenv("LOG_FILE", "radar_log.txt")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
EBAY_MARKET = os.getenv("EBAY_MARKET", "EBAY_US")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK") or os.getenv("DISCORD_WEBHOOK_URL")

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 12))

MAX_PRICE = int(os.getenv("MAX_PRICE", 450))
MIN_PRICE = int(os.getenv("MIN_PRICE", 15))
MIN_PROFIT = int(os.getenv("MIN_PROFIT", 15))
LOCAL_RESALE_FACTOR = float(os.getenv("LOCAL_RESALE_FACTOR", 0.82))

SOLD_SEARCH_LIMIT = int(os.getenv("SOLD_SEARCH_LIMIT", 40))

CRAIGSLIST_REGIONS = [
    "newyork",
    "philadelphia",
    "southjersey",
    "jerseyshore",
    "delaware",
    "baltimore",
]

_BASE_KEYWORDS = [
    "iphone", "iphone cracked", "iphone for parts", "broken iphone",
    "samsung phone", "android phone", "pixel phone",
    "macbook", "macbook pro", "ipad", "ipad pro",
    "playstation", "playstaton", "ps5", "ps4", "xbox", "xobx",
    "nintendo switch", "gamecube", "retro console",
    "video game lot", "game lot", "pokemon", "pokmon", "sports cards",
    "mechanic tools", "tool lot", "power tools", "milwaukee", "dewalt",
    "garage cleanout", "moving sale", "estate sale", "first come first serve",
    "bulk lot", "bundle", "need gone", "must sell", "for parts", "not working",
    "electronics lot", "camera lot", "watch lot", "jewelry lot", "lego lot",
]

KEYWORDS = _dedupe_keep_order(list(SEARCH_TERMS) + _BASE_KEYWORDS)

EBAY_KEYWORDS = _dedupe_keep_order([
    kw for kw in KEYWORDS
    if any(token in kw for token in [
        "iphone", "ipad", "macbook", "playstation", "ps5", "ps4", "xbox", "switch",
        "video game", "game", "tool", "pokemon", "cards", "bundle", "lot", "for parts",
        "camera", "watch", "jewelry", "lego", "gpu", "graphics", "laptop", "tablet",
    ])
])

MERCARI_KEYWORDS = _dedupe_keep_order([
    kw for kw in KEYWORDS
    if any(token in kw for token in [
        "iphone", "ipad", "macbook", "playstation", "ps5", "ps4", "xbox", "switch",
        "pokemon", "cards", "bundle", "lot", "for parts", "broken", "cracked",
        "need gone", "must sell", "moving sale", "garage cleanout", "camera", "watch",
        "lego", "speaker", "electronics", "tablet", "laptop",
    ])
])

OFFERUP_KEYWORDS = _dedupe_keep_order([
    kw for kw in KEYWORDS
    if any(token in kw for token in [
        "iphone", "ipad", "macbook", "playstation", "ps5", "ps4", "xbox", "switch",
        "tool", "mechanic", "pokemon", "cards", "bundle", "lot", "need gone",
        "must sell", "moving sale", "garage cleanout", "estate sale", "camera",
        "electronics", "speaker", "generator", "compressor", "watch", "jewelry",
    ])
])

FACEBOOK_KEYWORDS = _dedupe_keep_order([
    kw for kw in KEYWORDS
    if any(token in kw for token in [
        "iphone", "ipad", "macbook", "playstation", "xbox", "switch", "tool", "lot",
        "moving sale", "garage cleanout", "estate sale", "must sell", "need gone",
        "camera", "electronics", "speaker", "generator", "compressor", "jewelry", "watch", "lego",
    ])
])

KEYWORDS_PER_CYCLE = int(os.getenv("KEYWORDS_PER_CYCLE", 24))
DEFAULT_KEYWORDS_PER_CYCLE = KEYWORDS_PER_CYCLE

ALERT_TOP_N = int(os.getenv("ALERT_TOP_N", 7))

ENABLE_EBAY = env_bool("ENABLE_EBAY", True)
ENABLE_EBAY_AUCTIONS = env_bool("ENABLE_EBAY_AUCTIONS", True)
ENABLE_MERCARI = env_bool("ENABLE_MERCARI", True)
ENABLE_CRAIGSLIST = env_bool("ENABLE_CRAIGSLIST", True)
ENABLE_OFFERUP = env_bool("ENABLE_OFFERUP", True)
ENABLE_FACEBOOK = env_bool("ENABLE_FACEBOOK", True)

SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", 180))
FB_SCAN_FREQUENCY = int(os.getenv("FB_SCAN_FREQUENCY", 2))

EBAY_SCAN_FREQUENCY = int(os.getenv("EBAY_SCAN_FREQUENCY", 1))
MERCARI_SCAN_FREQUENCY = int(os.getenv("MERCARI_SCAN_FREQUENCY", 1))
OFFERUP_SCAN_FREQUENCY = int(os.getenv("OFFERUP_SCAN_FREQUENCY", 2))

EBAY_KEYWORDS_PER_CYCLE = int(os.getenv("EBAY_KEYWORDS_PER_CYCLE", 8))
MERCARI_KEYWORDS_PER_CYCLE = int(os.getenv("MERCARI_KEYWORDS_PER_CYCLE", 12))
OFFERUP_KEYWORDS_PER_CYCLE = int(os.getenv("OFFERUP_KEYWORDS_PER_CYCLE", 10))
FACEBOOK_KEYWORDS_PER_CYCLE = int(os.getenv("FACEBOOK_KEYWORDS_PER_CYCLE", 8))

RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE = int(os.getenv("RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE", 8))

RADAR_ANALYSIS_CACHE_SECONDS = int(os.getenv("RADAR_ANALYSIS_CACHE_SECONDS", 21600))
RADAR_MIN_MARGIN = float(os.getenv("RADAR_MIN_MARGIN", 0.10))
SOURCE_FAILURE_COOLDOWN_SECONDS = int(os.getenv("SOURCE_FAILURE_COOLDOWN_SECONDS", 1800))

EBAY_MIN_PROFIT = float(os.getenv("EBAY_MIN_PROFIT", 8))
EBAY_MIN_MARGIN = float(os.getenv("EBAY_MIN_MARGIN", 0.08))
MERCARI_MIN_PROFIT = float(os.getenv("MERCARI_MIN_PROFIT", 8))
MERCARI_MIN_MARGIN = float(os.getenv("MERCARI_MIN_MARGIN", 0.08))
OFFERUP_MIN_PROFIT = float(os.getenv("OFFERUP_MIN_PROFIT", 8))
OFFERUP_MIN_MARGIN = float(os.getenv("OFFERUP_MIN_MARGIN", 0.08))
FB_MIN_PROFIT = float(os.getenv("FB_MIN_PROFIT", 10))
FB_MIN_MARGIN = float(os.getenv("FB_MIN_MARGIN", 0.05))


STRICT_FILTER_MODE = env_bool("STRICT_FILTER_MODE", True)
RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE = int(os.getenv("RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE", 8))
RADAR_ANALYSIS_CACHE_SECONDS = int(os.getenv("RADAR_ANALYSIS_CACHE_SECONDS", 21600))
SOURCE_FAILURE_COOLDOWN_SECONDS = int(os.getenv("SOURCE_FAILURE_COOLDOWN_SECONDS", 1800))
RADAR_MIN_MARGIN = float(os.getenv("RADAR_MIN_MARGIN", 0.12))
FB_MIN_MARGIN = float(os.getenv("FB_MIN_MARGIN", 0.05))
FB_MIN_PROFIT = int(os.getenv("FB_MIN_PROFIT", 10))
EBAY_MIN_MARGIN = float(os.getenv("EBAY_MIN_MARGIN", 0.14))
MERCARI_MIN_MARGIN = float(os.getenv("MERCARI_MIN_MARGIN", 0.12))
OFFERUP_MIN_MARGIN = float(os.getenv("OFFERUP_MIN_MARGIN", 0.10))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", 90))
ENABLE_ADMIN_PANEL = env_bool("ENABLE_ADMIN_PANEL", True)
