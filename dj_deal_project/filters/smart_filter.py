# SMART DEAL FILTER (CLAMS STYLE LIGHT)

def estimate_value(title):
    title = title.lower()

    if "iphone" in title:
        return 300
    if "ipad" in title:
        return 250
    if "macbook" in title:
        return 500
    if "playstation" in title or "ps5" in title:
        return 400
    if "xbox" in title:
        return 300
    if "tool" in title:
        return 150
    if "lot" in title:
        return 200

    return 100  # fallback


def filter_smart_deals(items):
    deals = []

    for item in items:
        try:
            price = float(item.get("price", 9999))
            title = item.get("title", "")

            est_value = estimate_value(title)

            # PROFIT LOGIC
            if price <= (est_value * 0.4):
                profit = est_value - price

                deals.append({
                    "title": title,
                    "price": price,
                    "est_value": est_value,
                    "profit": profit,
                    "url": item.get("url")
                })

        except:
            continue

    return deals


def process_smart_deals(results):
    deals = filter_smart_deals(results)

    print(f"[SMART DEALS] {len(deals)}")

    for d in deals:
        print(f"{d['title']} | BUY ${d['price']} → SELL ${d['est_value']} | PROFIT ${d['profit']}")
        print(d['url'])
        print("-----")

    return deals
