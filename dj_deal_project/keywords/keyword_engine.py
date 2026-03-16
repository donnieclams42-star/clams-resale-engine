
import random
import threading

from config import (
    KEYWORDS,
    DEFAULT_KEYWORDS_PER_CYCLE,
    EBAY_KEYWORDS_PER_CYCLE,
    MERCARI_KEYWORDS_PER_CYCLE,
    OFFERUP_KEYWORDS_PER_CYCLE,
    FACEBOOK_KEYWORDS_PER_CYCLE,
)

_lock = threading.Lock()
_state = {}


def _batch_size_for_stream(stream_name: str) -> int:
    name = (stream_name or "default").lower()
    if name == "ebay":
        return max(1, EBAY_KEYWORDS_PER_CYCLE)
    if name == "mercari":
        return max(1, MERCARI_KEYWORDS_PER_CYCLE)
    if name == "offerup":
        return max(1, OFFERUP_KEYWORDS_PER_CYCLE)
    if name == "facebook":
        return max(1, FACEBOOK_KEYWORDS_PER_CYCLE)
    return max(1, DEFAULT_KEYWORDS_PER_CYCLE)


def get_keywords_for_cycle(stream_name: str = "default") -> list[str]:
    if not KEYWORDS:
        return []

    with _lock:
        if stream_name not in _state:
            shuffled = KEYWORDS.copy()
            random.shuffle(shuffled)
            _state[stream_name] = {
                "keywords": shuffled,
                "cursor": 0,
            }

        stream = _state[stream_name]
        keywords = stream["keywords"]
        cursor = stream["cursor"]
        batch_size = min(_batch_size_for_stream(stream_name), len(keywords))

        batch = []
        for _ in range(batch_size):
            batch.append(keywords[cursor])
            cursor += 1
            if cursor >= len(keywords):
                cursor = 0
                random.shuffle(keywords)

        stream["cursor"] = cursor
        return batch
