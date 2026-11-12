"""Pick the receipt reader you chose in Settings.

To add a provider: write a class with extract(jpeg, categories) -> dict,
add it to PROVIDERS and to make_extractor().
"""
import os

from ..db import get_setting
from .base import ExtractionError, normalize

PROVIDERS = [
    {
        "id": "claude", "label": "Claude (Anthropic)", "default_model": "claude-haiku-5-5",
        "key_setting": "claude_api_key", "key_env": "ANTHROPIC_API_KEY",
        "note": "Accurate. Paid per use (about 2¢ per 100 receipts on Haiku).",
    },
    {
        "id": "gemini", "label": "Gemini (Google)", "default_model": "gemini-flash-latest",
        "key_setting": "gemini_api_key", "key_env": "GEMINI_API_KEY",
        "note": "Has a free tier. Free-tier data may be used by Google; check their terms.",
    },
    {
        "id": "ollama", "label": "Local model (Ollama)", "default_model": "qwen2.5vl",
        "key_setting": None, "key_env": None,
        "note": "Free and private. Needs Ollama installed and a strong PC. Slower.",
    },
    {
        "id": "manual", "label": "None (type it in myself)", "default_model": "",
        "key_setting": None, "key_env": None,
        "note": "No AI. You fill in vendor, date and total.",
    },
]
PROVIDER_IDS = {p["id"] for p in PROVIDERS}


def _key(conn, provider):
    p = next(p for p in PROVIDERS if p["id"] == provider)
    if p["key_env"] and os.environ.get(p["key_env"]):
        return os.environ[p["key_env"]]
    return get_setting(conn, p["key_setting"]) if p["key_setting"] else None


def current_provider(conn) -> str:
    prov = get_setting(conn, "provider", "claude")
    return prov if prov in PROVIDER_IDS else "claude"


def make_extractor(conn):
    provider = current_provider(conn)
    model = get_setting(conn, f"{provider}_model") or None
    if provider == "claude":
        from .claude import ClaudeExtractor
        return ClaudeExtractor(api_key=_key(conn, "claude"), model=model)
    if provider == "gemini":
        from .gemini import GeminiExtractor
        return GeminiExtractor(api_key=_key(conn, "gemini"), model=model)
    if provider == "ollama":
        from .ollama import OllamaExtractor
        return OllamaExtractor(url=get_setting(conn, "ollama_url"), model=model)
    return None


def extract_receipt(conn, jpeg: bytes, categories: list[str]) -> tuple[dict, str, str | None]:
    """Returns (data, provider_used, error_message)."""
    provider = current_provider(conn)
    if provider == "manual":
        return normalize({}), provider, None
    try:
        extractor = make_extractor(conn)
        return normalize(extractor.extract(jpeg, categories)), provider, None
    except ExtractionError as e:
        return normalize({}), provider, str(e)
    except Exception as e:  # noqa: BLE001 - never lose an upload because a reader crashed
        return normalize({}), provider, f"Unexpected error from {provider}: {e}"


def has_key(conn, provider: str) -> bool:
    return bool(_key(conn, provider))
