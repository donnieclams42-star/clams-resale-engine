from __future__ import annotations

from typing import Any


# Geography is data, not scanner logic. Radii are miles; providers convert to km.
SCAN_MARKETS: list[dict[str, Any]] = [
    {"id": "philadelphia", "name": "Philadelphia", "location": "Philadelphia, PA", "country": "US", "currency": "USD", "latitude": 39.9526, "longitude": -75.1652, "radius_miles": 35, "region": "northeast"},
    {"id": "atlantic-city", "name": "Atlantic City", "location": "Atlantic City, NJ", "country": "US", "currency": "USD", "latitude": 39.3643, "longitude": -74.4229, "radius_miles": 40, "region": "northeast"},
    {"id": "south-jersey", "name": "South Jersey", "location": "Vineland, NJ", "country": "US", "currency": "USD", "latitude": 39.4862, "longitude": -75.0260, "radius_miles": 45, "region": "northeast"},
    {"id": "cherry-hill", "name": "Cherry Hill / Camden", "location": "Cherry Hill, NJ", "country": "US", "currency": "USD", "latitude": 39.9348, "longitude": -75.0300, "radius_miles": 30, "region": "northeast"},
    {"id": "trenton", "name": "Trenton / Princeton", "location": "Trenton, NJ", "country": "US", "currency": "USD", "latitude": 40.2171, "longitude": -74.7429, "radius_miles": 35, "region": "northeast"},
    {"id": "newark", "name": "Newark / Jersey City", "location": "Newark, NJ", "country": "US", "currency": "USD", "latitude": 40.7357, "longitude": -74.1724, "radius_miles": 30, "region": "northeast"},
    {"id": "new-york", "name": "New York metro", "location": "New York, NY", "country": "US", "currency": "USD", "latitude": 40.7128, "longitude": -74.0060, "radius_miles": 30, "region": "northeast"},
    {"id": "allentown", "name": "Allentown / Lehigh Valley", "location": "Allentown, PA", "country": "US", "currency": "USD", "latitude": 40.6084, "longitude": -75.4902, "radius_miles": 45, "region": "northeast"},
    {"id": "baltimore", "name": "Baltimore", "location": "Baltimore, MD", "country": "US", "currency": "USD", "latitude": 39.2904, "longitude": -76.6122, "radius_miles": 35, "region": "mid-atlantic"},
    {"id": "washington-dc", "name": "Washington DC / Northern Virginia", "location": "Washington, DC", "country": "US", "currency": "USD", "latitude": 38.9072, "longitude": -77.0369, "radius_miles": 35, "region": "mid-atlantic"},
    {"id": "harrisburg", "name": "Harrisburg", "location": "Harrisburg, PA", "country": "US", "currency": "USD", "latitude": 40.2732, "longitude": -76.8867, "radius_miles": 50, "region": "northeast"},
    {"id": "scranton", "name": "Scranton / Wilkes-Barre", "location": "Scranton, PA", "country": "US", "currency": "USD", "latitude": 41.4090, "longitude": -75.6624, "radius_miles": 50, "region": "northeast"},
]

PRODUCT_FAMILIES: list[dict[str, Any]] = [
    {"id": "iphone-15-pro-max", "name": "iPhone 15 Pro Max", "kind": "phone"},
    {"id": "iphone-15-pro", "name": "iPhone 15 Pro", "kind": "phone"},
    {"id": "iphone-16-pro", "name": "iPhone 16 Pro / Pro Max", "kind": "phone"},
    {"id": "iphone-14-pro", "name": "iPhone 14 Pro / Pro Max", "kind": "phone"},
    {"id": "iphone-13-pro", "name": "iPhone 13 Pro / Pro Max", "kind": "phone"},
    {"id": "iphone-15-16-base", "name": "iPhone 15 / 16 base", "kind": "phone"},
    {"id": "galaxy-s24-ultra", "name": "Samsung Galaxy S24 Ultra", "kind": "phone"},
    {"id": "galaxy-s-family", "name": "Samsung Galaxy S23 Ultra / S24 / S25", "kind": "phone"},
    {"id": "pixel-pro", "name": "Google Pixel Pro family", "kind": "phone"},
    {"id": "macbook-air-m1", "name": "MacBook Air M1", "kind": "laptop"},
    {"id": "macbook-air-m2-m3", "name": "MacBook Air M2 / M3", "kind": "laptop"},
    {"id": "macbook-pro-silicon", "name": "MacBook Pro Apple Silicon", "kind": "laptop"},
    {"id": "ipad-silicon", "name": "iPad Pro / iPad Air Apple Silicon", "kind": "tablet"},
    {"id": "apple-watch", "name": "Apple Watch Ultra / recent Series", "kind": "wearable"},
    {"id": "switch-oled", "name": "Nintendo Switch OLED", "kind": "console"},
    {"id": "switch-2", "name": "Nintendo Switch 2", "kind": "console"},
    {"id": "steam-deck", "name": "Steam Deck LCD / OLED", "kind": "handheld"},
    {"id": "rog-ally", "name": "ROG Ally / Ally X", "kind": "handheld"},
    {"id": "ps5", "name": "PlayStation 5", "kind": "console"},
    {"id": "xbox-series", "name": "Xbox Series X / Series S", "kind": "console"},
    {"id": "rtx-4070", "name": "RTX 4070 family", "kind": "gpu"},
    {"id": "rtx-4080-4090", "name": "RTX 4080 / 4090", "kind": "gpu"},
    {"id": "gaming-pc", "name": "Gaming PC", "kind": "pc"},
    {"id": "retro-nintendo", "name": "GameCube / N64 / GBA SP / 3DS / Nintendo lots", "kind": "retro"},
    {"id": "camera-drone", "name": "Camera / drone families", "kind": "camera"},
    {"id": "electronics-generic", "name": "Electronics / mixed", "kind": "electronics"},
]

QUERY_PORTFOLIO: list[dict[str, Any]] = [
    {"query": "iphone 15 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-15-pro-max", "priority": 10},
    {"query": "iphone 15 pro", "query_type": "EXACT_MODEL", "product_family": "iphone-15-pro", "priority": 10},
    {"query": "iphone 16 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-16-pro", "priority": 10},
    {"query": "iphone 16 pro", "query_type": "EXACT_MODEL", "product_family": "iphone-16-pro", "priority": 12},
    {"query": "iphone 14 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-14-pro", "priority": 14},
    {"query": "iphone 13 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-13-pro", "priority": 16},
    {"query": "macbook air m1", "query_type": "EXACT_MODEL", "product_family": "macbook-air-m1", "priority": 12},
    {"query": "macbook air m2", "query_type": "EXACT_MODEL", "product_family": "macbook-air-m2-m3", "priority": 12},
    {"query": "switch oled", "query_type": "EXACT_MODEL", "product_family": "switch-oled", "priority": 10},
    {"query": "steam deck oled", "query_type": "EXACT_MODEL", "product_family": "steam-deck", "priority": 14},
    {"query": "ps5", "query_type": "EXACT_MODEL", "product_family": "ps5", "priority": 10},
    {"query": "rtx 4070", "query_type": "EXACT_MODEL", "product_family": "rtx-4070", "priority": 16},
    {"query": "rtx 4070 super", "query_type": "EXACT_MODEL", "product_family": "rtx-4070", "priority": 16},
    {"query": "rtx 4080", "query_type": "EXACT_MODEL", "product_family": "rtx-4080-4090", "priority": 18},
    {"query": "rtx 4090", "query_type": "EXACT_MODEL", "product_family": "rtx-4080-4090", "priority": 12},
    {"query": "15 promax", "query_type": "ABBREVIATION", "product_family": "iphone-15-pro-max", "priority": 20},
    {"query": "15pm", "query_type": "ABBREVIATION", "product_family": "iphone-15-pro-max", "priority": 22},
    {"query": "mba m1", "query_type": "ABBREVIATION", "product_family": "macbook-air-m1", "priority": 24},
    {"query": "mba m2", "query_type": "ABBREVIATION", "product_family": "macbook-air-m2-m3", "priority": 24},
    {"query": "n64", "query_type": "ABBREVIATION", "product_family": "retro-nintendo", "priority": 30},
    {"query": "gba sp", "query_type": "ABBREVIATION", "product_family": "retro-nintendo", "priority": 30},
    {"query": "iphon", "query_type": "MISSPELLING", "product_family": "iphone-15-16-base", "priority": 40},
    {"query": "nintedo", "query_type": "MISSPELLING", "product_family": "switch-oled", "priority": 42},
    {"query": "nintendoe", "query_type": "MISSPELLING", "product_family": "switch-oled", "priority": 42},
    {"query": "playstaion", "query_type": "MISSPELLING", "product_family": "ps5", "priority": 40},
    {"query": "samsng", "query_type": "MISSPELLING", "product_family": "galaxy-s-family", "priority": 42},
    {"query": "mackbook", "query_type": "MISSPELLING", "product_family": "macbook-air-m2-m3", "priority": 42},
    {"query": "apple phone", "query_type": "GENERIC", "product_family": "iphone-15-16-base", "priority": 50},
    {"query": "gaming computer", "query_type": "GENERIC", "product_family": "gaming-pc", "priority": 40},
    {"query": "gaming pc", "query_type": "GENERIC", "product_family": "gaming-pc", "priority": 30},
    {"query": "computer parts", "query_type": "GENERIC", "product_family": "rtx-4070", "priority": 50},
    {"query": "old consoles", "query_type": "GENERIC", "product_family": "retro-nintendo", "priority": 45},
    {"query": "camera stuff", "query_type": "GENERIC", "product_family": "camera-drone", "priority": 50},
    {"query": "electronics", "query_type": "GENERIC", "product_family": "electronics-generic", "priority": 60},
    {"query": "game lot", "query_type": "BUNDLE", "product_family": "retro-nintendo", "priority": 35},
    {"query": "gaming lot", "query_type": "BUNDLE", "product_family": "electronics-generic", "priority": 35},
    {"query": "nintendo lot", "query_type": "BUNDLE", "product_family": "retro-nintendo", "priority": 28},
    {"query": "electronics lot", "query_type": "BUNDLE", "product_family": "electronics-generic", "priority": 32},
    {"query": "phone lot", "query_type": "BUNDLE", "product_family": "iphone-15-16-base", "priority": 35},
    {"query": "console bundle", "query_type": "BUNDLE", "product_family": "ps5", "priority": 32},
    {"query": "camera bundle", "query_type": "BUNDLE", "product_family": "camera-drone", "priority": 40},
    {"query": "computer lot", "query_type": "BUNDLE", "product_family": "gaming-pc", "priority": 36},
    {"query": "must go", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 55},
    {"query": "need gone", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 55},
    {"query": "pickup today", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 55},
    {"query": "moving", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 58},
    {"query": "moving sale", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 50},
    {"query": "cleanout", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 52},
    {"query": "estate sale", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 52},
    {"query": "old game stuff", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "retro-nintendo", "priority": 48},
    {"query": "kids don't use", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 60},
    {"query": "found in garage", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 58},
    {"query": "don't know if works", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 50},
    {"query": "everything must go", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 50},
    {"query": "old electronics", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 48},
    {"query": "box of electronics", "query_type": "HOUSEHOLD_LANGUAGE", "product_family": "electronics-generic", "priority": 40},
    {"query": "free", "query_type": "PLACEHOLDER", "product_family": "electronics-generic", "priority": 25},
    {"query": "$1", "query_type": "PLACEHOLDER", "product_family": "electronics-generic", "priority": 25},
    {"query": "obo", "query_type": "PLACEHOLDER", "product_family": "electronics-generic", "priority": 45},
    {"query": "best offer", "query_type": "PLACEHOLDER", "product_family": "electronics-generic", "priority": 45},
    {"query": "make offer", "query_type": "PLACEHOLDER", "product_family": "electronics-generic", "priority": 50},
    {"query": "for parts", "query_type": "REPAIR", "product_family": "electronics-generic", "priority": 38},
    {"query": "untested", "query_type": "REPAIR", "product_family": "electronics-generic", "priority": 40},
    {"query": "as is", "query_type": "REPAIR", "product_family": "electronics-generic", "priority": 42},
    {"query": "broken iphone", "query_type": "REPAIR", "product_family": "iphone-15-16-base", "priority": 36},
]

CANARY_QUERIES = ["iphone 15 pro", "switch oled", "ps5", "nintendo lot", "gaming pc"]
CANARY_MARKET_IDS = ["philadelphia", "atlantic-city"]
CANARY_PROVIDERS = ["rigelbytes"]
# Backup comparison targets stay disabled until an admin comparison run.
COMPARISON_PROVIDER = "k1ra"

# Four overlapping metro cells. Not ZIP mesh, not nationwide.
FIRST_PROFIT_LEVEL1_MARKETS: list[dict[str, Any]] = [
    {"id": "south-jersey", "name": "South Jersey / Shore", "location": "Vineland, NJ", "latitude": 39.4862, "longitude": -75.0260, "radius_miles": 70, "group_order": 0, "priority_base": 8},
    {"id": "philadelphia", "name": "Philadelphia / Cherry Hill", "location": "Philadelphia, PA", "latitude": 39.9526, "longitude": -75.1652, "radius_miles": 55, "group_order": 1, "priority_base": 10},
    {"id": "trenton", "name": "Trenton / Princeton", "location": "Trenton, NJ", "latitude": 40.2171, "longitude": -74.7429, "radius_miles": 55, "group_order": 2, "priority_base": 28},
    {"id": "newark", "name": "Newark / Jersey City", "location": "Newark, NJ", "latitude": 40.7357, "longitude": -74.1724, "radius_miles": 45, "group_order": 3, "priority_base": 40},
]
LEVEL1_PROTECTED_MARKET_IDS = ["south-jersey", "philadelphia"]
PRECISION_RESULT_LIMIT = 12
TREASURE_RESULT_LIMIT = 15
PRECISION_CADENCE_MINUTES = 40
TREASURE_CADENCE_HOURS = 3
MARKET_STAGGER_MINUTES = 10
ESTIMATED_APIFY_USD_PER_RUN = 0.016
LEVEL1_MAX_RUNS_PER_DAY = 30
ESTIMATED_DAILY_APIFY_USD = round(ESTIMATED_APIFY_USD_PER_RUN * LEVEL1_MAX_RUNS_PER_DAY, 2)

# ~25 precision targets. First Profit Mode scans these, not hundreds.
FIRST_PROFIT_WATCHLIST: list[dict[str, Any]] = [
    {"query": "switch oled", "query_type": "EXACT_MODEL", "product_family": "switch-oled", "priority": 8, "lane": "PRECISION"},
    {"query": "steam deck oled", "query_type": "EXACT_MODEL", "product_family": "steam-deck", "priority": 10, "lane": "PRECISION"},
    {"query": "steam deck", "query_type": "EXACT_MODEL", "product_family": "steam-deck", "priority": 12, "lane": "PRECISION"},
    {"query": "ps5", "query_type": "EXACT_MODEL", "product_family": "ps5", "priority": 8, "lane": "PRECISION"},
    {"query": "xbox series x", "query_type": "EXACT_MODEL", "product_family": "xbox-series", "priority": 12, "lane": "PRECISION"},
    {"query": "new nintendo 3ds xl", "query_type": "EXACT_MODEL", "product_family": "retro-nintendo", "priority": 14, "lane": "PRECISION"},
    {"query": "nintendo 3ds xl", "query_type": "EXACT_MODEL", "product_family": "retro-nintendo", "priority": 14, "lane": "PRECISION"},
    {"query": "gamecube console", "query_type": "EXACT_MODEL", "product_family": "retro-nintendo", "priority": 12, "lane": "PRECISION"},
    {"query": "n64 console", "query_type": "EXACT_MODEL", "product_family": "retro-nintendo", "priority": 14, "lane": "PRECISION"},
    {"query": "iphone 13 pro", "query_type": "EXACT_MODEL", "product_family": "iphone-13-pro", "priority": 16, "lane": "PRECISION"},
    {"query": "iphone 13 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-13-pro", "priority": 16, "lane": "PRECISION"},
    {"query": "iphone 14 pro", "query_type": "EXACT_MODEL", "product_family": "iphone-14-pro", "priority": 14, "lane": "PRECISION"},
    {"query": "iphone 14 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-14-pro", "priority": 12, "lane": "PRECISION"},
    {"query": "iphone 15 pro", "query_type": "EXACT_MODEL", "product_family": "iphone-15-pro", "priority": 10, "lane": "PRECISION"},
    {"query": "iphone 15 pro max", "query_type": "EXACT_MODEL", "product_family": "iphone-15-pro-max", "priority": 10, "lane": "PRECISION"},
    {"query": "macbook air m1", "query_type": "EXACT_MODEL", "product_family": "macbook-air-m1", "priority": 12, "lane": "PRECISION"},
    {"query": "macbook air m2", "query_type": "EXACT_MODEL", "product_family": "macbook-air-m2-m3", "priority": 12, "lane": "PRECISION"},
    {"query": "macbook air m3", "query_type": "EXACT_MODEL", "product_family": "macbook-air-m2-m3", "priority": 12, "lane": "PRECISION"},
    {"query": "macbook pro m3", "query_type": "EXACT_MODEL", "product_family": "macbook-pro-silicon", "priority": 16, "lane": "PRECISION"},
    {"query": "rtx 4070", "query_type": "EXACT_MODEL", "product_family": "rtx-4070", "priority": 14, "lane": "PRECISION"},
    {"query": "rtx 4070 super", "query_type": "EXACT_MODEL", "product_family": "rtx-4070", "priority": 14, "lane": "PRECISION"},
    {"query": "rtx 4070 ti", "query_type": "EXACT_MODEL", "product_family": "rtx-4070", "priority": 16, "lane": "PRECISION"},
    {"query": "rtx 4080", "query_type": "EXACT_MODEL", "product_family": "rtx-4080-4090", "priority": 16, "lane": "PRECISION"},
    {"query": "rtx 4080 super", "query_type": "EXACT_MODEL", "product_family": "rtx-4080-4090", "priority": 16, "lane": "PRECISION"},
    {"query": "rtx 4090", "query_type": "EXACT_MODEL", "product_family": "rtx-4080-4090", "priority": 12, "lane": "PRECISION"},
]

FIRST_PROFIT_TREASURE: list[dict[str, Any]] = [
    {"query": "nintendo lot", "query_type": "BUNDLE", "product_family": "retro-nintendo", "priority": 28, "lane": "TREASURE"},
    {"query": "game lot", "query_type": "BUNDLE", "product_family": "retro-nintendo", "priority": 32, "lane": "TREASURE"},
    {"query": "old nintendo", "query_type": "GENERIC", "product_family": "retro-nintendo", "priority": 34, "lane": "TREASURE"},
    {"query": "old games", "query_type": "GENERIC", "product_family": "retro-nintendo", "priority": 36, "lane": "TREASURE"},
    {"query": "gaming stuff", "query_type": "GENERIC", "product_family": "electronics-generic", "priority": 40, "lane": "TREASURE"},
    {"query": "electronics lot", "query_type": "BUNDLE", "product_family": "electronics-generic", "priority": 32, "lane": "TREASURE"},
    {"query": "console bundle", "query_type": "BUNDLE", "product_family": "ps5", "priority": 30, "lane": "TREASURE"},
    {"query": "gameboy", "query_type": "GENERIC", "product_family": "retro-nintendo", "priority": 34, "lane": "TREASURE"},
    {"query": "3ds games", "query_type": "GENERIC", "product_family": "retro-nintendo", "priority": 34, "lane": "TREASURE"},
    {"query": "moving electronics", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 42, "lane": "TREASURE"},
    {"query": "cleanout electronics", "query_type": "URGENCY", "product_family": "electronics-generic", "priority": 42, "lane": "TREASURE"},
]


def first_profit_ebay_queries() -> list[dict[str, Any]]:
    return list(FIRST_PROFIT_WATCHLIST)


def first_profit_facebook_precision_queries() -> list[dict[str, Any]]:
    return list(FIRST_PROFIT_WATCHLIST)


def first_profit_facebook_treasure_queries() -> list[dict[str, Any]]:
    return list(FIRST_PROFIT_TREASURE)


def first_profit_facebook_queries() -> list[dict[str, Any]]:
    return first_profit_facebook_precision_queries() + first_profit_facebook_treasure_queries()


def first_profit_level1_markets() -> list[dict[str, Any]]:
    return list(FIRST_PROFIT_LEVEL1_MARKETS)


def miles_to_km(miles: int | float) -> int:
    try:
        return max(1, int(round(float(miles) * 1.60934)))
    except Exception:
        return 64


def market_by_id(market_id: str) -> dict[str, Any]:
    for market in FIRST_PROFIT_LEVEL1_MARKETS + SCAN_MARKETS:
        if market["id"] == market_id:
            return market
    return {}
