"""Read receipts with a local model through Ollama (free, private, needs a strong PC)."""
import base64

from .base import RECEIPT_SCHEMA, ExtractionError, Extractor, build_prompt, parse_json
from .http import post_json

DEFAULT_MODEL = "qwen2.5vl"
DEFAULT_URL = "http://localhost:11434"


class OllamaExtractor(Extractor):
    name = "ollama"

    def __init__(self, url: str | None = None, model: str | None = None):
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL

    def extract(self, jpeg: bytes, categories: list[str]) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": RECEIPT_SCHEMA,
            "messages": [{
                "role": "user",
                "content": build_prompt(categories),
                "images": [base64.b64encode(jpeg).decode("ascii")],
            }],
        }
        data = post_json(f"{self.url}/api/chat", body, timeout=600)
        try:
            return parse_json(data["message"]["content"])
        except KeyError as e:
            raise ExtractionError("Ollama returned no answer. Is the model a vision model?") from e
