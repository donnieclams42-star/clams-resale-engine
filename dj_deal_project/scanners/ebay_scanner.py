# 🔧 PATCHED ebay_scanner.py (NEW DEAL FILTERING ENABLED)

from utils.seen_deals import filter_new

def scan_ebay(*args, **kwargs):
    # --- ORIGINAL SCAN LOGIC SHOULD BE ABOVE THIS LINE ---
    # You should keep your existing scraping / API logic intact

    deals = []  # <-- your existing logic should populate this

    # ✅ FILTER ONLY NEW DEALS
    new_deals = filter_new(deals)

    return new_deals
