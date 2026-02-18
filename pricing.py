import statistics

LOCAL_FACTOR = 0.80

CONDITION_MULTIPLIERS = {
    "A": 1.0,
    "B": 0.85,
    "C": 0.70,
    "Parts": 0.50
}

def analyze_pricing(prices, condition, profit):
    if not prices:
        return None

    prices.sort()
    median_price = statistics.median(prices)
    high = max(prices)
    low = min(prices)

    adjusted = median_price * CONDITION_MULTIPLIERS.get(condition, 1.0)
    local = adjusted * LOCAL_FACTOR

    max_buy = local * (1 - profit)
    sell_target = local / (1 - profit) if profit < 0.99 else median_price

    # Volatility score
    volatility = (high - low) / median_price if median_price else 0

    # Confidence score (volume weighted)
    confidence = min(len(prices) * 2, 100)

    # Demand tier
    if confidence > 60 and volatility < 0.5:
        demand = "🔥 Strong"
    elif confidence > 30:
        demand = "⚠️ Moderate"
    else:
        demand = "❄️ Weak"

    return {
        "median": round(median_price, 2),
        "max_buy": round(max_buy, 2),
        "sell_target": round(sell_target, 2),
        "confidence": confidence,
        "volatility": round(volatility, 2),
        "demand": demand,
        "high": round(high, 2),
        "low": round(low, 2)
    }
