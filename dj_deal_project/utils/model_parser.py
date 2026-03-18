import re

PHONE_MODELS = [
    "iphone 8", "iphone x", "iphone xr", "iphone xs", "iphone xs max",
    "iphone 11", "iphone 11 pro", "iphone 11 pro max",
    "iphone 12", "iphone 12 mini", "iphone 12 pro", "iphone 12 pro max",
    "iphone 13", "iphone 13 mini", "iphone 13 pro", "iphone 13 pro max",
    "iphone 14", "iphone 14 plus", "iphone 14 pro", "iphone 14 pro max",
    "iphone 15", "iphone 15 plus", "iphone 15 pro", "iphone 15 pro max",
    "iphone 16", "iphone 16 pro", "iphone 16 pro max",
    "samsung s20", "samsung s21", "samsung s22", "samsung s23", "samsung s24",
]

MISSPELLINGS = {
    "iphone": ["iphon", "iphne", "ipone", "iphn"],
    "samsung": ["samsng", "samsun", "samung"],
    "playstation": ["playstaton", "playstion"],
    "switch": ["swich", "swtich"],
    "milwaukee": ["milwakee", "milwaukie", "milwauke"],
    "pokemon": ["pokmon", "pokeman"],
    "xbox": ["xobx"],
    "nintendo": ["nintndo"],
}

GENERIC_PHONE_WORDS = ["phone", "cell phone", "mobile phone", "smartphone", "iphone", "android", "samsung", "pixel"]
GENERIC_CONSOLE_WORDS = ["console", "game system", "video game system", "gaming console", "playstation", "ps5", "ps4", "xbox", "switch", "gamecube", "wii"]
GENERIC_TOOL_WORDS = ["power tool", "tools", "tool lot", "drill", "impact", "dewalt", "milwaukee", "makita", "snap on", "snapon", "tool box", "socket set"]
GENERIC_CARD_WORDS = ["card lot", "sports cards", "pokemon cards", "trading cards", "baseball cards", "basketball cards", "football cards", "hockey cards"]
GENERIC_ELECTRONICS_WORDS = ["electronics lot", "box of electronics", "random electronics", "laptop", "computer", "gpu", "graphics card", "tablet", "macbook", "ipad"]

LIQUIDATION_WORDS = [
    "garage sale", "estate sale", "moving sale", "yard sale", "storage cleanout", "garage cleanout",
    "attic cleanout", "everything must go", "need gone", "must sell", "make offer", "pickup today",
    "bulk lot", "mixed lot", "collection",
]

CONSOLE_PLATFORM_WORDS = ["playstation", "ps5", "ps4", "xbox", "xbox one", "xbox series x", "xbox series s", "switch", "nintendo switch", "gamecube", "wii"]
PHONE_PLATFORM_WORDS = ["iphone", "samsung", "galaxy", "pixel", "android", "phone", "smartphone"]
DEVICE_PLATFORM_WORDS = ["macbook", "ipad", "imac", "laptop", "tablet", "pc", "computer", "smart phones", "smartphone"]

PARTIAL_ITEM_PHRASES = [
    "for parts only", "parts only", "charger only", "cable only", "cord only", "case only", "cover only",
    "empty box", "box only", "manual only", "remote only", "dock only", "stand only", "shell only",
    "faceplate only", "no console", "no phone", "no tablet", "no laptop", "no tool", "no unit", "cartridge only",
]

EXACT_ACCESSORY_HINTS = [
    "otterbox", "screen protector", "usb c cable", "lightning cable", "power cord", "hdmi cable",
    "charging dock", "replacement battery", "phone case", "tablet case", "controller shell", "joystick cap",
    "tool bag", "carrying case", "battery charger", "wall adapter", "lens cap", "strap",
]

ACCESSORY_WORDS = [
    "case", "cover", "charger", "charging", "cable", "cord", "adapter", "screen protector",
    "protector", "mount", "holder", "dock", "shell only", "empty box", "box only", "manual only",
    "strap", "band", "stylus", "pen only", "battery only", "tool only", "bag only", "remote only",
    "stand only", "faceplate", "housing", "replacement shell", "replacement part", "lens cap", "tripod",
    "motherboard only", "frame only", "back cover", "tempered glass", "keyboard cover", "joycon shell",
    "dust cover", "skin", "wrap", "shell", "rear cover", "back glass", "camera lens", "lens protector",
    "sim tray", "enclosure", "mouse", "mice", "keyboard", "controller shell", "controller case",
    "manual", "guide", "handbook", "binder", "copy", "book", "textbook", "paperback", "hardcover",
    "key", "code", "digital download", "digital code", "activation code", "earbud", "earbuds", "earphone",
    "earphones", "headphones", "headset", "wireless earphone", "wireless earbuds", "tws", "mono earbud",
    "sticker", "sticker pack", "decal", "decals", "scrapbook", "journaling", "kawaii", "bag", "shirt", "hat", "hoodie",
]

CONSOLE_ACCESSORY_TERMS = [
    "dust cover", "cover", "protector", "shell", "skin", "wrap", "case", "stand", "dock",
    "faceplate", "power cord", "hdmi cable", "adapter", "charger", "controller shell", "controller case", "bag",
]

CONSOLE_GAME_TERMS = [
    "game", "game only", "disc", "disc only", "software", "ntsc", "cib", "complete in box",
    "e10", "teen", "mature", "ea sports", "warner bros", "ubisoft", "activision", "capcom", "cartridge", "game card",
    "edition", "collector", "collector s edition", "collectors edition", "deluxe", "ultimate edition", "special edition",
    "key", "code", "digital", "download", "region", "redeem", "activation", "sealed", "us ver", "ver ",
    "sonic frontiers", "lego star wars", "skywalker saga", "ufc 4", "ultimate fighting championship",
    "psychonauts", "motherlobe edition", "need for speed", "unbound", "palace edition",
    "oddworld", "abe s oddysee", "abe s exoddus", "kingdom hearts", "tiny tina", "wonderlands", "john wick hex",
    "fortnite", "final fantasy",
]

PHONE_PART_TERMS = [
    "back glass", "rear cover", "replacement", "housing", "battery cover", "frame", "lens",
    "camera lens", "part", "parts", "for iphone", "back cover", "sim tray", "enclosure",
]

DEVICE_ACCESSORY_TERMS = [
    "mouse", "mice", "keyboard", "bluetooth mouse", "wireless mouse", "accessory", "headset", "headphones",
    "earbuds", "earphones", "for macbook", "for ipad", "for laptop", "adapter", "charger", "case", "cover",
    "power adapter", "ac power adapter", "ac adapter", "blue tip", "charger lot", "lot of", "smart phones",
]

DOCUMENT_TERMS = ["manual", "owner s manual", "owners manual", "instruction manual", "guide", "handbook", "binder", "copy"]
BOOK_TERMS = ["book", "textbook", "paperback", "hardcover", "isbn", "study guide", " by ", "author "]
SOFTWARE_PATTERN_TERMS = ["edition", "bundle", "code", "key", "digital", "download", "pc game", "computer game", "free ship", "sealed", "cartridge"]
HARDWARE_TERMS = [
    "console", "system", "bundle with console", "tablet", "phone", "laptop", "macbook", "ipad", "controller",
    "tested working", "working", "works", "w controller", "with controller", "with cords", "with hookups",
]
SAFE_BUNDLE_PHRASES = ["with console", "with phone", "with tablet", "with laptop", "with macbook", "with ipad"]
AUTO_PART_TERMS = [
    "toyota", "honda", "ford", "chevy", "gmc", "cadet", "husqvarna", "tacoma", "door jamb", "interior light",
    "climate control", "air switch", "switch", "interlock", "sensor", "plunger", "knob", "for 2005", "for 2011", "for 20",
]
LOW_VALUE_BULK_JUNK = [
    "2pack", "2 pack", "3pcs", "3 pcs", "10pcs", "10 pcs", "200pcs", "200 pcs", "pack lot", "sticker pack",
]


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    for correct, mistakes in MISSPELLINGS.items():
        for mistake in mistakes:
            text = text.replace(mistake, correct)
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return f" {' '.join(text.split())} "


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(f" {term} " in text or term in text for term in terms)


def _looks_like_full_bundle(title_n: str) -> bool:
    if _contains_any(title_n, SAFE_BUNDLE_PHRASES):
        return True
    if " bundle " in title_n and any(word in title_n for word in [" console ", " phone ", " laptop ", " tablet ", " system "]):
        return True
    return False


def _has_hardware_signal(title_n: str) -> bool:
    return _contains_any(title_n, HARDWARE_TERMS)


def _looks_like_named_software(title_n: str) -> bool:
    if not _contains_any(title_n, CONSOLE_PLATFORM_WORDS + DEVICE_PLATFORM_WORDS):
        return False
    if _has_hardware_signal(title_n):
        return False
    if _contains_any(title_n, CONSOLE_GAME_TERMS):
        return True
    has_numeric_sequel = bool(re.search(r" [a-z]{3,} \d+(?:\.\d+)? ", title_n))
    has_edition_language = _contains_any(title_n, SOFTWARE_PATTERN_TERMS)
    if has_numeric_sequel and has_edition_language:
        return True
    if " pc " in title_n and (" bundle " in title_n or " lot " in title_n):
        return True
    return False


def _is_console_accessory_or_game(title_n: str) -> bool:
    if not _contains_any(title_n, CONSOLE_PLATFORM_WORDS):
        return False
    if _contains_any(title_n, ["key", "code", "digital", "download", "activation", "redeem", "region"]):
        return True
    if _contains_any(title_n, CONSOLE_ACCESSORY_TERMS):
        if not _looks_like_full_bundle(title_n):
            return True
    if _contains_any(title_n, CONSOLE_GAME_TERMS) or _looks_like_named_software(title_n):
        if not _has_hardware_signal(title_n) and not _looks_like_full_bundle(title_n):
            return True
    return False


def _is_phone_part_listing(title_n: str) -> bool:
    has_platform = _contains_any(title_n, PHONE_PLATFORM_WORDS) or any(f" {model} " in title_n for model in PHONE_MODELS)
    if not has_platform:
        return False
    if _contains_any(title_n, PHONE_PART_TERMS):
        if " unlocked " not in title_n and " works " not in title_n and " working " not in title_n and not _looks_like_full_bundle(title_n):
            return True
    return False


def _is_device_accessory_listing(title_n: str) -> bool:
    if not _contains_any(title_n, DEVICE_PLATFORM_WORDS):
        return False
    if _contains_any(title_n, DEVICE_ACCESSORY_TERMS):
        if not _looks_like_full_bundle(title_n):
            return True
    return False


def _is_document_or_book_listing(title_n: str) -> bool:
    if _contains_any(title_n, DOCUMENT_TERMS):
        return True
    if _contains_any(title_n, BOOK_TERMS) and not _has_hardware_signal(title_n):
        return True
    if (" bundle " in title_n or " volume " in title_n or " set " in title_n) and (" by " in title_n or " author " in title_n):
        if not _has_hardware_signal(title_n):
            return True
    if any(term in title_n for term in ["network security", "firewalls", "vpns"]):
        if not _has_hardware_signal(title_n):
            return True
    return False


def _is_auto_part_listing(title_n: str) -> bool:
    return _contains_any(title_n, AUTO_PART_TERMS)


def _is_low_value_junk(title_n: str) -> bool:
    return _contains_any(title_n, LOW_VALUE_BULK_JUNK)


def is_accessory(title: str) -> bool:
    title_n = normalize_text(title)
    return (
        any(word in title_n for word in ACCESSORY_WORDS)
        or _is_console_accessory_or_game(title_n)
        or _is_phone_part_listing(title_n)
        or _is_device_accessory_listing(title_n)
        or _is_document_or_book_listing(title_n)
        or _is_auto_part_listing(title_n)
        or _is_low_value_junk(title_n)
    )


def detect_category(title: str) -> str | None:
    title_n = normalize_text(title)
    if any(word in title_n for word in GENERIC_PHONE_WORDS):
        return "phone"
    if any(word in title_n for word in GENERIC_CONSOLE_WORDS):
        return "console"
    if any(word in title_n for word in GENERIC_TOOL_WORDS):
        return "tool"
    if any(word in title_n for word in GENERIC_CARD_WORDS):
        return "cards"
    if any(word in title_n for word in GENERIC_ELECTRONICS_WORDS):
        return "electronics"
    return None


def is_accessory_listing(title: str, keyword: str = "") -> bool:
    title_n = normalize_text(title)
    keyword_n = normalize_text(keyword)

    if _contains_any(title_n, AUTO_PART_TERMS) or _contains_any(title_n, ACCESSORY_WORDS) and _contains_any(title_n, ["smart phones", "laptop", "macbook", "ipad"]):
        return True
    if any(f" {phrase} " in title_n for phrase in PARTIAL_ITEM_PHRASES):
        return True
    if any(f" {hint} " in title_n for hint in EXACT_ACCESSORY_HINTS):
        return True
    if _is_console_accessory_or_game(title_n):
        return True
    if _is_phone_part_listing(title_n):
        return True
    if _is_device_accessory_listing(title_n):
        return True
    if _is_document_or_book_listing(title_n):
        return True
    if _is_auto_part_listing(title_n):
        return True
    if _is_low_value_junk(title_n):
        return True

    accessory_hit = any(word in title_n for word in ACCESSORY_WORDS)
    full_item_hit = any(signal in title_n for signal in [" console ", " system ", " phone ", " tablet ", " laptop ", " with controller ", " tested working ", " unlocked "])
    if accessory_hit and not full_item_hit:
        return True

    category_intent = detect_category(keyword_n) or detect_category(title_n)
    if category_intent in {"phone", "console", "tool", "electronics"}:
        reject_map = {
            "phone": ["case", "cover", "screen protector", "charger", "cable", "cord", "adapter", "sim tray", "lens protector", "back glass", "rear cover", "replacement", "housing", "earbuds", "earphones", "headset"],
            "console": ["controller", "remote", "power cord", "hdmi cable", "dock", "stand", "faceplate", "skin", "dust cover", "cover", "protector", "shell", "wrap", "case", "game", "disc", "software", "edition", "key", "code", "digital", "download", "manual", "guide", "book", "bag", "cartridge", "sealed", "us ver"],
            "tool": ["battery only", "charger only", "tool bag", "attachment only", "empty case", "manual", "guide", "switch", "sensor", "knob"],
            "electronics": ["cable", "charger", "adapter", "dock", "stand", "case", "mouse", "keyboard", "manual", "guide", "binder", "copy", "book", "textbook", "earbuds", "earphones", "headphones", "headset"],
        }
        if any(f" {term} " in title_n or term in title_n for term in reject_map.get(category_intent, [])):
            if not _looks_like_full_bundle(title_n):
                return True
    return False


def contains_phone_model(title: str) -> bool:
    title_n = normalize_text(title)
    if is_accessory_listing(title_n):
        return False
    return any(f" {model} " in title_n for model in PHONE_MODELS)


def extract_phone_model(title: str) -> str | None:
    title_n = normalize_text(title)
    if is_accessory_listing(title_n):
        return None
    for model in PHONE_MODELS:
        if f" {model} " in title_n:
            return model
    return None


def has_liquidation_signal(title: str) -> bool:
    title_n = normalize_text(title)
    return any(word in title_n for word in LIQUIDATION_WORDS)


def is_deal_candidate(title: str) -> bool:
    title_n = normalize_text(title)
    if is_accessory_listing(title_n):
        return False
    return contains_phone_model(title_n) or detect_category(title_n) is not None or has_liquidation_signal(title_n)
