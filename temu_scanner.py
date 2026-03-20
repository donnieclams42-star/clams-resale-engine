
from ebay import search_ebay
from market_analysis import analyze_market
from datetime import datetime
import json
import random

# --- CONFIG ---
MIN_PROFIT = 2
MIN_SELL_THROUGH = 5
MEMORY_FILE = "temu_keyword_memory.json"

EXPANSIONS = ["cheap","budget","portable","mini","wireless","usb","kit","set"]

BLOCK_KEYWORDS = ["case","cover","accessory","replacement","for parts","manual","sticker"]

def load_memory():
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_memory(mem):
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2)

def is_junk(title):
    t = (title or "").lower()
    return any(k in t for k in BLOCK_KEYWORDS)

def expand_query(query, memory):
    queries = [query]

    # base expansions
    for word in EXPANSIONS:
        queries.append(f"{query} {word}")

    # adaptive expansions from memory
    if query in memory:
        learned = memory[query].get("expansions", [])
        queries.extend(learned)

    return list(set(queries))

def update_memory(memory, base_query, query, profit, sell_through):
    if base_query not in memory:
        memory[base_query] = {"expansions": [], "score": 0}

    score = profit + (sell_through * 0.2)

    if score > 10:
        if query not in memory[base_query]["expansions"]:
            memory[base_query]["expansions"].append(query)

    memory[base_query]["score"] += score

def fetch_temu_items(seed_items=None, should_continue=None):
    seed_items = seed_items or []
    results = []
    memory = load_memory()

    for item in seed_items:
        if callable(should_continue) and not should_continue():
            break

        base_query = (item.get("query") or item.get("label") or item.get("title") or "Temu Flip").strip()

        expanded_queries = expand_query(base_query, memory)

        for query in expanded_queries:

            if is_junk(query):
                continue

            asking_price = float(item.get("asking_price") or item.get("buy_price") or item.get("price") or 0)
            if asking_price <= 0:
                continue

            sold_prices, active_prices, _suggestions, listing = search_ebay(query)

            if not sold_prices:
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

            profit = float(analysis.get("profit_delta") or 0)
            sell_through_pct = int(analysis.get("sell_through") or 0)

            low_confidence = False
            if profit < MIN_PROFIT:
                low_confidence = True

            if sell_through_pct < MIN_SELL_THROUGH:
                low_confidence = True

            update_memory(memory, base_query, query, profit, sell_through_pct)

            market_price = round(float(analysis.get("market_price") or 0), 2)

            if not market_price:
                market_price = asking_price * 1.3

            fees = round(market_price * 0.13, 2)
            shipping_cost = 5.0
            net_after_fees = round(market_price - fees - shipping_cost, 2)
            profit = round(net_after_fees - asking_price, 2)

            fees = round(float(analysis.get("estimated_fees") or 0), 2)
            shipping_cost = round(float(analysis.get("estimated_shipping") or 0), 2)
            net_after_fees = round(float(analysis.get("net_sale_estimate") or 0), 2)
            profit = round(profit, 2)
            roi = round((profit / asking_price) * 100, 1) if asking_price > 0 else 0.0
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
                "image": (listing or {}).get("image") if isinstance(listing, dict) else "",
                "image_url": (listing or {}).get("image") if isinstance(listing, dict) else "",
                "ebay_url": (listing or {}).get("url", "") if isinstance(listing, dict) else "",
                "temu_url": item.get("url") or item.get("link") or "",
            })

    save_memory(memory)

    if not results:
        return seed_items

    return results
