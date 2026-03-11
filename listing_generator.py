def clean_title(query: str) -> str:
    query = (query or "").strip()
    if not query:
        return "Item"
    return " ".join(word.capitalize() for word in query.split())


def clean_condition(condition: str) -> str:
    condition_map = {
        "A": "Excellent",
        "B": "Good",
        "C": "Fair",
        "Parts": "For Parts / Repair",
    }
    return condition_map.get(condition, condition or "Used")


def fb_listing(query: str, condition: str, price: float) -> dict:
    base_title = clean_title(query)
    condition_text = clean_condition(condition)

    title = f"{base_title} - {condition_text}"

    description = (
        f"{base_title}\n\n"
        f"Condition: {condition_text}\n\n"
        f"Fully tested and working.\n"
        f"Pickup available.\n"
        f"Shipping available."
    )

    return {
        "platform": "Facebook Marketplace",
        "title": title[:100],
        "price": round(float(price), 2),
        "description": description.strip(),
    }


def ebay_listing(query: str, condition: str, price: float) -> dict:
    base_title = clean_title(query)
    condition_text = clean_condition(condition)

    title = f"{base_title} | {condition_text} | Tested"

    description = (
        f"{base_title}\n\n"
        f"Condition: {condition_text}\n\n"
        f"Tested and fully functional.\n"
        f"Ships fast.\n"
        f"Shipping available."
    )

    return {
        "platform": "eBay",
        "title": title[:80],
        "price": round(float(price), 2),
        "description": description.strip(),
    }