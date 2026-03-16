def evaluate_profit(deal):

    price = deal.get("price")
    resale = deal.get("resale")

    if price is None or resale is None:
        return None

    try:
        price = float(price)
        resale = float(resale)
    except:
        return None

    # prevent zero / negative values
    if price <= 0 or resale <= 0:
        return None

    # sanity cap (prevents $100 → $8000 bugs)
    if resale > price * 6:
        return None

    profit = resale - price

    # minimum profit rule
    if profit < 30:
        return None

    # minimum margin rule (25%)
    margin = profit / price
    if margin < 0.25:
        return None

    deal["profit"] = round(profit, 2)
    deal["score"] = round(margin, 2)

    return deal