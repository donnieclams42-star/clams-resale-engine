def supply_ratio(active_count, sold_count):

    if sold_count == 0:
        return 0

    return round(active_count / sold_count,2)


def confidence_score(sold_count, volatility):

    score = 50

    score += min(sold_count,20)

    score -= volatility

    score = max(0,min(100,score))

    return round(score,1)