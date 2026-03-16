SUS_WORDS = [

    "deposit",
    "hold with deposit",
    "send deposit",
    "cashapp only",
    "zelle only",
    "venmo only",

    "shipping only",
    "no meetup",
    "no pick up",

    "icloud locked",
    "account locked",
    "activation locked",

    "for parts only no returns",

    "text me",
    "call this number",
    "contact outside facebook",

    "serious buyers only send deposit",

]

SUS_PHRASES = [

    "too good to be true",
    "urgent sale send money",
    "need deposit today",
]


def is_scam_listing(title):

    text = title.lower()

    for word in SUS_WORDS:

        if word in text:
            return True

    for phrase in SUS_PHRASES:

        if phrase in text:
            return True

    return False