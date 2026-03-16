import os


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# =====================================
# LOGGING
# =====================================

LOG_FILE = os.getenv("LOG_FILE", "radar_log.txt")


# =====================================
# EBAY API
# =====================================

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
EBAY_MARKET = os.getenv("EBAY_MARKET", "EBAY_US")


# =====================================
# WEBHOOKS
# =====================================

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK") or os.getenv("DISCORD_WEBHOOK_URL")


# =====================================
# PRICE FILTERS
# =====================================

MAX_PRICE = int(os.getenv("MAX_PRICE", 300))
MIN_PRICE = int(os.getenv("MIN_PRICE", 20))
MIN_PROFIT = int(os.getenv("MIN_PROFIT", 35))
LOCAL_RESALE_FACTOR = float(os.getenv("LOCAL_RESALE_FACTOR", 0.82))


# =====================================
# SOLD COMPS
# =====================================

SOLD_SEARCH_LIMIT = int(os.getenv("SOLD_SEARCH_LIMIT", 40))


# =====================================
# SCAN / HTTP
# =====================================

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 12))
KEYWORDS_PER_CYCLE = int(os.getenv("KEYWORDS_PER_CYCLE", 18))
ALERT_TOP_N = int(os.getenv("ALERT_TOP_N", 7))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
)

ENABLE_EBAY = env_bool("ENABLE_EBAY", True)
ENABLE_EBAY_AUCTIONS = env_bool("ENABLE_EBAY_AUCTIONS", True)
ENABLE_MERCARI = env_bool("ENABLE_MERCARI", True)
ENABLE_CRAIGSLIST = env_bool("ENABLE_CRAIGSLIST", True)

# OfferUp is left available, but disabled by default because it is riskier.
ENABLE_OFFERUP = env_bool("ENABLE_OFFERUP", False)


# =====================================
# CRAIGSLIST RSS REGIONS
# =====================================

CRAIGSLIST_REGIONS = [
    "southjersey",
    "philadelphia",
    "newyork",
    "jerseyshore",
    "delaware",
    "baltimore",
]


# =====================================
# KEYWORDS
# =====================================

PHONE_TERMS = [
    "iphone",
    "iphone 15",
    "iphone 14",
    "iphone 13",
    "iphone 12",
    "iphone 11",
    "iphone xr",
    "iphone lot",
    "broken iphone",
    "iphone cracked",
    "iphone parts",
    "iphone not working",
    "android phone",
    "samsung galaxy",
    "samsung phone",
    "pixel phone",
    "google pixel",
    "ipad",
    "ipad air",
    "ipad pro",
    "tablet lot",
    "macbook",
    "macbook pro",
    "macbook air",
    "gaming laptop",
]

GAMING_TERMS = [
    "ps5",
    "ps4",
    "playstation",
    "playstaton",
    "ps5 bundle",
    "ps4 bundle",
    "xbox",
    "xbox one",
    "xbox series x",
    "xbox series s",
    "xobx",
    "xbox bundle",
    "nintendo switch",
    "switch bundle",
    "nintndo",
    "gamecube",
    "wii",
    "retro console",
    "video game lot",
    "gaming bundle",
    "controller lot",
]

TOOL_TERMS = [
    "milwaukee",
    "milwauke",
    "dewalt",
    "makita",
    "snap on",
    "snapon",
    "craftsman tools",
    "tool lot",
    "tool bundle",
    "power tools",
    "power tool lot",
    "mechanic tools",
    "impact driver",
    "impact wrench",
    "cordless drill",
    "tool box",
    "rolling toolbox",
    "socket set",
    "air compressor",
]

CARD_TERMS = [
    "pokemon cards",
    "pokemon lot",
    "pokmon",
    "pokeman",
    "sports cards",
    "baseball cards",
    "basketball cards",
    "football cards",
    "card collection",
    "card lot",
    "vintage cards",
    "hockey cards",
    "michael jordan cards",
    "ken griffey jr cards",
    "trading cards",
]

LIQUIDATION_TERMS = [
    "garage sale",
    "garag sale",
    "estate sale",
    "estste sale",
    "moving sale",
    "movng sale",
    "yard sale",
    "storage cleanout",
    "garage cleanout",
    "basement cleanout",
    "attic cleanout",
    "everything must go",
    "need gone",
    "must sell",
    "make offer",
    "pickup today",
    "first come first serve",
    "bulk lot",
    "mixed lot",
    "box of electronics",
    "electronics lot",
    "random electronics",
    "bundle",
    "box of stuff",
]

REPAIR_TERMS = [
    "for parts",
    "not working",
    "doesnt work",
    "broken",
    "cracked screen",
    "needs repair",
    "not tested",
    "as is",
    "repair lot",
]

KEYWORDS = sorted(
    set(
        PHONE_TERMS
        + GAMING_TERMS
        + TOOL_TERMS
        + CARD_TERMS
        + LIQUIDATION_TERMS
        + REPAIR_TERMS
    )
)

SEARCH_TERMS = KEYWORDS
SEARCH_KEYWORDS = KEYWORDS