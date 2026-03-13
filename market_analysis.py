import statistics


def analyze_market(sold_prices, active_prices, condition, profit_target, local_factor, asking_price=None):

    if not sold_prices:
        return None

    sold_prices = [float(p) for p in sold_prices]
    active_prices = [float(p) for p in active_prices] if active_prices else []

    # ---------- Core price calculations ----------

    median_price = round(statistics.median(sold_prices), 2)

    fast_cash = round(median_price * 0.93, 2)
    market_price = round(median_price, 2)
    hold_price = round(median_price * 1.15, 2)

    # ---------- Market health ----------

    sold_count = len(sold_prices)
    active_count = len(active_prices)

    if active_count == 0:
        sell_through = 100
    else:
        sell_through = round((sold_count / active_count) * 100)

    # ---------- Volatility ----------

    price_range = max(sold_prices) - min(sold_prices)

    if price_range < 20:
        volatility = "Low"
    elif price_range < 80:
        volatility = "Medium"
    else:
        volatility = "High"

    # ---------- Liquidity ----------

    if sell_through >= 80:
        liquidity = "High"
    elif sell_through >= 50:
        liquidity = "Moderate"
    else:
        liquidity = "Low"

    # ---------- Risk ----------

    if volatility == "Low" and sell_through > 70:
        risk = "Low"
    elif volatility == "Medium":
        risk = "Moderate"
    else:
        risk = "High"

    # ---------- Flip Score ----------

    flip_score = min(100, int((sell_through * 0.6) + (100 - price_range) * 0.4))

    # ---------- Deal Score ----------

    deal_score = 50

    if asking_price:

        deal_margin = (market_price - asking_price) / market_price

        deal_score = int(deal_margin * 100)

        if deal_score < 0:
            deal_score = 0
        if deal_score > 100:
            deal_score = 100

    # ---------- Confidence ----------

    if sell_through > 80 and volatility == "Low":
        confidence = "High"
    elif sell_through > 50:
        confidence = "Medium"
    else:
        confidence = "Low"

    # ---------- Platform Ranking ----------

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

    # ---------- Return Data ----------

    return {

        "median_price": round(median_price, 2),

        "fast_cash": fast_cash,
        "market_price": market_price,
        "hold_price": hold_price,

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
        "platform_ranking": platform_ranking
    }