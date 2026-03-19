from ebay import search_ebay
from market_analysis import analyze_market
from datetime import datetime


def fetch_temu_items(seed_items=None, should_continue=None):
    seed_items = seed_items or []
    results = []

    for item in seed_items:
        if callable(should_continue) and not should_continue():
            break

        query = (item.get("query") or item.get("label") or item.get("title") or "Temu Flip").strip()
        asking_price = float(item.get("asking_price") or item.get("buy_price") or item.get("price") or 0)

        if asking_price <= 0:
            continue

        sold_prices, active_prices, _suggestions, listing = search_ebay(query)
        if not sold_prices:
            results.append({
                "title": item.get("title") or query,
                "label": item.get("label") or query,
                "query": query,
                "price": asking_price,
                "buy_price": asking_price,
                "avg_price": asking_price * 1.4,
                "market_price": asking_price * 1.4,
                "net_after_fees": asking_price * 1.15,
                "profit": round((asking_price * 1.15) - asking_price, 2),
                "roi": 15.0,
                "sell_through": 25,
                "sell_through_pct": 25,
                "source": "temu-fallback",
                "timestamp": datetime.utcnow().isoformat(),
                "image": "",
                "image_url": "",
                "ebay_url": ""
            })
            continue

        analysis = analyze_market(
            sold_prices,
            active_prices,
            "A",
            0.30,
            0.82,
            asking_price=asking_price,
        )
        if not analysis:
            continue

        market_price = round(float(analysis.get("market_price") or 0), 2)
        fees = round(float(analysis.get("estimated_fees") or 0), 2)
        shipping_cost = round(float(analysis.get("estimated_shipping") or 0), 2)
        net_after_fees = round(float(analysis.get("net_sale_estimate") or 0), 2)
        profit = round(float(analysis.get("profit_delta") or 0), 2)
        roi = round((profit / asking_price) * 100, 1) if asking_price > 0 else 0.0
        sell_through_pct = int(analysis.get("sell_through") or 0)
        gross_profit = round(max(market_price - asking_price, 0), 2)

        results.append({
            "title": item.get("title") or query,
            "label": item.get("label") or query,
            "query": query,
            "category": item.get("category") or "temu-flip",
            "price": asking_price,
            "asking_price": asking_price,
            "buy_price": asking_price,
            "estimated_value": market_price,
            "market_price": market_price,
            "average_sale_price": market_price,
            "avg_price": market_price,
            "gross_profit": gross_profit,
            "fees": fees,
            "shipping_cost": shipping_cost,
            "net_after_fees": net_after_fees,
            "profit": profit,
            "roi": roi,
            "sell_through": sell_through_pct,
            "sell_through_pct": sell_through_pct,
            "score": round((max(profit, 0) * 2.0) + (sell_through_pct * 0.4), 2),
            "source": "temu",
            "timestamp": datetime.utcnow().isoformat(),
            "image": (listing or {}).get("image", "") if isinstance(listing, dict) else "",
            "image_url": (listing or {}).get("image", "") if isinstance(listing, dict) else "",
            "ebay_url": (listing or {}).get("url", "") if isinstance(listing, dict) else "",
        })

    if not results:
        return seed_items
    return results
