import statistics
from typing import Optional


CONDITION_MULTIPLIERS = {
    "A": 1.00,
    "B": 0.88,
    "C": 0.72,
    "Parts": 0.50,
}


def clamp(value, low, high):
    return max(low, min(value, high))


def safe_median(values):
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return 0.0
    return float(statistics.median(cleaned))


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return float(d0 + d1)


def calc_trend_label(sorted_sold):
    """
    This is a proxy trend, not a true time-series trend.
    It compares the lower portion of observed prices to the upper portion.
    """
    if len(sorted_sold) < 6:
        return "Insufficient Data", 0.0

    lower_band = percentile(sorted_sold, 0.25)
    upper_band = percentile(sorted_sold, 0.75)

    if lower_band <= 0:
        return "Insufficient Data", 0.0

    move = ((upper_band - lower_band) / lower_band) * 100

    if move >= 18:
        return "Rising", round(move, 1)
    if move <= -18:
        return "Dropping", round(move, 1)
    return "Stable", round(move, 1)


def calc_sell_through(sold_count, active_count) -> tuple[Optional[float], str]:
    if active_count <= 0:
        return None, "N/A"

    rate = (sold_count / active_count) * 100

    if rate >= 200:
        label = "Very Hot"
    elif rate >= 120:
        label = "Strong"
    elif rate >= 80:
        label = "Balanced"
    elif rate >= 40:
        label = "Slow"
    else:
        label = "Oversupplied"

    return round(rate, 1), label


def calc_flip_speed(sell_through_rate, liquidity_score, volatility, sold_count):
    if sell_through_rate is not None:
        if sell_through_rate >= 180 and volatility < 0.45:
            return "INSTANT", 95
        if sell_through_rate >= 120:
            return "FAST", 84
        if sell_through_rate >= 80:
            return "GOOD", 72
        if sell_through_rate >= 40:
            return "MEDIUM", 58
        return "SLOW", 38

    proxy_score = round(
        (liquidity_score * 0.55) +
        (min(sold_count * 4, 100) * 0.25) +
        ((100 - min(volatility * 100, 100)) * 0.20)
    )

    if proxy_score >= 88:
        return "FAST", proxy_score
    if proxy_score >= 72:
        return "GOOD", proxy_score
    if proxy_score >= 58:
        return "MEDIUM", proxy_score
    return "SLOW", proxy_score


def calc_sniper(asking_price, max_buy):
    if asking_price is None or max_buy <= 0:
        return None, None, "N/A"

    gap = max_buy - asking_price
    gap_pct = (gap / max_buy) * 100

    if gap_pct < 0:
        label = "PASS"
    elif gap_pct < 10:
        label = "WEAK"
    elif gap_pct < 30:
        label = "GOOD"
    elif gap_pct < 60:
        label = "GREAT"
    else:
        label = "STEAL"

    return round(gap, 2), round(gap_pct, 1), label


def analyze_market(
    sold_prices,
    active_prices,
    condition="A",
    profit=0.40,
    local_factor=0.85,
    asking_price=None,
):
    sold_prices = sorted([float(x) for x in sold_prices if x is not None])
    active_prices = sorted([float(x) for x in active_prices if x is not None])

    if not sold_prices:
        return None

    sold_count = len(sold_prices)
    active_count = len(active_prices)

    sold_median = safe_median(sold_prices)
    sold_low = min(sold_prices)
    sold_high = max(sold_prices)

    active_median = safe_median(active_prices) if active_prices else None

    multiplier = CONDITION_MULTIPLIERS.get(condition, 1.00)
    adjusted_market = sold_median * multiplier
    local_market = adjusted_market * local_factor

    profit = clamp(float(profit), 0.05, 0.95)

    sell_target = local_market / (1 - profit)
    max_buy = local_market * (1 - profit)

    if active_median:
        market_price = min(active_median, sell_target)
    else:
        market_price = sell_target

    fast_cash = market_price * 0.93
    hold_price = max(sell_target, adjusted_market * 1.08)

    supply_ratio = (active_count / sold_count) if sold_count and active_count else None
    volatility = ((sold_high - sold_low) / sold_median) if sold_median else 0

    if sold_count >= 24:
        demand_label = "High"
        demand_score = 88
    elif sold_count >= 12:
        demand_label = "Moderate"
        demand_score = 70
    else:
        demand_label = "Low"
        demand_score = 48

    if supply_ratio is None:
        market_balance = "Active Data Unavailable"
        balance_score = 62
    elif supply_ratio < 0.8:
        market_balance = "Tight Market"
        balance_score = 90
    elif supply_ratio < 1.5:
        market_balance = "Balanced Market"
        balance_score = 74
    else:
        market_balance = "Crowded Market"
        balance_score = 46

    if volatility < 0.20:
        price_consistency = "Very Consistent"
        stability_score = 90
    elif volatility < 0.40:
        price_consistency = "Mostly Consistent"
        stability_score = 76
    elif volatility < 0.65:
        price_consistency = "Inconsistent"
        stability_score = 58
    else:
        price_consistency = "Highly Unstable"
        stability_score = 34

    if volatility < 0.35 and (supply_ratio is None or supply_ratio < 1.5):
        risk_level = "LOW"
    elif volatility < 0.75:
        risk_level = "MODERATE"
    else:
        risk_level = "HIGH"

    sold_score = min(sold_count * 5, 100)
    active_viability_score = 75 if active_count > 0 else 55

    liquidity_score = round(
        (sold_score * 0.35) +
        (balance_score * 0.30) +
        (stability_score * 0.20) +
        (active_viability_score * 0.15)
    )

    if liquidity_score >= 88:
        liquidity_label = "Very Strong"
    elif liquidity_score >= 74:
        liquidity_label = "Strong"
    elif liquidity_score >= 60:
        liquidity_label = "Moderate"
    elif liquidity_score >= 45:
        liquidity_label = "Weak"
    else:
        liquidity_label = "Very Weak"

    confidence = min(sold_count * 2, 100)

    supply_penalty = 0
    if supply_ratio is not None:
        supply_penalty = min(supply_ratio * 32, 100)

    buy_score = round(
        (liquidity_score * 0.36) +
        (confidence * 0.20) +
        ((100 - min(volatility * 100, 100)) * 0.20) +
        ((100 - supply_penalty) * 0.10) +
        (demand_score * 0.14)
    )

    if buy_score >= 85:
        buy_label = "Strong Buy"
    elif buy_score >= 70:
        buy_label = "Good Buy"
    elif buy_score >= 55:
        buy_label = "Borderline"
    else:
        buy_label = "Pass / Risky"

    condition_impact_percent = round((multiplier - 1.0) * 100, 2)
    spread_low_to_high = round(sold_high - sold_low, 2)
    est_margin_dollars = round(sell_target - max_buy, 2)
    roi_percent = round(((sell_target - max_buy) / max_buy) * 100, 1) if max_buy else 0

    trend_label, trend_strength = calc_trend_label(sold_prices)
    sell_through_rate, sell_through_label = calc_sell_through(sold_count, active_count)
    flip_speed, flip_speed_score = calc_flip_speed(
        sell_through_rate=sell_through_rate,
        liquidity_score=liquidity_score,
        volatility=volatility,
        sold_count=sold_count,
    )

    ask_value = None
    if asking_price not in (None, "", " "):
        try:
            ask_value = float(asking_price)
        except Exception:
            ask_value = None

    sniper_gap, sniper_gap_percent, sniper_label = calc_sniper(ask_value, max_buy)

    q1 = percentile(sold_prices, 0.25)
    q2 = percentile(sold_prices, 0.50)
    q3 = percentile(sold_prices, 0.75)

    return {
        "sold_median": round(sold_median, 2),
        "sold_low": round(sold_low, 2),
        "sold_high": round(sold_high, 2),
        "active_median": round(active_median, 2) if active_median is not None else None,
        "max_buy": round(max_buy, 2),
        "sell_target": round(sell_target, 2),
        "fast_cash": round(fast_cash, 2),
        "market_price": round(market_price, 2),
        "hold_price": round(hold_price, 2),
        "confidence": confidence,
        "sold_count": sold_count,
        "active_count": active_count,
        "market_balance": market_balance,
        "demand_label": demand_label,
        "demand_score": demand_score,
        "price_consistency": price_consistency,
        "stability_score": stability_score,
        "risk_level": risk_level,
        "liquidity_score": liquidity_score,
        "liquidity_label": liquidity_label,
        "condition_impact_percent": condition_impact_percent,
        "buy_score": buy_score,
        "buy_label": buy_label,
        "flip_speed": flip_speed,
        "flip_speed_score": flip_speed_score,
        "volatility_percent": round(volatility * 100, 1),
        "supply_ratio": round(supply_ratio, 2) if supply_ratio is not None else None,
        "spread_low_to_high": spread_low_to_high,
        "estimated_margin": est_margin_dollars,
        "roi_percent": roi_percent,
        "local_factor_percent": round(local_factor * 100, 1),
        "sell_through_rate": sell_through_rate,
        "sell_through_label": sell_through_label,
        "trend_label": trend_label,
        "trend_strength": trend_strength,
        "sniper_gap": sniper_gap,
        "sniper_gap_percent": sniper_gap_percent,
        "sniper_label": sniper_label,
        "asking_price": ask_value,
        "q1": round(q1, 2),
        "q2": round(q2, 2),
        "q3": round(q3, 2),
    }