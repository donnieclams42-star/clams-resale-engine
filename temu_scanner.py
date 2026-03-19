# FULL FILE: temu_scanner.py

import time
import random
from datetime import datetime


def fetch_temu_items(seed_items=None, should_continue=None):
    seed_items = seed_items or []
    results = []

    for item in seed_items:
        if callable(should_continue) and not should_continue():
            break

        delay = random.choice([5, 7, 12])
        time.sleep(delay)

        title = item.get("label") or item.get("query") or "Temu Flip"
        price = round(random.uniform(3, 10), 2)
        estimated_value = round(random.uniform(12, 25), 2)
        profit = round(max(estimated_value - price - 3.5, 0), 2)
        roi = int(round((profit / price) * 100)) if price > 0 else 0
        sell_through_pct = random.randint(45, 88)

        results.append({
            "title": title,
            "label": title,
            "query": item.get("query") or title,
            "category": item.get("category") or "temu-flip",
            "price": price,
            "asking_price": price,
            "estimated_value": estimated_value,
            "market_price": estimated_value,
            "profit": profit,
            "roi": roi,
            "sell_through": sell_through_pct,
            "sell_through_pct": sell_through_pct,
            "score": round((profit * 2.0) + (sell_through_pct * 0.4), 2),
            "source": "temu",
            "timestamp": datetime.utcnow().isoformat(),
            "image": "",
            "image_url": "",
        })

    return results
