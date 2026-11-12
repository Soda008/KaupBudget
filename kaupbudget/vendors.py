"""Turn messy vendor names into a stable key.

"WINCO FOODS #123 BOISE ID", "WinCo Foods" and "Winco Foods Inc" all become
"winco foods", so bank charges, receipts and past choices line up.
"""
import re
from difflib import SequenceMatcher

_PREFIXES = re.compile(r"^(sq|tst|pp|paypal|sp|py|pos|dd|ach|debit)\s*\*\s*", re.I)
_NOISE = {
    "the", "inc", "llc", "co", "corp", "company", "ltd", "store", "stores",
    "purchase", "pos", "debit", "card", "recurring", "payment",
}


def vendor_key(name: str) -> str:
    if not name:
        return ""
    s = _PREFIXES.sub("", name.strip())
    s = s.lower().replace("'", "")
    s = re.sub(r"[^a-z\s]", " ", s)          # drop digits/punctuation (store #s, card refs)
    words = [w for w in s.split() if w not in _NOISE and len(w) > 1]
    return " ".join(words[:2])


def first_word(key: str) -> str:
    return key.split(" ", 1)[0] if key else ""


def similarity(a: str, b: str) -> float:
    """0..1 how alike two vendor names are."""
    ka, kb = vendor_key(a), vendor_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if first_word(ka) == first_word(kb) and len(first_word(ka)) >= 3:
        return 0.85
    return SequenceMatcher(None, ka, kb).ratio()
