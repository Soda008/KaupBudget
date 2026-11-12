"""Tiny JSON-over-HTTP helper (stdlib only) for providers without an SDK here."""
import json
import urllib.error
import urllib.request

from .base import ExtractionError


def post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ExtractionError(f"HTTP {e.code} from {url.split('?')[0]}: {detail}") from e
    except urllib.error.URLError as e:
        raise ExtractionError(f"Couldn't reach {url.split('?')[0]}: {e.reason}") from e
    except TimeoutError as e:
        raise ExtractionError("The AI took too long to respond.") from e
