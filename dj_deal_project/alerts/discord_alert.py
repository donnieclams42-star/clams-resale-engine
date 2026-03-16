
import os
import requests
import time

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")
recent_alerts = set()


def _post_message(message: str) -> None:
    if not WEBHOOK_URL:
        print("Discord webhook missing")
        return
    r = requests.post(WEBHOOK_URL, json={"content": message}, timeout=10)
    if r.status_code == 429:
        time.sleep(2)
        r = requests.post(WEBHOOK_URL, json={"content": message}, timeout=10)
    r.raise_for_status()


def send_discord_alert(deal):
    title = str(deal.get("title", "")).strip()
    price = deal.get("price", 0)
    link = deal.get("link", "") or deal.get("url", "")
    key = f"{title}_{price}_{link}"
    if key in recent_alerts:
        return False
    recent_alerts.add(key)
    message = f"""
🔥 DEAL FOUND

{title}

Price: ${price}
Value: ${deal.get("market_value") or deal.get("resale")}
Profit: ${deal.get("profit")}
Confidence: {deal.get("confidence", "n/a")}
Source: {deal.get("source") or deal.get("market") or ""}

{link}
"""
    _post_message(message)
    print("Discord alert sent:", title)
    time.sleep(0.5)
    return True


def send_test_discord_alert():
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    message = f"✅ CLAMS Radar test notification\n\nIf you see this, Discord alerts are connected.\n\n{stamp}"
    _post_message(message)
    print("Discord test alert sent")
    return True
