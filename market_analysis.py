import statistics


def classify_deal_temperature(asking_price, max_buy, local_market_value):
    if asking_price is None or asking_price <= 0:
        return "NO ASK"

    if max_buy <= 0:
        return "PASS"

    if asking_price <= round(max_buy * 0.85, 2):
        return "HOT DEAL"
    if asking_price <= max_buy:
        return "WARM DEAL"

    premium_gap = ((asking_price - max_buy) / max_buy) * 100 if max_buy else 999
    if premium_gap <= 10 and asking_price <= local_market_value:
        return "COOL DEAL"

    return "PASS"


def analyze_market(sold_prices, active_prices, condition, profit_target, local_factor, asking_price=None):

    if not sold_prices:
        return None

    sold_prices = [float(p) for p in sold_prices]
    active_prices = [float(p) for p in active_prices] if active_prices else []

    median_price = round(statistics.median(sold_prices), 2)

    fast_cash = round(median_price * 0.93, 2)
    market_price = round(median_price, 2)
    hold_price = round(median_price * 1.15, 2)
    local_market_value = round(market_price * float(local_factor), 2)
    max_buy = round(local_market_value * (1 - float(profit_target)), 2)

    sold_count = len(sold_prices)
    active_count = len(active_prices)

    if active_count == 0:
        sell_through = 100
    else:
        sell_through = round((sold_count / active_count) * 100)

    price_range = max(sold_prices) - min(sold_prices)

    if price_range < 20:
        volatility = "Low"
    elif price_range < 80:
        volatility = "Medium"
    else:
        volatility = "High"

    if sell_through >= 80:
        liquidity = "High"
    elif sell_through >= 50:
        liquidity = "Moderate"
    else:
        liquidity = "Low"

    if volatility == "Low" and sell_through > 70:
        risk = "Low"
    elif volatility == "Medium":
        risk = "Moderate"
    else:
        risk = "High"

    flip_score = min(100, int((sell_through * 0.6) + (100 - price_range) * 0.4))

    deal_score = 50
    profit_delta = None
    profit_margin_percent = None
    deal_temperature = "NO ASK"

    if asking_price is not None:
        asking_price = float(asking_price)
        if market_price > 0:
            deal_margin = (local_market_value - asking_price) / market_price
            deal_score = int(max(0, min(deal_margin * 100, 100)))
        profit_delta = round(local_market_value - asking_price, 2)
        if asking_price > 0:
            profit_margin_percent = round((profit_delta / asking_price) * 100, 1)
        deal_temperature = classify_deal_temperature(asking_price, max_buy, local_market_value)

    if sell_through > 80 and volatility == "Low":
        confidence = "High"
    elif sell_through > 50:
        confidence = "Medium"
    else:
        confidence = "Low"

    platform_scores = {
        "Facebook Marketplace": sell_through + 15,
        "eBay": sell_through,
        "Mercari": sell_through - 5,
        "OfferUp": sell_through - 10
    }

    best_platform = max(platform_scores, key=platform_scores.get)

    platform_ranking = sorted(
        platform_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return {
        "median_price": round(median_price, 2),
        "fast_cash": fast_cash,
        "market_price": market_price,
        "hold_price": hold_price,
        "local_market_value": local_market_value,
        "max_buy": max_buy,
        "sell_through": sell_through,
        "volatility": volatility,
        "liquidity": liquidity,
        "risk": risk,
        "flip_score": flip_score,
        "deal_score": deal_score,
        "confidence": confidence,
        "sold_count": sold_count,
        "active_count": active_count,
        "best_platform": best_platform,
        "platform_ranking": platform_ranking,
        "profit_delta": profit_delta,
        "profit_margin_percent": profit_margin_percent,
        "deal_temperature": deal_temperature,
    }
