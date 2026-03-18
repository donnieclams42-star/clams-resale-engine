import random
import threading

from config import (
    KEYWORDS,
    EBAY_KEYWORDS,
    MERCARI_KEYWORDS,
    OFFERUP_KEYWORDS,
    FACEBOOK_KEYWORDS,
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


def _keywords_for_stream(stream_name: str) -> list[str]:
    name = (stream_name or "default").lower()
    if name == "ebay" and EBAY_KEYWORDS:
        return EBAY_KEYWORDS
    if name == "mercari" and MERCARI_KEYWORDS:
        return MERCARI_KEYWORDS
    if name == "offerup" and OFFERUP_KEYWORDS:
        return OFFERUP_KEYWORDS
    if name == "facebook" and FACEBOOK_KEYWORDS:
        return FACEBOOK_KEYWORDS
    return KEYWORDS


def get_keywords_for_cycle(stream_name: str = "default") -> list[str]:
    keywords = _keywords_for_stream(stream_name)
    if not keywords:
        return []

    with _lock:
        state_key = (stream_name or "default").lower()
        if state_key not in _state or _state[state_key].get("source_size") != len(keywords):
            shuffled = list(keywords)
            random.shuffle(shuffled)
            _state[state_key] = {
                "keywords": shuffled,
                "cursor": 0,
                "source_size": len(keywords),
            }

        stream = _state[state_key]
        local_keywords = stream["keywords"]
        cursor = stream["cursor"]
        batch_size = min(_batch_size_for_stream(state_key), len(local_keywords))

        batch = []
        for _ in range(batch_size):
            batch.append(local_keywords[cursor])
            cursor += 1
            if cursor >= len(local_keywords):
                cursor = 0
                random.shuffle(local_keywords)

        stream["cursor"] = cursor
        return batch
