def generate_misspellings(word):

    variations = set()

    word = word.lower()
    variations.add(word)

    # swapped letters
    for i in range(len(word) - 1):
        swapped = list(word)
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        variations.add("".join(swapped))

    # missing letters
    for i in range(len(word)):
        variations.add(word[:i] + word[i + 1:])

    # duplicate letters
    for i in range(len(word)):
        variations.add(word[:i] + word[i] + word[i] + word[i + 1:])

    return list(variations)