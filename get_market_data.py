def get_market_data(query):

    token = get_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    params = {
        "q": query,
        "limit": 25
    }

    response = requests.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers=headers,
        params=params
    )

    data = response.json()

    items = data.get("itemSummaries", [])

    sold_prices = []
    sold_items = []

    for item in items:

        try:

            price = float(item["price"]["value"])

            sold_prices.append(price)

            sold_items.append({
                "title": item.get("title"),
                "image": item.get("image", {}).get("imageUrl"),
                "link": item.get("itemWebUrl")
            })

        except:
            pass

    return sold_prices, [], sold_items