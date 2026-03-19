# FULL FILE: temu_scanner.py

from datetime import datetime

def fetch_temu_items():
    return [
        {
            "title": "Temu Placeholder Item",
            "price": 5.0,
            "estimated_value": 15.0,
            "profit": 10.0,
            "roi": 200,
            "source": "temu",
            "timestamp": datetime.utcnow().isoformat()
        }
    ]
