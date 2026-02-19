import statistics

LOCAL_FACTOR = 0.80

CONDITION_MULTIPLIERS = {
    "A": 1.0,
    "B": 0.85,
    "C": 0.70,
    "Parts": 0.50
}

def analyze_market(sold_prices, active_prices, condition, profit):

    if not sold_prices:
        return None

    sold_prices.sort()
    sold_median = statistics.median(sold_prices)
    sold_high = max(sold_prices)
    sold_low = min(sold_prices)

    active_median = statistics.median(active_prices) if active_prices else 0

    adjusted = sold_median * CONDITION_MULTIPLIERS.get(condition, 1.0)
    local = adjusted * LOCAL_FACTOR

    max_buy = local * (1 - profit)
    sell_target = local / (1 - profit) if profit < 0.99 else sold_median

    supply_ratio = len(active_prices) / len(sold_prices) if sold_prices else 0

    if supply_ratio < 0.8:
        pressure = "🔥 Seller Advantage"
    elif supply_ratio < 1.5:
        pressure = "⚖ Balanced"
    else:
        pressure = "📉 Oversupplied"

    volatility = (sold_high - sold_low) / sold_median if sold_median else 0

    undercut_price = active_median - 1 if active_median else sell_target

    return {
        "sold_median": round(sold_median, 2),
        "active_median": round(active_median, 2),
        "max_buy": round(max_buy, 2),
        "sell_target": round(sell_target, 2),
        "pressure": pressure,
        "supply_ratio": round(supply_ratio, 2),
        "volatility": round(volatility, 2),
        "undercut": round(undercut_price, 2)
    }
