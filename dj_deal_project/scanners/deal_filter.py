# DEAL FILTER MODULE

MAX_PRICE = 100  # anything under this = deal

def filter_deals(items):
    deals = []

    for item in items:
        try:
            price = float(item.get("price", 9999))

            if price <= MAX_PRICE:
                deals.append(item)

        except:
            continue

    return deals


def process_and_print_deals(results):
    deals = filter_deals(results)

    print(f"[DEALS FOUND] {len(deals)}")

    for d in deals:
        print(f"{d.get('title')} - ${d.get('price')} - {d.get('url')}")

    return deals
