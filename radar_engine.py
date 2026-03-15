
# Radar Engine – Flip Speed + Market Signals

def quick_flip_score(sold_count, active_count, volatility=0):
    if active_count <= 0:
        active_count = 1

    sell_through = sold_count / active_count

    sell_score = min(sell_through * 60, 60)

    supply_score = max(0, 25 - (active_count * 0.5))

    volatility_score = max(0, 15 - volatility)

    score = sell_score + supply_score + volatility_score
    score = max(0, min(score, 100))

    if score >= 85:
        label = "INSTANT FLIP"
    elif score >= 65:
        label = "FAST FLIP"
    elif score >= 45:
        label = "GOOD FLIP"
    elif score >= 25:
        label = "SLOW FLIP"
    else:
        label = "AVOID"

    return round(score,1), label
