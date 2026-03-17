
import os

def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1","true","yes","on"}

LOG_FILE = os.getenv("LOG_FILE", "radar_log.txt")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
EBAY_MARKET = os.getenv("EBAY_MARKET", "EBAY_US")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK") or os.getenv("DISCORD_WEBHOOK_URL")

# --- NETWORK SETTINGS ---
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 12))

# --- PRICE FILTERS ---
MAX_PRICE = int(os.getenv("MAX_PRICE", 500))
MIN_PRICE = int(os.getenv("MIN_PRICE", 15))
MIN_PROFIT = int(os.getenv("MIN_PROFIT", 10))
LOCAL_RESALE_FACTOR = float(os.getenv("LOCAL_RESALE_FACTOR", 0.82))

SOLD_SEARCH_LIMIT = int(os.getenv("SOLD_SEARCH_LIMIT", 40))

# --- CRAIGSLIST REGIONS (required by scanner) ---
CRAIGSLIST_REGIONS = [
    "newyork",
    "philadelphia",
    "southjersey",
    "jerseyshore",
    "delaware",
    "baltimore"
]

# --- KEYWORDS ---
KEYWORDS = [
    "iphone","iphone cracked","samsung phone",
    "macbook","macbook pro","ipad","ipad pro",
    "playstation","playstaton","xbox",
    "video game lot","pokemon","pokmon",
    "mechanic tools","tool lot",
    "garage cleanout","moving sale",
    "first come first serve","bulk lot"
]

KEYWORDS_PER_CYCLE = int(os.getenv("KEYWORDS_PER_CYCLE", 18))
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

EBAY_KEYWORDS_PER_CYCLE = int(os.getenv("EBAY_KEYWORDS_PER_CYCLE", 6))
MERCARI_KEYWORDS_PER_CYCLE = int(os.getenv("MERCARI_KEYWORDS_PER_CYCLE", 8))
OFFERUP_KEYWORDS_PER_CYCLE = int(os.getenv("OFFERUP_KEYWORDS_PER_CYCLE", 5))
FACEBOOK_KEYWORDS_PER_CYCLE = int(os.getenv("FACEBOOK_KEYWORDS_PER_CYCLE", 5))

RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE = int(os.getenv("RADAR_MAX_ANALYSIS_CALLS_PER_CYCLE", 6))

RADAR_ANALYSIS_CACHE_SECONDS = int(os.getenv("RADAR_ANALYSIS_CACHE_SECONDS", 21600))
RADAR_MIN_MARGIN = float(os.getenv("RADAR_MIN_MARGIN", 0.15))
SOURCE_FAILURE_COOLDOWN_SECONDS = int(os.getenv("SOURCE_FAILURE_COOLDOWN_SECONDS", 1800))
