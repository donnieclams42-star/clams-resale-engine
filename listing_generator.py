import re


def detect_category(query: str):

    q = query.lower()

    if any(word in q for word in ["ps4","ps5","xbox","nintendo","console","gamecube","switch"]):
        return "Video Games & Consoles"

    if any(word in q for word in ["iphone","android","samsung","phone"]):
        return "Cell Phones"

    if any(word in q for word in ["card","pokemon","baseball","basketball","trading card"]):
        return "Trading Cards"

    if any(word in q for word in ["tool","drill","dewalt","milwaukee","toolbox"]):
        return "Tools"

    if any(word in q for word in ["tv","monitor","electronics","speaker","radio"]):
        return "Electronics"

    return "General Merchandise"


def clean_title(query: str):

    title = query.strip()

    title = re.sub(r"\s+", " ", title)

    return title.title()


def assist_title(query: str, platform: str):

    base = clean_title(query)

    if platform == "facebook":
        return f"{base} – Tested Working"

    if platform == "ebay":
        return f"{base} – Fast Shipping"

    if platform == "mercari":
        return f"{base} – Great Condition"

    if platform == "offerup":
        return f"{base} – Local Pickup"

    return base


def assist_description(query: str, platform: str):

    base = f"{clean_title(query)} in good working condition."

    if platform == "facebook":
        return f"""{base}

Fully tested and ready to use.

Local pickup available.
Shipping available.
"""

    if platform == "ebay":
        return f"""{base}

Ships fast and packaged safely.

Feel free to message with any questions.
"""

    if platform == "mercari":
        return f"""{base}

Clean item and ships quickly.
"""

    if platform == "offerup":
        return f"""{base}

Local pickup preferred.
"""

    return base


def generate_platform_listing(query, platform, fast_price, market_price):

    category = detect_category(query)

    title = assist_title(query, platform)

    description = assist_description(query, platform)

    price = round(market_price)

    return {
        "platform": platform,
        "title": title,
        "price": price,
        "description": description,
        "category": category
    }


def generate_listings(query, condition, fast_price, market_price, platforms=None):

    if platforms is None:
        platforms = ["facebook", "ebay"]

    listings = {}

    for platform in platforms:

        listing = generate_platform_listing(
            query,
            platform,
            fast_price,
            market_price
        )

        listings[platform] = listing

    return listings