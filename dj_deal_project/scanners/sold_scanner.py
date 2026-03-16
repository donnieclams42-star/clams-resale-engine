import statistics

def clean_prices(prices):

    if len(prices) < 5:
        return prices

    prices = sorted(prices)

    trim = int(len(prices)*0.15)

    return prices[trim:-trim]


def median_price(prices):

    prices = clean_prices(prices)

    return round(statistics.median(prices),2)