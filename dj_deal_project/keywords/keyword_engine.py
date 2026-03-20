
from .search_terms import SEARCH_TERMS
import random

def get_keywords_for_cycle(source="default", count=10):
    pool = SEARCH_TERMS.get(source, []) + SEARCH_TERMS.get("default", [])
    if not pool:
        return []
    random.shuffle(pool)
    return pool[:count]
