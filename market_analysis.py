
# FULL FILE REPLACEMENT

def analyze_market(title="", price=0):
    """
    Safe market analysis fallback so scanners never crash.
    """

    try:
        base_price = float(price or 0)

        if base_price <= 0:
            base_price = 5.0

        market_price = round(base_price * 2.2, 2)
        fees = round(market_price * 0.13, 2)
        shipping = 5.0
        net = round(market_price - fees - shipping, 2)
        profit = round(net - base_price, 2)

        return {
            "market_price": market_price,
            "avg_price": market_price,
            "estimated_fees": fees,
            "net_sale_estimate": net,
            "profit": profit,
            "sell_through": 25
        }

    except Exception as e:
        print("ANALYSIS ERROR:", e)
        return {
            "market_price": 0,
            "avg_price": 0,
            "estimated_fees": 0,
            "net_sale_estimate": 0,
            "profit": 0,
            "sell_through": 0
        }
