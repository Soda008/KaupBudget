"""Read receipts with Claude (Anthropic API)."""
import base64
import json

import anthropic

from .base import RECEIPT_SCHEMA, ExtractionError, Extractor, build_prompt

DEFAULT_MODEL = "claude-haiku-5-5"


class ClaudeExtractor(Extractor):
    name = "claude"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        try:
            self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        except Exception as e:  # noqa: BLE001 - missing credentials surface here on some SDK versions
            raise ExtractionError("No Claude API key set. Add one in Settings.") from e

    def _call(self, content, with_effort: bool):
        output_config = {"format": {"type": "json_schema", "schema": RECEIPT_SCHEMA}}
        if with_effort:
            output_config["effort"] = "low"  # reading a receipt doesn't need deep thinking
        return self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            output_config=output_config,
            messages=[{"role": "user", "content": content}],
        )

    def extract(self, jpeg: bytes, categories: list[str]) -> dict:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpeg).decode("ascii"),
                },
            },
            {"type": "text", "text": build_prompt(categories)},
        ]
        try:
            try:
                resp = self._call(content, with_effort=True)
            except anthropic.BadRequestError as e:
                if "effort" not in str(e).lower():
                    raise
                resp = self._call(content, with_effort=False)  # older models don't take effort
        except anthropic.AuthenticationError as e:
            raise ExtractionError("Claude API key is missing or invalid. Check Settings.") from e
        except anthropic.NotFoundError as e:
            raise ExtractionError(f"Claude model '{self.model}' wasn't found. Check Settings.") from e
        except anthropic.RateLimitError as e:
            raise ExtractionError("Claude rate limit hit. Wait a minute and try again.") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"Claude API error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError("Couldn't reach Claude. Check your internet connection.") from e
        except TypeError as e:
            if "authentication" in str(e).lower():  # SDK raises this when no key is configured
                raise ExtractionError("No Claude API key set. Add one in Settings.") from e
            raise

        if resp.stop_reason == "refusal":
            raise ExtractionError("Claude declined to read this image.")
        if resp.stop_reason == "max_tokens":
            raise ExtractionError("Receipt was too long to read in one go.")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except ValueError as e:
            raise ExtractionError("Claude's reply wasn't valid receipt data.") from e
