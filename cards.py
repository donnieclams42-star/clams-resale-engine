# ===============================
# CLAMS Trading Cards Engine v1
# ===============================

from ebay import get_market_data
import statistics

def median_safe(prices):
    if not prices:
        return 0
    return round(statistics.median(prices), 2)


def filter_raw(items):
    filtered = []
    for item in items:
        title = item["title"].lower()
        if all(x not in title for x in ["psa", "bgs", "sgc", "graded"]):
            filtered.append(item["price"])
    return filtered


def analyze_card(base_query):
    results = {}

    # RAW
    sold_prices, _, sold_items = get_market_data(base_query)
    raw_prices = filter_raw(sold_items)
    results["raw"] = median_safe(raw_prices)

    # PSA Grades
    for grade in ["PSA 8", "PSA 9", "PSA 10"]:
        query = f"{base_query} {grade}"
        sold_prices, _, _ = get_market_data(query)
        results[grade] = median_safe(sold_prices)

    return results


def spread_analysis(results):
    spreads = {}

    raw = results.get("raw", 0)
    psa9 = results.get("PSA 9", 0)
    psa10 = results.get("PSA 10", 0)

    if raw and psa9:
        spreads["9_vs_raw"] = round(psa9 / raw, 2)
    if raw and psa10:
        spreads["10_vs_raw"] = round(psa10 / raw, 2)
    if psa9 and psa10:
        spreads["10_vs_9"] = round(psa10 / psa9, 2)

    return spreads