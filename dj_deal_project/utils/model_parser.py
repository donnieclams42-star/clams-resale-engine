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
    "case",
    "cover",
    "charger",
    "charging",
    "cable",
    "cord",
    "adapter",
    "screen protector",
    "protector",
    "mount",
    "holder",
    "dock",
    "shell only",
    "empty box",
]

GENERIC_PHONE_WORDS = [
    "phone",
    "cell phone",
    "mobile phone",
    "smartphone",
    "iphone",
    "android",
    "samsung",
    "pixel",
]

GENERIC_CONSOLE_WORDS = [
    "console",
    "game system",
    "video game system",
    "gaming console",
    "playstation",
    "ps5",
    "ps4",
    "xbox",
    "switch",
    "gamecube",
    "wii",
]

GENERIC_TOOL_WORDS = [
    "power tool",
    "tools",
    "tool lot",
    "drill",
    "impact",
    "dewalt",
    "milwaukee",
    "makita",
    "snap on",
    "snapon",
    "tool box",
    "socket set",
]

GENERIC_CARD_WORDS = [
    "card lot",
    "sports cards",
    "pokemon cards",
    "trading cards",
    "baseball cards",
    "basketball cards",
    "football cards",
    "hockey cards",
]

GENERIC_ELECTRONICS_WORDS = [
    "electronics lot",
    "box of electronics",
    "random electronics",
    "laptop",
    "computer",
    "gpu",
    "graphics card",
]

LIQUIDATION_WORDS = [
    "garage sale",
    "estate sale",
    "moving sale",
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
    "bulk lot",
    "mixed lot",
    "bundle",
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


def normalize_text(text: str) -> str:

    text = (text or "").lower()

    for correct, mistakes in MISSPELLINGS.items():
        for mistake in mistakes:
            text = text.replace(mistake, correct)

    return " ".join(text.split())


def is_accessory(title: str) -> bool:

    title = normalize_text(title)

    return any(word in title for word in ACCESSORY_WORDS)


def contains_phone_model(title: str) -> bool:

    title = normalize_text(title)

    if is_accessory(title):
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

    if is_accessory(title):
        return None

    for model in PHONE_MODELS:
        if model in title:
            return model

    # IMPORTANT CHANGE
    # Do NOT return generic_phone anymore
    return None


def has_liquidation_signal(title: str) -> bool:

    title = normalize_text(title)

    return any(word in title for word in LIQUIDATION_WORDS)


def is_deal_candidate(title: str) -> bool:

    title = normalize_text(title)

    if is_accessory(title):
        return False

    return (
        contains_phone_model(title)
        or detect_category(title) is not None
        or has_liquidation_signal(title)
    )