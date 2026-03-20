import statistics

def volatility(prices):

    if len(prices) < 2:
        return 0

    return round(statistics.stdev(prices),2)


def price_spread(prices):

    if not prices:
        return 0

    return round(max(prices) - min(prices),2)


def trend(prices):

    if len(prices) < 3:
        return "Unknown"

    if prices[-1] > prices[0]:
        return "Rising"

    if prices[-1] < prices[0]:
        return "Falling"

    return "Stable"