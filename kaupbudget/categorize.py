"""Learn which categories you pick for each vendor, and suggest the top 3.

Signals, strongest first:
  1. Your past picks for this vendor (recent picks count more).
  2. Words on the receipt's line items that you've tied to a category before
     (so "pizza" at WinCo nudges Eating Out up).
  3. The AI's guess (mostly matters for vendors you've never categorized).
  4. Your most-used categories overall, to fill out the list.
Only categories you picked yourself (category_confirmed = 1) are learned from.
"""
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date

from .vendors import first_word, vendor_key

HALF_LIFE_DAYS = 180
_STOP = {"and", "the", "with", "for", "each", "item", "qty", "oz", "lb", "pkg", "pack", "reg", "sale"}


def _words(items) -> set:
    out = set()
    for it in items or []:
        desc = (it.get("description") if isinstance(it, dict) else str(it)) or ""
        for w in re.findall(r"[a-z]{3,}", desc.lower()):
            if w not in _STOP:
                out.add(w)
    return out


def _age_weight(d: str) -> float:
    try:
        age = (date.today() - date.fromisoformat(d)).days
    except (TypeError, ValueError):
        return 0.5
    return 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)


def suggest(conn, vendor: str, items=None, ai_guess: str | None = None, n: int = 3) -> list:
    cats = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM categories WHERE archived = 0")}
    if not cats:
        return []
    by_name = {v.lower(): k for k, v in cats.items()}
    scores = defaultdict(float)
    reasons = defaultdict(list)

    # 1. Vendor history
    key = vendor_key(vendor)
    fw = first_word(key)
    if key:
        rows = conn.execute(
            "SELECT category_id, date, vendor_key FROM transactions "
            "WHERE category_confirmed = 1 AND category_id IS NOT NULL "
            "AND (vendor_key = ? OR vendor_key = ? OR vendor_key LIKE ?)",
            (key, fw, fw + " %"),
        ).fetchall()
        hist = defaultdict(float)
        counts = Counter()
        for r in rows:
            if r["category_id"] not in cats:
                continue
            w = _age_weight(r["date"]) * (1.0 if r["vendor_key"] == key else 0.5)
            hist[r["category_id"]] += w
            counts[r["category_id"]] += 1
        total = sum(hist.values())
        if total:
            n_rows = sum(counts.values())
            for cid, w in hist.items():
                scores[cid] += w / total
                reasons[cid].append(f"picked {counts[cid]} of {n_rows} times for this vendor")

    # 2. Line-item words
    words = _words(items)
    if words:
        word_cats = defaultdict(Counter)
        for r in conn.execute(
            "SELECT t.category_id, r.items_json FROM receipts r JOIN transactions t ON t.id = r.transaction_id "
            "WHERE r.status = 'saved' AND t.category_confirmed = 1 AND t.category_id IS NOT NULL "
            "AND r.items_json IS NOT NULL"
        ):
            try:
                past = json.loads(r["items_json"])
            except ValueError:
                continue
            for w in _words(past) & words:
                word_cats[w][r["category_id"]] += 1
        item_scores = defaultdict(float)
        hit_words = defaultdict(list)
        for w, ctr in word_cats.items():
            tot = sum(ctr.values())
            for cid, c in ctr.items():
                item_scores[cid] += c / tot
                hit_words[cid].append(w)
        if item_scores:
            top = max(item_scores.values())
            for cid, s in item_scores.items():
                if cid in cats:
                    scores[cid] += 0.5 * s / top
                    reasons[cid].append("items like " + ", ".join(sorted(hit_words[cid])[:3]))

    # 3. AI guess
    if ai_guess and ai_guess.lower() in by_name:
        cid = by_name[ai_guess.lower()]
        has_history = any("vendor" in r for rs in reasons.values() for r in rs)
        scores[cid] += 0.3 if has_history else 1.0
        reasons[cid].append("AI suggestion")

    # 4. Fill with overall favorites
    if len(scores) < n:
        for r in conn.execute(
            "SELECT category_id, COUNT(*) c FROM transactions WHERE category_confirmed = 1 "
            "AND category_id IS NOT NULL GROUP BY category_id ORDER BY c DESC"
        ):
            if r["category_id"] in cats and r["category_id"] not in scores:
                scores[r["category_id"]] = 0.01 * math.log1p(r["c"])
                reasons[r["category_id"]].append("one of your most used")
            if len(scores) >= n:
                break
    if len(scores) < n:
        for cid in cats:
            if cid not in scores:
                scores[cid] = 0.0
                reasons[cid].append("")
            if len(scores) >= n:
                break

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [
        {"id": cid, "name": cats[cid], "score": round(s, 3), "reason": "; ".join(r for r in reasons[cid] if r)}
        for cid, s in ranked
    ]
