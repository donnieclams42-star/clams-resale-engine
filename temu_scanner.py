import json
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from ebay import search_ebay
from market_analysis import analyze_market

TEMU_TIMEOUT = int(os.getenv("TEMU_HTTP_TIMEOUT", "25"))
TEMU_MAX_RESULTS = int(os.getenv("TEMU_MAX_RESULTS", "30"))
TEMU_MAX_ITEMS_PER_QUERY = int(os.getenv("TEMU_MAX_ITEMS_PER_QUERY", "8"))
MIN_PROFIT = float(os.getenv("TEMU_MIN_PROFIT", "4"))
MIN_SELL_THROUGH = int(os.getenv("TEMU_MIN_SELL_THROUGH", "10"))
MEMORY_FILE = os.getenv("TEMU_MEMORY_FILE", "temu_keyword_memory.json")

BLOCK_KEYWORDS = [
    "case", "cover", "accessory", "replacement", "for parts", "manual", "sticker", "decal",
    "shirt", "hoodie", "hat", "bag", "sock", "wig", "nail", "pillow cover",
]

DEFAULT_TEMU_SEEDS = [
    {"query": "car vacuum portable", "label": "Auto Gadgets", "category": "car gadgets"},
    {"query": "led strip lights", "label": "LED Lights", "category": "home gadgets"},
    {"query": "under cabinet lights motion sensor", "label": "Lighting", "category": "home gadgets"},
    {"query": "drawer organizer set", "label": "Organizers", "category": "home gadgets"},
    {"query": "wireless mouse rechargeable", "label": "Desk Gear", "category": "office"},
    {"query": "mini label printer", "label": "Desk Gear", "category": "office"},
    {"query": "pet grooming glove", "label": "Pet Items", "category": "pet"},
    {"query": "air fryer liners", "label": "Kitchen", "category": "kitchen"},
    {"query": "portable blender", "label": "Kitchen", "category": "kitchen"},
    {"query": "magnetic phone mount", "label": "Car Gadgets", "category": "car gadgets"},
    {"query": "cable organizer", "label": "Desk Accessories", "category": "office"},
    {"query": "resistance bands set", "label": "Fitness", "category": "fitness"},
    {"query": "solar garden lights", "label": "Outdoor", "category": "outdoor"},
    {"query": "makeup organizer", "label": "Beauty", "category": "beauty"},
    {"query": "phone tripod", "label": "Creator Tools", "category": "creator"},
    {"query": "bluetooth speaker mini", "label": "Audio", "category": "electronics"},
    {"query": "usb desk fan", "label": "Mini Gadgets", "category": "home gadgets"},
    {"query": "vacuum storage bags", "label": "Storage", "category": "home gadgets"},
    {"query": "car seat gap organizer", "label": "Auto Gadgets", "category": "car gadgets"},
    {"query": "wireless earbuds", "label": "Audio", "category": "electronics"},
]

TEMU_HEADERS = {
    "User-Agent": os.getenv("TEMU_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

EXPANSIONS = ["cheap", "mini", "portable", "wireless", "rechargeable", "set"]


def build_temu_seed_items():
    return [dict(item) for item in DEFAULT_TEMU_SEEDS]


def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_memory(mem):
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(mem, f, indent=2)
    except Exception:
        pass


def is_junk(title):
    t = (title or '').lower()
    return any(k in t for k in BLOCK_KEYWORDS)


def expand_query(query, memory):
    queries = [query]
    for word in EXPANSIONS:
        queries.append(f"{query} {word}")
    if query in memory:
        queries.extend(memory[query].get('expansions', []))
    seen = set()
    out = []
    for q in queries:
        s = q.strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def update_memory(memory, base_query, query, profit, sell_through):
    memory.setdefault(base_query, {"expansions": [], "score": 0})
    score = profit + (sell_through * 0.2)
    if score > 10 and query not in memory[base_query]["expansions"]:
        memory[base_query]["expansions"].append(query)
    memory[base_query]["score"] += score


def _extract_price(text: str):
    if not text:
        return None
    m = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except Exception:
        return None


def _clean_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith('http'):
        return href
    return f"https://www.temu.com{href}"


def _parse_anchor_products(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a.get('href') or ''
        if '/goods.html' not in href and 'goods_id=' not in href and '/search_result.html' not in href:
            continue
        link = _clean_url(href)
        text = ' '.join(a.stripped_strings)
        price = _extract_price(text)
        title = re.sub(r'\s+', ' ', text).strip()
        if not title or not price or price <= 0:
            continue
        if link in seen or is_junk(title):
            continue
        seen.add(link)
        products.append({
            'title': title,
            'price': round(float(price), 2),
            'url': link,
            'image': '',
        })
        if len(products) >= TEMU_MAX_ITEMS_PER_QUERY:
            break
    return products


def _search_temu(query: str):
    search_url = f"https://www.temu.com/search_result.html?search_key={quote_plus(query)}"
    try:
        r = requests.get(search_url, headers=TEMU_HEADERS, timeout=TEMU_TIMEOUT)
        r.raise_for_status()
    except Exception:
        return []
    return _parse_anchor_products(r.text)


def _fallback_market_numbers(asking_price: float):
    avg_sell = round(max(asking_price * 2.2, asking_price + 6), 2)
    fees = round(avg_sell * 0.13, 2)
    shipping = 5.0
    net = round(avg_sell - fees - shipping, 2)
    profit = round(net - asking_price, 2)
    return avg_sell, fees, shipping, net, profit


def fetch_temu_items(seed_items=None, should_continue: Callable[[], bool] | None = None):
    seed_items = seed_items or build_temu_seed_items()
    results = []
    memory = load_memory()
    seen_links = set()

    for seed in seed_items:
        if callable(should_continue) and not should_continue():
            break
        base_query = (seed.get('query') or seed.get('label') or seed.get('title') or 'Temu').strip().lower()
        for query in expand_query(base_query, memory):
            if callable(should_continue) and not should_continue():
                break
            if is_junk(query):
                continue
            products = _search_temu(query)
            if not products:
                continue
            for product in products:
                if product['url'] in seen_links:
                    continue
                seen_links.add(product['url'])
                asking_price = float(product.get('price') or 0)
                if asking_price <= 0:
                    continue
                sold_prices, active_prices, _suggestions, listing = search_ebay(product['title'])
                analysis = None
                if sold_prices:
                    analysis = analyze_market(sold_prices, active_prices, 'A', 0.30, 0.82, asking_price=asking_price)
                if analysis:
                    avg_sell = round(float(analysis.get('market_price') or 0), 2)
                    fees = round(float(analysis.get('estimated_fees') or (avg_sell * 0.13)), 2)
                    shipping_cost = round(float(analysis.get('estimated_shipping') or 5.0), 2)
                    net_after_fees = round(float(analysis.get('net_sale_estimate') or (avg_sell - fees - shipping_cost)), 2)
                    profit = round(float(analysis.get('profit_delta') or (net_after_fees - asking_price)), 2)
                    sell_through_pct = int(analysis.get('sell_through') or 0)
                    confidence = 'HIGH' if profit >= 12 and sell_through_pct >= 35 else 'MEDIUM' if profit >= MIN_PROFIT else 'LOW'
                else:
                    avg_sell, fees, shipping_cost, net_after_fees, profit = _fallback_market_numbers(asking_price)
                    sell_through_pct = 0
                    confidence = 'LOW'
                if profit < MIN_PROFIT and analysis:
                    continue
                if sell_through_pct < MIN_SELL_THROUGH and analysis:
                    continue
                update_memory(memory, base_query, query, profit, sell_through_pct)
                ebay_url = listing.get('url') if isinstance(listing, dict) else ''
                ebay_image = listing.get('image') if isinstance(listing, dict) else ''
                results.append({
                    'title': product.get('title') or query.title(),
                    'label': seed.get('label') or query.title(),
                    'query': query,
                    'category': seed.get('category') or 'temu-flip',
                    'price': asking_price,
                    'asking_price': asking_price,
                    'buy_price': asking_price,
                    'avg_price': avg_sell,
                    'avg_sell_price': avg_sell,
                    'average_sale_price': avg_sell,
                    'market_price': avg_sell,
                    'market_value': avg_sell,
                    'fees': fees,
                    'estimated_fees': fees,
                    'shipping_cost': shipping_cost,
                    'estimated_shipping': shipping_cost,
                    'net_after_fees': net_after_fees,
                    'net_sale_estimate': net_after_fees,
                    'profit': profit,
                    'gross_profit': round(max(avg_sell - asking_price, 0), 2),
                    'roi': round((profit / asking_price) * 100, 1) if asking_price > 0 else 0.0,
                    'sell_through_pct': sell_through_pct,
                    'sell_through': sell_through_pct,
                    'confidence': confidence,
                    'source': 'Temu',
                    'temu_url': product.get('url', ''),
                    'temu_search_url': f"https://www.temu.com/search_result.html?search_key={quote_plus(query)}",
                    'ebay_url': ebay_url,
                    'display_image': product.get('image') or ebay_image or '',
                    'image': product.get('image') or ebay_image or '',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'score': round((profit * 3) + sell_through_pct, 2),
                })
                if len(results) >= TEMU_MAX_RESULTS:
                    save_memory(memory)
                    return sorted(results, key=lambda x: (x.get('score', 0), x.get('profit', 0)), reverse=True)[:TEMU_MAX_RESULTS]
            time.sleep(random.uniform(0.5, 1.5))
    save_memory(memory)
    return sorted(results, key=lambda x: (x.get('score', 0), x.get('profit', 0)), reverse=True)[:TEMU_MAX_RESULTS]
