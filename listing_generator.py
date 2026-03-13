def generate_listings(item, condition, fast_cash_price, market_price):

    facebook = {
        "title": f"{item} - {condition}",
        "price": round(fast_cash_price, 2),
        "description": f"""{item}

Condition: {condition}

Fully tested and working.
Pickup available.
Shipping available."""
    }

    ebay = {
        "title": f"{item} | {condition} | Tested",
        "price": round(market_price, 2),
        "description": f"""{item}

Condition: {condition}

Tested and fully functional.
Ships fast.
Shipping available."""
    }

    return {
        "facebook": facebook,
        "ebay": ebay
    }