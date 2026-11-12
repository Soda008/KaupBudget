"""Placeholder for a live US Bank connection (likely through Plaid or SimpleFIN).

Decide the route later; whichever it is only needs to return rows in the shape
described in bank/__init__.py and call ingest().
"""


def fetch_transactions(since: str) -> list[dict]:
    raise NotImplementedError("Live bank sync isn't set up yet. Use CSV import for now.")
