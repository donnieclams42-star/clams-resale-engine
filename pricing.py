import statistics

CONDITION_MULTIPLIERS = {
    "A": 1.0,
    "B": 0.85,
    "C": 0.70,
    "Parts": 0.50
}


def analyze_market(sold_prices, active_prices, condition, profit, local_factor):
    if not sold_prices:
        return None

    sold_prices = sorted(sold_prices)

    sold_median = statistics.median(sold_prices)
    sold_high = max(sold_prices)
    sold_low = min(sold_prices)

    active_median = statistics.median(active_prices) if active_prices else 0

    # ---------------------------
    # CONDITION ADJUSTMENT
    # ---------------------------
    multiplier = CONDITION_MULTIPLIERS.get(condition, 1.0)
    adjusted = sold_median * multiplier
    local = adjusted * local_factor

    condition_impact_percent = round((multiplier - 1.0) * 100, 2)

    # ---------------------------
    # PROFIT CONTROL
    # ---------------------------
    profit = max(0.0, min(float(profit), 0.95))

    max_buy = local * (1 - profit)
    sell_target = local / (1 - profit) if profit < 0.99 else sold_median

    # ---------------------------
    # SMART FAST CASH (C RULE)
    # Undercut lower of active_median or sell_target by 3%
    # ---------------------------
    if active_median:
        baseline = min(active_median, sell_target)
    else:
        baseline = sell_target

    undercut = baseline * 0.97

    # ---------------------------
    # MARKET BALANCE
    # ---------------------------
    sold_count = len(sold_prices)
    active_count = len(active_prices)

    supply_ratio = active_count / sold_count if sold_count else 0

    if supply_ratio < 0.8:
        market_balance_label = "Tight Market"
    elif supply_ratio < 1.5:
        market_balance_label = "Balanced Market"
    else:
        market_balance_label = "Crowded Market"

    # ---------------------------
    # PRICE CONSISTENCY
    # ---------------------------
    volatility = (sold_high - sold_low) / sold_median if sold_median else 0

    if volatility < 0.25:
        price_consistency_label = "Very Consistent"
    elif volatility < 0.50:
        price_consistency_label = "Mostly Consistent"
    elif volatility < 0.80:
        price_consistency_label = "Inconsistent"
    else:
        price_consistency_label = "Highly Unstable"

    # ---------------------------
    # RISK LEVEL
    # ---------------------------
    if volatility < 0.35 and supply_ratio < 1.5:
        risk_level = "LOW"
    elif volatility < 0.75:
        risk_level = "MODERATE"
    else:
        risk_level = "HIGH"

    # ---------------------------
    # LIQUIDITY SCORE (Balanced + Fast Flip Hybrid)
    # ---------------------------
    # Weighting:
    # Sold count strength = 30%
    # Market balance = 30%
    # Consistency = 25%
    # Active viability = 15%

    sold_score = min(sold_count * 5, 100)  # scaled data strength

    balance_score = (
        90 if supply_ratio < 0.8 else
        75 if supply_ratio < 1.5 else
        50
    )

    consistency_score = (
        90 if volatility < 0.25 else
        75 if volatility < 0.50 else
        55 if volatility < 0.80 else
        35
    )

    active_viability_score = 75 if active_median else 60

    liquidity_score = round(
        (sold_score * 0.30) +
        (balance_score * 0.30) +
        (consistency_score * 0.25) +
        (active_viability_score * 0.15)
    )

    if liquidity_score >= 90:
        liquidity_label = "Very Strong"
    elif liquidity_score >= 75:
        liquidity_label = "Strong"
    elif liquidity_score >= 60:
        liquidity_label = "Moderate"
    elif liquidity_score >= 40:
        liquidity_label = "Weak"
    else:
        liquidity_label = "Very Weak"

    # ---------------------------
    # CONFIDENCE
    # ---------------------------
    confidence = min(sold_count * 2, 100)

    return {
        "sold_median": round(sold_median, 2),
        "active_median": round(active_median, 2),
        "max_buy": round(max_buy, 2),
        "sell_target": round(sell_target, 2),
        "undercut": round(undercut, 2),
        "confidence": confidence,

        # New enhanced metrics
        "sold_count": sold_count,
        "active_count": active_count,
        "market_balance": market_balance_label,
        "price_consistency": price_consistency_label,
        "risk_level": risk_level,
        "liquidity_score": liquidity_score,
        "liquidity_label": liquidity_label,
        "condition_impact_percent": condition_impact_percent
    }