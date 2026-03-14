def deal_score(market_price, max_buy, sold_count=0, active_count=0, volatility=0):

    if market_price <= 0:
        return 0, "PASS"

    margin = (market_price - max_buy) / market_price
    margin_score = min(max(margin * 100, 0), 40)

    liquidity_score = min(sold_count * 2, 30)

    if sold_count > 0:
        supply_ratio = active_count / sold_count
    else:
        supply_ratio = 0

    if supply_ratio < 0.7:
        supply_score = 20
    elif supply_ratio < 1.5:
        supply_score = 10
    else:
        supply_score = 0

    volatility_penalty = min(volatility, 20)

    score = margin_score + liquidity_score + supply_score - volatility_penalty
    score = max(0, min(score, 100))

    if score >= 70:
        decision = "HOT DEAL"
    elif score >= 45:
        decision = "WARM DEAL"
    elif score >= 25:
        decision = "COOL DEAL"
    else:
        decision = "PASS"

    return round(score, 1), decision
