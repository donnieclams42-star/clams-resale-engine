import hashlib
import random
from datetime import datetime, timezone

try:
    from dj_deal_project.keywords.search_terms import SEARCH_TERMS
    from dj_deal_project import config as cfg
except Exception:
    from keywords.search_terms import SEARCH_TERMS
    import config as cfg


def _dedupe(values):
    seen = set()
    out = []
    for value in values:
        item = str(value or '').strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _source_terms(source: str):
    source = (source or '').strip().lower()
    mapping = {
        'ebay': getattr(cfg, 'EBAY_KEYWORDS', SEARCH_TERMS),
        'mercari': getattr(cfg, 'MERCARI_KEYWORDS', SEARCH_TERMS),
        'offerup': getattr(cfg, 'OFFERUP_KEYWORDS', SEARCH_TERMS),
        'facebook': getattr(cfg, 'FACEBOOK_KEYWORDS', SEARCH_TERMS),
        'craigslist': getattr(cfg, 'FACEBOOK_KEYWORDS', SEARCH_TERMS),
        'temu': SEARCH_TERMS,
    }
    return _dedupe(mapping.get(source, SEARCH_TERMS))


def _per_cycle_for(source: str) -> int:
    source = (source or '').strip().lower()
    mapping = {
        'ebay': int(getattr(cfg, 'EBAY_KEYWORDS_PER_CYCLE', 16) or 16),
        'mercari': int(getattr(cfg, 'MERCARI_KEYWORDS_PER_CYCLE', 12) or 12),
        'offerup': int(getattr(cfg, 'OFFERUP_KEYWORDS_PER_CYCLE', 10) or 10),
        'facebook': int(getattr(cfg, 'FACEBOOK_KEYWORDS_PER_CYCLE', 8) or 8),
        'craigslist': int(getattr(cfg, 'KEYWORDS_PER_CYCLE', 8) or 8),
        'temu': max(60, int(getattr(cfg, 'KEYWORDS_PER_CYCLE', 24) or 24)),
    }
    return max(1, mapping.get(source, int(getattr(cfg, 'KEYWORDS_PER_CYCLE', 12) or 12)))


def get_keywords_for_cycle(source: str = '', full_scan: bool = False):
    terms = _source_terms(source)
    if not terms:
        return []
    if full_scan:
        return terms

    # Stable rotation through the list by hour + source.
    now = datetime.now(timezone.utc)
    cycle_key = f"{source}|{now.strftime('%Y-%m-%d-%H')}"
    seed = int(hashlib.sha256(cycle_key.encode('utf-8')).hexdigest()[:16], 16)
    rng = random.Random(seed)
    pool = terms[:]
    rng.shuffle(pool)
    count = min(len(pool), _per_cycle_for(source))
    return pool[:count]
