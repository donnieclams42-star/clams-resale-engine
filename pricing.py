import statistics


def analyze_market(sold_prices, active_prices, condition, profit_target, local_factor, asking_price):

    if not sold_prices:
        return None

    # Core pricing stats
    median_price = statistics.median(sold_prices)

    p25_price = statistics.quantiles(sold_prices, n=4)[0] if len(sold_prices) >= 4 else median_price
    p75_price = statistics.quantiles(sold_prices, n=4)[2] if len(sold_prices) >= 4 else median_price

    volatility_value = 0
    if len(sold_prices) > 1:
        volatility_value = round(statistics.stdev(sold_prices), 2)

    market_price = round(median_price, 2)
    fast_cash = round(market_price * 0.93, 2)
    hold_price = round(market_price * 1.15, 2)

    max_buy = round(market_price * (1 - profit_target), 2)

    sell_through = 0

    if active_prices:
        sell_through = round(len(sold_prices) / len(active_prices) * 100, 2)

    sold_count = len(sold_prices)
    active_count = len(active_prices)

    # Supply ratio
    supply_ratio = 0
    if sold_count > 0:
        supply_ratio = round(active_count / sold_count, 2)

    # Market condition labels
    demand = "High" if sell_through > 80 else "Medium" if sell_through > 50 else "Low"
    liquidity = "Strong" if sold_count > 20 else "Moderate" if sold_count > 10 else "Weak"

    volatility = "Low"
    if volatility_value > median_price * 0.25:
        volatility = "High"
    elif volatility_value > median_price * 0.15:
        volatility = "Medium"

    risk = "Low"
    if supply_ratio > 1.5:
        risk = "High"
    elif supply_ratio > 1:
        risk = "Medium"

    score = 80
    decision = "BUY"

    return {
        "fast_cash": fast_cash,
        "market_price": market_price,
        "hold_price": hold_price,
        "max_buy": max_buy,
        "deal_score": score,
        "deal_decision": decision,
        "sell_through": sell_through,
        "sold_count": sold_count,
        "active_count": active_count,
        "median_price": round(median_price,2),
        "p25_price": round(p25_price,2),
        "p75_price": round(p75_price,2),
        "volatility_value": volatility_value,
        "supply_ratio": supply_ratio,
        "demand": demand,
        "liquidity": liquidity,
        "volatility": volatility,
        "risk": risk
    }