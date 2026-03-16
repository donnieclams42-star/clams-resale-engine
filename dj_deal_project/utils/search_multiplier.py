def generate_search_terms(base_terms):

    expanded = set()

    prefixes = [
        "",
        "broken ",
        "cracked ",
        "used ",
        "old ",
        "cheap ",
        "parts ",
    ]

    suffixes = [
        "",
        " parts",
        " broken",
        " cracked",
        " not working",
    ]

    for term in base_terms:

        for p in prefixes:
            for s in suffixes:

                new_term = f"{p}{term}{s}".strip()

                expanded.add(new_term)

    return list(expanded)