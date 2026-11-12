"""Read receipts with Google Gemini (has a free tier; check Google's data terms)."""
import base64

from .base import ExtractionError, Extractor, build_prompt, parse_json
from .http import post_json

DEFAULT_MODEL = "gemini-flash-latest"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiExtractor(Extractor):
    name = "gemini"

    def __init__(self, api_key: str | None, model: str | None = None):
        if not api_key:
            raise ExtractionError("No Gemini API key set. Add one in Settings.")
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

    def extract(self, jpeg: bytes, categories: list[str]) -> dict:
        body = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}},
                    {"text": build_prompt(categories)},
                ]
            }],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        data = post_json(URL.format(model=self.model), body, headers={"x-goog-api-key": self.api_key})
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ExtractionError("Gemini returned no answer for this image.") from e
        return parse_json(text)
