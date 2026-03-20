
import json, time, os

CACHE_FILE = "market_cache.json"
CACHE_TTL = 14400  # 4 hours

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return []
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_cache_valid():
    if not os.path.exists(CACHE_FILE):
        return False
    age = time.time() - os.path.getmtime(CACHE_FILE)
    return age < CACHE_TTL

def get_cached_results(source):
    data = load_cache()
    return [d for d in data if d.get("source") == source]

def update_cache(new_items):
    data = load_cache()
    existing_links = {d.get("link") for d in data}
    for item in new_items:
        if item.get("link") not in existing_links:
            item["timestamp"] = time.time()
            data.append(item)
    save_cache(data)
