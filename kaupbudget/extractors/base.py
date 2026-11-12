"""Shared pieces for every receipt reader (AI provider)."""
import json
import re
from datetime import datetime


class ExtractionError(RuntimeError):
    """A reader failed; the message is shown to you in the app."""


RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "subtotal": {"type": ["number", "null"]},
        "tax": {"type": ["number", "null"]},
        "tip": {"type": ["number", "null"]},
        "total": {"type": ["number", "null"]},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "price": {"type": ["number", "null"]},
                },
                "required": ["description", "price"],
                "additionalProperties": False,
            },
        },
        "suggested_category": {"type": ["string", "null"]},
    },
    "required": ["vendor", "date", "subtotal", "tax", "tip", "total", "items", "suggested_category"],
    "additionalProperties": False,
}


def build_prompt(categories: list[str]) -> str:
    return (
        "Read this purchase receipt and return JSON with these fields:\n"
        '- vendor: the store or restaurant name as a person would say it (e.g. "WinCo Foods"), '
        "not the address or a slogan.\n"
        "- date: purchase date as YYYY-MM-DD, or null if not shown.\n"
        "- subtotal, tax, tip: numbers, or null if not on the receipt.\n"
        "- total: the final amount actually paid, INCLUDING any tip. If a tip and a new total are "
        "handwritten on the receipt, use the handwritten total.\n"
        "- items: each purchased line item with description and price. Leave out totals, tax, "
        "payment and change lines.\n"
        f"- suggested_category: the best fit from this list: {', '.join(categories)}.\n"
        "Return only the JSON object with keys vendor, date, subtotal, tax, tip, total, items, "
        "suggested_category."
    )


def parse_json(text: str) -> dict:
    """Pull a JSON object out of a model reply, tolerating ``` fences."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ExtractionError("The AI reply didn't contain receipt data.")
    try:
        return json.loads(m.group(0))
    except ValueError as e:
        raise ExtractionError("The AI reply wasn't valid JSON.") from e


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    try:
        return round(float(str(v).replace("$", "").replace(",", "").strip()), 2)
    except ValueError:
        return None


def _date(v):
    if not v:
        return None
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize(raw: dict) -> dict:
    """Clean up whatever a provider returned into one consistent shape."""
    raw = raw or {}
    items = []
    for it in raw.get("items") or []:
        if isinstance(it, dict) and it.get("description"):
            items.append({"description": str(it["description"]).strip(), "price": _num(it.get("price"))})
    out = {
        "vendor": (raw.get("vendor") or "").strip() or None,
        "date": _date(raw.get("date")),
        "subtotal": _num(raw.get("subtotal")),
        "tax": _num(raw.get("tax")),
        "tip": _num(raw.get("tip")),
        "total": _num(raw.get("total")),
        "items": items,
        "suggested_category": (raw.get("suggested_category") or "").strip() or None,
    }
    if out["total"] is None and out["subtotal"] is not None:
        out["total"] = round(out["subtotal"] + (out["tax"] or 0) + (out["tip"] or 0), 2)
    return out


class Extractor:
    name = "base"

    def extract(self, jpeg: bytes, categories: list[str]) -> dict:  # pragma: no cover
        raise NotImplementedError
