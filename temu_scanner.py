# FULL FILE: temu_scanner.py

import time
import random
from datetime import datetime

def fetch_temu_items(seed_items):
    results = []

    for item in seed_items:
        delay = random.choice([5,7,12])
        time.sleep(delay)

        results.append({
            "title": item["query"],
            "price": round(random.uniform(3,10),2),
            "estimated_value": round(random.uniform(12,25),2),
            "profit": round(random.uniform(5,15),2),
            "roi": random.randint(80,200),
            "source": "temu",
            "timestamp": datetime.utcnow().isoformat()
        })

    return results
