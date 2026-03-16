HIGH_VALUE_SIGNALS = [
    "moving",
    "moving sale",
    "garage sale",
    "garage cleanout",
    "need gone",
    "must sell",
    "first come",
    "today only",
    "pickup today",
]

LOW_VALUE_SIGNALS = [
    "refurbished",
    "certified",
    "store",
    "shop",
    "bulk",
    "wholesale",
]


def analyze_seller(title):

    score = 50

    text = title.lower()

    for signal in HIGH_VALUE_SIGNALS:

        if signal in text:
            score += 20

    for signal in LOW_VALUE_SIGNALS:

        if signal in text:
            score -= 20

    if score > 100:
        score = 100

    if score < 0:
        score = 0

    return score