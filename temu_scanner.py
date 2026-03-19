
import re

BLOCK_TERMS = [
    "mail in","repair","service","upgrade","unlock","mod","installation"
]

ACCESSORY_TERMS = [
    "case","cover","stick","module","shell","housing","replacement","parts","for ps5","compatible"
]

GAME_TERMS = [
    "ps5 game","playstation game","xbox game"
]

def is_blocked(title: str) -> bool:
    t = title.lower()
    if any(term in t for term in BLOCK_TERMS):
        return True
    if any(term in t for term in ACCESSORY_TERMS):
        return True
    return False

def classify_item(title: str) -> str:
    t = title.lower()
    if "ps5" in t and "game" not in t:
        return "console"
    if "game" in t:
        return "game"
    if any(x in t for x in ACCESSORY_TERMS):
        return "accessory"
    return "unknown"

def valid_price(category: str, price: float) -> bool:
    if category == "console":
        return 150 <= price <= 600
    if category == "game":
        return 5 <= price <= 80
    return True

def clean_item(item: dict):
    title = item.get("title","")
    price = float(item.get("price",0))

    if is_blocked(title):
        return None

    category = classify_item(title)

    if not valid_price(category, price):
        return None

    item["category"] = category
    return item
