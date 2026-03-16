import random
import threading

from config import KEYWORDS, KEYWORDS_PER_CYCLE

_lock = threading.Lock()
_state = {}


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

        batch = []
        for _ in range(min(KEYWORDS_PER_CYCLE, len(keywords))):
            batch.append(keywords[cursor])
            cursor += 1
            if cursor >= len(keywords):
                cursor = 0
                random.shuffle(keywords)

        stream["cursor"] = cursor
        return batch