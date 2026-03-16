import os
import requests
import time

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")

recent_alerts = set()


def send_discord_alert(deal):

    if not WEBHOOK_URL:
        print("Discord webhook missing")
        return

    title = deal.get("title", "")
    price = deal.get("price", 0)
    link = deal.get("link", "") or deal.get("url", "")

    key = f"{title}_{price}_{link}"

    if key in recent_alerts:
        return

    recent_alerts.add(key)

    message = f"""
🔥 DEAL FOUND

{title}

Price: ${price}
Value: ${deal.get("market_value") or deal.get("resale")}
Profit: ${deal.get("profit")}

{link}
"""

    try:
        r = requests.post(WEBHOOK_URL, json={"content": message}, timeout=10)

        if r.status_code == 429:
            time.sleep(2)

        print("Discord alert sent:", title)

    except Exception as e:
        print("Discord alert failed:", e)

    time.sleep(0.5)