PHONE_MODELS = [
    "iphone 8",
    "iphone x",
    "iphone xr",
    "iphone xs",
    "iphone xs max",
    "iphone 11",
    "iphone 11 pro",
    "iphone 11 pro max",
    "iphone 12",
    "iphone 12 mini",
    "iphone 12 pro",
    "iphone 12 pro max",
    "iphone 13",
    "iphone 13 mini",
    "iphone 13 pro",
    "iphone 13 pro max",
    "iphone 14",
    "iphone 14 plus",
    "iphone 14 pro",
    "iphone 14 pro max",
    "iphone 15",
    "iphone 15 plus",
    "iphone 15 pro",
    "iphone 15 pro max",
    "samsung s20",
    "samsung s21",
    "samsung s22",
    "samsung s23",
    "samsung s24",
]

ACCESSORY_WORDS = [
    "case", "cover", "charger", "charging", "cable", "cord", "adapter", "screen protector",
    "protector", "mount", "holder", "dock", "shell only", "empty box", "box only", "manual only",
    "strap", "band", "stylus", "pen only", "battery only", "tool only", "bag only", "remote only",
    "stand only", "faceplate", "housing", "replacement shell", "replacement part", "lens cap", "tripod",
    "motherboard only", "frame only", "back cover", "tempered glass", "keyboard cover", "joycon shell",
]

PARTIAL_ITEM_PHRASES = [
    "for parts only", "parts only", "charger only", "cable only", "cord only", "case only", "cover only",
    "empty box", "box only", "manual only", "remote only", "dock only", "stand only", "shell only",
    "faceplate only", "no console", "no phone", "no tablet", "no laptop", "no tool", "no unit",
]

EXACT_ACCESSORY_HINTS = [
    "otterbox", "screen protector", "usb c cable", "lightning cable", "power cord", "hdmi cable",
    "charging dock", "replacement battery", "phone case", "tablet case", "controller shell", "joystick cap",
    "tool bag", "carrying case", "battery charger", "wall adapter", "lens cap", "strap",
]

GENERIC_PHONE_WORDS = [
    "phone", "cell phone", "mobile phone", "smartphone", "iphone", "android", "samsung", "pixel",
]

GENERIC_CONSOLE_WORDS = [
    "console", "game system", "video game system", "gaming console", "playstation", "ps5", "ps4", "xbox", "switch", "gamecube", "wii",
]

GENERIC_TOOL_WORDS = [
    "power tool", "tools", "tool lot", "drill", "impact", "dewalt", "milwaukee", "makita", "snap on", "snapon", "tool box", "socket set",
]

GENERIC_CARD_WORDS = [
    "card lot", "sports cards", "pokemon cards", "trading cards", "baseball cards", "basketball cards", "football cards", "hockey cards",
]

GENERIC_ELECTRONICS_WORDS = [
    "electronics lot", "box of electronics", "random electronics", "laptop", "computer", "gpu", "graphics card",
]

LIQUIDATION_WORDS = [
    "garage sale", "estate sale", "moving sale", "yard sale", "storage cleanout", "garage cleanout", "basement cleanout",
    "attic cleanout", "everything must go", "need gone", "must sell", "make offer", "pickup today", "bulk lot", "mixed lot", "bundle",
]

MISSPELLINGS = {
    "iphone": ["iphon", "iphne", "ipone", "iphn"],
    "samsung": ["samsng", "samsun", "samung"],
    "playstation": ["playstaton", "playstion"],
    "switch": ["swich", "swtich"],
    "milwaukee": ["milwakee", "milwaukie", "milwauke"],
    "pokemon": ["pokmon", "pokeman"],
    "estate": ["estste"],
    "moving": ["movng"],
    "garage": ["garag"],
    "xbox": ["xobx"],
    "nintendo": ["nintndo"],
}

FULL_ITEM_SIGNALS = [
    "console", "system", "phone", "tablet", "laptop", "macbook", "ipad", "iphone", "xbox", "ps5", "ps4",
    "switch", "drill", "impact", "tool lot", "tool bundle", "card lot", "collection", "bundle", "lot",
]


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    for correct, mistakes in MISSPELLINGS.items():
        for mistake in mistakes:
            text = text.replace(mistake, correct)
    return " ".join(text.split())


def is_accessory(title: str) -> bool:
    title = normalize_text(title)
    return any(word in title for word in ACCESSORY_WORDS)


def is_accessory_listing(title: str, keyword: str = "") -> bool:
    title_n = normalize_text(title)
    keyword_n = normalize_text(keyword)
    text = f"{title_n} {keyword_n}".strip()

    if any(phrase in title_n for phrase in PARTIAL_ITEM_PHRASES):
        return True

    if any(hint in title_n for hint in EXACT_ACCESSORY_HINTS):
        return True

    accessory_hit = any(word in title_n for word in ACCESSORY_WORDS)
    full_item_hit = any(signal in title_n for signal in FULL_ITEM_SIGNALS)
    if accessory_hit and not full_item_hit:
        return True

    category_intent = detect_category(keyword_n) or detect_category(title_n)
    if category_intent in {"phone", "console", "tool", "electronics"}:
        reject_map = {
            "phone": ["case", "cover", "screen protector", "charger", "cable", "cord", "adapter", "sim tray", "lens protector"],
            "console": ["controller", "remote", "power cord", "hdmi cable", "dock", "stand", "faceplate", "skin"],
            "tool": ["battery only", "charger only", "tool bag", "attachment only", "empty case"],
            "electronics": ["cable", "charger", "adapter", "dock", "stand", "case"],
        }
        if any(term in title_n for term in reject_map.get(category_intent, [])):
            if not any(signal in title_n for signal in ["bundle", "lot", "with console", "with phone", "with tablet", "with charger", "with controller"]):
                return True

    return False


def contains_phone_model(title: str) -> bool:
    title = normalize_text(title)
    if is_accessory_listing(title):
        return False
    return any(model in title for model in PHONE_MODELS)


def detect_category(title: str) -> str | None:
    title = normalize_text(title)
    if any(word in title for word in GENERIC_PHONE_WORDS):
        return "phone"
    if any(word in title for word in GENERIC_CONSOLE_WORDS):
        return "console"
    if any(word in title for word in GENERIC_TOOL_WORDS):
        return "tool"
    if any(word in title for word in GENERIC_CARD_WORDS):
        return "cards"
    if any(word in title for word in GENERIC_ELECTRONICS_WORDS):
        return "electronics"
    return None


def extract_phone_model(title: str) -> str | None:
    title = normalize_text(title)
    if is_accessory_listing(title):
        return None
    for model in PHONE_MODELS:
        if model in title:
            return model
    return None


def has_liquidation_signal(title: str) -> bool:
    title = normalize_text(title)
    return any(word in title for word in LIQUIDATION_WORDS)


def is_deal_candidate(title: str) -> bool:
    title = normalize_text(title)
    if is_accessory_listing(title):
        return False
    return contains_phone_model(title) or detect_category(title) is not None or has_liquidation_signal(title)
